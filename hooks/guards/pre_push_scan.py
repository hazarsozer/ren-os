#!/usr/bin/env python3
"""
hooks/guards/pre_push_scan.py — G8 enforced critical few: push content-scan +
force-push guard (Task 6.2, RenOS 0.2 Phase 6).

Spec §3.6 A-8 item 1 (push content-scan + force-push guard) + item 6
(backup-remote changes get a different check, in write_gate.py). PreToolUse
hook, matcher `tool_name == "Bash"`. Real runtime enforcement — the gate is a
hook, not an honor system.

Contract: donor has NO PreToolUse hook precedent (its only hook is
SessionStart — see `hooks/wake-up/CC_API_NOTES.md`), so this follows the
DOCUMENTED Claude Code PreToolUse contract instead: stdin JSON
`{"tool_name": ..., "tool_input": {...}, "cwd": ...}`; exit 0 = allow; exit 2
with a message on stderr = block. NEVER raises internally — any internal
error degrades to ALLOW plus a warning on stderr (a broken guard must not
brick the harness; a guard silently never firing is doctor's job to flag,
not this script's job to prevent by crashing louder).

Checks, in order:
  1. FORCE/REWRITE guard — force-push (including `+refspec` force syntax,
     e.g. `git push origin +main` / `+HEAD:main`, not just `--force`/`-f`)
     or a history-rewrite-then-push shape blocks unless `REN_ALLOW_FORCE=1`
     is set (an explicit, deliberate human re-run, not a default-allow).
  2. Remote heuristic — pushes to a remote named "backup" skip BOTH the path
     denylist and the secrets scan (the private backup remote's entire point
     is to contain everything, including wiki/ and any fixture secrets it
     might carry); every other remote gets both checks. Remote-name
     extraction fails TOWARD scanning (unknown/ambiguous remote => scan).
  3. PATH DENYLIST — `git ls-files` (not `git diff --stat`, which misses
     already-tracked-but-newly-pushed history) checked against
     `PATH_DENYLIST`.
  4. SECRETS SCAN — `lib.memory.scrub.scan` over the same file list, skipping
     files >1MB or non-UTF-8 (treated as binary). A finding blocks, naming
     KINDS and PATHS — never the secret content itself.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("ren-pre-push-scan")

# Path denylist salvaged from donor `scripts/publish.sh`'s DENYLIST array
# (its own comment: "Maintainer-only paths that MUST NOT appear in any
# commit; defense-in-depth"). Donor's full array also lists a few
# donor-specific filenames (docs/SHIP_CHECKLIST.md, "tour", ".github",
# "plugins") that don't exist in this repo's layout; kept here is the subset
# that maps onto RenOS's actual maintainer-only paths.
PATH_DENYLIST: tuple[str, ...] = (
    "wiki/",
    "raw/",
    "docs/superpowers/",
    ".claude/",
    "tests/",
)

_GIT_PUSH_RE = re.compile(r"(?:^|[;&|]\s*)git\s+push\b")
_FORCE_FLAG_RE = re.compile(r"(?:^|\s)(--force(?:-with-lease)?|-f)\b")
_REWRITE_RE = re.compile(r"\bgit\s+(rebase|filter-repo)\b|--mirror\b")

ALLOW_FORCE_ENV = "REN_ALLOW_FORCE"
BACKUP_REMOTE_NAME = "backup"
_MAX_SCAN_BYTES = 1_000_000  # 1MB — skip larger files in the secrets scan


def _ensure_plugin_root_on_path() -> None:
    """Put the repo root on sys.path[0] so `from lib... import ...` resolves
    in the installed runtime, same convention as hooks/wake-up/ren-wake-up.py."""
    val = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    root = Path(os.path.expanduser(os.path.expandvars(val))) if val else Path(__file__).resolve().parents[2]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _has_force_refspec(command: str) -> bool:
    """True if a positional refspec argument after `git push` uses `+`
    force syntax (`git push origin +main`, `git push origin +HEAD:main`).
    Only checks whitespace-separated positional tokens after the push
    keyword, so option values and URLs elsewhere in the command can't
    false-positive."""
    match = _GIT_PUSH_RE.search(command)
    if match is None:
        return False
    after = command[match.end():]
    for token in after.split():
        if token.startswith("+") and len(token) > 1:
            return True
    return False


def _extract_remote(command: str, cwd: str) -> str:
    """Best-effort remote-name extraction from a `git push [...]` command.

    Bare `git push` (no explicit remote token) reads the current branch's
    upstream via `git config`. On ANY ambiguity or failure this returns ""
    (never a real remote name) so callers fail TOWARD scanning, never away
    from it — an unrecognized remote is never treated as "backup".
    """
    match = _GIT_PUSH_RE.search(command)
    if match is None:
        return ""
    after = command[match.end():].strip()
    tokens = [t for t in after.split() if not t.startswith("-")]
    if tokens:
        return tokens[0]

    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and "/" in result.stdout.strip():
            return result.stdout.strip().split("/", 1)[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def _ls_files(cwd: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "ls-files"], capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def _denylisted_paths(files: list[str]) -> list[str]:
    return [f for f in files if any(f.startswith(prefix) for prefix in PATH_DENYLIST)]


def _scan_secrets(cwd: str, files: list[str]) -> list[tuple[str, str]]:
    """Return `[(path, kind), ...]` for every file matching
    `lib.memory.scrub.PATTERNS`. Skips files over 1MB or that fail to decode
    as UTF-8 (treated as binary) — bounded scan, not a full repo audit."""
    _ensure_plugin_root_on_path()
    from lib.memory import scrub as _scrub

    findings: list[tuple[str, str]] = []
    root = Path(cwd)
    for rel in files:
        path = root / rel
        try:
            if not path.is_file() or path.stat().st_size > _MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for finding in _scrub.scan(text):
            findings.append((rel, finding.kind))
    return findings


def _block(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def check_push(command: str, cwd: str) -> int:
    """Run the full push-scan decision for one `command` string. Returns the
    process exit code (0 allow, 2 block). Pure enough to unit test directly."""
    if not _GIT_PUSH_RE.search(command):
        return 0  # not a push at all — nothing for this guard to do

    if _FORCE_FLAG_RE.search(command) or _REWRITE_RE.search(command) or _has_force_refspec(command):
        if os.environ.get(ALLOW_FORCE_ENV) == "1":
            return 0
        return _block(
            "BLOCKED: force-push / history-rewrite-then-push detected. "
            f"Re-run with {ALLOW_FORCE_ENV}=1 to confirm this is deliberate."
        )

    remote = _extract_remote(command, cwd)
    if remote == BACKUP_REMOTE_NAME:
        return 0  # private backup remote: its whole point is to contain everything

    files = _ls_files(cwd)

    denylisted = _denylisted_paths(files)
    if denylisted:
        return _block(
            "BLOCKED: push includes maintainer-only path(s) not allowed on this "
            f"remote: {', '.join(denylisted[:10])}"
        )

    findings = _scan_secrets(cwd, files)
    if findings:
        kinds = sorted({kind for _, kind in findings})
        paths = sorted({path for path, _ in findings})
        return _block(
            "BLOCKED: secret-shaped content detected in outgoing push "
            f"(kinds: {', '.join(kinds)}; paths: {', '.join(paths[:10])})"
        )

    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        logger.warning("could not parse stdin JSON: %s", exc)
        return 0

    try:
        tool_input = event.get("tool_input") or {}
        command = tool_input.get("command") or ""
        cwd = event.get("cwd") or os.getcwd()
        if not command:
            return 0
        return check_push(command, cwd)
    except Exception as exc:  # noqa: BLE001 — load-bearing graceful failure
        print(f"WARNING: pre_push_scan guard failed internally, allowing: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
