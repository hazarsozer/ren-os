"""
Tests for the estimator calibration loop (Task 10, RenOS 0.6.1 E5a).

Three groups, mirroring the task brief:
  (a) wrap's harvest step pairs measured tokens with real text and moves
      `estimator.json`'s ratio toward the measured chars-per-token;
  (b) wake-up's cheap `estimate_tokens` uses the persisted calibrated ratio
      when present and falls back to `CHARS_PER_TOKEN` when absent/corrupt;
  (c) wake-up persists `last_injection.txt` byte-identical to the
      additionalContext it emitted.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/instrument/test_calibration_loop.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.instrument import calibration, collect, estimator
from lib.ren_paths import state_dir, wiki_root

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK_PATH = REPO_ROOT / "hooks" / "wake-up" / "ren-wake-up.py"


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def isolated_state(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    wiki_root().mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_transcript(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def _assistant_text_turn(session: str, text: str, *, output_tokens: int,
                         cache_creation: int = 0) -> dict:
    return {
        "sessionId": session,
        "type": "assistant",
        "timestamp": "2026-07-30T10:00:00Z",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
            "model": "claude-sonnet-4-6",
            "usage": {
                "input_tokens": 3,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": 0,
                "output_tokens": output_tokens,
            },
        },
    }


def _spawn_turn(session: str, models: list[str | None]) -> dict:
    return {
        "sessionId": session,
        "type": "assistant",
        "timestamp": "2026-07-30T10:01:00Z",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "Task", "input": ({"model": m} if m else {})}
                for m in models
            ],
            "usage": {"input_tokens": 1, "output_tokens": 10},
        },
    }


@pytest.fixture
def transcript_env(isolated_state, monkeypatch, tmp_path):
    """A resolvable transcript for session `sess-1`, addressed the way Claude
    Code addresses it: `<CLAUDE_CONFIG_DIR>/projects/<encoded-cwd>/<id>.jsonl`."""
    claude_dir = tmp_path / "claude-config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_dir))
    cwd = tmp_path / "Dev" / "demo"
    cwd.mkdir(parents=True)
    project_dir = claude_dir / "projects" / str(cwd).replace("/", "-")
    return {"claude_dir": claude_dir, "cwd": cwd, "project_dir": project_dir}


# ------------------------------------------------- (a) wrap-side calibration


def test_harvest_and_calibrate_moves_ratio_toward_measured(transcript_env):
    """A text-only assistant turn is an EXACTLY attributable (text, tokens)
    pair: its rendered text chars over its own `output_tokens`. Calibrating
    from it must move the stored ratio off the 4.0 default toward that pair."""
    text = "x" * 600  # 600 chars / 100 tokens => 6.0 chars per token
    _write_transcript(
        transcript_env["project_dir"] / "sess-1.jsonl",
        [_assistant_text_turn("sess-1", text, output_tokens=100)],
    )

    result = calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])

    assert result["calibrated"] is True
    assert result["samples"], "expected at least one calibration sample"
    data = json.loads((state_dir() / "metrics" / "estimator.json").read_text(encoding="utf-8"))
    assert data["chars_per_token"] == pytest.approx(6.0)
    assert data["samples"] == 1


def test_harvest_and_calibrate_records_usage_and_spawns(transcript_env):
    """The harvest step is also what brings `harvest_session_usage` live: it
    must record the session usage AND one `subagent_spawn` metric per spawn
    (the input Task 9's routing audit reads)."""
    _write_transcript(
        transcript_env["project_dir"] / "sess-1.jsonl",
        [
            _assistant_text_turn("sess-1", "y" * 400, output_tokens=100),
            _spawn_turn("sess-1", ["claude-opus-4-5", None]),
        ],
    )

    calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])

    spawns = collect.read(kind=collect.KIND_SUBAGENT_SPAWN)
    assert len(spawns) == 2
    assert {s["model"] for s in spawns} == {"claude-opus-4-5", None}
    assert all(s["parallel_peak"] == 2 for s in spawns)
    assert all(s["session"] == "sess-1" for s in spawns)

    usage = collect.read(kind=collect.KIND_CACHE_READ)
    assert len(usage) == 1
    assert usage[0]["session"] == "sess-1"
    assert usage[0]["output_tokens"] == 110


