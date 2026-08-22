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
    from lib.ren_paths import interpreter_record_path

    d = interpreter_record_path().parent
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


def test_record_lives_outside_the_synced_wiki(monkeypatch, tmp_path):
    """0.8.3: the record names an absolute interpreter path on THIS
    filesystem, so it must not sit under the wiki root — `/ren:backup` pushes
    the wiki to a remote, which is how a machine-specific path used to reach
    other machines. That sync is the only reason the old `platform.node()`
    guard existed; storing the record where it cannot travel retires it."""
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    from lib.ren_paths import interpreter_record_path, wiki_root

    record = interpreter_record_path()
    assert wiki_root() not in record.parents, \
        f"{record} is inside the synced wiki and would be backed up"


def test_legacy_record_under_the_wiki_is_ignored(state, monkeypatch, tmp_path):
    """A pre-0.8.3 record left at `state_dir()/interpreter.json` must not be
    read. `/ren:update`'s re-warm deletes it, but a wiki restored from backup
    can reintroduce one — pointing at another machine's filesystem."""
    from lib.ren_paths import state_dir

    legacy = state_dir()
    legacy.mkdir(parents=True, exist_ok=True)
    _record(legacy, _executable(tmp_path / "python3"))

    result = doctor.check_interpreter_freshness()

    assert result.status == "info", \
        "a legacy record under the wiki was read; only the machine-local one counts"


def test_machine_field_is_diagnostic_only(state, tmp_path, monkeypatch):
    """`machine` is still recorded so a human reading the file knows where it
    came from, but nothing compares it. `platform.node()` returned an
    IP-derived name on the development machine (`192.168.1.17` vs the
    recorded `Hazars-MacBook-Air.local`, same laptop), so comparing it
    rejected valid records after every network change — a permanent silent
    degrade. Validity is now only ever "does this path work here"."""
    interp = _executable(tmp_path / "cache" / "ren-os" / "ren" / "9.9.9" / "python3")
    _record(state, interp, machine="some-other-laptop", plat="plan9")
    monkeypatch.setattr(
        doctor.ren_paths, "current_plugin_cache_version", lambda: "9.9.9"
    )

    result = doctor.check_interpreter_freshness()

    assert result.status == "ok", \
        "a live, current interpreter was rejected over a diagnostic-only field"


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


def test_exec_bit_missing_warns(state, tmp_path):
    """A synced or restored .venv that lost its exec bit: the hook rejects
    it (`os.access(p, os.X_OK)` is False), so doctor must warn — reporting
    `ok` here is exactly the silent degradation this check exists to catch."""
    path = tmp_path / "cache" / "ren-os" / "ren" / "9.9.9" / ".venv" / "bin" / "python3"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    path.chmod(0o644)  # no execute bit
    _record(state, path)

    result = doctor.check_interpreter_freshness()

    assert result.status == "warn"
    assert "not executable" in result.message


def test_not_a_python_name_warns(state, tmp_path):
    """The hook requires `p.name.startswith("python")`; a record pointing at
    a differently-named binary is rejected by the hook and must warn here
    too, not report `ok`."""
    interp = _executable(tmp_path / "some-other-binary")
    _record(state, interp)

    result = doctor.check_interpreter_freshness()

    assert result.status == "warn"
    assert "not a python binary" in result.message


def test_non_dict_record_is_info_not_crash(state):
    """A top-level non-dict `interpreter.json` (`null`, a number, a list)
    parses fine but has no `.get(...)` — must degrade to `info`, not raise
    `AttributeError`."""
    (state / "interpreter.json").write_text("null", encoding="utf-8")

    result = doctor.check_interpreter_freshness()

    assert result.status == "info"


@pytest.mark.parametrize(
    "recorded,expected",
    [
        ("/h/.claude/plugins/cache/ren-os/ren/0.8.2/.venv/bin/python3", "0.8.2"),
        ("/h/.renos/.envs/0.8.2/bin/python3", "0.8.2"),
        ("/somewhere/else/bin/python3", "unknown"),
    ],
)
def test_version_derived_from_both_venv_layouts(recorded, expected):
    """`warm_environment` resolves through `uv run`, which honors
    `UV_PROJECT_ENVIRONMENT` — and #40 has every invocation point that at
    `ren_paths.envs_dir()` so uv does not write a `.venv` into the immutable
    plugin cache dir. So the recorded interpreter is normally under
    `~/.renos/.envs/<version>/`, not `.../ren/<version>/`. Recognizing only
    the latter returned "unknown" and silently skipped the currency check."""
    assert doctor._recorded_interpreter_version(recorded) == expected
