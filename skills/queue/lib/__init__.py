"""
skills.queue library — thin presentation verbs over lib.memory.queue and
lib.memory.revert (Task 8.3b, RenOS 0.2 Phase 8).

Gap this closes: the wrap screen (Task 8.2) tells the friend to run
"/ren:approve <qid>", but no skill implemented that verb. This module is
deliberately THIN — every function is a render-friendly wrapper over
existing lib logic (the queue, Task 2.1; revert, Task 2.3); no new business
logic lives here. Unknown ids (qid or write_id) render as a friendly
one-line error string, never a raw traceback — these functions are meant to
be called directly from a live session's response text.
"""

from __future__ import annotations

from lib.memory import queue, revert as revert_lib


def _render_conflicts(conflicts: list[dict]) -> str:
    if not conflicts:
        return ""
    lines = [f"    ⚠ {c.get('kind')}: {c.get('evidence', '')} (page: {c.get('page')})" for c in conflicts]
    return "\n" + "\n".join(lines)


def review() -> str:
    """Render every pending queue entry, human-readable, with any attached
    conflicts shown indented underneath."""
    entries = queue.pending()
    if not entries:
        return "No pending queue entries."

    lines = [f"{len(entries)} pending queue entr{'y' if len(entries) == 1 else 'ies'}:"]
    for entry in entries:
        p = entry.proposal
        salient = " [salient]" if p.salience else ""
        lines.append(
            f"  {entry.qid} — {p.op} {p.page} (producer={p.producer}, writer={p.writer}){salient}"
            f"{_render_conflicts(entry.conflicts)}"
        )
    return "\n".join(lines)


def approve_and_apply(qid: str, who: str, session: str) -> str:
    """Approve then apply `qid` in one step. Returns a confirmation
    including the resulting write_id and a one-line revert hint. Unknown
    qid, or an illegal state transition, renders as a friendly error string."""
    try:
        queue.approve(qid, approved_by=who)
        prov = queue.apply(qid)
    except KeyError:
        return f"No such queue entry: {qid}"
    except queue.QueueStateError as exc:
        return f"Could not approve/apply {qid}: {exc}"

    return (
        f"Applied {qid} → {prov.page} (write_id={prov.write_id}). "
        f"Revert with /ren:revert {prov.write_id} if this was a mistake."
    )


def reject_with_reason(qid: str, why: str) -> str:
    """Reject `qid` with `why`. Unknown qid or illegal transition renders as
    a friendly error string, not a traceback."""
    try:
        queue.reject(qid, why)
    except KeyError:
        return f"No such queue entry: {qid}"
    except queue.QueueStateError as exc:
        return f"Could not reject {qid}: {exc}"
    return f"Rejected {qid}: {why}"


def revert_write(write_id: str) -> str:
    """Revert `write_id` via `lib.memory.revert.revert`. Returns a
    human-readable confirmation including any citing pages a human should
    re-check. Unknown write_id renders as a friendly error string."""
    try:
        result = revert_lib.revert(write_id)
    except KeyError:
        return f"No such write_id: {write_id}"

    base = f"Reverted {write_id} on {result.page}."
    if result.citers:
        return base + f" {len(result.citers)} page(s) cite this write and may need review: {', '.join(result.citers)}"
    return base + " No other pages cite this write."


__all__ = ["review", "approve_and_apply", "reject_with_reason", "revert_write"]
