"""
skills.wrap library — internal implementation for /ren:wrap (Task 4.1, RenOS
0.2 Phase 4).

Public entry: `wrap_session(narrative_md, durable_items, session, llm_call=None)
-> dict`.

Per spec §3.1 producer 1 (L1 session continuity) + §3.8 (unified wrap
surface) + §3.10 (quarantine): the live Claude session (SKILL.md) writes the
narrative and proposes candidate durable items; this module is the part that
actually touches the single write-queue (Task 2.1) and the classifier gate
(`.classifier.gate`).

Two different risk tiers, per §3.6's risk-tiered approval gates:
  - L1 (the session narrative) is a ROUTINE BOUNDED WRITE: it always
    auto-applies (propose -> approve -> apply, right here), tagged
    `writer="llm-auto"`, which the queue's Task-2.4 wiring auto-quarantines —
    it is data, not instruction, until a human reviews it. One-step revert
    (Task 2.3) is what makes "auto-apply" safe here.
  - Durable items are DURABLE KNOWLEDGE: they only ever get `queue.propose()`'d
    here, never auto-approved/applied. They sit pending for a human's OK — the
    unified end-of-wrap approval screen (Task 8.2, not yet built) is where
    that OK happens; this module just gets them correctly queued or correctly
    turned away (gated out, or refused for a planted secret).

Donor `skills/wrap/lib/{classifier.py,types.py,diff_plan.py}` is NOT ported
wholesale — its CONTEXT.md-rewrite / diff_plan machinery assumed direct wiki
writes, which 0.2's single write-queue makes obsolete (every write, including
L1, goes through `lib.memory.queue` now). Only the classifier's prompt/parse
DISCIPLINE was adapted (see `.classifier`), reshaped for the different
question this module asks per item ("is this durable?") rather than donor's
whole-session multi-label classification.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from lib import ren_paths
from lib.instrument import collect
from lib.memory.queue import Proposal, apply, approve, propose
from lib.memory.scrub import SecretsFound

from .classifier import gate

_SLUG_WORD_RE = re.compile(r"[a-z0-9]+")


def _slugify(text: str, *, max_words: int = 8) -> str:
    """Kebab-case slug derived from `text`'s first few significant words.
    Falls back to "item" if nothing alphanumeric is found (e.g. all-emoji or
    all-punctuation input) so a durable item never fails to queue purely
    because it produced an empty page name."""
    words = _SLUG_WORD_RE.findall(text.lower())
    return "-".join(words[:max_words]) or "item"


def wrap_session(
    narrative_md: str,
    durable_items: list[str],
    session: str,
    llm_call: Callable[[str], str] | None = None,
) -> dict:
    """Run the wrap write path for one session close-out.

    Returns a dict:
      - "l1_qid": qid of the (already applied + quarantined) L1 entry
      - "durable_qids": qids of items gated "durable" and successfully queued
        (pending human approval — NOT auto-applied)
      - "gated_out": [{"item", "verdict", "reason"}] for non-durable items
      - "refused": [{"item", "reason"}] for durable items the queue itself
        refused (currently: a planted secret — `SecretsFound` propagates from
        `lib.memory.scrub` via `queue.propose`'s door-side scrub, and is
        caught here so ONE bad item doesn't crash the whole wrap)
      - "fail_closed": True if the classifier gate fell back to the
        deterministic path (due to an LLM error) for at least one durable
        candidate during this call
    """
    l1_entry = propose(
        Proposal(
            op="ADD",
            page=f"l1/session-{session}.md",
            content=narrative_md,
            reason="end-of-session L1 narrative summary",
            producer="wrap",
            writer="llm-auto",
            session=session,
        )
    )
    approve(l1_entry.qid, approved_by="wrap-auto")
    apply(l1_entry.qid)

    events_before = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)

    durable_qids: list[str] = []
    gated_out: list[dict] = []
    refused: list[dict] = []

    for item in durable_items:
        decision = gate(item, llm_call)

        if decision.verdict != "durable":
            gated_out.append(
                {"item": item, "verdict": decision.verdict, "reason": decision.reason}
            )
            continue

        page = f"lessons/{_slugify(item)}.md"
        try:
            entry = propose(
                Proposal(
                    op="ADD",
                    page=page,
                    content=item,
                    reason=decision.reason,
                    producer="wrap",
                    writer="llm-auto",
                    session=session,
                )
            )
        except SecretsFound as exc:
            refused.append({"item": item, "reason": str(exc)})
            continue

        durable_qids.append(entry.qid)

    events_after = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    new_events = events_after[len(events_before):]
    fail_closed = any(e.get("event") == "fail_closed" for e in new_events)

    return {
        "l1_qid": l1_entry.qid,
        "durable_qids": durable_qids,
        "gated_out": gated_out,
        "refused": refused,
        "fail_closed": fail_closed,
    }


def _session_queue_entries(session: str) -> list[dict]:
    """Read every queue-entry JSON file directly under `state_dir()/queue/`,
    filtered to `proposal.session == session`.

    `lib.memory.queue`'s public surface only exposes `pending()` (PENDING
    entries only) — the wrap screen needs BOTH pending and already-applied
    entries for this session (auto-tier applies included), so this reads the
    same on-disk JSON files queue.py itself owns, rather than reaching into
    queue.py's private `_all_entries()` (a module under active parallel
    development elsewhere in this build — safer not to couple to its
    internals). Read-only; never mutates a queue file."""
    queue_dir = ren_paths.state_dir() / "queue"
    if not queue_dir.is_dir():
        return []

    entries: list[dict] = []
    for path in sorted(queue_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("proposal", {}).get("session") == session:
            entries.append(data)
    return entries


def _conflict_flags(conflicts: list[dict]) -> list[str]:
    flags: list[str] = []
    for conflict in conflicts:
        kind = conflict.get("kind")
        if kind == "supersedes":
            flags.append(f"supersedes {conflict.get('write_id')}")
        elif kind == "contradicts":
            evidence = (conflict.get("evidence") or "")[:60]
            flags.append(f"contradicts: {evidence}")
        elif kind == "duplicate":
            flags.append("duplicate")
    return flags


def render_wrap_screen(wrap_result: dict, session: str) -> str:
    """Render the unified end-of-wrap screen (spec §3.8 A-10 / G15): one
    legible screen naming what happened this session even though risk tiers
    fragment the underlying writes across auto-applied and pending entries.

    PURE PRESENTATION: reads queue state on disk via `_session_queue_entries`
    and the given `wrap_result` (the return value of `wrap_session`); writes
    NOTHING. Three sections plus a refused note and a footer:
      - "What I learned" — the L1 entry's qid + one-line status.
      - "Auto-saved (revertible)" — this session's entries with
        `approved_by == "auto-tier"` (routine bounded writes that
        auto-applied), each with its write_id and a revert hint.
      - "Needs your OK" — this session's still-PENDING entries (durable
        candidates, pins, anything awaiting a human), each with its target
        page, reason, and any conflict flags (supersedes/contradicts/
        duplicate) from `lib.memory.semantics`.
    """
    entries = _session_queue_entries(session)
    by_qid = {e["qid"]: e for e in entries}

    lines: list[str] = ["# Wrap summary", ""]

    # --- What I learned ---
    lines.append("## What I learned")
    l1_entry = by_qid.get(wrap_result.get("l1_qid"))
    if l1_entry is not None:
        status = l1_entry.get("status")
        status_label = "applied (quarantined, unreviewed)" if status == "applied" else status
        lines.append(f"- session summary ({l1_entry['qid']}): {status_label}")
    else:
        lines.append("- session summary: (not found)")
    lines.append("")

    # --- Auto-saved (revertible) ---
    lines.append("## Auto-saved (revertible)")
    auto_entries = [e for e in entries if e.get("approved_by") == "auto-tier"]
    if auto_entries:
        for entry in auto_entries:
            write_id = entry.get("write_id")
            page = entry["proposal"]["page"]
            lines.append(f"- {page} (write_id={write_id}) — revert with: /ren:revert {write_id}")
    else:
        lines.append("- (none this session)")
    lines.append("")

    # --- Needs your OK ---
    lines.append("## Needs your OK")
    pending_entries = [e for e in entries if e.get("status") == "pending"]
    if pending_entries:
        for entry in pending_entries:
            page = entry["proposal"]["page"]
            reason = entry["proposal"].get("reason", "")
            flags = _conflict_flags(entry.get("conflicts") or [])
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"- {entry['qid']} → {page} — {reason}{flag_str}")
    else:
        lines.append("- (nothing pending)")
    lines.append("")

    # --- Refused (never queued) ---
    refused = wrap_result.get("refused") or []
    if refused:
        lines.append("## Refused (not queued)")
        for item in refused:
            # Deliberately do NOT render `item["item"]` — that's the raw
            # candidate text, which is exactly what got refused for
            # containing a secret. `reason` is `lib.memory.scrub.SecretsFound`'s
            # message, which names kinds + counts only, never secret content.
            lines.append(f"- refused: {item.get('reason', '')}")
        lines.append("")

    lines.append("approve: /ren:approve <qid> · reject: /ren:reject <qid>")
    return "\n".join(lines) + "\n"


__all__ = ["wrap_session", "render_wrap_screen"]
