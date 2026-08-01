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


@pytest.fixture(scope="session", autouse=True)
def _real_renos_untouched():
    """Fail the run loudly if the suite modified the real ~/.renos or ~/.claude."""
    start = time.time()
    yield
    touched: list[str] = []
    for root in (_REAL_RENOS, _REAL_CLAUDE):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            try:
                if path.lstat().st_mtime > start:
                    touched.append(str(path))
            except OSError:
                continue
    if touched:
        raise AssertionError(
            "test suite wrote into the real ~/.renos or ~/.claude (isolation "
            f"breach, issue #13/L3): {touched[:20]}"
        )
