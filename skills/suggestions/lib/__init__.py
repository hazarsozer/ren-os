"""
skills.suggestions library — internal implementation for /ren:suggestions
(Task 19, RenOS 0.4.2 "the suggestion pipeline").

This is the single interactive approve/reject surface over
`lib.suggestions`' durable store (Task 14) — the first place any suggestion
actually gets APPLIED. `lib.suggestions.decide` is a pure state transition;
this module is what turns an "accepted" decision into a real write, by
`kind`/payload `action`:

  page_write        → `lib.memory.queue.propose` then `approve_and_apply`.
                       Instruction-plane (`global/`) pages go through the
                       SAME human-gated door as ever — the recorded
                       suggestion decision IS the human approval.
  promote_to_global → `lib.memory.promotion.promote_to_global` then
                       `approve_and_apply`.
  refresh_claude_md → `lib.adapter.claude_md.write_global_claude_md`.
  review_contradiction → applies nothing; returns the two page paths +
                       evidence for the session to reconcile conversationally.

Failure contract (0.4.5): "accepted" means the change actually landed. The
apply runs FIRST; only a successful apply (including intentional no-op
outcomes like a duplicate page_write or a review_contradiction handoff)
records the "accepted" decision. An apply that raises leaves the suggestion
PENDING — still visible in `/ren:suggestions`, still retryable, its
fingerprint never deduped by a decision that didn't happen. The error is
caught and surfaced in the returned `"detail"`, never raised past `accept()`
(except for an unknown `sid`, which raises `KeyError` before any apply is
attempted).

Immutability (0.5.x, codex P1): `lib.suggestions.decide()` raises
`ValueError` for an entry that isn't currently "pending" — decided
("accepted"/"declined") and expired entries can never be re-decided.
`accept()` checks this up front, before any apply, and returns
`{"applied": False, "detail": "already <status>"}`; `decline()` catches the
same `ValueError` and surfaces the equivalent result.

Decision-recording failure (0.5.x, codex P2/P3): the `decide()` call that
runs AFTER a successful apply has its own try/except. If it raises, `accept()`
still returns the apply result, with `"decision_recorded": False` added — the
suggestion stays pending (will re-offer) even though its effect already
landed. That's safe by construction: re-accepting a `page_write` suggestion
dedups to `noop-duplicate`, and re-running `promote_to_global` is idempotent.
On a successful `decide()`, `"decision_recorded": True` is added instead.
"""

from __future__ import annotations

import re

from lib.adapter import claude_md
from lib.memory import promotion, queue
from lib.memory.queue import Proposal
from lib.suggestions import decide, get_suggestion, pending_suggestions

_PREVIEW_MAX_CHARS = 100
_PREVIEW_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)

_NOOP_DUPLICATE = "noop-duplicate"


def _content_preview(content: str | None) -> str:
    """First meaningful body line of a page_write payload's content — what
    the friend is actually saying yes/no to. Skips frontmatter and the
    quarantine banner; truncates to one legible line. Reimplemented locally
    from `skills.wrap.lib._content_preview` (private to its own module)."""
    if not content:
        return ""
    body = _PREVIEW_FRONTMATTER_RE.sub("", content, count=1)
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("> [!ren-quarantine]"):
            continue
        if len(line) > _PREVIEW_MAX_CHARS:
            return line[:_PREVIEW_MAX_CHARS] + "…"
        return line
    return ""


def render_suggestion(s: dict) -> str:
    """Title, rationale, producer, and (for page_write payloads) a content
    preview — the single suggestion the friend is deciding on right now."""
    lines = [f"[{s['producer']}] {s['title']}", f"  {s['rationale']}"]
    if s.get("kind") == "page_write":
        preview = _content_preview((s.get("payload") or {}).get("content"))
        if preview:
            lines.append(f"  > {preview}")
    return "\n".join(lines)


def render_list() -> str:
    """Numbered pending suggestions, oldest first; "No pending suggestions."
    when the store is empty."""
    pending = pending_suggestions()
    if not pending:
        return "No pending suggestions."
    return "\n".join(f"{i}. {render_suggestion(s)}" for i, s in enumerate(pending, start=1))


