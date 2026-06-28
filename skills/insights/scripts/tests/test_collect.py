"""Hermetic tests for skills/insights/scripts/collect.py.

Every test seeds a throwaway temp ~/.claude tree (crafted *.jsonl + *.tmp),
runs the read-only collector against it, and asserts:
  - it summarizes the crafted sources (project / tools / topics / errors),
  - malformed JSONL lines are skipped (never fatal),
  - --days filters by file mtime,
  - --project filters by project,
  - an empty window is tolerated,
  - and the run writes NOTHING to disk (load-bearing read-only invariant).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Import the collector module directly from the sibling scripts/ dir.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import collect  # noqa: E402  (path inserted above)

REF_NOW = 1_700_000_000.0  # fixed wall-clock for deterministic --days tests
DAY = collect.SECONDS_PER_DAY


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _rec(rtype: str, **kw) -> dict:
    base = {"type": rtype, "sessionId": kw.pop("sid", "sess-1")}
    base.update(kw)
    return base


def _user_text(text: str, sid: str = "sess-1", **meta) -> dict:
    return _rec("user", sid=sid, message={"role": "user", "content": text}, **meta)


def _assistant(blocks: list, sid: str = "sess-1", **meta) -> dict:
    return _rec("assistant", sid=sid, message={"role": "assistant", "content": blocks}, **meta)


def _tool_result(is_error: bool, text: str = "", sid: str = "sess-1") -> dict:
    return _rec(
        "user",
        sid=sid,
        message={
            "role": "user",
            "content": [{"type": "tool_result", "is_error": is_error, "content": text}],
        },
    )


def write_jsonl(path: Path, lines: list) -> None:
    """Write records as JSONL. A plain str entry is written verbatim (used to
    inject malformed lines); a dict is json-encoded."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    for item in lines:
        out.append(item if isinstance(item, str) else json.dumps(item))
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def seed_claude_home(tmp_path: Path) -> Path:
    """Build a representative ~/.claude tree and return the .claude dir."""
    claude = tmp_path / ".claude"
    proj_sf = claude / "projects" / "-home-hsozer-Dev-startup-framework"
    proj_side = claude / "projects" / "-home-hsozer-Dev-sidecar"

    # --- startup-framework transcript: valid records + malformed lines ---
    sf_lines = [
        _rec(
            "user",
            sid="sf-aaaa",
            cwd="/home/hsozer/Dev/startup-framework",
            gitBranch="fix/v1.0-preship-blockers",
            version="2.1.150",
            timestamp="2026-05-30T08:00:00Z",
            message={"role": "user", "content": "Help me debug the postgres auth migration error"},
        ),
        "{ this is not valid json",          # malformed — must be skipped
        "garbage line with no braces",        # malformed — must be skipped
        "",                                    # blank — ignored
        _assistant(
            [
                {"type": "text", "text": "Looking at the postgres migration now."},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/x"}},
                {"type": "tool_use", "name": "Edit", "input": {}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "psql"}},
            ],
            sid="sf-aaaa",
            timestamp="2026-05-30T08:01:00Z",
        ),
        _tool_result(True, "psql: error: connection failed", sid="sf-aaaa"),
        _assistant(
            [{"type": "tool_use", "name": "Bash", "input": {"command": "psql retry"}}],
            sid="sf-aaaa",
            timestamp="2026-05-30T08:02:00Z",
        ),
        _tool_result(False, "ok", sid="sf-aaaa"),
        '{"type": "user", "message": 12345}',  # well-formed JSON, odd shape — tolerated
    ]
    write_jsonl(proj_sf / "sf-aaaa.jsonl", sf_lines)

    # --- sidecar transcript: clean, no errors ---
    side_lines = [
        _rec(
            "user",
            sid="side-bbbb",
            cwd="/home/hsozer/Dev/sidecar",
            gitBranch="main",
            version="2.1.150",
            timestamp="2026-05-29T10:00:00Z",
            message={"role": "user", "content": "Add onboarding screen styling polish"},
        ),
        _assistant(
            [
                {"type": "text", "text": "Adding the onboarding styling."},
                {"type": "tool_use", "name": "Edit", "input": {}},
                {"type": "tool_use", "name": "Edit", "input": {}},
            ],
            sid="side-bbbb",
            timestamp="2026-05-29T10:05:00Z",
        ),
    ]
    write_jsonl(proj_side / "side-bbbb.jsonl", side_lines)

    # --- narrative save-session summary ---
    sd = claude / "session-data"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "2026-05-30-startup-framework-session.tmp").write_text(
        "# Session: 2026-05-30\n"
        "**Date:** 2026-05-30\n"
        "**Project:** startup-framework\n"
        "**Branch:** fix/v1.0-preship-blockers\n"
        "---\n"
        "Removed the activity feed module and extracted lib/sf_paths.\n"
        "Shipped the deterministic classifier for sf-wrap.\n",
        encoding="utf-8",
    )
    return claude


