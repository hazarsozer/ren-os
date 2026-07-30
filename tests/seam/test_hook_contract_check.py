"""Tests for scripts/seam/hook_contract_check.py (issue #11 §1 item 1)."""
import json, subprocess, sys
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[2] / "scripts/seam/hook_contract_check.py"


def _run(hook_stdout: str, hook_exit: int, tmp_path: Path) -> subprocess.CompletedProcess:
    fake = tmp_path / "fake_hook.py"
    fake.write_text(
        f"import sys\nsys.stdout.write({hook_stdout!r})\nsys.exit({hook_exit})\n"
    )
    return subprocess.run(
        [sys.executable, str(CHECKER), "--hook-cmd", f"{sys.executable} {fake}"],
        capture_output=True, text=True,
    )


def test_healthy_injection_passes(tmp_path):
    out = json.dumps({"hookSpecificOutput": {"additionalContext": "## RenOS wake-up\n..."}})
    assert _run(out, 0, tmp_path).returncode == 0


def test_loud_degrade_passes(tmp_path):
    out = json.dumps({"hookSpecificOutput": {"additionalContext": "memory injection DISABLED: uv timeout"}})
    assert _run(out, 0, tmp_path).returncode == 0


def test_silent_empty_fails(tmp_path):
    out = json.dumps({"hookSpecificOutput": {"additionalContext": ""}})
    assert _run(out, 0, tmp_path).returncode == 1


def test_nonzero_exit_fails(tmp_path):
    out = json.dumps({"hookSpecificOutput": {"additionalContext": "fine"}})
    assert _run(out, 1, tmp_path).returncode == 1


def test_non_json_fails(tmp_path):
    assert _run("Traceback (most recent call last)...", 0, tmp_path).returncode == 1
