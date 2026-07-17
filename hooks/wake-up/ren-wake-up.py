#!/usr/bin/env python3
"""
ren-wake-up.py — RenOS SessionStart wake-up hook (Task 5.1, RenOS 0.2 Phase 5).

Per ADR-008 (carried from donor, verified there 2026-05-28): emits a wiki
context payload via `hookSpecificOutput.additionalContext` to be injected
into the conversation layer as a system-reminder. The cacheable system-prompt
prefix is unmodified; cache benefit is preserved across sessions. This is the
highest-risk artifact in the plugin — the JSON output contract below is
preserved byte-for-byte from the donor hook.

Path convention: framework root `~/.renos/`, wiki `~/.renos/wiki/`.

Operating model:
  1. Read stdin JSON (CC's SessionStart event: cwd, source, session_id, ...)
  2. Resolve cwd → project context (if any)
  3. Compose the additionalContext payload via `wakeup.compose_wake_up_context`
     (Task 5.1 deltas: L1 + L2 map for the active project, ranked + salience-
     boosted extras, unconditional miss-log/injected-bytes instrumentation)
  4. Emit JSON to stdout; exit 0
  5. NEVER raise — graceful failure logs to stderr + emits empty context

Idempotency: hook is read-only on the wiki (instrumentation writes go through
lib.instrument, not direct wiki-page writes).
Order-insensitive: no dependency on other plugins' hooks.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

# Late import: keep hook startup fast (avoid importing lib/ unless needed)

logger = logging.getLogger("ren-wake-up")

# B1: on a clean machine the SessionStart hook runs under bare `python3`, which
# lacks the project deps (pyyaml, python-ulid) that `wakeup` imports transitively
# via lib.memory.provenance. Left unhandled that surfaced as a swallowed
# ModuleNotFoundError → permanently-empty additionalContext, SILENTLY. The hook
# must instead either self-heal (re-exec under `uv run`, which has the deps) or
# degrade LOUDLY. This env flag guards the re-exec against infinite recursion.
REEXEC_GUARD_ENV = "REN_WAKEUP_REEXEC"
# SessionStart hook timeout is 10s; leave headroom. A warm `uv run` is sub-second;
# a cold one that blows this budget times out here and falls through to the loud
# degrade message rather than hanging the session start.
_REEXEC_TIMEOUT_S = 7.0


def _degrade_message() -> str:
    """Loud additionalContext emitted when RenOS memory injection is disabled
    because the hook could not load its Python deps AND could not self-heal via
    `uv run`. NEVER return "" here — the whole point of B1 is that a broken
    environment is visible, not silent."""
    return (
        "## RenOS wake-up: memory injection DISABLED\n\n"
        "The wake-up hook could not load RenOS's Python dependencies "
        "(e.g. `pyyaml`, `python-ulid`) under the plain `python3` interpreter, "
        "and could not self-heal via `uv run`. Your wiki/memory context was "
        "**not** injected this session — prior-session continuity is unavailable.\n\n"
        "To fix: run `/ren:doctor` (it checks the environment), and/or install "
        "`uv` so the hook can self-heal by re-running under the project venv."
    )


def _reexec_under_uv(raw_stdin: str) -> str | None:
    """Re-run THIS script under `uv run --project <root> python …` (which has the
    project deps) and return the additionalContext it computed. Returns None —
    signalling the caller to fall back to `_degrade_message` — when uv is
    unavailable, we are already inside a re-exec (guard flag set), or the child
    fails/times out. Passes the original stdin through so the child sees the same
    SessionStart event. NEVER raises."""
    if os.environ.get(REEXEC_GUARD_ENV) == "1":
        return None  # already re-exec'd once; do not recurse
    if shutil.which("uv") is None:
        return None
    root = str(_plugin_root())
    script = str(Path(__file__).resolve())
    child_env = dict(os.environ)
    child_env[REEXEC_GUARD_ENV] = "1"
    try:
        proc = subprocess.run(
            ["uv", "run", "--project", root, "python", script],
            input=raw_stdin, capture_output=True, text=True,
            timeout=_REEXEC_TIMEOUT_S, env=child_env,
        )
    except (OSError, subprocess.SubprocessError):
        logger.warning("uv re-exec failed to launch", exc_info=True)
        return None
    if proc.returncode != 0:
        logger.warning("uv re-exec exited %s: %s", proc.returncode, (proc.stderr or "")[-500:])
        return None
    try:
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["additionalContext"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning("uv re-exec produced unparsable output")
        return None


def _setup_logging() -> None:
    """Log to ~/.renos/logs/wake-up-<date>.log (stderr fallback)."""
    log_dir = Path.home() / ".renos" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        log_path = log_dir / f"wake-up-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"
        handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _plugin_root() -> Path:
    """Resolve the repo/plugin root — where lib/, hooks/, skills/ live.

    Prefers `$CLAUDE_PLUGIN_ROOT` (the env Claude Code sets when invoking the
    hook), `.strip()`+expand-guarded; else falls back to
    `Path(__file__).resolve().parents[2]` — hooks/wake-up/ren-wake-up.py →
    parents[2] == repo root. Both agree in production.
    """
    val = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if val:
        return Path(os.path.expanduser(os.path.expandvars(val)))
    return Path(__file__).resolve().parents[2]


def _ensure_plugin_root_on_path() -> None:
    """Put the repo root on sys.path[0] so `from lib.ren_paths import …`
    resolves in the installed runtime. Idempotent."""
    root = str(_plugin_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _resolve_wiki_root() -> Path:
    """Resolve the wiki root via `lib.ren_paths.wiki_root()` (the 3-tier
    REN_WIKI_ROOT → CLAUDE_PLUGIN_OPTION_WIKIROOT → framework_root()/wiki
    resolution). Defensive fallback: if `lib.ren_paths` is somehow not
    importable, resolve the same tiers inline so the hook never breaks."""
    _ensure_plugin_root_on_path()
    try:
        from lib.ren_paths import wiki_root
        return wiki_root()
    except ImportError:
        logger.warning("lib.ren_paths unavailable; resolving wiki root inline", exc_info=True)
        for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT"):
            val = os.environ.get(var, "").strip()
            if val:
                return Path(os.path.expanduser(os.path.expandvars(val)))
        return Path.home() / ".renos" / "wiki"


def main() -> int:
    """Entry point. Reads stdin JSON; emits stdout JSON. Always returns 0."""
    _setup_logging()

    raw = ""
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        logger.warning("could not parse stdin JSON: %s", exc)
        event = {}

    cwd = event.get("cwd") or os.getcwd()
    source = event.get("source", "")
    session = event.get("session_id") or "unknown"

    wiki_root = _resolve_wiki_root()

    # Import path: the script lives at hooks/wake-up/ren-wake-up.py with the
    # `wakeup/` package right next to it. Python can't resolve
    # `from hooks.wake_up.wakeup import ...` because the parent dir has a
    # dash. Add THIS script's dir to sys.path and import `wakeup` directly —
    # carried from donor (bug caught by its own end-to-end smoke test).
    #
    # The package is named `wakeup` (not `lib`) deliberately: the repo-root
    # `lib/` package and a hook-local `lib/` cannot both be top-level names on
    # one sys.path — once the plugin root is inserted below, a bare `import
    # lib` would resolve to repo-root lib and shadow a hook-local helper.
    try:
        script_dir = Path(__file__).resolve().parent
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))
        _ensure_plugin_root_on_path()
        from wakeup import compose_wake_up_context  # type: ignore[import-not-found]

        context_text = compose_wake_up_context(
            cwd=Path(cwd),
            wiki_root=wiki_root,
            source=source,
            session=session,
        )
    except ModuleNotFoundError as exc:
        # B1: bare `python3` lacks the project deps. Try to self-heal by
        # re-running under `uv run` (which has them); if that isn't possible,
        # degrade LOUDLY instead of the old silent empty payload.
        logger.warning("wakeup deps unavailable (%s); attempting uv re-exec", exc)
        relayed = _reexec_under_uv(raw)
        context_text = relayed if relayed is not None else _degrade_message()
    except Exception:  # noqa: BLE001 — load-bearing graceful failure
        logger.error("compose failed:\n%s", traceback.format_exc())
        context_text = ""

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context_text,
        }
    }
    try:
        json.dump(output, sys.stdout)
        sys.stdout.write("\n")
    except OSError as exc:
        logger.error("could not write stdout: %s", exc)
        return 0

    logger.info(
        "wake-up emitted %d chars of additionalContext (source=%s, cwd=%s)",
        len(context_text), source, cwd,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
