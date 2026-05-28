"""Tests for hooks/wake-up/verify/collect.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


# Import collect.py by file path (it's a script, not a package)
_COLLECT_PATH = Path(__file__).resolve().parents[1] / "collect.py"
_spec = importlib.util.spec_from_file_location("collect", _COLLECT_PATH)
_collect = importlib.util.module_from_spec(_spec)
sys.modules["collect"] = _collect
_spec.loader.exec_module(_collect)

UsageRecord = _collect.UsageRecord
parse_probe_filename = _collect.parse_probe_filename
extract_usage_records = _collect.extract_usage_records
collect_directory = _collect.collect_directory
write_csv = _collect.write_csv


# ---------------------------------------------------------------------------
# parse_probe_filename
# ---------------------------------------------------------------------------


class TestParseFilename:
    def test_canonical_format(self):
        result = parse_probe_filename("probe-A-1-2026-05-28T20-30-00Z.jsonl")
        assert result is not None
        arm, idx, ts = result
        assert arm == "A"
        assert idx == 1
        assert ts.startswith("2026-")

    def test_arm_c_session_42(self):
        result = parse_probe_filename("probe-C-42-2026-12-31T23-59-59Z.jsonl")
        assert result is not None
        arm, idx, ts = result
        assert arm == "C"
        assert idx == 42

    def test_unrecognized_returns_none(self):
        assert parse_probe_filename("random-file.txt") is None
        assert parse_probe_filename("probe-X-1-bad.jsonl") is None  # arm X not allowed
        assert parse_probe_filename("probe-A-1.jsonl") is None  # missing timestamp


# ---------------------------------------------------------------------------
# extract_usage_records
# ---------------------------------------------------------------------------


def _make_jsonl(tmp_path: Path, events: list[dict]) -> Path:
    """Helper: write events to a probe-style JSONL file."""
    path = tmp_path / "probe-A-1-2026-05-28T20-30-00Z.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")
    return path


class TestExtractUsageRecords:
    def test_top_level_usage(self, tmp_path: Path):
        events = [
            {"type": "result", "model": "claude-sonnet-4-6", "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 800,
            }},
            {"type": "result", "model": "claude-sonnet-4-6", "usage": {
                "input_tokens": 20,
                "output_tokens": 30,
                "cache_read_input_tokens": 800,
                "cache_creation_input_tokens": 0,
            }},
        ]
        path = _make_jsonl(tmp_path, events)
        records = extract_usage_records(path, arm="A", session_index=1, timestamp="2026-05-28T20-30-00Z")

        assert len(records) == 2
        # Turn 1: cache_creation dominant (warm-up)
        assert records[0].turn == 1
        assert records[0].cache_creation == 800
        assert records[0].cache_read == 0
        # Turn 2: cache_read dominant (warm cache)
        assert records[1].turn == 2
        assert records[1].cache_read == 800

    def test_nested_message_usage(self, tmp_path: Path):
        """Usage may appear under message.usage for streaming events."""
        events = [
            {"type": "assistant", "message": {
                "model": "claude-sonnet-4-6",
                "usage": {
                    "input_tokens": 50,
                    "output_tokens": 100,
                    "cache_read_input_tokens": 5000,
                    "cache_creation_input_tokens": 0,
                },
            }},
        ]
        path = _make_jsonl(tmp_path, events)
        records = extract_usage_records(path, arm="B", session_index=2, timestamp="t")

        assert len(records) == 1
        assert records[0].cache_read == 5000
        assert records[0].model == "claude-sonnet-4-6"

    def test_no_usage_skipped(self, tmp_path: Path):
        """Events without usage data don't produce records."""
        events = [
            {"type": "system", "subtype": "init"},
            {"type": "hook", "event": "SessionStart"},
            {"type": "result", "usage": {
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
            }},  # all zeros → warm-up event, skipped
        ]
        path = _make_jsonl(tmp_path, events)
        records = extract_usage_records(path, arm="A", session_index=1, timestamp="t")
        assert records == []

    def test_malformed_json_lines_skipped(self, tmp_path: Path):
        """Lines that fail JSON parse are skipped (graceful degradation)."""
        path = tmp_path / "probe-A-1-t.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            fh.write("not json\n")
            fh.write(json.dumps({"type": "result", "usage": {
                "input_tokens": 1, "output_tokens": 1,
                "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0,
            }}) + "\n")
            fh.write("\n")  # empty line
            fh.write("also not json\n")
        records = extract_usage_records(path, arm="A", session_index=1, timestamp="t")
        assert len(records) == 1
        assert records[0].cache_read == 100

    def test_missing_file_returns_empty(self, tmp_path: Path):
        records = extract_usage_records(
            tmp_path / "missing.jsonl",
            arm="A", session_index=1, timestamp="t",
        )
        assert records == []


# ---------------------------------------------------------------------------
# collect_directory
# ---------------------------------------------------------------------------


class TestCollectDirectory:
    def test_walks_canonical_files(self, tmp_path: Path):
        # Write probe-A and probe-B files
        for arm in ("A", "B"):
            path = tmp_path / f"probe-{arm}-1-2026-05-28T20-30-00Z.jsonl"
            with path.open("w", encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "result", "usage": {
                    "input_tokens": 10, "output_tokens": 5,
                    "cache_read_input_tokens": 500, "cache_creation_input_tokens": 0,
                }}) + "\n")

        records = collect_directory(tmp_path)
        arms = sorted({r.arm for r in records})
        assert arms == ["A", "B"]

    def test_skips_non_conforming_files(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("not a probe file")
        (tmp_path / "random.jsonl").write_text(json.dumps({"type": "x"}) + "\n")
        records = collect_directory(tmp_path)
        assert records == []

    def test_missing_dir_returns_empty(self, tmp_path: Path):
        records = collect_directory(tmp_path / "missing")
        assert records == []


# ---------------------------------------------------------------------------
# write_csv
# ---------------------------------------------------------------------------


class TestWriteCsv:
    def test_writes_canonical_columns(self, tmp_path: Path):
        records = [
            UsageRecord(
                session_id="A-1-t", arm="A", session_index=1, timestamp="t",
                turn=1, model="claude-sonnet-4-6",
                cache_read=0, cache_creation=800, input_tokens=10, output_tokens=5,
            ),
        ]
        out = tmp_path / "out.csv"
        write_csv(records, out)

        with out.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["arm"] == "A"
        assert rows[0]["cache_creation"] == "800"
        assert rows[0]["cache_read"] == "0"
        # Canonical column order
        assert reader.fieldnames == [
            "session_id", "arm", "session_index", "timestamp", "turn",
            "model", "cache_read", "cache_creation", "input_tokens", "output_tokens",
        ]

    def test_empty_records_writes_header_only(self, tmp_path: Path):
        out = tmp_path / "empty.csv"
        write_csv([], out)
        content = out.read_text(encoding="utf-8")
        assert content.startswith("session_id,arm,session_index")
        # Just the header row + nothing else
        assert content.count("\n") == 1
