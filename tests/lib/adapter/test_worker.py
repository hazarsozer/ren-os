"""
tests.lib.adapter.test_worker — TDD for `lib.adapter.worker.parse_worker_json`
(Task 12b). Worker subagents (ingest-project knowledge drafting, retrospective
enrichment) return fenced ```json blocks despite raw-JSON-only instructions;
this is the one shared parser every call site should use instead of ad-hoc
fence-stripping.
"""

from __future__ import annotations

import pytest

from lib.adapter.worker import WorkerOutputError, parse_worker_json


def test_parses_clean_json_object():
    assert parse_worker_json('{"a": 1}') == {"a": 1}


def test_parses_clean_json_array():
    assert parse_worker_json('[1, 2, 3]') == [1, 2, 3]


def test_strips_json_fence():
    raw = '```json\n{"a": 1}\n```'
    assert parse_worker_json(raw) == {"a": 1}


def test_strips_bare_fence():
    raw = '```\n{"a": 1}\n```'
    assert parse_worker_json(raw) == {"a": 1}


def test_strips_leading_prose_before_object():
    raw = 'Here is the result:\n{"a": 1}'
    assert parse_worker_json(raw) == {"a": 1}


def test_strips_leading_prose_before_array():
    raw = 'Sure, here you go:\n[1, 2, 3]'
    assert parse_worker_json(raw) == [1, 2, 3]


def test_strips_leading_prose_and_fence_together():
    raw = 'Here is the JSON:\n```json\n{"verdict": "durable"}\n```'
    assert parse_worker_json(raw) == {"verdict": "durable"}


def test_strips_trailing_prose_after_object():
    raw = '{"verdict": "durable", "reason": "because"}\nHope this helps!'
    assert parse_worker_json(raw) == {"verdict": "durable", "reason": "because"}


def test_strips_trailing_prose_after_array():
    raw = '[1, 2, 3]\nLet me know if you need anything else.'
    assert parse_worker_json(raw) == [1, 2, 3]


def test_invalid_json_raises_worker_output_error_with_raw_preserved():
    raw = "not json at all, no braces here"
    with pytest.raises(WorkerOutputError) as exc_info:
        parse_worker_json(raw)
    assert exc_info.value.raw == raw


def test_malformed_json_inside_fence_raises_with_raw_preserved():
    raw = '```json\n{"a": 1,}\n```'
    with pytest.raises(WorkerOutputError) as exc_info:
        parse_worker_json(raw)
    assert exc_info.value.raw == raw


def test_non_str_input_raises_worker_output_error():
    with pytest.raises(WorkerOutputError):
        parse_worker_json(None)  # type: ignore[arg-type]
