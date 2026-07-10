"""
lib.suggestions — the 0.4.2 durable suggestion store (Task 14, "the
suggestion pipeline").

Suggestions are RARE AND HIGH-STAKES by design (spec §1.2): this store never
writes wiki pages, and it never applies a suggestion's payload — `decide` is
a pure state transition, application logic is a later task (Task 19).

Persistence is the state: one JSON file per suggestion at
`state_dir()/"suggestions"/<sid>.json`, same as `lib.memory.queue`.

The never-re-nag contract (mirrors the companions reconciler's doctrine,
`lib/companions/__init__.py`): a suggestion is offered iff it has no recorded
decision. Declines are durable — never re-nag. Decided fingerprints live in
an append-only ledger (`state_dir()/suggestions/decisions.jsonl`), written by
`decide()` alongside the entry file. `record` dedups a new spec's fingerprint
against the ledger UNION pending suggestions' fingerprints — it no longer
parses every entry file, so a later task can prune decided entry files
without breaking dedup.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ulid import ULID

from lib import ren_paths

_SUGGESTIONS_DIRNAME = "suggestions"
_PENDING = "pending"
_DECISIONS = ("accepted", "declined")
_EXPIRED = "expired"

DECIDED_RETENTION_DAYS = 90
PENDING_MAX_AGE_DAYS = 30


@dataclass(frozen=True)
class SuggestionSpec:
    producer: str          # "retrospective"|"promotion"|"doctrine"|"wiki-health"
    title: str             # one human line
    rationale: str         # "you did X in N of last M sessions"
    evidence: dict         # structured, producer-shaped
    kind: str              # "page_write" | "structured_action"
    payload: dict          # page_write: full Proposal kwargs; structured_action: {"action": ..., ...}
    fingerprint: str       # stable identity for durable-decline dedup
    # Dedup is fingerprint-EXACT by design (see `record`) — no normalization
    # or alias matching. Today both sides of a wiki-health pair come from
    # the same sweep's rel-path normalization, so alias divergence (e.g. two
    # different string forms for the same page) can't occur. Revisit if a
    # second producer starts emitting fingerprints from a different path
    # form for the same underlying page.


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _suggestions_dir() -> Path:
    d = ren_paths.state_dir() / _SUGGESTIONS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _suggestion_path(sid: str) -> Path:
    return _suggestions_dir() / f"{sid}.json"


def _ledger_path() -> Path:
    return _suggestions_dir() / "decisions.jsonl"


def _persist(entry: dict) -> None:
    """Atomic write: temp file + os.replace, so a crash mid-write never leaves
    a torn/partial suggestion file."""
    path = _suggestion_path(entry["sid"])
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load(sid: str) -> dict:
    path = _suggestion_path(sid)
    if not path.exists():
        raise KeyError(sid)
    return json.loads(path.read_text(encoding="utf-8"))


def all_suggestions() -> list[dict]:
    """Every suggestion regardless of status, in no particular order. One
    corrupted entry file must never take down whole-store listing —
    unparsable files are skipped with a stderr warning, same torn-file
    tolerance as `lib.memory.queue.all_entries`."""
    entries: list[dict] = []
    for path in _suggestions_dir().glob("*.json"):
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"ren suggestions: skipping unparsable entry file {path.name}: {exc}", file=sys.stderr)
    return entries


def get_suggestion(sid: str) -> dict:
    """Return the stored entry for `sid`. Raises KeyError if unknown."""
    return _load(sid)


def _append_ledger_line(line: dict) -> None:
    with _ledger_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def ledger_fingerprints() -> set[str]:
    """Fingerprints of every decided (accepted or declined) suggestion, read
    from the durable decision ledger. If the ledger file doesn't exist yet
    but decided entry files do (pre-0.5.0 store), backfill the ledger from
    them first. Unparsable ledger lines are skipped with a stderr warning,
    same torn-file tolerance as `all_suggestions`."""
    path = _ledger_path()
    if not path.exists():
        decided_entries = [e for e in all_suggestions() if e["status"] in _DECISIONS]
        for entry in decided_entries:
            _append_ledger_line({
                "fingerprint": entry["fingerprint"],
                "decision": entry["status"],
                "sid": entry["sid"],
                "ts": entry["decided_at"],
            })
        if not decided_entries:
            return set()

    fingerprints: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            fingerprints.add(json.loads(line)["fingerprint"])
        except (json.JSONDecodeError, TypeError, KeyError, ValueError) as exc:
            print(f"ren suggestions: skipping unparsable ledger line: {exc}", file=sys.stderr)
    return fingerprints


def record(spec: SuggestionSpec) -> dict | None:
    """Record `spec` as a new pending suggestion, unless its fingerprint is
    already pending or decided — in which case returns None (never re-nag)."""
    existing_fingerprints = ledger_fingerprints() | {e["fingerprint"] for e in pending_suggestions()}
    if spec.fingerprint in existing_fingerprints:
        return None

    entry = {
        "sid": f"s-{ULID()}",
        "ts": _now_iso(),
        **asdict(spec),
        "status": _PENDING,
        "decided_at": None,
    }
    _persist(entry)
    return entry


def pending_suggestions() -> list[dict]:
    """All suggestions with status=="pending", oldest first (sid is a ULID,
    so lexicographic sort == chronological order)."""
    entries = [e for e in all_suggestions() if e["status"] == _PENDING]
    entries.sort(key=lambda e: e["sid"])
    return entries


def decided_fingerprints() -> set[str]:
    """Fingerprints of every non-pending (accepted or declined) suggestion."""
    return ledger_fingerprints()


def decide(sid: str, decision: str) -> dict:
    """Transition `sid` to `decision` ("accepted" or "declined"). Pure state
    transition — does NOT apply the suggestion's payload; application is the
    caller's job (Task 19). Raises KeyError for an unknown sid, ValueError
    for an invalid decision OR if the entry is not currently "pending" —
    decided ("accepted"/"declined") and expired entries are immutable."""
    if decision not in _DECISIONS:
        raise ValueError(f"decision must be one of {_DECISIONS}, got {decision!r}")
    entry = _load(sid)
    if entry["status"] != _PENDING:
        raise ValueError(f"suggestion {sid!r} is already {entry['status']!r} — decide() only accepts pending entries")
    entry["status"] = decision
    entry["decided_at"] = _now_iso()
    _persist(entry)
    _append_ledger_line({
        "fingerprint": entry["fingerprint"],
        "decision": decision,
        "sid": entry["sid"],
        "ts": entry["decided_at"],
    })
    return entry


def _parse_ts(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def prune_decided(retention_days: int = DECIDED_RETENTION_DAYS) -> int:
    """Delete decided (accepted/declined) entry files whose `decided_at` is
    older than `retention_days`. The decision ledger is untouched — dedup
    stays intact after pruning (see module docstring). Entries with a
    missing or unparsable `decided_at` are skipped (never delete on
    ambiguity). Returns the count of files deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0
    for entry in all_suggestions():
        if entry.get("status") not in _DECISIONS:
            continue
        decided_at = entry.get("decided_at")
        if not decided_at:
            continue
        try:
            ts = _parse_ts(decided_at)
        except (ValueError, TypeError):
            continue
        if ts < cutoff:
            _suggestion_path(entry["sid"]).unlink(missing_ok=True)
            deleted += 1
    return deleted


def expire_stale_pending(max_age_days: int = PENDING_MAX_AGE_DAYS) -> int:
    """Transition pending entries whose `ts` is older than `max_age_days` to
    status="expired" (decided_at stays None, fingerprint is NOT ledgered —
    expiry is not a decline, see module docstring). Returns the count
    expired."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    expired = 0
    for entry in pending_suggestions():
        ts = entry.get("ts")
        if not ts:
            continue
        try:
            parsed = _parse_ts(ts)
        except (ValueError, TypeError):
            continue
        if parsed < cutoff:
            entry["status"] = _EXPIRED
            _persist(entry)
            expired += 1
    return expired


__all__ = [
    "SuggestionSpec",
    "DECIDED_RETENTION_DAYS",
    "PENDING_MAX_AGE_DAYS",
    "all_suggestions",
    "get_suggestion",
    "record",
    "pending_suggestions",
    "decided_fingerprints",
    "ledger_fingerprints",
    "decide",
    "prune_decided",
    "expire_stale_pending",
]
