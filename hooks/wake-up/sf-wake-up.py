#!/usr/bin/env python3
"""
sf-wake-up.py — Startup-Framework SessionStart wake-up hook.

Per ADR-008 (verified 2026-05-28 — see hooks/wake-up/verify/REPORT-evidence.md):
emits a wiki context payload via `hookSpecificOutput.additionalContext` to be
injected into the conversation layer as a system-reminder. The cacheable
system-prompt prefix is unmodified; cache benefit is preserved across sessions.

Locked path convention (per team-lead 2026-05-28):
  - Framework root: ~/.startup-framework/
  - Wiki: ~/.startup-framework/wiki/

Operating model per CC_API_NOTES.md:
  1. Read stdin JSON (CC's SessionStart event)
  2. Resolve cwd → project context (if any)
  3. Read master + project wiki indices, recent log tails
  4. Compose additionalContext payload; truncate to <5K tokens
  5. Emit JSON to stdout; exit 0
  6. NEVER raise — graceful failure logs to stderr + emits empty context

Idempotency: hook is read-only on the wiki.
Order-insensitive: no dependency on other plugins' hooks.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from pathlib import Path

# Late import: keep hook startup fast (avoid importing lib/ unless needed)


# Per CC SessionStart matcher: "source" enum is startup/resume/clear/compact
# We fire on startup AND compact (re-injection after context compaction), but
# NOT on resume or clear (those have their own state). The matcher is set in
# the hooks.json registration.

logger = logging.getLogger("sf-wake-up")

# Log to ~/.startup-framework/logs/wake-up-<date>.log (stderr fallback)
def _setup_logging() -> None:
    log_dir = Path.home() / ".startup-framework" / "logs"
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
    """
    Resolve the plugin root — the directory where lib/, hooks/, skills/ live as
    real dirs (post-Crucible restructure, ADR-030; the root IS the plugin).

    Prefer $CLAUDE_PLUGIN_ROOT (the env Claude Code sets when invoking the hook:
    hooks.json runs `python3 "$CLAUDE_PLUGIN_ROOT/hooks/wake-up/sf-wake-up.py"`),
    .strip()+expand-guarded for the same reasons as _resolve_wiki_root. Else fall
    back to Path(__file__).resolve().parents[2] — hooks/wake-up/sf-wake-up.py →
    parents[2] == plugin root. Both agree in production (verified against the
    real tree).
    """
    val = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if val:
        return Path(os.path.expanduser(os.path.expandvars(val)))
    return Path(__file__).resolve().parents[2]


def _ensure_plugin_root_on_path() -> None:
    """
    Put the plugin root on sys.path[0] so plugin-root-relative imports like
    `from lib.sf_paths import …` resolve in the installed runtime.

    hooks.json invokes the hook by absolute path with cwd set to the session's
    project (not the plugin root) and no PYTHONPATH, so a top-level package like
    `lib` is not importable unless we add the plugin root explicitly. (ADR-031:
    the wiki-root resolution unifies onto lib.sf_paths.wiki_path(), which needs
    this insert.)

    Idempotent: a no-op if the root is already on sys.path.
    """
    root = str(_plugin_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _resolve_wiki_root() -> Path:
    """
    Resolve the wiki root via `lib.sf_paths.wiki_path()` — the single source of
    truth for the 3-tier resolution (SF_WIKI_ROOT → CLAUDE_PLUGIN_OPTION_WIKIROOT
    → framework_root()/wiki), per ADR-031's F1 unification. The hook previously
    inlined this logic; delegating keeps the Python reader and the shell scripts
    (`${SF_WIKI_ROOT:-${CLAUDE_PLUGIN_OPTION_WIKIROOT:-...}}`) in lockstep with one
    resolver. Each tier is `.strip()`-guarded (empty/whitespace = unset) and
    expandvars+expanduser-normalized so a literal `${HOME}`/`~` default is safe —
    this is what closes the C1 bug (the old `Path("")`-is-truthy fallthrough).

    Defensive fallback: if `lib.sf_paths` is somehow not importable in the
    installed runtime, resolve the same 3 tiers inline so the hook never breaks
    (graceful failure is load-bearing).
    """
    _ensure_plugin_root_on_path()
    try:
        from lib.sf_paths import wiki_path
        return wiki_path()
    except ImportError:
        logger.warning("lib.sf_paths unavailable; resolving wiki root inline", exc_info=True)
        for var in ("SF_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT"):
            val = os.environ.get(var, "").strip()
            if val:
                return Path(os.path.expanduser(os.path.expandvars(val)))
        return Path.home() / ".startup-framework" / "wiki"


def main() -> int:
    """
    Entry point.

    Reads stdin JSON; emits stdout JSON. Always returns 0 (graceful failure
    is the load-bearing safety invariant — never abort the session).
    """
    _setup_logging()

    # Read CC's SessionStart event payload
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        logger.warning("could not parse stdin JSON: %s", exc)
        event = {}

    cwd = event.get("cwd") or os.getcwd()
    source = event.get("source", "")

    # Locked path: ~/.startup-framework/wiki/ (resolved via explicit three-way
    # fallback — see _resolve_wiki_root for the C1 bug this closes).
    wiki_root = _resolve_wiki_root()

    # Compose the context payload.
    #
    # Import path: the script lives at hooks/wake-up/sf-wake-up.py with the
    # `wakeup/` package right next to it. Python can't resolve
    # `from hooks.wake_up.wakeup import ...` because the parent dir `wake-up` has
    # a dash. We add THIS script's dir to sys.path and import `wakeup` directly.
    # Bug caught by the end-to-end smoke test 2026-05-28 — unit tests passed via
    # relative imports but the standalone-script invocation path was broken.
    #
    # The package is named `wakeup` (not `lib`) deliberately (ADR-031): the
    # repo-root `lib/` package (lib.sf_paths) and a hook-local `lib/` cannot both
    # be top-level names on one sys.path — once the plugin root is inserted below,
    # a bare `import lib` would resolve to repo-root lib and shadow this helper.
    try:
        script_dir = Path(__file__).resolve().parent
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))
        # Also put the plugin root on sys.path so plugin-root-relative imports
        # (e.g. lib.sf_paths) resolve in the installed runtime (ADR-031).
        _ensure_plugin_root_on_path()
        from wakeup import compose_wake_up_context  # type: ignore[import-not-found]

        context_text = compose_wake_up_context(
            cwd=Path(cwd),
            wiki_root=wiki_root,
            source=source,
        )
    except Exception:  # noqa: BLE001 — load-bearing graceful failure
        logger.error("compose failed:\n%s", traceback.format_exc())
        context_text = ""

    # Emit the hook output JSON per CC_API_NOTES.md §4.2
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
        return 0  # still exit 0 to not abort the session

    logger.info(
        "wake-up emitted %d chars of additionalContext (source=%s, cwd=%s)",
        len(context_text), source, cwd,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
