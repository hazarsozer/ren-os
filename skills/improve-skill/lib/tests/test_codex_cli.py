"""
Tests for skills.improve-skill.lib.codex_cli (A2 — cross-vendor critic adapter).

`run_exec` shells `codex exec` for a single non-interactive turn and returns a
ClaudeRun-shaped result so it is a drop-in judge runner for `judge_assertion`.
The subprocess is mocked — no live codex calls in the suite.

Run with:
    python3 -m pytest skills/improve-skill/lib/tests/test_codex_cli.py -v
"""

from __future__ import annotations

import subprocess

import pytest

from ..claude_cli import ClaudeRun
from ..codex_cli import run_exec
from ..types import ApiUsage


def _fake_completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=["codex"], returncode=returncode, stdout=stdout, stderr="")


def test_run_exec_parses_stdout(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed("TRUE\n"))
    run = run_exec("judge this", model="gpt-5", timeout_seconds=30)
    assert isinstance(run, ClaudeRun)
    assert run.output_text == "TRUE"
    assert run.is_error is False
    assert run.timed_out is False
    # codex token usage is not surfaced in the Anthropic shape (documented gap, A2 §5)
    assert run.usage == ApiUsage(0, 0)


def test_run_exec_nonzero_returncode_is_error(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed("boom", returncode=1))
    run = run_exec("x", model="gpt-5")
    assert run.is_error is True


def test_run_exec_timeout_sets_flag(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=1)

    monkeypatch.setattr(subprocess, "run", _raise)
    run = run_exec("x", model="gpt-5", timeout_seconds=1)
    assert run.timed_out is True
    assert run.output_text == ""


def test_run_exec_passes_model_in_command(monkeypatch):
    seen = {}

    def _capture(cmd, *a, **k):
        seen["cmd"] = cmd
        return _fake_completed("FALSE")

    monkeypatch.setattr(subprocess, "run", _capture)
    run_exec("x", model="o3-mini")
    assert seen["cmd"][0] == "codex"
    assert "o3-mini" in seen["cmd"]


def test_run_exec_is_drop_in_for_judge_runner_signature(monkeypatch):
    # judge_assertion calls runner(prompt, bare=..., model=..., timeout_seconds=...).
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed("TRUE"))
    run = run_exec("x", bare=False, model="gpt-5", timeout_seconds=42)
    assert run.output_text == "TRUE"
