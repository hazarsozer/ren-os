"""
Doctor check for the recorded fast-path interpreter (spec 2026-08-21 (0.8.2) §8).

The wake-up hook re-execs under an interpreter recorded at install time to
avoid a cold-uv cost that trips _REEXEC_TIMEOUT_S (#11 §4). The record is
written by install and never refreshed by update, so it goes stale on a version
bump -- silently, because the hook falls through safely and no check read it.

Run with: uv run pytest tests/skills/doctor/test_interpreter_freshness.py -v
"""

from __future__ import annotations

import importlib
import json
import platform
import sys

import pytest

doctor = importlib.import_module("skills.doctor.lib")


@pytest.fixture
def state(monkeypatch, tmp_path):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    from lib.ren_paths import state_dir

    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record(state_dir, interpreter, *, machine=None, plat=None):
    (state_dir / "interpreter.json").write_text(json.dumps({
        "interpreter": str(interpreter),
        "warmed_at": "2026-07-31T15:13:00+00:00",
        "machine": machine if machine is not None else platform.node(),
        "platform": plat if plat is not None else sys.platform,
    }), encoding="utf-8")


def _executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_dangling_interpreter_warns(state):
    _record(state, "/nonexistent/cache/ren-os/ren/0.6.1/.venv/bin/python3")

    result = doctor.check_interpreter_freshness()

    assert result.status == "warn"
    assert "0.6.1" in result.message


def test_no_record_is_info_not_warn(state):
    result = doctor.check_interpreter_freshness()

    assert result.status == "info"


def test_foreign_machine_record_skips(state, tmp_path):
    interp = _executable(tmp_path / "python3")
    _record(state, interp, machine="some-other-laptop")

    result = doctor.check_interpreter_freshness()

    assert result.status == "skip", \
        "a synced record from another machine is ignored by the hook by design"


def test_valid_current_interpreter_is_ok(state, tmp_path, monkeypatch):
    interp = _executable(
        tmp_path / "cache" / "ren-os" / "ren" / "9.9.9" / ".venv" / "bin" / "python3"
    )
    _record(state, interp)
    monkeypatch.setattr(
        doctor.ren_paths, "current_plugin_cache_version", lambda: "9.9.9"
    )

    result = doctor.check_interpreter_freshness()

    assert result.status == "ok"


def test_valid_but_non_current_version_warns(state, tmp_path, monkeypatch):
    interp = _executable(
        tmp_path / "cache" / "ren-os" / "ren" / "0.7.9" / ".venv" / "bin" / "python3"
    )
    _record(state, interp)
    monkeypatch.setattr(
        doctor.ren_paths, "current_plugin_cache_version", lambda: "9.9.9"
    )

    result = doctor.check_interpreter_freshness()

    assert result.status == "warn"
