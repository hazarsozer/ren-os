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

`propose` also dedups against the APPLIED target page itself (0.4.0, Task 2,
Codex M2 slice): if the proposed content, once normalized, matches what's
already on the page, `propose` returns a synthetic `QueueEntry` with
`status="noop-duplicate"` — this entry is never persisted to disk and never
transitions state, it exists only to tell the caller nothing changed.

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
import re
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
_NOOP_DUPLICATE = "noop-duplicate"

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_REN_KEY_LINE_RE = re.compile(r"^ren_\w+:.*$\n?", re.MULTILINE)


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


def all_entries() -> list[QueueEntry]:
    """Public whole-queue read API (0.4.0, Task 1): every entry regardless of
    status, in no particular order. One corrupted entry file must never take
    down whole-queue listing (final-verification finding): unparsable files
    are skipped with a stderr warning — same torn-file tolerance
    locks._read_holder applies to a torn lockfile. Single-entry reads by qid
    (`get`) still surface the corruption for that entry specifically.

    Consumers must not parse `state_dir()/"queue"/*.json` directly — this is
    the one place that owns the on-disk queue-entry format."""
    entries: list[QueueEntry] = []
    for path in _queue_dir().glob("*.json"):
        try:
            entries.append(_entry_from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(f"ren queue: skipping unparsable entry file {path.name}: {exc}", file=sys.stderr)
    return entries


_all_entries = all_entries  # internal alias for existing call sites


def _current_page_body(page: str) -> str | None:
    """Read the wiki page at `page`, or `None` if it doesn't exist / can't be
    read. Used by the applied-page dedup check in `propose`."""
    path = ren_paths.safe_join(ren_paths.wiki_root(), page)
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _normalize_body(text: str) -> str:
    """Strip only the `ren_*` provenance lines `write_apply`/`stamp_frontmatter`
    upsert into frontmatter, then trim — so the EFFECTIVE content of a
    proposal (what `apply`/`apply_auto` would actually write, quarantine
    banner included where applicable — see `_quarantined_content`) can be
    compared against what's on disk today.

    Deliberately does NOT strip the whole frontmatter block: a page's other
    frontmatter fields (e.g. `identity.md`'s `working_style`) are real
    content, not write-plumbing, and a proposal that only changes one of
    those must NOT be swallowed as a duplicate. Only `stamp_frontmatter`'s
    own `ren_*` keys are noise here — they're added downstream of this
    comparison and never appear in a proposal's raw content.

    Also deliberately does NOT touch the quarantine banner: whether a
    banner is present is real content as far as this comparison is
    concerned. Comparing `_quarantined_content(p)` (the effective write)
    against the on-disk body already accounts for it correctly on both
    sides — e.g. `wiki_health.release_page` proposes banner-free content
    against a bannered page and correctly registers as a real change, while
    a resubmitted identical llm-auto proposal computes the same bannered
    content on both sides and correctly registers as a no-op.

    If stripping `ren_*` lines leaves the frontmatter block empty (the
    common case for a page `stamp_frontmatter` had to create a brand-new
    fence for, since it had no frontmatter of its own), the now-empty fence
    is dropped too rather than left dangling — otherwise a page with no
    frontmatter at all would never normalize equal to its own stamped
    self."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return text.strip()

    fm_content = _REN_KEY_LINE_RE.sub("", match.group(1) + "\n").strip("\n")
    body = text[match.end():]
    if not fm_content:
        return body.strip()
    return f"---\n{fm_content}\n---\n{body}".strip()


def propose(p: Proposal) -> QueueEntry:
    """Submit `p` at the single write-door.

    Order: `p`'s fields are already validated (raises ValueError at
    `Proposal` construction if invalid, so an invalid proposal never reaches
    here) → scrub `p.content` if present (fail-closed: raises
    `lib.memory.scrub.SecretsFound` BEFORE anything is persisted) → dedup
    against existing PENDING entries with the same page + same content hash
    (idempotent propose: returns the existing entry unchanged, no new file) →
    applied-page dedup: for ADD/UPDATE, if the normalized proposed content
    matches the normalized content already on the target page, returns a
    synthetic, NEVER-persisted `QueueEntry` with `status="noop-duplicate"` —
    no file is written and this status never transitions. `propose_and_apply`
    already treats any non-pending status as a hold/no-op, so this composes
    without changes there. → detect conflicts via `lib.memory.semantics`
    (best-effort import; `[]` when absent) → persist → return the new entry.
    """
    if p.content is not None:
        scrub.scrub_or_raise(p.content)

    target_hash = _content_hash(p.content)
    for existing in pending():
        if existing.proposal.page == p.page and _content_hash(existing.proposal.content) == target_hash:
            return existing

    if p.op in ("ADD", "UPDATE") and p.content is not None:
        current = _current_page_body(p.page)
        if current is not None:
            effective = _quarantined_content(p) or ""
            if _content_hash(_normalize_body(current)) == _content_hash(_normalize_body(effective)):
                return QueueEntry(qid=f"q-{ULID()}", ts=_now_iso(), proposal=p, status=_NOOP_DUPLICATE)

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
    entries = [e for e in all_entries() if e.status == _PENDING]
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


def _quarantined_content(proposal: Proposal) -> str | None:
    """Read-time data-not-instruction (spec §10): llm-auto ADD/UPDATE content
    is banner-marked at the one door every write passes through — on BOTH the
    approved and the auto-applied paths. Promotion is the only exit."""
    content = proposal.content
    if proposal.writer == "llm-auto" and proposal.op in ("ADD", "UPDATE") and content is not None:
        return quarantine.mark(content)
    return content


def _check_add_race(qid: str, entry: "QueueEntry", verb: str) -> None:
    """codex D5: an ADD proposal built its write assuming the target page was
    absent (that's what "ADD" means); if the page was created out-of-band
    between propose and apply, blindly `os.replace`-ing it would silently
    clobber whatever landed there. Only applies to `op=="ADD"` — UPDATE's
    semantics (replace whatever is there) are unchanged.

    Compares the CURRENT on-disk body against the proposal's effective
    content, both normalized via `_normalize_body` (same comparison
    `propose()` already uses for its own applied-page dedup check):
      - page still absent -> no-op, caller proceeds with the write.
      - identical normalized content -> the entry is transitioned to
        `noop-duplicate` (mirrors `propose()`'s own dedup outcome for the
        same situation) and `QueueStateError` is raised so the caller never
        reaches `write_apply.apply_write`.
      - different content -> the entry is held: reverted to `pending` with
        an added `contradicts` conflict (the same hold mechanics
        `propose_and_apply` already uses for a detected contradiction), and
        `QueueStateError` is raised.
    """
    proposal = entry.proposal
    if proposal.op != "ADD":
        return
    current = _current_page_body(proposal.page)
    if current is None:
        return

    effective = _quarantined_content(proposal) or ""
    if _content_hash(_normalize_body(current)) == _content_hash(_normalize_body(effective)):
        entry.status = _NOOP_DUPLICATE
        _persist(entry)
        raise QueueStateError(
            f"cannot {verb} {qid}: ADD target {proposal.page!r} already has identical "
            "content — no-op"
        )

    entry.status = _PENDING
    entry.conflicts = entry.conflicts + [
        {
            "kind": "contradicts",
            "page": proposal.page,
            "write_id": None,
            "evidence": f"target page {proposal.page!r} was created out-of-band since this ADD was proposed",
        }
    ]
    _persist(entry)
    raise QueueStateError(
        f"cannot {verb} {qid}: ADD target {proposal.page!r} now exists with different "
        "content — held for review"
    )


def apply(qid: str) -> Provenance:
    """Apply an approved entry through `write_apply.apply_write`.

    Requires status=="approved" (else QueueStateError). Builds a `Provenance`
    via `new_provenance`, with `supersedes` set to the write_id of the first
    `conflicts` entry whose `kind` is `"supersedes"` (or `None` if there isn't
    one). On success, marks the entry `applied` with the resulting `write_id`.

    codex D5: before writing, an `ADD` whose target now exists on disk (it
    was absent when proposed) is re-checked via `_check_add_race` — see that
    helper for the held/no-op outcomes.
    """
    entry = _load(qid)
    if entry.status != _APPROVED:
        raise QueueStateError(f"cannot apply {qid}: status is {entry.status!r}, not 'approved'")
    _check_add_race(qid, entry, "apply")

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

    write_apply.apply_write(proposal.page, _quarantined_content(proposal), prov)

    entry.status = _APPLIED
    entry.write_id = prov.write_id
    _persist(entry)
    return prov


def apply_auto(qid: str) -> Provenance:
    """Apply a PENDING entry directly, bypassing the approve step — legal
    whenever the risk-tier model (`lib.governance.tiers`) resolves the
    proposal to the "auto" tier. Per spec §10's two-plane pivot, the DATA
    plane (any non-global memory write) auto-applies for every writer class,
    attended or not — provenance (G2) and one-step revert (G4) are the
    accountability mechanism, not a human diff. llm-auto content still gets
    the read-time quarantine banner here (via `_quarantined_content`), same
    as on the `apply()` path — auto-apply skips the human gate, not the
    quarantine.

    Raises `QueueStateError` if the entry isn't `pending`, or if the tier
    model doesn't classify this proposal as "auto" (a `global/` page — the
    INSTRUCTION plane — always requires the normal `approve()`/`apply()`
    path; promotion through a human is the only door from remembered to
    obeyed). `lib.governance.tiers` is imported lazily inside this function
    to avoid an import cycle (governance depends on nothing in `lib.memory`,
    but keeping the import local here means queue.py never has to import
    governance at module load time either).

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
    # NOTE: `_check_add_race` is deliberately NOT wired in here. Unlike
    # `apply()` (human approve -> apply, a real time gap where an external
    # actor can land the page first), `apply_auto` is reached synchronously
    # from `propose_and_apply` with no gap — and several producers
    # (`skills.wrap.lib.wrap_session`'s L1 write chief among them) legitimately
    # re-`ADD` the SAME page across repeated calls in one session as an
    # upsert. Wiring the race check here false-positives on that shipped
    # behavior (see tests/skills/wrap/test_wrap_flow.py's two-wrap-same-
    # session coverage) without closing any real race — codex D5's failure
    # scenario is specifically the approve()/apply() human gap.

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

    write_apply.apply_write(
        proposal.page, _quarantined_content(proposal), prov, journal_extra={"auto": True}
    )

    entry.status = _APPLIED
    entry.approved_by = "auto-tier"
    entry.write_id = prov.write_id
    _persist(entry)
    return prov


