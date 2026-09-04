"""hooks/hooks.json — every registered hook must route through run-hook.sh.

Windows Claude Code runs hook `command` strings under Git Bash, and
run-hook.sh (hooks/run-hook.sh) resolves the Python interpreter portably
(python3 -> python -> `py -3`) instead of hooks.json hardcoding `python3`.
This asserts every command was migrated and still names a real .py script,
plus that the doctor-grepped 'ren-wake-up.py' substring survived the edit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"

_COMMAND_RE = re.compile(
    r'^bash "\$CLAUDE_PLUGIN_ROOT/hooks/run-hook\.sh" "\$CLAUDE_PLUGIN_ROOT/(hooks/[\w./-]+\.py)"$'
)


def _iter_commands():
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for hook_list in data["hooks"].values():
        for matcher_entry in hook_list:
            for hook in matcher_entry["hooks"]:
                yield hook["command"]


def test_every_command_routes_through_run_hook_sh():
    commands = list(_iter_commands())
    assert commands, "expected at least one hook command"
    for command in commands:
        assert _COMMAND_RE.match(command), f"not routed through run-hook.sh: {command}"


def test_every_referenced_py_script_exists():
    for command in _iter_commands():
        match = _COMMAND_RE.match(command)
        assert match, f"not routed through run-hook.sh: {command}"
        py_relpath = match.group(1)
        assert (REPO_ROOT / py_relpath).is_file(), f"missing script: {py_relpath}"


def test_wake_up_substring_survives_for_doctor_grep():
    raw = HOOKS_JSON.read_text(encoding="utf-8")
    assert "ren-wake-up.py" in raw