def test_harvest_and_calibrate_is_idempotent_per_session(transcript_env):
    """Wrapping twice in one session must not double-count spawn records."""
    _write_transcript(
        transcript_env["project_dir"] / "sess-1.jsonl",
        [_spawn_turn("sess-1", ["claude-opus-4-5"])],
    )

    calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])
    second = calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])

    assert second["already_recorded"] is True
    assert len(collect.read(kind=collect.KIND_SUBAGENT_SPAWN)) == 1


def test_missing_transcript_skips_silently(transcript_env):
    result = calibration.harvest_and_calibrate("nope", cwd=transcript_env["cwd"])
    assert result["calibrated"] is False
    assert result["reason"] == "no-transcript"
    assert not (state_dir() / "metrics" / "estimator.json").exists()


def test_zero_token_turns_never_calibrate(transcript_env):
    """Degraded/zero-token sessions must never reach `calibrate` — no
    division by zero, no poisoned ratio."""
    _write_transcript(
        transcript_env["project_dir"] / "sess-1.jsonl",
        [_assistant_text_turn("sess-1", "z" * 500, output_tokens=0)],
    )

    result = calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])

    assert result["calibrated"] is False
    assert result["reason"] == "no-samples"
    assert not (state_dir() / "metrics" / "estimator.json").exists()


def test_injection_pair_used_when_plausible(transcript_env):
    """`last_injection.txt` + the session's measured
    `cache_creation_input_tokens` form the brief's designed pair. It is only
    used when the implied ratio is PLAUSIBLE — see `calibration`'s docstring:
    on a cold session the measured cache-creation covers the whole prompt
    prefix, not the injection alone, so an implausible pair is dropped rather
    than allowed to poison the ratio."""
    injection = "i" * 4000
    (state_dir() / "metrics").mkdir(parents=True, exist_ok=True)
    calibration.last_injection_path().write_text(injection, encoding="utf-8")
    _write_transcript(
        transcript_env["project_dir"] / "sess-1.jsonl",
        # 4000 chars / 1000 cache-creation tokens => 4.0, inside the band.
        [_assistant_text_turn("sess-1", "", output_tokens=0, cache_creation=1000)],
    )

    result = calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])

    assert result["calibrated"] is True
    assert ("injection", 4000, 1000) in [
        (kind, chars, tokens) for kind, chars, tokens in result["samples"]
    ]


def test_implausible_injection_pair_dropped(transcript_env):
    injection = "i" * 4000
    (state_dir() / "metrics").mkdir(parents=True, exist_ok=True)
    calibration.last_injection_path().write_text(injection, encoding="utf-8")
    _write_transcript(
        transcript_env["project_dir"] / "sess-1.jsonl",
        # 4000 chars / 40000 tokens => 0.1 chars/token: cold-session prefix,
        # not attributable to the injection. Must be dropped.
        [_assistant_text_turn("sess-1", "", output_tokens=0, cache_creation=40000)],
    )

    result = calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])

    assert result["calibrated"] is False
    assert result["reason"] == "no-samples"


def test_tool_using_turns_are_not_calibration_samples(transcript_env):
    """Only text-only assistant turns are attributable: `output_tokens` on a
    tool-using turn also covers serialized tool input we don't measure."""
    turn = _assistant_text_turn("sess-1", "a" * 400, output_tokens=100)
    turn["message"]["content"].append({"type": "tool_use", "name": "Read", "input": {}})
    _write_transcript(transcript_env["project_dir"] / "sess-1.jsonl", [turn])

    result = calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])

    assert result["calibrated"] is False


def test_malformed_transcript_lines_never_raise(transcript_env):
    path = transcript_env["project_dir"] / "sess-1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "not json\n[]\n"
        + json.dumps(_assistant_text_turn("sess-1", "b" * 800, output_tokens=100))
        + "\n",
        encoding="utf-8",
    )

    result = calibration.harvest_and_calibrate("sess-1", cwd=transcript_env["cwd"])

    assert result["calibrated"] is True


