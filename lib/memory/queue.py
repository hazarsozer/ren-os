"""
lib.memory.queue — G1 the single write-queue (Task 2.1, RenOS 0.2 Phase 2).

Spec §3.1 "The single write path" (council A-3): durable memory has exactly
ONE door — a diff-queue with contradiction/supersede checking and dedup at the
queue; multiple producers (wrap, pin, retrospective, routine, promotion) feed
it, but nothing reaches a wiki page except through `propose` → `approve` →
`apply` here.

Persistence is the state: one JSON file per entry at
`state_dir()/"queue"/<qid>.json`. There is no module-level cache — every call
re-reads from disk, so the queue survives a process restart by construction
(the files ARE the state).

Producer/writer field vetting lives at the queue door (`Proposal.__post_init__`)
rather than downstream, so a malformed proposal never gets a qid at all.
Secrets-scrubbing (`lib.memory.scrub`) also happens at the door — `propose`
fails closed on a planted secret before anything is written to disk, not just
later at `apply` time (defense in depth: `write_apply.apply_write` scrubs
again, but a proposal should never even enter the queue carrying one).

`lib.memory.semantics` (contradiction/supersede/duplicate detection) is being
built in parallel and may not exist yet — imported the same best-effort way
`write_apply` imports `scrub`: `conflicts` is `[]` when the module is absent.

Ordering caveat (Task 9.3 doc-note-4, accepted limitation): ULIDs are
monotonic within one Python process but NOT across concurrent processes in
the same millisecond — so `pending()`'s oldest-first ordering and
`snapshot.prune()`'s keep-N-most-recent are best-effort under multi-process
same-millisecond races. Page-level leases (`lib.memory.locks`) still prevent
lost updates: ordering is cosmetic here, integrity is not affected.
"""

from __future__ import annotations

import hashlib
import json
import sys
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

from ulid import ULID

from lib import ren_paths
from lib.memory import quarantine, scrub, write_apply
from lib.memory.provenance import Op, WriterClass, Provenance, new_provenance

try:
    from lib.memory import semantics as _semantics
except ImportError:  # pragma: no cover - exercised via monkeypatch until builder-0-2's task lands
    _semantics = None

_OPS: tuple[str, ...] = get_args(Op)
_WRITER_CLASSES: tuple[str, ...] = get_args(WriterClass)
_PRODUCERS: tuple[str, ...] = ("wrap", "pin", "retrospective", "routine", "promotion")

_QUEUE_DIRNAME = "queue"
_PENDING = "pending"
_APPROVED = "approved"
_APPLIED = "applied"
_REJECTED = "rejected"


class QueueStateError(Exception):
    """Raised on an illegal status transition (e.g. apply before approve)."""


@dataclass(frozen=True)
class Proposal:
    op: str                  # "ADD"|"UPDATE"|"DELETE"|"NOOP" — validated against provenance.Op
    page: str                # wiki-relative
    content: str | None
    reason: str
    producer: str            # "wrap"|"pin"|"retrospective"|"routine"|"promotion"
    writer: str              # WriterClass value
    session: str
    salience: bool = False

    def __post_init__(self) -> None:
        if self.op not in _OPS:
            raise ValueError(f"op {self.op!r} is invalid; must be one of {_OPS}")
        if self.producer not in _PRODUCERS:
            raise ValueError(f"producer {self.producer!r} is invalid; must be one of {_PRODUCERS}")
        if self.writer not in _WRITER_CLASSES:
            raise ValueError(f"writer {self.writer!r} is invalid; must be one of {_WRITER_CLASSES}")


@dataclass
class QueueEntry:
    qid: str                 # "q-" + ULID
    ts: str                  # ISO-8601 UTC
    proposal: Proposal
    conflicts: list[dict] = field(default_factory=list)
    status: str = _PENDING
    approved_by: str | None = None
    write_id: str | None = None
    rejected_reason: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _content_hash(content: str | None) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _queue_dir() -> Path:
    d = ren_paths.state_dir() / _QUEUE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _entry_path(qid: str) -> Path:
    return _queue_dir() / f"{qid}.json"


