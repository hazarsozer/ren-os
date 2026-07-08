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


def _strip_trailing_prose(text: str) -> str:
    """Trim to the LAST closer matching the leading `{`/`[`, dropping any
    prose the worker appended after the JSON value (e.g. a chatty sign-off).
    Returns `text` unchanged if it doesn't start with `{`/`[`, or if no
    matching closer is found."""
    if text.startswith("{"):
        end = text.rfind("}")
    elif text.startswith("["):
        end = text.rfind("]")
    else:
        return text
    if end == -1:
        return text
    return text[: end + 1]


def parse_worker_json(raw: str) -> Any:
    """Parse a worker subagent's JSON output, tolerating a markdown fence
    and/or leading/trailing prose around the `{`/`[`...`}`/`]` value (e.g. a
    fenced block, a "here's the result:" preamble, or a chatty sign-off after
    the JSON). Note: non-`json`-tagged or oddly-tagged fences (e.g. ` ```js `)
    aren't specially recognized — only a bare ``` ``` ``` or ``` ```json ```
    fence is stripped; anything else falls through to the prose-stripping
    path. Raises `WorkerOutputError` (carrying `raw` unmodified) if the
    result still isn't valid JSON after both the untrimmed and
    trailing-trimmed attempts."""
    if not isinstance(raw, str):
        raise WorkerOutputError(
            f"worker output must be str, got {type(raw).__name__}", raw=raw
        )

    text = _strip_fence(raw.strip())
    text = _strip_leading_prose(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        trimmed = _strip_trailing_prose(text)
        if trimmed != text:
            try:
                return json.loads(trimmed)
            except json.JSONDecodeError:
                pass
        raise WorkerOutputError(f"worker output is not valid JSON: {exc}", raw=raw) from exc


__all__ = ["WorkerOutputError", "parse_worker_json"]
