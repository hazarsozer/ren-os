"""
Root test isolation (issue #13).

Every test runs against an isolated HOME under tmp_path, so no test can write
into the developer's real ~/.renos (wake-up logs, wiki/.ren/metrics, plugin
data). Two layers:

  1. `_isolate_home` (autouse, function-scoped) — repoints HOME at a per-test
     tmp dir and clears every RenOS path-override env var, then asserts the
     resolvers actually land under tmp so a future bypass fails loudly.
  2. `_real_renos_untouched` (autouse, session-scoped) — snapshots a start
     timestamp and, after the whole suite, fails if any file under the real
     ~/.renos is newer than it.

Root cause the layers guard against: path defaults frozen at import time
(e.g. the old `DEFAULT_FRAMEWORK_ROOT = Path.home() / ".renos"` module
constant) resolve the REAL home before any fixture can patch it — resolvers
must read HOME/env lazily at call time (fixed in lib/ren_paths.py).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

# Captured at import time, BEFORE any HOME monkeypatching — these are the
# developer's real ~/.renos and ~/.claude that the suite must never touch
# (~/.claude added 0.6.2 review finding L3: hooks and plugin-data paths can
# resolve there too).
_REAL_RENOS = Path(os.environ.get("HOME", "/nonexistent")) / ".renos"
_REAL_CLAUDE = Path(os.environ.get("HOME", "/nonexistent")) / ".claude"

# Every env var the path resolvers in lib/ren_paths.py (and the hooks'
# defensive inline fallbacks) consult. Cleared per-test so ambient shell
# state can't redirect writes outside tmp.
_PATH_ENV_VARS = (
    "REN_FRAMEWORK_ROOT",
    "REN_WIKI_ROOT",
    "CLAUDE_PLUGIN_OPTION_WIKIROOT",
    "CLAUDE_PLUGIN_OPTION_DEVROOT",
    "CLAUDE_PLUGIN_DATA",
    "CLAUDE_PLUGIN_ROOT",
    "CLAUDE_CONFIG_DIR",
    "REN_CLAUDE_DIR",
)


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    """Point HOME (and all RenOS path env overrides) at tmp for every test."""
    home = tmp_path / "isolated-home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    for var in _PATH_ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    # Guard: the resolvers must land under tmp. If a resolver ever goes back
    # to freezing Path.home() at import time, this fails on every test.
    from lib.ren_paths import framework_root, plugin_data_dir, wiki_root

    for resolved in (framework_root(), wiki_root(), plugin_data_dir()):
        assert str(resolved).startswith(str(tmp_path)), (
            f"test isolation breach: {resolved} resolves outside tmp_path "
            f"({tmp_path}) — a path default is being resolved at import time"
        )
    yield


def _claude_watch_paths() -> list[Path]:
    """The only paths under the real ~/.claude that RenOS code can write.

    Dogfood-2 finding M4: the old blanket rglob over all of ~/.claude
    false-positived constantly — a live Claude Code harness writes there
    CONTINUOUSLY while the suite runs (bash-commands.log, cost-tracker.log,
    history.jsonl, daemon/, cache/, statsig/, todos/, shell-snapshots/,
    file-history/, ...), and pytest attributes the session-teardown error to
    whatever test happened to be collected last (the intermittent "manifest
    test flake"). Exclusion lists can't win an arms race against harness
    churn, so the watch is inverted: only what RenOS itself could touch.

    Per lib/ren_paths.py, RenOS writes under ~/.claude exactly two things:
      - CLAUDE.md (`claude_user_dir()` — the managed pointer-block in
        lib/adapter/claude_md.py and skills/install),
      - plugins/data/renos/ (`plugin_data_dir()` — snapshots, code-maps).
    Plus, defensively, any plugins/ entry whose name starts with "ren"
    (loader-installed plugin dirs). Everything else under ~/.claude is
    harness-owned and out of scope. ~/.renos keeps its full watch.
    """
    watch = [_REAL_CLAUDE / "CLAUDE.md", _REAL_CLAUDE / "plugins" / "data" / "renos"]
    plugins = _REAL_CLAUDE / "plugins"
    if plugins.is_dir():
        for sub in plugins.iterdir():
            if sub.name.startswith("ren"):
                watch.append(sub)
            elif sub.is_dir() and sub.name != "data":
                watch.extend(p for p in sub.iterdir() if p.name.startswith("ren"))
    return watch


@pytest.fixture(scope="session", autouse=True)
def _real_renos_untouched():
    """Fail the run loudly if the suite modified the real ~/.renos, or any
    RenOS-writable path under the real ~/.claude (see `_claude_watch_paths`)."""
    start = time.time()
    yield
    touched: list[str] = []
    roots = [_REAL_RENOS, *_claude_watch_paths()]
    for root in roots:
        if not root.exists():
            continue
        for path in (root.rglob("*") if root.is_dir() else [root]):
            try:
                if path.lstat().st_mtime > start:
                    touched.append(str(path))
            except OSError:
                continue
    if touched:
        raise AssertionError(
            "test suite wrote into the real ~/.renos or a RenOS-owned path "
            f"under ~/.claude (isolation breach, issue #13/L3): {touched[:20]}"
        )
