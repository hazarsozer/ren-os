#!/usr/bin/env python3
"""
hooks/guards/write_gate.py — G8 enforced critical few: durable-write gate,
wiki mass-delete guard, and backup-remote-change confirmation (Task 6.2,
RenOS 0.2 Phase 6).

Spec §3.6 A-8 item 2 (wiki mass-delete), item 5 (durable/global memory writes
— "the write gate is a hook not an honor system"), item 6 (backup-remote
changes, confirm not block). PreToolUse hook, matchers `Write`/`Edit`/
`NotebookEdit` (direct-write gate) AND `Bash` (mass-delete + bash-wiki-write
+ remote-change checks).

Bash-wiki-write (Task 6, 0.3.2): catches shell commands that WRITE into the
wiki other than `rm`/`unlink` — redirects (`>`/`>>`), `sed -i`, `tee`, and
cp/mv/install/rsync destinations. Best-effort by design: it extracts only
the tokens a command would write to, not a full shell parser, so `python -c`
writers and other exotic paths stay invisible. Reads and copies OUT of the
wiki are never touched.

Same stdin/exit-code contract as `pre_push_scan.py` (see that module's
docstring for why there's no donor precedent to follow instead) — exit 0
allow, exit 2 + stderr message block, and a JSON
`{"permissionDecision": "ask"}` on stdout for the one ask-tier check here
(backup-remote change: confirm, don't block — the private backup existing at
all is desirable, only silently repointing it is the risk). NEVER raises
internally; any internal error degrades to ALLOW plus a stderr warning.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

logger = logging.getLogger("ren-write-gate")

QUEUE_MESSAGE = (
    "BLOCKED: durable wiki writes go through the queue: /ren:pin or wrap — "
    "direct edits bypass provenance"
)
MASS_DELETE_MESSAGE = (
    "BLOCKED: mass-delete of wiki content detected — destructive-tier actions "
    "always require explicit human confirmation, not a hook auto-allow"
)
BASH_WIKI_WRITE_MESSAGE = (
    "BLOCKED: this shell command writes into the wiki — durable wiki writes go "
    "through the write substrate (/ren:pin or wrap), never direct shell edits: "
    "they'd bypass snapshot/journal/revert. (Best-effort guard: it catches "
    "redirects, sed -i, tee, cp/mv — not every possible writer.)"
)

QUEUE_APPLY_ENV = "REN_QUEUE_APPLY"
MASS_DELETE_THRESHOLD = 3

_RM_RE = re.compile(r"(?:^|[;&|]\s*)(rm|unlink)\b")
_REMOTE_SET_RE = re.compile(r"\bgit\s+remote\s+(set-url|add)\s+\S*backup\S*", re.IGNORECASE)
_SHELL_SEPARATORS = (";", "&&", "||", "|")
_REDIRECT_TARGET_RE = re.compile(r">{1,2}\s*([^\s;|&<>]+)")
_DEST_COMMANDS = frozenset({"cp", "mv", "install", "rsync"})


def _ensure_plugin_root_on_path() -> None:
    """Put the repo root on sys.path[0] so `from lib... import ...` resolves
    in the installed runtime, same convention as hooks/wake-up/ren-wake-up.py."""
    val = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    root = Path(os.path.expanduser(os.path.expandvars(val))) if val else Path(__file__).resolve().parents[2]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _resolve_under(path_str: str, base: Path) -> bool:
    """True if `path_str` resolves to `base` itself or somewhere under it."""
    try:
        resolved = Path(path_str).expanduser().resolve()
        base_resolved = base.resolve()
    except OSError:
        return False
    return resolved == base_resolved or base_resolved in resolved.parents


def check_direct_write(file_path: str) -> int:
    """Gate a Write/Edit/NotebookEdit `file_path`. Returns 0 (allow) or 2
    (block, with the queue message already printed to stderr)."""
    if not file_path:
        return 0

    _ensure_plugin_root_on_path()
    from lib import ren_paths

    wiki_root = ren_paths.wiki_root()
    if not _resolve_under(file_path, wiki_root):
        return 0  # not under the wiki at all — nothing for this gate to do

    if _resolve_under(file_path, ren_paths.state_dir()):
        return 0  # machine state (.ren/) — lib.memory manages this directly

    if os.environ.get(QUEUE_APPLY_ENV) == "1":
        return 0  # a sanctioned apply (write_apply) is in progress

    print(QUEUE_MESSAGE, file=sys.stderr)
    return 2


def _extract_rm_targets(command: str) -> list[str]:
    """Best-effort token extraction of path-looking arguments after
    rm/unlink, skipping flags and stopping at the first shell separator so a
    chained `&& something-else` isn't counted. Good enough for the
    mass-delete COUNT heuristic — not a full shell parser."""
    match = _RM_RE.search(command)
    if match is None:
        return []
    after = command[match.end():]
    cut = min((after.find(sep) for sep in _SHELL_SEPARATORS if sep in after), default=-1)
    if cut != -1:
        after = after[:cut]
    return [t for t in after.split() if t and not t.startswith("-")]


def check_mass_delete(command: str, cwd: str) -> int:
    """Gate an `rm`/`unlink` Bash command that touches >= MASS_DELETE_THRESHOLD
    wiki paths, or the wiki root itself. Returns 0 (allow) or 2 (block)."""
    if not _RM_RE.search(command):
        return 0

    _ensure_plugin_root_on_path()
    from lib import ren_paths

    wiki_root_resolved = ren_paths.wiki_root().resolve()
    targets = _extract_rm_targets(command)

    wiki_hit_count = 0
    root_hit = False
    for target in targets:
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = Path(cwd) / candidate
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved == wiki_root_resolved:
            root_hit = True
        elif wiki_root_resolved in resolved.parents:
            wiki_hit_count += 1

    if root_hit or wiki_hit_count >= MASS_DELETE_THRESHOLD:
        print(MASS_DELETE_MESSAGE, file=sys.stderr)
        return 2
    return 0


def _bash_write_targets(command: str) -> list[str]:
    """Best-effort extraction of the paths a shell command would WRITE to:
    redirect targets, `sed -i` file args, `tee` args, and the destination
    (last non-flag arg) of cp/mv/install/rsync. NOT a shell parser — a
    defense-in-depth heuristic; reads (`cat`, `grep`) and copies OUT of the
    wiki produce no targets. `python -c`/heredoc writers are invisible by
    design (documented best-effort)."""
    targets: list[str] = list(_REDIRECT_TARGET_RE.findall(command))
    for segment in re.split(r"[;|&]+", command):
        tokens = segment.strip().split()
        if not tokens:
            continue
        cmd = tokens[0]
        args = [t for t in tokens[1:] if not t.startswith("-")]
        if cmd == "sed" and any(t.startswith("-i") for t in tokens[1:]):
            targets.extend(args[1:] if len(args) > 1 else args)  # args[0] is the sed script
        elif cmd == "tee":
            targets.extend(args)
        elif cmd in _DEST_COMMANDS and args:
            targets.append(args[-1])
    return [t.strip("'\"") for t in targets if t]


def check_bash_wiki_write(command: str, cwd: str) -> int:
    """Gate a Bash command whose WRITE targets resolve under the wiki (but
    not under machine state `.ren/`). Returns 0 (allow) or 2 (block)."""
    if os.environ.get(QUEUE_APPLY_ENV) == "1":
        return 0
    targets = _bash_write_targets(command)
    if not targets:
        return 0

    _ensure_plugin_root_on_path()
    from lib import ren_paths

    wiki_root = ren_paths.wiki_root().resolve()
    state_dir = ren_paths.state_dir()
    for target in targets:
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = Path(cwd) / candidate
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        under_wiki = resolved == wiki_root or wiki_root in resolved.parents
        if under_wiki and not _resolve_under(str(resolved), state_dir):
            print(BASH_WIKI_WRITE_MESSAGE, file=sys.stderr)
            return 2
    return 0


def check_backup_remote_change(command: str) -> dict | None:
    """Return the ask-tier decision dict if `command` looks like it repoints
    the "backup" git remote, else None."""
    if _REMOTE_SET_RE.search(command):
        return {"permissionDecision": "ask"}
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        logger.warning("could not parse stdin JSON: %s", exc)
        return 0

    try:
        tool_name = event.get("tool_name") or ""
        tool_input = event.get("tool_input") or {}
        cwd = event.get("cwd") or os.getcwd()

        if tool_name in ("Write", "Edit", "NotebookEdit"):
            file_path = tool_input.get("file_path") or ""
            return check_direct_write(file_path)

        if tool_name == "Bash":
            command = tool_input.get("command") or ""
            if not command:
                return 0

            rc = check_mass_delete(command, cwd)
            if rc != 0:
                return rc

            rc = check_bash_wiki_write(command, cwd)
            if rc != 0:
                return rc

            ask = check_backup_remote_change(command)
            if ask is not None:
                json.dump(ask, sys.stdout)
                sys.stdout.write("\n")
                return 0

        return 0
    except Exception as exc:  # noqa: BLE001 — load-bearing graceful failure
        print(f"WARNING: write_gate guard failed internally, allowing: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
