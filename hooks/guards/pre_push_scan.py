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
  1. FORCE/REWRITE guard — bare force-push (`--force`/`-f`, or `+refspec`
     force syntax e.g. `git push origin +main` / `+HEAD:main`) or a
     mirror-push (`--mirror`) blocks unless `REN_ALLOW_FORCE=1` is set (an
     explicit, deliberate human re-run, not a default-allow). Only the push
     SEGMENT is inspected, so a `git rebase … && git push` isn't blocked on
     the local rebase; `--force-with-lease` (the safe idiom) is allowed
     without the env var (M8).
  2. Remote heuristic — pushes to a remote named "backup" skip BOTH the path
     denylist and the secrets scan (the private backup remote's entire point
     is to contain everything, including wiki/ and any fixture secrets it
     might carry); every other remote gets both checks. Remote-name
     extraction fails TOWARD scanning (unknown/ambiguous remote => scan).
  3. PATH DENYLIST — applies ONLY when the repo being pushed IS the RenOS
     plugin repo (identified by a root `.claude-plugin/plugin.json` naming
     the plugin "ren"); a user's own repo that tracks tests/ etc. is never
     denylisted (B2). Scans `git ls-files` (not `git diff --stat`, which
     misses already-tracked-but-newly-pushed history) against `PATH_DENYLIST`.
  4. SECRETS SCAN — `lib.memory.scrub.scan` over the OUTGOING file set only
     (`@{u}..HEAD`, or the full tree on a first push with no upstream),
     skipping files >1MB or non-UTF-8 (treated as binary). A secret in a file
     not part of this push does not block (B2). A finding blocks, naming
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
# M8: `--force-with-lease` is the SAFE idiom (refuses to clobber unseen remote
# work) — it must NOT require REN_ALLOW_FORCE. Only bare `--force`/`-f` do. The
# negative lookahead keeps `--force` from matching the `--force` prefix of
# `--force-with-lease`.
_FORCE_FLAG_RE = re.compile(r"(?:^|\s)(--force(?!-with-lease)|-f)\b")
_REWRITE_RE = re.compile(r"\bgit\s+(rebase|filter-repo)\b|--mirror\b")
# M8: command separators, for isolating the segment that actually carries the
# `git push` — so a `git rebase … && git push` doesn't trip the rewrite check
# on the (local, separate) rebase segment.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;&|\n]")

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


def _push_segments(command: str) -> list[str]:
    """Return EVERY separator-delimited command segment that carries `git push`,
    stripped. Force/rewrite checks run against each of these, not the whole
    command, so a `git rebase … && git push` (rebase in a separate, local
    segment) isn't blocked and a `--force` inside an earlier commit message
    can't false-positive — but a chained `git push … && git push --force …`
    still has its trailing forced push inspected (each push segment is checked).
    Falls back to `[whole command]` if no segment isolates a push."""
    segments = [
        segment.strip()
        for segment in _SEGMENT_SPLIT_RE.split(command)
        if re.search(r"\bgit\s+push\b", segment)
    ]
    return segments or [command.strip()]


def _is_renos_repo(cwd: str) -> bool:
    """True iff `cwd`'s git repo IS the RenOS plugin/dev repo — the only repo
    the maintainer PATH_DENYLIST applies to. Identified by a repo-root
    `.claude-plugin/plugin.json` naming the plugin "ren". Any other repo the
    user happens to push from (their own projects, which legitimately track
    `tests/`, `.claude/`, `docs/`) is never subject to the denylist. Never
    raises — any failure degrades to False (not-renos => denylist skipped)."""
    try:
        top = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if top.returncode != 0 or not top.stdout.strip():
        return False
    manifest = Path(top.stdout.strip()) / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("name") == "ren"


def _outgoing_files(cwd: str) -> list[str]:
    """Files to run the secrets scan over: only those touched by commits not
    yet on the upstream (`@{u}..HEAD`) — a secret-shaped string in a file that
    is NOT part of this push must not block. When there is no upstream (first
    push of a branch), everything tracked is outgoing, so fall back to the full
    `git ls-files` tree. Never raises — degrades to [] on diff failure with an
    upstream present (fail toward not-scanning that file set rather than
    crashing the guard)."""
    try:
        rev = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            capture_output=True, text=True, timeout=5,
        )
        has_upstream = rev.returncode == 0 and bool(rev.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        has_upstream = False

    if not has_upstream:
        return _ls_files(cwd)

    try:
        diff = subprocess.run(
            ["git", "-C", cwd, "diff", "--name-only", "@{u}..HEAD"],
            capture_output=True, text=True, timeout=15,
        )
        if diff.returncode != 0:
            return []
        return [line for line in diff.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


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

    # M8: force/rewrite checks apply per push SEGMENT (not the whole command),
    # so a `git rebase … && git push` (safe plain push git will reject if
    # non-ff) isn't blocked and `--force-with-lease` (safe idiom) no longer
    # requires the env var. But EVERY push segment is inspected, so a chained
    # `git push … && git push --force …` still has its forced push caught.
    segments = _push_segments(command)
    if any(
        _FORCE_FLAG_RE.search(s) or _REWRITE_RE.search(s) or _has_force_refspec(s)
        for s in segments
    ):
        if os.environ.get(ALLOW_FORCE_ENV) == "1":
            return 0
        return _block(
            "BLOCKED: force-push / mirror-push detected. "
            f"Re-run with {ALLOW_FORCE_ENV}=1 to confirm this is deliberate."
        )

    # Backup-remote skip applies ONLY when EVERY push in the command targets the
    # private backup remote (its whole point is to contain everything). A single
    # chained push to any other remote forces the denylist + secrets scan to run.
    remotes = [_extract_remote(s, cwd) for s in segments]
    if remotes and all(r == BACKUP_REMOTE_NAME for r in remotes):
        return 0

    # B2: the maintainer PATH_DENYLIST is a RenOS-repo-only concern — it must
    # not block a user pushing their OWN repo that legitimately tracks tests/,
    # .claude/, docs/. Scoped by repo identity.
    if _is_renos_repo(cwd):
        denylisted = _denylisted_paths(_ls_files(cwd))
        if denylisted:
            return _block(
                "BLOCKED: push includes maintainer-only path(s) not allowed on this "
                f"remote: {', '.join(denylisted[:10])}"
            )

    # B2: scan only the OUTGOING changes, not the whole tracked tree — a
    # secret-shaped string in a file that isn't part of this push must not block.
    findings = _scan_secrets(cwd, _outgoing_files(cwd))
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
