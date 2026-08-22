"""`/ren:update`'s re-warm closing step (open-work: "install writes
per-version artifacts that update never refreshes").

`warm_environment()` was called only by `/ren:install`, so the recorded
fast-path interpreter kept naming a plugin cache dir the update had just
superseded. It fails safe — the hook falls through to `uv run` — which is
exactly why it went unnoticed for roughly ten releases.
"""
from __future__ import annotations

import importlib
import json

import pytest

up = importlib.import_module("skills.update.lib")


@pytest.fixture
def framework(monkeypatch, tmp_path):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    return tmp_path


def test_rewarm_records_the_interpreter(framework, monkeypatch):
    from lib.ren_paths import interpreter_record_path

    monkeypatch.setattr(
        "skills.install.lib.warm_environment",
        lambda: {"interpreter": "/w/python3", "warmed_at": "2026-08-22T00:00:00+00:00"},
    )
    result = up.rewarm_interpreter()

    assert result["status"] == "warmed"
    assert result["interpreter"] == "/w/python3"


def test_rewarm_removes_the_legacy_synced_record(framework, monkeypatch):
    """The pre-0.8.3 record lived under the wiki, inside `/ren:backup`'s push.
    Leaving it there keeps syncing one machine's absolute paths to every other
    machine that restores the wiki."""
    from lib.ren_paths import state_dir

    legacy = state_dir() / "interpreter.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"interpreter": "/old/python3"}), encoding="utf-8")

    monkeypatch.setattr(
        "skills.install.lib.warm_environment", lambda: {"interpreter": "/w/python3"}
    )
    result = up.rewarm_interpreter()

    assert result["legacy_removed"] is True
    assert not legacy.exists()


def test_rewarm_never_raises_and_never_gates_the_update(framework, monkeypatch):
    """A failed warm degrades the fast path; it does not fail the update.
    `warm_environment` shells out to `uv sync` — network-bound and entirely
    capable of failing on a machine whose update otherwise succeeded."""
    def _boom():
        raise RuntimeError("uv sync exploded")

    monkeypatch.setattr("skills.install.lib.warm_environment", _boom)
    result = up.rewarm_interpreter()

    assert result["status"].startswith("error:")
    assert "uv sync exploded" in result["status"]


def test_rewarm_still_retires_the_legacy_record_when_the_warm_fails(framework, monkeypatch):
    """The legacy file is stale regardless of whether the new warm succeeds —
    cleaning it up must not be hostage to `uv sync` working."""
    from lib.ren_paths import state_dir

    legacy = state_dir() / "interpreter.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("{}", encoding="utf-8")

    def _boom():
        raise RuntimeError("nope")

    monkeypatch.setattr("skills.install.lib.warm_environment", _boom)
    result = up.rewarm_interpreter()

    assert result["status"].startswith("error:")
    assert result["legacy_removed"] is True
    assert not legacy.exists()
