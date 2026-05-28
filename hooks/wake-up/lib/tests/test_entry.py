"""
Tests for the sf-wake-up.py entry script (the executable hook).

We exercise the script as a subprocess (mirrors how CC actually invokes hooks)
to verify the load-bearing invariants:
  - Always emits valid JSON to stdout (so CC can parse it)
  - Always exits 0 (so CC never aborts the session on a hook bug)
  - Emits `hookSpecificOutput.additionalContext` shape per CC_API_NOTES.md §4.2
  - Degrades to empty context (not crash) when wiki not bootstrapped
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


SF_WAKE_UP = Path(__file__).resolve().parents[2] / "sf-wake-up.py"


def _run_hook(stdin_payload: str = "{}", env_overrides: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Invoke the hook as a subprocess; return (exit_code, stdout, stderr)."""
    import os
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    # Point SF_WIKI_ROOT to a non-existent path → graceful degradation path
    env.setdefault("SF_WIKI_ROOT", str(Path("/tmp/sf-wake-up-test-no-wiki")))

    result = subprocess.run(
        [sys.executable, str(SF_WAKE_UP)],
        input=stdin_payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


class TestHookEntryPoint:
    def test_emits_valid_json_to_stdout(self):
        rc, stdout, _ = _run_hook()
        assert rc == 0, f"hook exited non-zero: {rc}"
        data = json.loads(stdout)  # raises if invalid JSON
        assert "hookSpecificOutput" in data

    def test_canonical_output_shape(self):
        """Pin: output matches CC_API_NOTES.md §4.2 schema exactly."""
        _, stdout, _ = _run_hook()
        data = json.loads(stdout)
        assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert isinstance(data["hookSpecificOutput"]["additionalContext"], str)

    def test_empty_stdin_handled_gracefully(self):
        """Pin: empty stdin produces valid JSON + exit 0 (not a crash)."""
        rc, stdout, _ = _run_hook(stdin_payload="")
        assert rc == 0
        data = json.loads(stdout)
        assert "hookSpecificOutput" in data

    def test_malformed_stdin_handled_gracefully(self):
        rc, stdout, _ = _run_hook(stdin_payload="{not valid json")
        assert rc == 0
        data = json.loads(stdout)
        assert "hookSpecificOutput" in data

    def test_missing_wiki_emits_empty_context(self):
        """Pin: when wiki_root doesn't exist, additionalContext is empty,
        but the JSON envelope is still emitted + exit 0."""
        _, stdout, _ = _run_hook()
        data = json.loads(stdout)
        # Empty wiki → empty additionalContext
        assert data["hookSpecificOutput"]["additionalContext"] == ""

    def test_session_payload_passed_through(self):
        """CC's SessionStart payload includes 'cwd' + 'source' fields."""
        payload = json.dumps({
            "cwd": "/tmp/test-cwd",
            "source": "startup",
        })
        rc, stdout, _ = _run_hook(stdin_payload=payload)
        assert rc == 0
        data = json.loads(stdout)
        assert "hookSpecificOutput" in data

    def test_compact_source_value_accepted(self):
        """Per hooks-guide, SessionStart matcher accepts: startup, resume, clear, compact."""
        for source in ["startup", "resume", "clear", "compact"]:
            payload = json.dumps({"source": source})
            rc, _, _ = _run_hook(stdin_payload=payload)
            assert rc == 0, f"hook crashed on source={source}"
