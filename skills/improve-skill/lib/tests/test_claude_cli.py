from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ..claude_cli import ClaudeRun, _activated_from_stream, run_print
from ..types import ApiUsage


def _fake_completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr="")


def test_run_print_parses_text_and_usage(monkeypatch):
    payload = json.dumps({
        "result": "hello world",
        "usage": {"input_tokens": 10, "output_tokens": 4},
    })
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(payload))
    run = run_print("hi", bare=True, timeout_seconds=30)
    assert isinstance(run, ClaudeRun)
    assert run.output_text == "hello world"
    assert run.usage == ApiUsage(input_tokens=10, output_tokens=4)
    assert run.timed_out is False


def test_run_print_timeout_sets_flag(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)
    monkeypatch.setattr(subprocess, "run", _raise)
    run = run_print("hi", bare=True, timeout_seconds=1)
    assert run.timed_out is True
    assert run.output_text == ""


# ── _activated_from_stream unit tests ──────────────────────────────────────────

# Real event shape recorded from live `claude --output-format stream-json`:
# Skill activation is a tool_use block NESTED inside an assistant message's content[].
_REAL_SKILL_LINE = json.dumps({
    "type": "assistant",
    "message": {
        "model": "claude-sonnet-4-6",
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_01S4bEgeopx8GQqeoALGpXsr",
                "name": "Skill",
                "input": {"skill": "resume-session"},
                "caller": {"type": "direct"},
            }
        ],
    },
})

# A non-Skill tool_use nested inside assistant — must NOT be counted.
_NON_SKILL_LINE = json.dumps({
    "type": "assistant",
    "message": {
        "content": [
            {
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "ls"},
            }
        ]
    },
})


def test_activated_from_stream_detects_nested_skill() -> None:
    """The real stream-json shape nests tool_use inside assistant.message.content[].
    The parser must find it there and return the skill name."""
    raw = _REAL_SKILL_LINE + "\n" + _NON_SKILL_LINE
    result = _activated_from_stream(raw)
    assert result == ("resume-session",)


def test_activated_from_stream_empty_when_no_skill_events() -> None:
    """A stream with no Skill tool_use events returns an empty tuple."""
    raw = _NON_SKILL_LINE + "\n" + json.dumps({"type": "result", "result": "done"})
    assert _activated_from_stream(raw) == ()
