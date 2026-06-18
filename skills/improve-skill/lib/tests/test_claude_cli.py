from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ..claude_cli import ClaudeRun, run_print
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