def _entry_to_dict(entry: QueueEntry) -> dict:
    return asdict(entry)


def _entry_from_dict(data: dict) -> QueueEntry:
    proposal = Proposal(**data["proposal"])
    return QueueEntry(
        qid=data["qid"],
        ts=data["ts"],
        proposal=proposal,
        conflicts=list(data.get("conflicts", [])),
        status=data["status"],
        approved_by=data.get("approved_by"),
        write_id=data.get("write_id"),
        rejected_reason=data.get("rejected_reason"),
    )


def _persist(entry: QueueEntry) -> None:
    """Atomic write: temp file + os.replace, so a crash mid-write never leaves
    a torn/partial queue entry file."""
    path = _entry_path(entry.qid)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(_entry_to_dict(entry), indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load(qid: str) -> QueueEntry:
    path = _entry_path(qid)
    if not path.exists():
        raise KeyError(qid)
    return _entry_from_dict(json.loads(path.read_text(encoding="utf-8")))


def _all_entries() -> list[QueueEntry]:
    """One corrupted entry file must never take down whole-queue listing
    (final-verification finding): unparsable files are skipped with a stderr
    warning — same torn-file tolerance locks._read_holder applies to a torn
    lockfile. Single-entry reads by qid (`get`) still surface the corruption
    for that entry specifically."""
    entries: list[QueueEntry] = []
    for path in _queue_dir().glob("*.json"):
        try:
            entries.append(_entry_from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(f"ren queue: skipping unparsable entry file {path.name}: {exc}", file=sys.stderr)
    return entries


def propose(p: Proposal) -> QueueEntry:
    """Submit `p` at the single write-door.

    Order: `p`'s fields are already validated (raises ValueError at
    `Proposal` construction if invalid, so an invalid proposal never reaches
    here) → scrub `p.content` if present (fail-closed: raises
    `lib.memory.scrub.SecretsFound` BEFORE anything is persisted) → dedup
    against existing PENDING entries with the same page + same content hash
    (idempotent propose: returns the existing entry unchanged, no new file) →
    detect conflicts via `lib.memory.semantics` (best-effort import; `[]` when
    absent) → persist → return the new entry.
    """
    if p.content is not None:
        scrub.scrub_or_raise(p.content)

    target_hash = _content_hash(p.content)
    for existing in pending():
        if existing.proposal.page == p.page and _content_hash(existing.proposal.content) == target_hash:
            return existing

    if _semantics is not None:
        conflicts = [
            asdict(c)
            for c in _semantics.detect(op=p.op, page=p.page, content=p.content, wiki_root=ren_paths.wiki_root())
        ]
    else:
        conflicts = []

    entry = QueueEntry(
        qid=f"q-{ULID()}",
        ts=_now_iso(),
        proposal=p,
        conflicts=conflicts,
        status=_PENDING,
    )
    _persist(entry)
    return entry


def pending() -> list[QueueEntry]:
    """All entries with status=="pending", oldest first (qid is a ULID, so
    lexicographic sort == chronological order)."""
    entries = [e for e in _all_entries() if e.status == _PENDING]
    entries.sort(key=lambda e: e.qid)
    return entries


def get(qid: str) -> QueueEntry:
    """Return the entry for `qid`. Raises KeyError if unknown."""
    return _load(qid)


def approve(qid: str, approved_by: str) -> None:
    """Transition `qid` from pending to approved. Raises QueueStateError otherwise."""
    entry = _load(qid)
    if entry.status != _PENDING:
        raise QueueStateError(f"cannot approve {qid}: status is {entry.status!r}, not 'pending'")
    entry.status = _APPROVED
    entry.approved_by = approved_by
    _persist(entry)


def apply(qid: str) -> Provenance:
    """Apply an approved entry through `write_apply.apply_write`.

    Requires status=="approved" (else QueueStateError). Builds a `Provenance`
    via `new_provenance`, with `supersedes` set to the write_id of the first
    `conflicts` entry whose `kind` is `"supersedes"` (or `None` if there isn't
    one). On success, marks the entry `applied` with the resulting `write_id`.
    """
    entry = _load(qid)
    if entry.status != _APPROVED:
        raise QueueStateError(f"cannot apply {qid}: status is {entry.status!r}, not 'approved'")

    supersedes = next(
        (c.get("write_id") for c in entry.conflicts if c.get("kind") == "supersedes"),
        None,
    )
    proposal = entry.proposal
    prov = new_provenance(
        writer=proposal.writer,
        session=proposal.session,
        op=proposal.op,
        page=proposal.page,
        supersedes=supersedes,
    )

    content = proposal.content
    if proposal.writer == "llm-auto" and proposal.op in ("ADD", "UPDATE") and content is not None:
        # Spec §3.1/§3.10: LLM-auto content is data-not-instruction until a
        # human reviews it. Quarantine-mark it here, at the one door every
        # write passes through, rather than relying on every producer to
        # remember to mark its own proposals.
        content = quarantine.mark(content)

    write_apply.apply_write(proposal.page, content, prov)

    entry.status = _APPLIED
    entry.write_id = prov.write_id
    _persist(entry)
    return prov


def apply_auto(qid: str) -> Provenance:
    """Apply a PENDING entry directly, bypassing the approve step — legal
    ONLY when the risk-tier model (Task 6.1, `lib.governance.tiers`) resolves
    the proposal to the "auto" tier (a routine's bounded, non-global-page
    memory write). This is spec §3.6's "routine bounded writes auto-apply
    with provenance tags + one-step revert" path: provenance (G2) and revert
    (G4) already make an auto-applied write no less accountable than an
    approved one, just skipping the human-approval step for the narrow case
    the spec says is safe to skip it for.

    Raises `QueueStateError` if the entry isn't `pending`, or if the tier
    model doesn't classify this proposal as "auto" (e.g. a human/llm-auto
    writer, or a `global/` page — those always require the normal
    `approve()`/`apply()` path). `lib.governance.tiers` is imported lazily
    inside this function to avoid an import cycle (governance depends on
    nothing in `lib.memory`, but keeping the import local here means queue.py
    never has to import governance at module load time either).

    On success: marks the entry `applied` with `approved_by="auto-tier"` and
    the resulting `write_id`, and the journal line for this write carries
    `extra={"auto": True}` (via `write_apply.apply_write`'s `journal_extra`
    param) — so an auto-applied write is distinguishable from a
    human-approved one in the journal, not just in the queue-entry file.
    """
    from lib.governance.tiers import queue_auto_apply_allowed

    entry = _load(qid)
    if entry.status != _PENDING:
        raise QueueStateError(f"cannot apply_auto {qid}: status is {entry.status!r}, not 'pending'")
    if not queue_auto_apply_allowed(entry.proposal):
        raise QueueStateError(
            f"cannot apply_auto {qid}: proposal (writer={entry.proposal.writer!r}, "
            f"page={entry.proposal.page!r}) does not resolve to the 'auto' tier"
        )

    supersedes = next(
        (c.get("write_id") for c in entry.conflicts if c.get("kind") == "supersedes"),
        None,
    )
    proposal = entry.proposal
    prov = new_provenance(
        writer=proposal.writer,
        session=proposal.session,
        op=proposal.op,
        page=proposal.page,
        supersedes=supersedes,
    )

    write_apply.apply_write(proposal.page, proposal.content, prov, journal_extra={"auto": True})

    entry.status = _APPLIED
    entry.approved_by = "auto-tier"
    entry.write_id = prov.write_id
    _persist(entry)
    return prov


def reject(qid: str, why: str) -> None:
    """Reject a pending or approved entry, recording `why`."""
    entry = _load(qid)
    if entry.status not in (_PENDING, _APPROVED):
        raise QueueStateError(f"cannot reject {qid}: status is {entry.status!r}")
    entry.status = _REJECTED
    entry.rejected_reason = why
    _persist(entry)


__all__ = [
    "Proposal",
    "QueueEntry",
    "QueueStateError",
    "propose",
    "pending",
    "get",
    "approve",
    "apply",
    "apply_auto",
    "reject",
]
