"""
Tests for hooks/observers/read_tracker.py — the PostToolUse observer that
feeds wiki page-read usage events into Task 4's decay signal (Task 5,
RenOS 0.5.5 spec §4.3).

Subprocess-run, mirroring the real Claude Code invocation contract: stdin
JSON in, exit code out, and — the load-bearing property for a PostToolUse
OBSERVER — NO stdout ever (stray stdout would surface as hook output to the
user; this hook must be silent). Every test redirects `REN_WIKI_ROOT` to
tmp_path — never the real wiki.

Run with: uv run pytest tests/hooks/test_read_tracker.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from lib.instrument import collect

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / "hooks" / "observers" / "read_tracker.py"

_ENV_VARS_TO_CLEAR = (
    "REN_WIKI_ROOT",
    "CLAUDE_PLUGIN_OPTION_WIKIROOT",
    "REN_FRAMEWORK_ROOT",
    "CLAUDE_PLUGIN_ROOT",
    "PYTHONPATH",
)


def _run_hook(
    stdin_payload: dict | str,
    wiki_root: Path,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for var in _ENV_VARS_TO_CLEAR:
        env.pop(var, None)
    env["REN_WIKI_ROOT"] = str(wiki_root)
    if extra_env:
        env.update(extra_env)

    stdin_text = stdin_payload if isinstance(stdin_payload, str) else json.dumps(stdin_payload)
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )


@pytest.fixture
def wiki_root_path(tmp_path, monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "wiki"
    root.mkdir()
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    return root


def _page_reads() -> list[dict]:
    return collect.read(kind=collect.KIND_PAGE_READ)


# =============================================================================
# core behavior
# =============================================================================


def test_wiki_read_logged(wiki_root_path):
    target = wiki_root_path / "projects" / "p" / "x.md"
    target.parent.mkdir(parents=True)
    target.write_text("hello\n", encoding="utf-8")

    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(target)},
        "cwd": str(wiki_root_path),
        "session_id": "sess-1",
    }
    result = _run_hook(payload, wiki_root_path)

    assert result.returncode == 0
    assert result.stdout == ""

    entries = _page_reads()
    assert len(entries) == 1
    assert entries[0]["page"] == "projects/p/x.md"
    assert entries[0]["session"] == "sess-1"


def test_non_wiki_read_ignored(wiki_root_path):
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": "/etc/hostname"},
        "cwd": str(wiki_root_path),
        "session_id": "sess-1",
    }
    result = _run_hook(payload, wiki_root_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert _page_reads() == []


def test_archive_read_ignored(wiki_root_path):
    target = wiki_root_path / "archive" / "old-notes.md"
    target.parent.mkdir(parents=True)
    target.write_text("stale\n", encoding="utf-8")

    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(target)},
        "cwd": str(wiki_root_path),
        "session_id": "sess-1",
    }
    result = _run_hook(payload, wiki_root_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert _page_reads() == []


def test_traversal_resolved(wiki_root_path):
    outside = wiki_root_path.parent / "outside.md"
    outside.write_text("nope\n", encoding="utf-8")
    traversal_path = str(wiki_root_path / ".." / "outside.md")

    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": traversal_path},
        "cwd": str(wiki_root_path),
        "session_id": "sess-1",
    }
    result = _run_hook(payload, wiki_root_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert _page_reads() == []


def test_garbage_stdin_exit_zero(wiki_root_path):
    result = _run_hook("not json at all {{{", wiki_root_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert _page_reads() == []


def test_closed_stdin_exit_zero(wiki_root_path):
    # Critical fix (0.5.5 Task 5): a closed/unreadable stdin — reproduced
    # live via `python3 hooks/observers/read_tracker.py <&-`, which raises
    # AttributeError ('NoneType' object has no attribute 'read', since
    # Python sets sys.stdin to None when fd 0 is invalid at startup) — must
    # NOT propagate past exit 0. This is a PostToolUse OBSERVER; any
    # non-zero exit is a contract violation regardless of cause. `preexec_fn`
    # closes fd 0 in the child after fork, before exec, mirroring `<&-`.
    env = dict(os.environ)
    for var in _ENV_VARS_TO_CLEAR:
        env.pop(var, None)
    env["REN_WIKI_ROOT"] = str(wiki_root_path)

    result = subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
        preexec_fn=lambda: os.close(0),
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert _page_reads() == []


def test_non_read_tool_name_ignored(wiki_root_path):
    # Defense-in-depth: the hook double-checks tool_name itself even though
    # hooks.json's matcher already scopes it to "Read".
    target = wiki_root_path / "projects" / "p" / "x.md"
    target.parent.mkdir(parents=True)
    target.write_text("hello\n", encoding="utf-8")

    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(target)},
        "cwd": str(wiki_root_path),
        "session_id": "sess-1",
    }
    result = _run_hook(payload, wiki_root_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert _page_reads() == []


def test_missing_deps_exit_zero(wiki_root_path, tmp_path):
    # Real (non-monkeypatched) repro: point CLAUDE_PLUGIN_ROOT at a directory
    # with no `lib` package, so `from lib import ren_paths` genuinely raises
    # ImportError inside the subprocess — same failure shape a broken/partial
    # install would produce.
    target = wiki_root_path / "projects" / "p" / "x.md"
    target.parent.mkdir(parents=True)
    target.write_text("hello\n", encoding="utf-8")

    bogus_root = tmp_path / "bogus-plugin-root"
    bogus_root.mkdir()

    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(target)},
        "cwd": str(wiki_root_path),
        "session_id": "sess-1",
    }
    result = _run_hook(payload, wiki_root_path, extra_env={"CLAUDE_PLUGIN_ROOT": str(bogus_root)})

    assert result.returncode == 0
    assert result.stdout == ""
    assert "ren-read-tracker" in result.stderr
    assert _page_reads() == []


# =============================================================================
# latency gate (0.5.5 Task 5 plan requirement) — Hazar's fallback decision
# (drop read events entirely) hangs on this number, so it's asserted AND
# printed for the task report.
# =============================================================================


def test_latency_mean_invocation_under_bound(wiki_root_path):
    payload = json.dumps(
        {
            "tool_name": "Read",
            "tool_input": {"file_path": "/etc/hostname"},
            "cwd": str(wiki_root_path),
            "session_id": "sess-1",
        }
    )
    env = dict(os.environ)
    for var in _ENV_VARS_TO_CLEAR:
        env.pop(var, None)
    env["REN_WIKI_ROOT"] = str(wiki_root_path)

    runs = 20
    start = time.perf_counter()
    for _ in range(runs):
        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )
        assert result.returncode == 0
    elapsed = time.perf_counter() - start

    mean_ms = (elapsed / runs) * 1000
    print(f"\nread_tracker mean invocation latency: {mean_ms:.2f}ms over {runs} runs")
    # Generous CI-safe bound (task brief §Step 4): each invocation is a fresh
    # `python3` process (interpreter startup dominates), not the hot path a
    # tighter bound would target.
    assert mean_ms < 300, f"mean invocation latency {mean_ms:.2f}ms exceeds 300ms bound"