def resolve_and_apply(qid: str, resolution: str) -> Provenance:
    """Apply a PENDING entry that was held on a `contradicts` conflict, after
    the live session has reasoned about the contradiction.

    `resolution` must say WHY the new content stands despite the prior
    conflicting claim — a blank resolution raises `ValueError` before
    anything is touched. The reasoning is recorded on the journal line via
    `journal_extra={"auto": True, "contradiction_resolution": resolution}`,
    alongside the entry itself (`approved_by="model-resolved"`) — so the
    "why" survives next to the write, not just in the session transcript.

    Otherwise mirrors `apply_auto`: raises `QueueStateError` if the entry
    isn't `pending`, and refuses instruction-plane targets (a `global/`
    page) exactly like `apply_auto` does via `queue_auto_apply_allowed` —
    resolving a contradiction is still a data-plane operation, not a
    backdoor into the human-gated instruction plane.
    """
    from lib.governance.tiers import queue_auto_apply_allowed

    if not resolution.strip():
        raise ValueError("a contradiction resolution must say WHY")

    entry = _load(qid)
    if entry.status != _PENDING:
        raise QueueStateError(f"cannot resolve_and_apply {qid}: status is {entry.status!r}, not 'pending'")
    if not queue_auto_apply_allowed(entry.proposal):
        raise QueueStateError(
            f"cannot resolve_and_apply {qid}: proposal (writer={entry.proposal.writer!r}, "
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

    write_apply.apply_write(
        proposal.page,
        _quarantined_content(proposal),
        prov,
        journal_extra={"auto": True, "contradiction_resolution": resolution.strip()},
    )

    entry.status = _APPLIED
    entry.approved_by = "model-resolved"
    entry.write_id = prov.write_id
    _persist(entry)
    return prov


def auto_apply_eligible(entry: QueueEntry) -> bool:
    """True iff a PENDING `entry` may be released via `apply_auto` under
    v2.2 policy: no `contradicts` conflict, and the tier model resolves the
    proposal to "auto" (a bounded, non-global memory write). Factored out of
    `propose_and_apply` (Task 3) so the hold logic has exactly one
    implementation — the queue-governance-2-to-3 migration (Task 10) reuses
    this same function to decide which 0.2-gated pending entries to release,
    so the two call sites cannot drift.

    Does NOT check `entry.status` itself — callers that only care about
    pending entries should filter via `pending()` first (as `propose_and_apply`
    and the migration both do); a caller that passes a non-pending entry gets
    whatever this predicate says about its proposal/conflicts alone.
    """
    from lib.governance.tiers import queue_auto_apply_allowed

    if any(c.get("kind") == "contradicts" for c in entry.conflicts):
        return False
    return queue_auto_apply_allowed(entry.proposal)


def propose_and_apply(p: Proposal) -> tuple[QueueEntry, Provenance | None]:
    """v2.2 data-plane door: propose, then auto-apply when policy allows.

    Holds (returns (entry, None), status stays pending) in exactly three cases:
      1. instruction-plane target (tier model says not auto — global/ pages),
      2. a `contradicts` conflict was detected — the live session must REASON
         about it (revise the proposal, or resolve_and_apply with a note);
         supersedes/duplicate conflicts do NOT hold (UPDATE-supersede is the
         normal shape of a changing fact, journal records the lineage),
      3. idempotent-propose returned an entry that isn't pending anymore.

    Cases 1-2 are `auto_apply_eligible`; case 3 is checked here since
    `auto_apply_eligible` doesn't look at `entry.status`.
    """
    entry = propose(p)
    if entry.status != _PENDING:
        return entry, None
    if not auto_apply_eligible(entry):
        return entry, None
    prov = apply_auto(entry.qid)
    return get(entry.qid), prov


def approve_and_apply(qid: str, who: str) -> Provenance:
    """Approve then apply `qid` in one step — the explicit human-approval
    path for instruction-plane (`global/`) proposals, now that per-write
    gating is gone for everything else (v2.2, Task 8: relocated from the
    deleted `skills.queue.lib`, session param dropped since provenance
    already carries the proposal's session). Raises `KeyError` for an
    unknown qid, `QueueStateError` for an illegal transition (e.g. already
    applied) — same as the two calls it wraps."""
    approve(qid, approved_by=who)
    return apply(qid)


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
    "all_entries",
    "propose",
    "pending",
    "get",
    "approve",
    "apply",
    "apply_auto",
    "resolve_and_apply",
    "auto_apply_eligible",
    "propose_and_apply",
    "approve_and_apply",
    "reject",
]