def _apply(sid: str, kind: str, payload: dict, session: str) -> dict:
    """Perform the accepted suggestion's real effect. Raising is the ONLY
    failure signal — `accept()` records the decision iff this returns."""
    if kind == "page_write":
        new_entry = queue.propose(Proposal(**payload))
        if new_entry.status == _NOOP_DUPLICATE:
            return {"sid": sid, "applied": False, "detail": "content already on page"}
        prov = queue.approve_and_apply(new_entry.qid, who="suggestions")
        return {
            "sid": sid,
            "applied": True,
            "detail": {"qid": new_entry.qid, "write_id": prov.write_id, "page": prov.page},
        }

    action = payload.get("action")

    if action == "promote_to_global":
        qe = promotion.promote_to_global(payload["source_page"], session)
        prov = queue.approve_and_apply(qe.qid, who="suggestions")
        return {
            "sid": sid,
            "applied": True,
            "detail": {"qid": qe.qid, "write_id": prov.write_id, "page": prov.page},
        }

    if action == "refresh_claude_md":
        path, result = claude_md.write_global_claude_md()
        return {"sid": sid, "applied": True, "detail": {"path": str(path), "result": result}}

    if action == "review_contradiction":
        return {
            "sid": sid,
            "applied": False,
            "detail": {
                "page": payload.get("page"),
                "with": payload.get("with"),
                "evidence": payload.get("evidence"),
            },
        }

    return {"sid": sid, "applied": False, "detail": f"unknown suggestion kind {kind!r} / action {action!r}"}


def accept(sid: str, session: str) -> dict:
    """Apply `sid`'s payload by `kind`/action, then record it as accepted.

    Returns `{"sid", "applied": bool, "detail": ...}` plus, once an apply has
    been attempted, `"decision_recorded": bool`. Raises `KeyError` if `sid`
    doesn't exist (before any apply is attempted).

    P1: decided ("accepted"/"declined") and expired entries are immutable —
    accept() checks the entry's status up front (before any apply) and
    surfaces `{"applied": False, "detail": "already <status>"}` without
    touching anything.

    0.4.5 ordering: the apply runs first; an apply that raises leaves the
    suggestion PENDING (visible and retryable — its fingerprint is never
    deduped by a decision that didn't happen) and surfaces the error in
    `"detail"`. Intentional non-write outcomes (duplicate content,
    review_contradiction handoff, unknown kind) still count as decided —
    retrying them cannot change the outcome.

    P3/P2: the post-apply `decide()` call has its own try/except. If it
    raises, the apply result is returned as-is with `"decision_recorded":
    False` added — the suggestion stays pending and will re-offer. That's
    safe: a crash between apply and decide leaves a pending suggestion whose
    effect already landed, but re-accepting it is benign — `page_write`
    dedups to `noop-duplicate` and `promote_to_global` re-runs idempotently.
    On success, `"decision_recorded": True` is added.
    """
    entry = get_suggestion(sid)
    if entry["status"] != "pending":
        return {"sid": sid, "applied": False, "detail": f"already {entry['status']}"}

    try:
        result = _apply(sid, entry["kind"], entry.get("payload") or {}, session)
    except Exception as exc:  # noqa: BLE001 - failure contract: surface, never raise past accept()
        return {"sid": sid, "applied": False, "detail": str(exc)}

    try:
        decide(sid, "accepted")
    except Exception:  # noqa: BLE001 - decision-recording failure must not lose the apply result
        return {**result, "decision_recorded": False}

    return {**result, "decision_recorded": True}


def decline(sid: str) -> dict:
    """Record `sid` as declined — durable, never re-offered (`decide`'s
    fingerprint dedup covers that). Raises `KeyError` for an unknown sid.

    P1: a decided or expired entry is immutable — `decide()` raises
    `ValueError` in that case, which this surfaces as
    `{"applied": False, "detail": "already <status>"}` instead of
    propagating."""
    try:
        return decide(sid, "declined")
    except ValueError:
        entry = get_suggestion(sid)
        return {"sid": sid, "applied": False, "detail": f"already {entry['status']}"}


__all__ = ["render_suggestion", "render_list", "accept", "decline"]
