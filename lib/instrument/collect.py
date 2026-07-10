"""
lib.instrument.collect — instrumentation collectors with ground truth
(Task 3.1, RenOS 0.2 Phase 3).

Spec §3.9 "Instrumentation with ground truth" + §2's success bar: "if 0.2
ships and the pillars are still estimates, 0.2 failed." This module is where
every measured number in the framework's exit-criteria report ultimately
comes from — token & cache accounting, injected-context size, retrieval
hit-rate inputs, per-capability token use, classifier-eval events. Two
concerns:

  1. `record`/`read` — a generic append-only metrics log, one JSON line per
     event, rotated by calendar month at
     `ren_paths.state_dir()/"metrics"/<YYYY-MM>.jsonl`. Every other collector
     in the framework (wake-up hook, wrap gate, retrieval-eval harness) calls
     `record()` with one of the canonical `KIND_*` constants below; nothing
     invents its own ad-hoc metrics file.

  2. `harvest_session_usage` — ground truth for the cache-preservation
     experiment (exit criterion 1): parses ONE Claude Code session transcript
     JSONL (the files under `~/.claude/projects/<encoded-cwd>/*.jsonl`) and
     sums the real `cache_read_input_tokens` / `cache_creation_input_tokens`
     / `input_tokens` / `output_tokens` fields the harness already recorded —
     never an LLM self-report of its own cache behavior.

Real transcript shape (found under `~/.claude/projects/`, read-only, no
transcript CONTENT copied into this repo — see
`tests/fixtures/transcript_usage.jsonl` for a synthetic fixture with the same
structure): each line is a JSON object with top-level `sessionId`, `type`,
`timestamp`, and (for assistant turns) a `message` object containing a
`usage` block:

    {"sessionId": "...", "type": "assistant", "timestamp": "...",
     "message": {"role": "assistant", "content": [...], "model": "...",
                 "usage": {"input_tokens": 6, "cache_creation_input_tokens": 30606,
                           "cache_read_input_tokens": 0, "output_tokens": 293,
                           "server_tool_use": {...}, "cache_creation": {...},
                           "service_tier": "standard", "iterations": [...]}}}

Not every line is an assistant turn (donor's `skills/insights/scripts/collect.py`
walks the same transcript family and confirms this) — `user`, `attachment`,
`queue-operation`, and other line types appear interleaved and carry no
`usage` block. This module borrows that same tolerant, line-by-line,
skip-on-malformed discovery/parse discipline; it does NOT borrow the
donor script's topic/keyword extraction machinery (that's retrospective's
concern, not instrumentation's).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lib import ren_paths

METRICS_DIRNAME = "metrics"

# Canonical metric kinds — downstream phases (wake-up hook, wrap gate,
# retrieval-eval harness, doctor) import these rather than hardcoding strings.
KIND_INJECTED_BYTES = "injected_bytes"
KIND_CACHE_READ = "cache_read_tokens"
KIND_L3_FETCH = "l3_fetch"
KIND_WAKEUP_SURFACE = "wakeup_surface"
KIND_CAPABILITY_TOKENS = "capability_tokens"
KIND_CODEMAP_TOKENS = "codemap_tokens"
KIND_CLASSIFIER_EVENT = "classifier_event"
KIND_JUDGE_EVENT = "judge_event"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _metrics_dir() -> Path:
    d = ren_paths.state_dir() / METRICS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _month_file(ts: str) -> Path:
    """Month-file path for timestamp `ts` (first 7 chars, "YYYY-MM")."""
    month = ts[:7]
    return _metrics_dir() / f"{month}.jsonl"


def record(kind: str, data: dict) -> None:
    """Append one metric line: `{"ts": <ISO-8601 UTC>, "kind": kind, **data}`.

    Written to the calendar-month file the current timestamp falls in
    (`metrics/<YYYY-MM>.jsonl`), so a long-running framework install
    naturally rotates its metrics log without any explicit prune step.
    `data` must be JSON-serializable; ordinary dicts/lists/str/int/float/
    bool/None all round-trip fine.
    """
    ts = _now_iso()
    line = {"ts": ts, "kind": kind, **data}
    path = _month_file(ts)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def read(kind: str | None = None, since: str | None = None) -> list[dict]:
    """Return metric lines across all month files, oldest-first.

    Month files sort lexicographically in chronological order
    ("2026-01.jsonl" < "2026-02.jsonl"), and each file is itself
    append-ordered, so a plain sorted-glob + in-order read is sufficient —
    no explicit timestamp sort needed. Optionally filter to a single `kind`
    and/or entries with `ts >= since` (ISO-8601 string comparison, which is
    correct for same-format zero-padded UTC timestamps).
    """
    out: list[dict] = []
    for path in sorted(_metrics_dir().glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if kind is not None and entry.get("kind") != kind:
                continue
            if since is not None and entry.get("ts", "") < since:
                continue
            out.append(entry)
    return out


def harvest_session_usage(transcript_path: Path) -> dict:
    """Parse ONE Claude Code session transcript JSONL and sum its real usage.

    Returns `{"session": <sessionId or filename-stem>, "cache_read_input_tokens",
    "cache_creation_input_tokens", "input_tokens", "output_tokens", "turns"}`,
    summed across every assistant-message line that carries a `usage` block.
    `turns` counts those usage-carrying assistant messages.

    Tolerant by design (same discipline as the donor's transcript walker):
    a malformed JSON line, a non-dict line, a non-assistant line, or an
    assistant line with no `usage` block is skipped, never raised on. The
    session id is taken from the first line (of any type) that carries a
    `sessionId` string; if none do, falls back to the transcript file's stem.
    """
    transcript_path = Path(transcript_path)
    session_id: str | None = None
    cache_read = 0
    cache_creation = 0
    input_tokens = 0
    output_tokens = 0
    turns = 0

    with transcript_path.open("r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue

            if session_id is None:
                sid = obj.get("sessionId")
                if isinstance(sid, str) and sid:
                    session_id = sid

            if obj.get("type") != "assistant":
                continue
            message = obj.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue

            cache_read += int(usage.get("cache_read_input_tokens", 0) or 0)
            cache_creation += int(usage.get("cache_creation_input_tokens", 0) or 0)
            input_tokens += int(usage.get("input_tokens", 0) or 0)
            output_tokens += int(usage.get("output_tokens", 0) or 0)
            turns += 1

    return {
        "session": session_id or transcript_path.stem,
        "cache_read_input_tokens": cache_read,
        "cache_creation_input_tokens": cache_creation,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "turns": turns,
    }


__all__ = [
    "KIND_INJECTED_BYTES",
    "KIND_CACHE_READ",
    "KIND_L3_FETCH",
    "KIND_WAKEUP_SURFACE",
    "KIND_CAPABILITY_TOKENS",
    "KIND_CODEMAP_TOKENS",
    "KIND_CLASSIFIER_EVENT",
    "KIND_JUDGE_EVENT",
    "record",
    "read",
    "harvest_session_usage",
]