def snapshot(root: Path) -> dict[str, tuple[int, float, str]]:
    """Map every file under root → (size, mtime, sha256). Used to prove the
    collector mutates nothing."""
    snap: dict[str, tuple[int, float, str]] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            st = p.stat()
            snap[str(p.relative_to(root))] = (
                st.st_size,
                st.st_mtime,
                hashlib.sha256(data).hexdigest(),
            )
    return snap


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestResolveClaudeDir:
    def test_explicit_arg_wins(self, tmp_path):
        got = collect.resolve_claude_dir(str(tmp_path / "x"))
        assert got == tmp_path / "x"

    def test_env_var_used(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
        assert collect.resolve_claude_dir(None) == tmp_path / "cfg"

    def test_home_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        assert collect.resolve_claude_dir(None) == tmp_path / ".claude"

    def test_decode_project_dir_is_lossy_best_effort(self):
        # Decoding is documented-lossy: '-' maps to '/' for both real
        # separators and literal dashes, so 'startup-framework' becomes
        # 'startup/framework'. The function is a hint only — accurate project
        # names come from the record-level `cwd` field, not this decode.
        assert (
            collect.decode_project_dir("-home-hsozer-Dev-startup-framework")
            == "/home/hsozer/Dev/startup/framework"
        )


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------


class TestSummarize:
    def test_extracts_project_tools_errors_topics(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        data = collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)

        by_project = {s.project: s for s in data.sessions}
        assert "startup-framework" in by_project
        assert "sidecar" in by_project

        sf = by_project["startup-framework"]
        # tools tallied from assistant tool_use blocks
        assert sf.tool_counts["Bash"] == 2
        assert sf.tool_counts["Edit"] == 1
        assert sf.tool_counts["Read"] == 1
        # one tool_result with is_error true
        assert sf.error_results == 1
        # error phrases scanned from user text + result text
        assert sf.error_phrase_hits >= 1
        # Bash errored and was used >1 → retry suspected
        assert sf.retry_suspected is True
        # topics extracted from text (stopwords stripped)
        assert "postgres" in sf.topic_counts
        assert "the" not in sf.topic_counts
        # metadata captured
        assert sf.branch == "fix/v1.0-preship-blockers"
        assert "2.1.150" in sf.versions

    def test_render_block_has_markers(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        out = collect.render(collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW))
        assert collect.DATA_BLOCK_HEADER in out
        assert collect.DATA_BLOCK_FOOTER in out
        assert "sessions_found: 2" in out
        assert "## AGGREGATE" in out
        assert "## SESSIONS" in out
        assert "startup-framework" in out
        assert "sidecar" in out
        # narrative summary surfaced
        assert "## SESSION_SUMMARIES" in out

    def test_precise_retry_via_tool_use_id(self, tmp_path):
        # When tool_use carries an id and the errored tool_result references it
        # via tool_use_id, the errored tool is tied precisely.
        claude = tmp_path / ".claude"
        proj = claude / "projects" / "-home-hsozer-Dev-app"
        lines = [
            _rec("user", sid="t", cwd="/home/hsozer/Dev/app",
                 message={"role": "user", "content": "run the build"}),
            _assistant(
                [{"type": "tool_use", "id": "tu_1", "name": "Bash", "input": {}}],
                sid="t",
            ),
            _rec("user", sid="t", message={"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "is_error": True,
                 "content": "build failed"}]}),
            _assistant(
                [{"type": "tool_use", "id": "tu_2", "name": "Bash", "input": {}}],
                sid="t",
            ),
        ]
        write_jsonl(proj / "t.jsonl", lines)
        data = collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)
        sf = data.sessions[0]
        assert "Bash" in sf.tools_with_errors
        assert sf.tool_counts["Bash"] == 2
        assert sf.retry_suspected is True

    def test_summary_tmp_parsed(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        data = collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)
        assert len(data.summaries) == 1
        doc = data.summaries[0]
        assert doc.project == "startup-framework"
        assert doc.branch == "fix/v1.0-preship-blockers"
        assert "activity feed" in doc.snippet.lower()


