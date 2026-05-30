"""Fixtures for the installed-plugin-runtime integration tests (ADR-030).

Everything the tests need is exposed through fixtures that return factory
callables + result objects, so the test module needs no cross-module imports
(``tests/`` is not a package — pytest collects it via rootdir).

The three factories:
    make_plugin_root(include_feed=True)  -> Path   (a fake $CLAUDE_PLUGIN_ROOT)
    make_home(with_wiki=True, with_feed_clone=True) -> SeededHome
    run_wake_up(plugin_root, home, cwd, set_plugin_root_env=True, ...) -> HookRun

A HookRun carries the parsed additionalContext, the concatenated hook log, the
exit code, and raw stdout/stderr — so assertions ride observable behavior and
failures are debuggable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest


# --- constants --------------------------------------------------------------

# Path of sf-wake-up.py relative to the plugin root (post-Crucible: root IS plugin).
WAKE_UP_REL = Path("hooks") / "wake-up" / "sf-wake-up.py"

# A distinctive marker seeded into the home wiki's index.md. Its presence in the
# emitted additionalContext proves the wiki was resolved from the home-default
# path ($HOME/.startup-framework/wiki) — i.e. C1 is closed.
WIKI_SENTINEL = "INSTALLED-RUNTIME-WIKI-SENTINEL-7f3a91"

# Master-index section header lifecycle's composer emits (hooks/wake-up/wakeup).
MASTER_INDEX_HEADER = "Master wiki index"

# feed.reader._format_header literal (stable substring across fresh/stale forms).
FEED_BLOCK_HEADER = "Activity Feed — recent friend activity"

# The hook's graceful-degrade log line on ImportError (the C2 silent path).
FEED_UNAVAILABLE_LOG = "feed module unavailable; skipping feed integration"

# Friend handles seeded into the activity-feed clone. The own handle must match
# identity.md's `handle:` field so feed.config.handle() resolves.
OWN_HANDLE = "testfriend"
FRIEND_HANDLES = (OWN_HANDLE, "friend-b", "friend-c")


# --- result objects ---------------------------------------------------------


@dataclass(frozen=True)
class SeededHome:
    """A fake $HOME with the framework dir seeded under .startup-framework/."""

    path: Path
    sentinel: str
    own_handle: str
    friend_handles: tuple[str, ...]
    has_wiki: bool
    has_feed_clone: bool


@dataclass(frozen=True)
class HookRun:
    """The observable result of one sf-wake-up.py subprocess invocation."""

    returncode: int
    context: str  # parsed hookSpecificOutput.additionalContext ("" if unparsable)
    log: str  # concatenated <home>/.startup-framework/logs/wake-up-*.log
    stdout: str
    stderr: str


# --- pure helpers (module-level so fixtures can compose them) ----------------


def _identity_md(handle: str) -> str:
    """Minimal valid wiki/identity.md (frontmatter feed.config.handle() reads)."""
    return (
        "---\n"
        'title: "Test Friend\'s Identity"\n'
        "type: identity\n"
        "schema_version: 1\n"
        'framework_version: "1.0.0"\n'
        f"handle: {handle}\n"
        'name: "Test Friend"\n'
        "phase: ideation\n"
        "---\n\n"
        "# About Test Friend\n\nInstalled-runtime fixture identity.\n"
    )


def _feed_log_md(handle: str, ts: str) -> str:
    """A <handle>.log.md mirroring the proven _populate_feed_fixture shape."""
    return (
        "---\n"
        "schema_version: 1\n"
        'framework_version: "1.0.0"\n'
        "type: feed-entry\n"
        f"handle: {handle}\n"
        "---\n\n"
        f"## [{ts}] start | {handle} | working in ~/Dev/sidecar/\n\n"
        f"## [{ts}] end | {handle} | session complete\n\n"
        "Worked on sidecar — set up JWT middleware.\n"
        "Touched: src/auth/jwt.ts, src/api/login.ts.\n"
    )


def _materialize_plugin_root(dest: Path, *, repo_root: Path, include_feed: bool) -> Path:
    """Copy the real plugin files into `dest` in the post-Crucible layout.

    Real files only (symlinks dereferenced via copytree's default), mirroring what
    Claude Code places under $CLAUDE_PLUGIN_ROOT. We copy what the hook touches:
    .claude-plugin/plugin.json, hooks/ (incl. wake-up/wakeup + hooks.json), lib/, feed/.
    `lib/` (the framework path/handle core, ADR-031) is always materialized because
    feed.config now re-exports `lib.sf_paths`; a fake root with feed/ but no lib/ would
    fail to import. skills/ is a real but empty dir purely for shape parity.
    """
    dest.mkdir(parents=True, exist_ok=True)

    cp = dest / ".claude-plugin"
    cp.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo_root / ".claude-plugin" / "plugin.json", cp / "plugin.json")

    shutil.copytree(
        repo_root / "hooks",
        dest / "hooks",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "verify"),
        symlinks=False,
    )

    shutil.copytree(
        repo_root / "lib",
        dest / "lib",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"),
        symlinks=False,
    )

    if include_feed:
        shutil.copytree(
            repo_root / "feed",
            dest / "feed",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"),
            symlinks=False,
        )

    skills = dest / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    (skills / ".gitkeep").write_text("", encoding="utf-8")

    return dest


def _seed_home(home: Path, *, with_wiki: bool, with_feed_clone: bool) -> SeededHome:
    """Seed <home>/.startup-framework/ with a wiki and/or an activity-feed clone."""
    sf = home / ".startup-framework"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    if with_wiki:
        wiki = sf / "wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / "index.md").write_text(
            f"# Master Wiki Index\n\n{WIKI_SENTINEL}\n\n"
            "- [decisions](decisions/)\n- [projects](projects/)\n",
            encoding="utf-8",
        )
        (wiki / "log.md").write_text(
            f"# Log\n\n## [{ts}] decision | seeded master log entry for installed-runtime test\n",
            encoding="utf-8",
        )
        (wiki / "identity.md").write_text(_identity_md(OWN_HANDLE), encoding="utf-8")

    if with_feed_clone:
        feed_dir = sf / "activity-feed"
        feed_dir.mkdir(parents=True, exist_ok=True)
        for handle in FRIEND_HANDLES:
            (feed_dir / f"{handle}.log.md").write_text(_feed_log_md(handle, ts), encoding="utf-8")

    return SeededHome(
        path=home,
        sentinel=WIKI_SENTINEL,
        own_handle=OWN_HANDLE,
        friend_handles=FRIEND_HANDLES,
        has_wiki=with_wiki,
        has_feed_clone=with_feed_clone,
    )


def _read_hook_log(home: Path) -> str:
    log_dir = home / ".startup-framework" / "logs"
    if not log_dir.is_dir():
        return ""
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(log_dir.glob("wake-up-*.log"))
    )


def _run_wake_up(
    *,
    plugin_root: Path,
    home: Path,
    cwd: Path,
    set_plugin_root_env: bool,
    extra_env: dict[str, str] | None,
    source: str,
    timeout: int,
) -> HookRun:
    """Invoke sf-wake-up.py as a subprocess the way Claude Code does.

    The environment is built FROM SCRATCH — this is the load-bearing part. We set
    only PATH, HOME, LANG/LC_ALL, and (optionally) CLAUDE_PLUGIN_ROOT. We pass
    NEITHER SF_WIKI_ROOT NOR CLAUDE_PLUGIN_OPTION_WIKIROOT NOR SF_FRAMEWORK_ROOT
    NOR PYTHONPATH — so the home-default wiki tier (C1) and the hook's own
    plugin-root sys.path insertion (C2) are the paths actually under test, with no
    dev-tree crutch leaking in via the parent process.
    """
    script = plugin_root / WAKE_UP_REL
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "LANG": "C",
        "LC_ALL": "C",
    }
    if set_plugin_root_env:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    if extra_env:
        env.update(extra_env)

    stdin_payload = json.dumps(
        {"cwd": str(cwd), "source": source, "hook_event_name": "SessionStart"}
    )

    proc = subprocess.run(
        [sys.executable, str(script)],
        input=stdin_payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        timeout=timeout,
    )

    context = ""
    try:
        data = json.loads(proc.stdout)
        context = data.get("hookSpecificOutput", {}).get("additionalContext", "")
    except (json.JSONDecodeError, AttributeError):
        context = ""

    return HookRun(
        returncode=proc.returncode,
        context=context,
        log=_read_hook_log(home),
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


# --- fixtures ---------------------------------------------------------------


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repo root: tests/integration/installed_runtime/conftest.py -> parents[3]."""
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def neutral_cwd(tmp_path: Path) -> Path:
    """A session-project-like dir with NO wiki — the subprocess cwd.

    Pre-fix, the buggy `Path("")`-is-truthy bug resolves wiki_root to this cwd;
    keeping it wiki-less is what makes the C1 assertion bite.
    """
    d = tmp_path / "session-project"
    d.mkdir()
    return d


@pytest.fixture
def make_plugin_root(tmp_path: Path, repo_root: Path):
    """Factory: materialize a fake $CLAUDE_PLUGIN_ROOT (real files, Crucible shape)."""
    counter = {"n": 0}

    def _factory(*, include_feed: bool = True) -> Path:
        counter["n"] += 1
        dest = tmp_path / f"plugin-root-{counter['n']}"
        return _materialize_plugin_root(dest, repo_root=repo_root, include_feed=include_feed)

    return _factory


@pytest.fixture
def make_home(tmp_path: Path):
    """Factory: seed a fake $HOME with a wiki and/or activity-feed clone."""
    counter = {"n": 0}

    def _factory(*, with_wiki: bool = True, with_feed_clone: bool = True) -> SeededHome:
        counter["n"] += 1
        home = tmp_path / f"home-{counter['n']}"
        home.mkdir()
        return _seed_home(home, with_wiki=with_wiki, with_feed_clone=with_feed_clone)

    return _factory


@pytest.fixture
def run_wake_up(neutral_cwd: Path):
    """Factory: run sf-wake-up.py as a subprocess; return an observable HookRun."""

    def _factory(
        *,
        plugin_root: Path,
        home: SeededHome | Path,
        cwd: Path | None = None,
        set_plugin_root_env: bool = True,
        extra_env: dict[str, str] | None = None,
        source: str = "startup",
        timeout: int = 30,
    ) -> HookRun:
        home_path = home.path if isinstance(home, SeededHome) else home
        return _run_wake_up(
            plugin_root=plugin_root,
            home=home_path,
            cwd=cwd or neutral_cwd,
            set_plugin_root_env=set_plugin_root_env,
            extra_env=extra_env,
            source=source,
            timeout=timeout,
        )

    return _factory
