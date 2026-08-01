"""
Tests for `skills.install.lib.warm_environment` — cold-start fix (issue #11
§4, Task 5). Warms the venv (`uv sync --frozen`) and records the venv's real
interpreter path to `state_dir()/interpreter.json`, so the wake-up hook's
self-heal can re-exec directly under it instead of paying `uv run`'s cold
resolution cost (~7s on a fresh machine — trips `_REEXEC_TIMEOUT_S`).

Every test redirects `ren_paths`' framework root to tmp_path via
REN_FRAMEWORK_ROOT, same convention as tests/skills/install/test_flow.py —
never the real ~/.renos.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys

import pytest

import skills.install.lib as install_lib
from lib.ren_paths import state_dir, wiki_root
from skills.install.lib import warm_environment


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_warm_records_existing_interpreter(wiki):
    info = warm_environment()

    assert os.path.exists(info["interpreter"])
    assert "warmed_at" in info
    assert info["machine"] == platform.node()
    assert info["platform"] == sys.platform

    on_disk = json.loads((state_dir() / "interpreter.json").read_text(encoding="utf-8"))
    assert on_disk["interpreter"] == info["interpreter"]
    assert on_disk["warmed_at"] == info["warmed_at"]
    assert on_disk["machine"] == platform.node()
    assert on_disk["platform"] == sys.platform


def test_warm_overwrites_stale_record(wiki):
    stale_path = state_dir() / "interpreter.json"
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text(
        json.dumps({"interpreter": "/nonexistent/python", "warmed_at": "2000-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )

    info = warm_environment()

    on_disk = json.loads(stale_path.read_text(encoding="utf-8"))
    assert on_disk["interpreter"] == info["interpreter"]
    assert on_disk["interpreter"] != "/nonexistent/python"


# --- lockfile fallback (issue #14) -------------------------------------
# The published plugin shipped without uv.lock, so `uv sync --frozen` failed
# unconditionally ("Unable to find lockfile"). uv.lock is now tracked (see
# tests/test_repo_hygiene.py), and warm_environment degrades to a non-frozen
# sync when the lockfile is missing at the project root instead of dying.


@pytest.fixture
def fake_uv(wiki, tmp_path, monkeypatch):
    """Point `_repo_root()` at an empty project dir and stub subprocess.run,
    so both sync paths can be asserted without invoking real uv."""
    project = tmp_path / "plugin-root"
    project.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(project))

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="/fake/venv/bin/python\n", stderr="")

    monkeypatch.setattr(install_lib.subprocess, "run", fake_run)
    return project, calls


def test_warm_uses_frozen_sync_when_lockfile_present(fake_uv):
    project, calls = fake_uv
    (project / "uv.lock").write_text("# lock\n", encoding="utf-8")

    info = warm_environment()

    assert calls[0] == ["uv", "sync", "--frozen", "--project", str(project)]
    assert info["interpreter"] == "/fake/venv/bin/python"


def test_warm_falls_back_to_unfrozen_sync_when_lockfile_absent(fake_uv):
    project, calls = fake_uv
    assert not (project / "uv.lock").exists()

    info = warm_environment()

    assert calls[0] == ["uv", "sync", "--project", str(project)]
    assert "--frozen" not in calls[0]
    # Still records interpreter state — the fallback must not skip the point.
    assert info["interpreter"] == "/fake/venv/bin/python"
    on_disk = json.loads((state_dir() / "interpreter.json").read_text(encoding="utf-8"))
    assert on_disk["interpreter"] == "/fake/venv/bin/python"
    assert on_disk["machine"] == platform.node()