# ---------------------------------------------------------------------------
# Malformed-line tolerance
# ---------------------------------------------------------------------------


class TestMalformedTolerance:
    def test_malformed_lines_skipped_not_fatal(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        data = collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)
        # Despite two malformed lines + one odd-shaped record, the valid
        # records still produced a populated session.
        sf = next(s for s in data.sessions if s.project == "startup-framework")
        assert sf.message_count >= 3
        assert sum(sf.tool_counts.values()) == 4

    def test_all_malformed_file_yields_no_session(self, tmp_path):
        claude = tmp_path / ".claude"
        proj = claude / "projects" / "-home-hsozer-Dev-junk"
        write_jsonl(proj / "junk.jsonl", ["not json", "{still not", "}{"])
        data = collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)
        assert data.transcripts_scanned == 1
        assert data.sessions_found == 0  # nothing valid → no session, no crash


# ---------------------------------------------------------------------------
# --days mtime filtering
# ---------------------------------------------------------------------------


class TestDaysFilter:
    def _age_all(self, claude: Path, age_days: float) -> None:
        target = REF_NOW - age_days * DAY
        for p in claude.rglob("*"):
            if p.is_file():
                os.utime(p, (target, target))

    def test_old_files_excluded(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        self._age_all(claude, 40)  # everything is 40 days old
        data = collect.collect(days=30, claude_dir=str(claude), now=REF_NOW)
        assert data.sessions_found == 0
        assert data.transcripts_scanned == 0
        assert data.summaries_scanned == 0

    def test_recent_files_included(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        self._age_all(claude, 40)
        data = collect.collect(days=60, claude_dir=str(claude), now=REF_NOW)
        assert data.sessions_found == 2
        assert data.summaries_scanned == 1

    def test_window_days_reported(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        out = collect.render(collect.collect(days=7, claude_dir=str(claude), now=REF_NOW))
        assert "window_days: 7" in out


# ---------------------------------------------------------------------------
# --project filtering
# ---------------------------------------------------------------------------


class TestProjectFilter:
    def test_filters_to_matching_project(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        data = collect.collect(
            days=3650, project="sidecar", claude_dir=str(claude), now=REF_NOW
        )
        assert data.sessions_found == 1
        assert data.sessions[0].project == "sidecar"

    def test_filter_case_insensitive_substring(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        data = collect.collect(
            days=3650, project="STARTUP", claude_dir=str(claude), now=REF_NOW
        )
        assert data.sessions_found == 1
        assert data.sessions[0].project == "startup-framework"

    def test_nonmatching_filter_empty(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        data = collect.collect(
            days=3650, project="nonexistent-xyz", claude_dir=str(claude), now=REF_NOW
        )
        assert data.sessions_found == 0


# ---------------------------------------------------------------------------
# Empty-window tolerance
# ---------------------------------------------------------------------------


class TestEmptyWindow:
    def test_no_sources_renders_block(self, tmp_path):
        claude = tmp_path / ".claude"  # nothing seeded
        out = collect.render(collect.collect(days=30, claude_dir=str(claude), now=REF_NOW))
        assert "sessions_found: 0" in out
        assert "No local sessions found" in out
        assert collect.DATA_BLOCK_HEADER in out

    def test_empty_window_does_not_raise(self, tmp_path):
        claude = tmp_path / ".claude"
        # Should not raise even with totally absent dirs.
        data = collect.collect(days=1, claude_dir=str(claude), now=REF_NOW)
        assert data.sessions_found == 0


# ---------------------------------------------------------------------------
# Read-only invariant (LOAD-BEARING) — the collector writes NOTHING
# ---------------------------------------------------------------------------


class TestReadOnlyInvariant:
    def test_collect_function_writes_nothing(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        before = snapshot(tmp_path)
        collect.render(collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW))
        after = snapshot(tmp_path)
        assert before == after

    def test_subprocess_writes_nothing_and_emits_to_stdout(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        before = snapshot(tmp_path)
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS_DIR / "collect.py"),
                "--days",
                "3650",
                "--claude-dir",
                str(claude),
            ],
            capture_output=True,
            text=True,
        )
        after = snapshot(tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert collect.DATA_BLOCK_HEADER in proc.stdout
        assert "sessions_found: 2" in proc.stdout
        # Nothing created/modified/deleted anywhere under the seeded HOME.
        assert before == after

    def test_subprocess_no_files_created(self, tmp_path):
        claude = seed_claude_home(tmp_path)
        files_before = {str(p) for p in tmp_path.rglob("*") if p.is_file()}
        subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "collect.py"),
             "--claude-dir", str(claude), "--days", "3650"],
            capture_output=True, text=True, check=True,
        )
        files_after = {str(p) for p in tmp_path.rglob("*") if p.is_file()}
        assert files_before == files_after


# ---------------------------------------------------------------------------
# Project fallback — no-cwd path must use encoded dir name, not lossy decode
# ---------------------------------------------------------------------------


class TestProjectFallbackNoCwd:
    def test_no_cwd_prefers_encoded_dir_over_lossy_decode(self, tmp_path):
        """When a record has neither project nor cwd, the fallback must NOT use the
        lossy decode (which collapses '-' to '/', turning 'my-app' into 'app').
        It should surface the unambiguous encoded dir name instead."""
        claude = tmp_path / ".claude"
        proj = claude / "projects" / "-home-h-Dev-my-app"
        write_jsonl(proj / "s.jsonl", [
            _rec("user", sid="s", message={"role": "user", "content": "hi build"}),
            _assistant([{"type": "text", "text": "ok"}], sid="s"),
        ])
        data = collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)
        assert len(data.sessions) == 1
        assert data.sessions[0].project != "app", "still using lossy decode → wrong basename"
        assert data.sessions[0].project == "-home-h-Dev-my-app"


# ---------------------------------------------------------------------------
# Privacy: kickoff field dropped — verbatim first message must not reach LLM
# ---------------------------------------------------------------------------


class TestKickoffSecretSafety:
    SECRET = "sk-ant-api03-FAKESECRET-DO-NOT-EMIT-0123456789"
    # Structurally different sentinel: a 20-char AWS-style key with NO hyphens,
    # so a length cap alone won't catch it — must be caught by shape/prefix.
    AWS_SECRET = "AKIAIOSFODNN7EXAMPLE"

    def _seed_secret_first_message(self, tmp_path: Path) -> Path:
        claude = tmp_path / ".claude"
        proj = claude / "projects" / "-home-hsozer-Dev-app"
        lines = [
            _rec(
                "user",
                sid="s",
                cwd="/home/hsozer/Dev/app",
                message={
                    "role": "user",
                    "content": (
                        f"Use my key {self.SECRET} and {self.AWS_SECRET} "
                        f"to call the API and debug this"
                    ),
                },
            ),
            _assistant([{"type": "tool_use", "name": "Bash", "input": {}}], sid="s"),
        ]
        write_jsonl(proj / "s.jsonl", lines)
        return claude

    def test_secret_in_first_message_absent_from_output(self, tmp_path):
        claude = self._seed_secret_first_message(tmp_path)
        out = collect.render(
            collect.collect(days=3650, claude_dir=str(claude), now=REF_NOW)
        )
        # Case-insensitive: _scan_topics lowercases tokens, so the leaked secret
        # would appear lowercased — a case-sensitive check is a false green.
        assert self.SECRET.lower() not in out      # long sk- key must not reach the LLM-fed block
        assert self.AWS_SECRET.lower() not in out  # AWS-shaped key (no length cap can catch it)
        assert "kickoff" not in out                # the verbatim-echo line is gone entirely

    def test_session_facts_has_no_kickoff_field(self, tmp_path):
        assert not hasattr(collect.SessionFacts(), "kickoff")
