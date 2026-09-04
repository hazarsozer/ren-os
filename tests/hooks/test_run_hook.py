"""Tests for hooks/run-hook.sh — the cross-platform Python interpreter launcher.

Windows Claude Code executes hook `command` strings under Git Bash, but
hooks.json hardcoded `python3`, which isn't guaranteed on Windows PATH. This
launcher resolves python3 -> python -> `py -3` (in that order), execs the
hook script with stdin passed through untouched, and fails open (exit 0,
print `{}`) when no interpreter is found so a missing interpreter never
blocks tool use.

Skipped entirely if `bash` is not on PATH.
"""
from __future__ import annotations

import shutil
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_HOOK = REPO_ROOT / "hooks" / "run-hook.sh"
BASH = shutil.which("bash")


def _make_shim(dir_: Path, name: str, echoes: str) -> Path:
    """A fake interpreter shim: responds to a `-c pass` probe (any arg is
    literally `-c`) by exiting 0 with no output — like a real interpreter —
    and otherwise echoes `<echoes>:<all argv, space-joined>` then its stdin.
    """
    shim = dir_ / name
    shim.write_text(
        f"#!{BASH}\n"
        "for a in \"$@\"; do\n"
        "  if [ \"$a\" = \"-c\" ]; then exit 0; fi\n"
        "done\n"
        f"echo {echoes}:\"$*\"\n"
        "cat\n",
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR | stat.S_IXUSR)
    return shim


def _make_alias_stub_shim(dir_: Path, name: str) -> Path:
    """Mimics the Windows WindowsApps App Execution Alias `python.exe` stub:
    on PATH (`command -v` finds it) but exits 9009 with no output for any
    invocation, including a `-c pass` probe."""
    shim = dir_ / name
    shim.write_text(f"#!{BASH}\nexit 9009\n", encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR | stat.S_IXUSR)
    return shim


@pytest.fixture
def coreutils_dir(tmp_path_factory) -> Path:
    """A PATH entry with just `cat` symlinked in — not a real python3/python,
    so it can't accidentally satisfy the interpreter search."""
    d = tmp_path_factory.mktemp("coreutils")
    (d / "cat").symlink_to(shutil.which("cat"))
    return d


def _run(path_dirs: list[Path], script_path: str, stdin: str = "", env_extra: dict | None = None):
    env = {"PATH": ":".join(str(d) for d in path_dirs)}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [BASH, str(RUN_HOOK), script_path],
        input=stdin, capture_output=True, text=True, env=env, timeout=10,
    )


def test_uses_python3_when_present(tmp_path, coreutils_dir):
    _make_shim(tmp_path, "python3", "python3")
    proc = _run([tmp_path, coreutils_dir], "/some/hook.py")
    assert proc.returncode == 0
    assert proc.stdout.startswith("python3:/some/hook.py")


def test_falls_back_to_python_when_no_python3(tmp_path, coreutils_dir):
    _make_shim(tmp_path, "python", "python")
    proc = _run([tmp_path, coreutils_dir], "/some/hook.py")
    assert proc.returncode == 0
    assert proc.stdout.startswith("python:/some/hook.py")


def test_exits_zero_and_prints_empty_json_when_no_interpreter(tmp_path):
    proc = _run([tmp_path], "/some/hook.py")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "{}"
    assert "no python interpreter on PATH" in proc.stderr


def test_stdin_passed_through_untouched(tmp_path, coreutils_dir):
    _make_shim(tmp_path, "python3", "python3")
    proc = _run([tmp_path, coreutils_dir], "/some/hook.py", stdin="hello stdin\n")
    assert proc.stdout == "python3:/some/hook.py\nhello stdin\n"


def test_env_override_wins(tmp_path, coreutils_dir):
    _make_shim(tmp_path, "python3", "python3")
    override = _make_shim(tmp_path, "custom-python", "custom")
    proc = _run([tmp_path, coreutils_dir], "/some/hook.py", env_extra={"REN_HOOK_PYTHON": str(override)})
    assert proc.stdout.startswith("custom:/some/hook.py")


def test_windows_app_execution_alias_stub_is_skipped_for_py(tmp_path, coreutils_dir):
    """On stock Windows, `python.exe` on PATH is often the WindowsApps App
    Execution Alias stub: `command -v` finds it, but running it exits 9009
    with no output. The launcher must probe before exec'ing, skip this
    candidate, and fall through to `py -3` (the real interpreter)."""
    _make_alias_stub_shim(tmp_path, "python")
    _make_shim(tmp_path, "py", "py")
    proc = _run([tmp_path, coreutils_dir], "/some/hook.py")
    assert proc.returncode == 0
    assert proc.stdout.startswith("py:-3 /some/hook.py")


def test_uses_py_dash_3_when_only_py_present(tmp_path, coreutils_dir):
    """Dedicated `py -3` coverage: with no python3/python on PATH at all,
    the launcher must fall all the way through to `py -3 <script>`."""
    _make_shim(tmp_path, "py", "py")
    proc = _run([tmp_path, coreutils_dir], "/some/hook.py")
    assert proc.returncode == 0
    assert proc.stdout.startswith("py:-3 /some/hook.py")
