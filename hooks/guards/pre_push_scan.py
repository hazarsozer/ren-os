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
  4. SECRETS SCAN — `lib.memory.scrub.scan` over the OUTGOING ADDED LINES
     only (`git diff --unified=0` against `@{u}`, or the remote default
     branch's merge-base on a first branch push — issues #27/#28; full file
     contents only on a genuinely first publish with no remote refs),
     skipping blobs >1MB or non-UTF-8 (treated as binary). Secret-shaped
     content not added by this push does not block (B2, content
     granularity). A finding blocks, naming KINDS and PATHS — never the
     secret content itself.
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

_GIT_PUSH_RE = re.compile(r"(?:^|[;&|\n]\s*)git\s+push\b")
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


def _remote_base_ref(cwd: str, remote: str) -> str:
    """Best-effort base ref for a no-upstream push: the push target's default
    branch as a remote-tracking ref (`<remote>/HEAD` when set, else
    `<remote>/main`, else `<remote>/master`; unnamed remote falls back to
    "origin"). Returns "" when none resolves — the remote has no known refs,
    so everything is genuinely outgoing (issue #27)."""
    name = remote or "origin"
    for candidate in (f"{name}/HEAD", f"{name}/main", f"{name}/master"):
        try:
            rev = subprocess.run(
                ["git", "-C", cwd, "rev-parse", "--verify", "--quiet", candidate],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        if rev.returncode == 0 and rev.stdout.strip():
            return candidate
    return ""


def _scan_base(cwd: str, remote: str) -> str | None:
    """Diff base for the outgoing secrets scan: `"@{u}.."` when an upstream
    exists; else the push target's default branch as `"<ref>..."` (since the
    merge-base — issue #27: the full-tree fallback blocked every new branch
    of a repo whose tree legitimately carries secret-shaped fixtures already
    on the remote); `None` only when the remote has no known refs at all
    (genuinely first publish — everything tracked really is outgoing)."""
    try:
        rev = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            capture_output=True, text=True, timeout=5,
        )
        if rev.returncode == 0 and rev.stdout.strip():
            return "@{u}.."
    except (OSError, subprocess.TimeoutExpired):
        pass
    base_ref = _remote_base_ref(cwd, remote)
    return f"{base_ref}..." if base_ref else None  # three-dot: since merge-base


def _outgoing_blobs(cwd: str, remote: str = "") -> dict[str, str]:
    """Text to run the secrets scan over, keyed by file path. B2, applied at
    CONTENT granularity (issue #28): only the push's ADDED lines are scanned
    (`git diff --unified=0 <base>HEAD`, `+` lines per file) — pre-existing
    secret-shaped text in a file the push happens to edit is not part of this
    push and must not block, while a real secret introduced by the push's own
    added lines is still caught. Only with no scan base at all (first publish
    of the repo) does the scan cover full tracked-file contents. Never raises
    — degrades to {} on diff failure (fail toward not-scanning rather than
    crashing the guard); files/blobs over 1MB are skipped as in `_scan_secrets`.
    """
    base = _scan_base(cwd, remote)
    root = Path(cwd)

    if base is None:
        blobs: dict[str, str] = {}
        for rel in _ls_files(cwd):
            path = root / rel
            try:
                if not path.is_file() or path.stat().st_size > _MAX_SCAN_BYTES:
                    continue
                blobs[rel] = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        return blobs

    try:
        diff = subprocess.run(
            ["git", "-C", cwd, "diff", "--unified=0", f"{base}HEAD"],
            capture_output=True, text=True, timeout=15,
        )
        if diff.returncode != 0:
            return {}
    except (OSError, subprocess.TimeoutExpired):
        return {}

    blobs = {}
    current: str | None = None
    for line in diff.stdout.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            current = None if target == "/dev/null" else target.removeprefix("b/")
        elif current and line.startswith("+") and not line.startswith("+++"):
            blobs[current] = blobs.get(current, "") + line[1:] + "\n"
    return blobs