def test_wrap_session_calls_the_calibration_loop(isolated_state, monkeypatch):
    """The wiring that matters: `wrap_session` must invoke the harvest step
    (which is what brings `harvest_session_usage` live), and a failure inside
    it must never break the wrap close-out."""
    import skills.wrap.lib as wrap_lib

    calls = []

    def boom(session, cwd=None):
        calls.append((session, cwd))
        raise RuntimeError("harvest exploded")

    monkeypatch.setattr(wrap_lib.calibration, "harvest_and_calibrate", boom)

    result = wrap_lib.wrap_session(
        narrative_md="Did a thing.\n", durable_items=[], session="sess-1", project=None
    )

    assert calls and calls[0][0] == "sess-1"
    assert result["l1_qid"]


# ------------------------------------------ (b) wake-up reads the calibration


def _wakeup_module():
    hook_dir = str(HOOK_PATH.parent)
    if hook_dir not in sys.path:
        sys.path.insert(0, hook_dir)
    import wakeup  # type: ignore[import-not-found]

    return wakeup


def test_wakeup_estimator_uses_persisted_ratio(isolated_state):
    estimator.calibrate([("x" * 800, 100)])  # 8.0 chars per token
    wakeup = _wakeup_module()

    assert wakeup.estimate_tokens("y" * 800) == 100


def test_wakeup_estimator_falls_back_when_absent(isolated_state):
    wakeup = _wakeup_module()
    assert wakeup.estimate_tokens("y" * 800) == int(800 / wakeup.CHARS_PER_TOKEN)


def test_wakeup_estimator_falls_back_when_corrupt(isolated_state):
    path = state_dir() / "metrics" / "estimator.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    wakeup = _wakeup_module()

    assert wakeup.estimate_tokens("y" * 800) == int(800 / wakeup.CHARS_PER_TOKEN)


def test_wakeup_estimator_ignores_nonpositive_ratio(isolated_state):
    path = state_dir() / "metrics" / "estimator.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"chars_per_token": 0, "samples": 3}), encoding="utf-8")
    wakeup = _wakeup_module()

    assert wakeup.estimate_tokens("y" * 800) == int(800 / wakeup.CHARS_PER_TOKEN)


# --------------------------------------------- (c) wake-up persists the pair


def _run_hook(tmp_path, env_extra: dict) -> dict:
    import os

    env = dict(os.environ)
    env.pop("REN_WIKI_ROOT", None)
    env.pop("CLAUDE_PLUGIN_OPTION_WIKIROOT", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps({"cwd": str(tmp_path), "source": "startup", "session_id": "sess-hook"}),
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_wakeup_writes_last_injection_matching_emitted_context(isolated_state, tmp_path):
    out = _run_hook(tmp_path, {"REN_FRAMEWORK_ROOT": str(isolated_state)})
    emitted = out["hookSpecificOutput"]["additionalContext"]
    assert emitted.strip(), "expected a non-empty payload (wiki exists but is empty => notice)"

    persisted = calibration.last_injection_path()
    assert persisted.is_file()
    assert persisted.read_bytes() == emitted.encode("utf-8")


def test_last_injection_is_overwritten_not_appended(isolated_state, tmp_path):
    calibration.last_injection_path().parent.mkdir(parents=True, exist_ok=True)
    calibration.last_injection_path().write_text("stale payload", encoding="utf-8")

    out = _run_hook(tmp_path, {"REN_FRAMEWORK_ROOT": str(isolated_state)})
    emitted = out["hookSpecificOutput"]["additionalContext"]

    assert calibration.last_injection_path().read_text(encoding="utf-8") == emitted
    assert "stale payload" not in calibration.last_injection_path().read_text(encoding="utf-8")


def test_persist_failure_never_breaks_injection(isolated_state, monkeypatch, capsys):
    """The write is best-effort: an unwritable state dir degrades to
    not-written, never to a lost injection."""
    def boom(text):
        raise OSError("read-only fs")

    monkeypatch.setattr(calibration, "_write_text_atomic", boom)
    assert calibration.persist_last_injection("hello") is False
