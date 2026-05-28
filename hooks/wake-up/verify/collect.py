"""
collect.py — Scrape per-turn usage metrics from probe.sh JSON-L outputs.

Per the ADR-008 cache-preservation verification plan (lifecycle plan §2):
walks a directory of `probe-<arm>-<session>-<ts>.jsonl` files emitted by
probe.sh, extracts per-turn `cache_read_input_tokens` / `cache_creation_input_tokens`
/ `input_tokens` / `output_tokens` from Claude Code's stream-json output, and
writes a normalized CSV.

The CSV columns are:
    session_id, arm, session_index, timestamp, turn, model,
    cache_read, cache_creation, input_tokens, output_tokens

Per team-lead's refinement: we extract metrics for BOTH turn 1 AND turn 2.
Cache benefit shows turn 2+ (turn 1 is cache CREATION; turn 2 demonstrates
the read-back).

Usage:
    python3 collect.py PROBE_OUTPUT_DIR OUTPUT_CSV
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# probe.sh names files like: probe-A-1-2026-05-28T20-30-00Z.jsonl
# We extract arm, session_index, timestamp from the filename for reproducibility.
_PROBE_FILENAME_RE = re.compile(
    r"^probe-(?P<arm>[A-C])-(?P<idx>\d+)-(?P<ts>[0-9T\-Z]+)\.jsonl$"
)


@dataclass(frozen=True)
class UsageRecord:
    """One row in the collected CSV — usage metrics from a single turn."""

    session_id: str
    arm: str               # "A" | "B" | "C"
    session_index: int
    timestamp: str         # ISO-format from filename
    turn: int              # 1-indexed turn number within the session
    model: str
    cache_read: int        # cache_read_input_tokens
    cache_creation: int    # cache_creation_input_tokens
    input_tokens: int
    output_tokens: int


def parse_probe_filename(filename: str) -> tuple[str, int, str] | None:
    """
    Extract (arm, session_index, timestamp) from a probe output filename.

    Returns None if the filename doesn't match the canonical pattern.
    """
    match = _PROBE_FILENAME_RE.match(filename)
    if not match:
        return None
    return match.group("arm"), int(match.group("idx")), match.group("ts")


def extract_usage_records(
    jsonl_path: Path,
    *,
    arm: str,
    session_index: int,
    timestamp: str,
) -> list[UsageRecord]:
    """
    Walk a single probe JSON-L file; emit one UsageRecord per turn with usage data.

    Claude Code stream-json emits events of multiple shapes. Usage objects appear
    in events with `type` == "result" (final per-call usage) and may also appear
    in nested message events. We extract from the first event-shape that yields
    well-formed usage; downstream stats only need the turn-level totals.

    Args:
        jsonl_path: Path to one probe-output JSONL file.
        arm: The experimental arm (A/B/C) from the filename.
        session_index: The session number within the batch.
        timestamp: ISO timestamp from the filename.

    Returns:
        List of UsageRecord (zero-or-more entries; one per detected turn).
    """
    records: list[UsageRecord] = []
    turn_counter = 0
    session_id = f"{arm}-{session_index}-{timestamp}"

    try:
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("skipping non-JSON line %d in %s", line_no, jsonl_path)
                    continue

                usage = _extract_usage_from_event(event)
                if usage is None:
                    continue

                turn_counter += 1
                records.append(
                    UsageRecord(
                        session_id=session_id,
                        arm=arm,
                        session_index=session_index,
                        timestamp=timestamp,
                        turn=turn_counter,
                        model=usage.get("model", "unknown"),
                        cache_read=int(usage.get("cache_read", 0)),
                        cache_creation=int(usage.get("cache_creation", 0)),
                        input_tokens=int(usage.get("input_tokens", 0)),
                        output_tokens=int(usage.get("output_tokens", 0)),
                    )
                )
    except OSError as exc:
        logger.warning("Could not read %s: %s", jsonl_path, exc)

    return records


def _extract_usage_from_event(event: dict) -> dict | None:
    """
    Normalize a stream-json event into a usage dict, or None if the event
    doesn't carry usage.

    Returns a dict with keys: cache_read, cache_creation, input_tokens,
    output_tokens, model (when available).
    """
    if not isinstance(event, dict):
        return None

    # Top-level usage (terminal `result` events)
    usage = event.get("usage")
    model = event.get("model", "")

    # Nested usage (inside message.usage for streaming events)
    if usage is None:
        message = event.get("message")
        if isinstance(message, dict):
            usage = message.get("usage")
            model = message.get("model", model)

    if not isinstance(usage, dict):
        return None

    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_creation = usage.get("cache_creation_input_tokens", 0)
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    # Skip events where usage exists but every field is zero — likely a
    # warm-up event, not a real turn.
    if cache_read == 0 and cache_creation == 0 and input_tokens == 0:
        return None

    return {
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
    }


def collect_directory(probe_dir: Path) -> list[UsageRecord]:
    """
    Walk a probe-output directory and aggregate UsageRecords from all files.

    Files not matching the canonical probe pattern are skipped (with a
    debug-level log line).
    """
    if not probe_dir.is_dir():
        logger.error("probe directory not found: %s", probe_dir)
        return []

    records: list[UsageRecord] = []
    for jsonl_path in sorted(probe_dir.glob("probe-*.jsonl")):
        parsed = parse_probe_filename(jsonl_path.name)
        if parsed is None:
            logger.debug("skipping non-conforming filename: %s", jsonl_path.name)
            continue
        arm, idx, ts = parsed
        records.extend(
            extract_usage_records(jsonl_path, arm=arm, session_index=idx, timestamp=ts)
        )
    return records


def write_csv(records: list[UsageRecord], output_path: Path) -> None:
    """Write the collected records to a CSV file."""
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "session_id", "arm", "session_index", "timestamp", "turn",
            "model", "cache_read", "cache_creation", "input_tokens", "output_tokens",
        ])
        for r in records:
            writer.writerow([
                r.session_id, r.arm, r.session_index, r.timestamp, r.turn,
                r.model, r.cache_read, r.cache_creation, r.input_tokens, r.output_tokens,
            ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect cache-preservation probe metrics into CSV.")
    parser.add_argument("probe_dir", type=Path, help="Directory containing probe-*.jsonl files")
    parser.add_argument("output_csv", type=Path, help="Output CSV path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    records = collect_directory(args.probe_dir)
    if not records:
        logger.warning("Collected zero usage records from %s", args.probe_dir)
        write_csv([], args.output_csv)
        return 0

    write_csv(records, args.output_csv)
    logger.info("Wrote %d records to %s", len(records), args.output_csv)

    # Quick summary
    by_arm: dict[str, int] = {}
    for r in records:
        by_arm[r.arm] = by_arm.get(r.arm, 0) + 1
    for arm in sorted(by_arm):
        logger.info("  arm=%s records=%d", arm, by_arm[arm])

    return 0


if __name__ == "__main__":
    sys.exit(main())