def _has_force_refspec(command: str) -> bool:
    """True if a positional refspec argument after `git push` uses `+`
    force syntax (`git push origin +main`, `git push origin +HEAD:main`).
    Only checks whitespace-separated positional tokens after the push
    keyword, so option values and URLs elsewhere in the command can't
    false-positive. Tokens are stripped of surrounding shell quotes first
    — the shell removes them before git parses the refspec."""
    match = _GIT_PUSH_RE.search(command)
    if match is None:
        return False
    after = command[match.end():]
    for token in after.split():
        token = token.strip("\"'")
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


def _normalize_git_url(url: str) -> str:
    """Reduce a git remote URL to a comparable `host/owner/repo` form:
    `git@github.com:owner/repo.git`, `ssh://git@github.com/owner/repo`, and
    `https://github.com/owner/repo` all normalize identically."""
    url = url.strip().lower()
    url = re.sub(r"^[a-z+]+://", "", url)  # https:// | ssh:// | git+ssh://
    url = re.sub(r"^[^@/]+@", "", url)     # git@host:… | user@host/…
    url = url.replace(":", "/", 1)
    url = re.sub(r"\.git$", "", url)
    return url.rstrip("/")


def _is_own_canonical_remote(cwd: str, remote: str) -> bool:
    """True iff `remote`'s URL matches the plugin manifest's `repository`
    field — the repo's own canonical home (issue #26: since the dev-backup
    mirror was retired, the dev repo IS its public remote, and the
    maintainer denylist must not block the maintainer's own push there).
    Any failure (no such remote, no manifest, no `repository` field)
    degrades to False — fail TOWARD scanning."""
    if not remote:
        return False
    try:
        top = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if top.returncode != 0 or not top.stdout.strip():
            return False
        manifest = Path(top.stdout.strip()) / ".claude-plugin" / "plugin.json"
        repository = json.loads(manifest.read_text(encoding="utf-8")).get("repository")
        if not isinstance(repository, str) or not repository.strip():
            return False
        url = subprocess.run(
            # `--push` (dogfood-2 M2): compare the URL the push actually goes
            # to — a divergent push URL (`git remote set-url --push`) must not
            # stand the denylist down. Git falls back to the fetch URL when no
            # pushurl is set, so the common case is unchanged.
            ["git", "-C", cwd, "remote", "get-url", "--push", remote],
            capture_output=True, text=True, timeout=5,
        )
        if url.returncode != 0 or not url.stdout.strip():
            return False
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    return _normalize_git_url(url.stdout) == _normalize_git_url(repository)


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


def _scan_secrets(blobs: dict[str, str]) -> list[tuple[str, str]]:
    """Return `[(path, kind), ...]` for every blob matching
    `lib.memory.scrub.PATTERNS`. Blobs are the ADDED-LINES text per outgoing
    file (or full file contents on a first publish) — see `_outgoing_blobs`.
    Skips blobs over 1MB — bounded scan, not a full repo audit."""
    _ensure_plugin_root_on_path()
    from lib.memory import scrub as _scrub

    findings: list[tuple[str, str]] = []
    for rel, text in blobs.items():
        if len(text.encode("utf-8", errors="replace")) > _MAX_SCAN_BYTES:
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
    # .claude/, docs/. Scoped by repo identity. Issue #26: it must ALSO not
    # block the maintainer pushing the plugin repo to its own canonical home
    # (every push segment's remote URL matches the manifest's `repository`) —
    # since the dev-backup mirror was retired, the dev repo IS that remote and
    # legitimately tracks the denylisted paths. Any OTHER remote (a
    # distribution repo, a fork) keeps the denylist; the secrets scan below
    # runs regardless.
    if _is_renos_repo(cwd) and not all(_is_own_canonical_remote(cwd, r) for r in remotes):
        denylisted = _denylisted_paths(_ls_files(cwd))
        if denylisted:
            return _block(
                "BLOCKED: push includes maintainer-only path(s) not allowed on this "
                f"remote: {', '.join(denylisted[:10])}"
            )

    # B2: scan only the OUTGOING changes — the push's added lines, not whole
    # touched files or the tracked tree (issues #27/#28) — a secret-shaped
    # string in content that isn't part of this push must not block.
    findings = _scan_secrets(_outgoing_blobs(cwd, next((r for r in remotes if r), "")))
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
