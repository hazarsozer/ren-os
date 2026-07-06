"""
Tests for lib.instrument.collect — G18 instrumentation collectors with ground
truth (Task 3.1).

Two concerns under test:
  1. record/read — append-only metrics log rotated by calendar month.
  2. harvest_session_usage — sums REAL usage fields from one transcript JSONL
     (tests/fixtures/transcript_usage.jsonl — synthetic values/text, same
     structure as a real ~/.claude/projects/<encoded-cwd>/*.jsonl transcript).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/instrument/test_collect.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.instrument import collect
from lib.ren_paths import state_dir, wiki_root

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "transcript_usage.jsonl"


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def isolated_state(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    wiki_root().mkdir(parents=True, exist_ok=True)
    return tmp_path


# ------------------------------------------------------------ record / read


def test_record_read_round_trip(isolated_state):
    collect.record(collect.KIND_INJECTED_BYTES, {"bytes": 4096, "capability": "wake-up"})

    entries = collect.read()
    assert len(entries) == 1
    assert entries[0]["kind"] == collect.KIND_INJECTED_BYTES
    assert entries[0]["bytes"] == 4096
    assert entries[0]["capability"] == "wake-up"
    assert "ts" in entries[0]


def test_month_file_naming_and_rotation(isolated_state, monkeypatch):
    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-01-15T00:00:00Z")
    collect.record(collect.KIND_CACHE_READ, {"tokens": 100})

    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-02-01T00:00:00Z")
    collect.record(collect.KIND_CACHE_READ, {"tokens": 200})

    metrics_dir = state_dir() / "metrics"
    files = sorted(p.name for p in metrics_dir.glob("*.jsonl"))
    assert files == ["2026-01.jsonl", "2026-02.jsonl"]

    entries = collect.read(kind=collect.KIND_CACHE_READ)
    assert [e["tokens"] for e in entries] == [100, 200]  # oldest-first, merged across files


def test_read_filters_by_kind(isolated_state):
    collect.record(collect.KIND_INJECTED_BYTES, {"bytes": 1})
    collect.record(collect.KIND_CACHE_READ, {"tokens": 2})
    collect.record(collect.KIND_INJECTED_BYTES, {"bytes": 3})

    only_injected = collect.read(kind=collect.KIND_INJECTED_BYTES)
    assert len(only_injected) == 2
    assert all(e["kind"] == collect.KIND_INJECTED_BYTES for e in only_injected)


def test_read_filters_by_since(isolated_state, monkeypatch):
    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-01-01T00:00:00Z")
    collect.record(collect.KIND_L3_FETCH, {"n": 1})

    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-01-15T00:00:00Z")
    collect.record(collect.KIND_L3_FETCH, {"n": 2})

    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-01-31T00:00:00Z")
    collect.record(collect.KIND_L3_FETCH, {"n": 3})

    entries = collect.read(since="2026-01-10T00:00:00Z")
    assert [e["n"] for e in entries] == [2, 3]


def test_read_combines_kind_and_since_filters(isolated_state, monkeypatch):
    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-01-01T00:00:00Z")
    collect.record(collect.KIND_L3_FETCH, {"n": 1})
    collect.record(collect.KIND_CACHE_READ, {"n": 1})

    monkeypatch.setattr(collect, "_now_iso", lambda: "2026-01-15T00:00:00Z")
    collect.record(collect.KIND_L3_FETCH, {"n": 2})

    entries = collect.read(kind=collect.KIND_L3_FETCH, since="2026-01-10T00:00:00Z")
    assert len(entries) == 1
    assert entries[0]["n"] == 2


def test_read_empty_when_no_metrics_dir_yet(isolated_state):
    assert collect.read() == []


def test_canonical_kind_constants_exist():
    assert collect.KIND_INJECTED_BYTES == "injected_bytes"
    assert collect.KIND_CACHE_READ == "cache_read_tokens"
    assert collect.KIND_L3_FETCH == "l3_fetch"
    assert collect.KIND_WAKEUP_SURFACE == "wakeup_surface"
    assert collect.KIND_CAPABILITY_TOKENS == "capability_tokens"
    assert collect.KIND_CODEMAP_TOKENS == "codemap_tokens"
    assert collect.KIND_CLASSIFIER_EVENT == "classifier_event"


def test_record_never_raises_on_unusual_but_serializable_data(isolated_state):
    collect.record(
        collect.KIND_CLASSIFIER_EVENT,
        {
            "nested": {"a": [1, 2, 3], "b": None, "c": True, "d": 3.14},
            "empty_list": [],
            "unicode": "héllo wörld — em dash —",
        },
    )

    entries = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    assert len(entries) == 1
    assert entries[0]["nested"]["c"] is True
    assert entries[0]["unicode"] == "héllo wörld — em dash —"


# ------------------------------------------------------- harvest_session_usage


def test_harvest_session_usage_returns_known_sums_from_fixture():
    result = collect.harvest_session_usage(FIXTURE_PATH)

    assert result["session"] == "test-session-fixture-001"
    assert result["input_tokens"] == 50
    assert result["cache_creation_input_tokens"] == 600
    assert result["cache_read_input_tokens"] == 3500
    assert result["output_tokens"] == 175
    assert result["turns"] == 4


def test_harvest_session_usage_falls_back_to_filename_stem_when_no_session_id(tmp_path):
    transcript = tmp_path / "no-session-id-here.jsonl"
    transcript.write_text(
        '{"type": "assistant", "message": {"usage": {"input_tokens": 1, "output_tokens": 1, '
        '"cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}}\n',
        encoding="utf-8",
    )

    result = collect.harvest_session_usage(transcript)
    assert result["session"] == "no-session-id-here"
    assert result["turns"] == 1


def test_harvest_session_usage_skips_malformed_and_foreign_lines_without_raising(tmp_path):
    transcript = tmp_path / "mixed.jsonl"
    transcript.write_text(
        "\n".join(
            [
                "not json at all {{{",
                '{"type": "user", "message": {"content": "hi"}}',
                '{"type": "queue-operation"}',
                '{"sessionId": "s1", "type": "assistant", "message": {"usage": {'
                '"input_tokens": 7, "output_tokens": 3, "cache_read_input_tokens": 0, '
                '"cache_creation_input_tokens": 0}}}',
                '{"sessionId": "s1", "type": "assistant", "message": {"no_usage_here": true}}',
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = collect.harvest_session_usage(transcript)
    assert result["session"] == "s1"
    assert result["input_tokens"] == 7
    assert result["output_tokens"] == 3
    assert result["turns"] == 1
