"""
lib.adapter.worker — shared worker-output JSON parsing (Task 12b).

Worker subagents (ingest-project knowledge drafting, retrospective
enrichment, wrap's classifier gate) are instructed to return raw JSON only,
but in practice often wrap their answer in a ```json fence or prepend prose
before it. Every call site was stripping this ad hoc; `parse_worker_json` is
the one shared implementation everyone should use instead.
"""

from __future__ import annotations

import json
from typing import Any


class WorkerOutputError(Exception):
    """Raised when a worker's output can't be parsed as JSON. Carries the
    raw, unmodified text so the caller can log or surface it for debugging."""

    def __init__(self, message: str, raw: str) -> None:
        super().__init__(message)
        self.raw = raw


def _strip_fence(text: str) -> str:
    """Extract the contents of a ```json or ``` fence, wherever it appears
    (a worker may prepend prose before the fence). Returns `text` unchanged
    if no fence is found."""
    for fence in ("```json\n", "```\n"):
        if fence in text:
            start = text.index(fence) + len(fence)
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()
    return text


def _strip_leading_prose(text: str) -> str:
    """Slice from the first `{` or `[` to drop any prose the worker prepended
    before the JSON value. Returns `text` unchanged if neither is found."""
    first_obj = text.find("{")
    first_arr = text.find("[")
    candidates = [i for i in (first_obj, first_arr) if i != -1]
    if not candidates:
        return text
    return text[min(candidates):]


def parse_worker_json(raw: str) -> Any:
    """Parse a worker subagent's JSON output, tolerating a markdown fence
    and/or leading prose before the first `{`/`[`. Raises `WorkerOutputError`
    (carrying `raw` unmodified) if the result still isn't valid JSON."""
    if not isinstance(raw, str):
        raise WorkerOutputError(
            f"worker output must be str, got {type(raw).__name__}", raw=raw
        )

    text = _strip_fence(raw.strip())
    text = _strip_leading_prose(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise WorkerOutputError(f"worker output is not valid JSON: {exc}", raw=raw) from exc


__all__ = ["WorkerOutputError", "parse_worker_json"]
