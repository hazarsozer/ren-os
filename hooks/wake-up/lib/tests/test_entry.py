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

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SF_WAKE_UP = Path(__file__).resolve().parents[2] / "sf-wake-up.py"


def _load_wake_up_module():
    """Load the dash-named sf-wake-up.py as an importable module.

    Side-effect-free: the file is only imports + function defs guarded by
    `if __name__ == "__main__"`, so main() does NOT run on import.
    """
    spec = importlib.util.spec_from_file_location("sf_wake_up", SF_WAKE_UP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_WAKE_UP = _load_wake_up_module()


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


class TestWikiRootResolution:
    """Regression guard for C1 (REVIEW-v1.0-preship.md §C1).

    The old `Path(os.environ.get("SF_WIKI_ROOT","")) or (...)` never fell back
    because `Path("")` is `PosixPath('.')` (truthy), so in production —
    SF_WIKI_ROOT unset — wiki_root silently became CWD and CLAUDE_PLUGIN_OPTION_WIKIROOT
    was ignored entirely. These tests pin the explicit three-way fallback and
    the defensive ${HOME}/~ expansion.
    """

    HOME_DEFAULT = Path.home() / ".startup-framework" / "wiki"

    def test_sf_wiki_root_honored(self, monkeypatch):
        monkeypatch.setenv("SF_WIKI_ROOT", "/custom/wiki")
        monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", raising=False)
        assert _WAKE_UP._resolve_wiki_root() == Path("/custom/wiki")

    def test_plugin_option_honored_when_sf_unset(self, monkeypatch):
        """The CLAUDE_PLUGIN_OPTION_WIKIROOT case — the userConfig var every
        shell script reads, which the buggy Python layer ignored."""
        monkeypatch.delenv("SF_WIKI_ROOT", raising=False)
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", "/plugin/wiki")
        assert _WAKE_UP._resolve_wiki_root() == Path("/plugin/wiki")

    def test_home_default_when_both_unset(self, monkeypatch):
        """The core C1 regression: remove SF_WIKI_ROOT → home default fires
        (NOT CWD)."""
        monkeypatch.delenv("SF_WIKI_ROOT", raising=False)
        monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", raising=False)
        assert _WAKE_UP._resolve_wiki_root() == self.HOME_DEFAULT

    def test_empty_and_whitespace_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv("SF_WIKI_ROOT", "   ")
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", "")
        assert _WAKE_UP._resolve_wiki_root() == self.HOME_DEFAULT

    def test_sf_takes_precedence_over_plugin_option(self, monkeypatch):
        monkeypatch.setenv("SF_WIKI_ROOT", "/first")
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", "/second")
        assert _WAKE_UP._resolve_wiki_root() == Path("/first")

    def test_expands_dollar_home(self, monkeypatch):
        """plugin.json's literal `${HOME}/.startup-framework/wiki` default must
        resolve to the real home path, not a literal `${HOME}` dir — same C1
        failure class one layer down."""
        monkeypatch.delenv("SF_WIKI_ROOT", raising=False)
        monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", "${HOME}/.startup-framework/wiki")
        resolved = _WAKE_UP._resolve_wiki_root()
        assert resolved == self.HOME_DEFAULT
        assert "${HOME}" not in str(resolved)

    def test_expands_tilde(self, monkeypatch):
        monkeypatch.setenv("SF_WIKI_ROOT", "~/wiki")
        monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", raising=False)
        resolved = _WAKE_UP._resolve_wiki_root()
        assert resolved == Path.home() / "wiki"
        assert "~" not in str(resolved)
