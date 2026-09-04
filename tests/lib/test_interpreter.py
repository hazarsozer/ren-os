"""lib.interpreter.recorded_interpreter_status — Windows venv layout.

`skills.install.lib.warm_environment` writes a record pointing at whatever
interpreter `uv run` resolved. On native Windows that's a `Scripts\\python.exe`
layout instead of POSIX `bin/python3`. No behaviour change is expected here —
this just proves the existing predicate (which only inspects `p.is_file()`,
`p.name.startswith("python")`, and `os.access(p, os.X_OK)`) already accepts
that layout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from lib.interpreter import recorded_interpreter_status


def test_windows_scripts_python_exe_layout_is_ok(tmp_path):
    interp = tmp_path / ".envs" / "0.8.6" / "Scripts" / "python.exe"
    interp.parent.mkdir(parents=True, exist_ok=True)
    interp.write_text("", encoding="utf-8")
    interp.chmod(0o755)

    record_path = tmp_path / "interpreter.json"
    record_path.write_text(json.dumps({"interpreter": str(interp)}), encoding="utf-8")

    path, reason = recorded_interpreter_status(record_path)

    assert reason == "ok"
    assert path == interp
