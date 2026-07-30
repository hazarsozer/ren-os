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

import pytest

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

    on_disk = json.loads((state_dir() / "interpreter.json").read_text(encoding="utf-8"))
    assert on_disk["interpreter"] == info["interpreter"]
    assert on_disk["warmed_at"] == info["warmed_at"]


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
