"""skills.distill.lib — the #60 wiki-distiller's mechanical substrate.

Spec: docs/superpowers/specs/2026-08-18-knowledge-flows-train-design.md §3.
The worker agent does the judgment (mining L1s, drafting content); this lib
owns everything deterministic: the watermark, L1 enumeration, journal dedup,
verdict validation (shared with wrap via gate_precomputed), and the capped
apply through the single write door with producer="distiller".
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from lib import ren_paths
from lib.instrument import collect
from lib.memory import journal
from lib.memory.quarantine import escape_untrusted
from lib.memory.queue import Proposal, propose_and_apply
from lib.memory.scrub import SecretsFound
from lib.suggestions import SuggestionSpec
from lib.suggestions import record as record_suggestion
from skills.wrap.lib import _durable_create_page, _target_trust, eligible_update_targets
from skills.wrap.lib.classifier import PlacementError, gate_precomputed

WRITE_CAP = 10  # spec §3.4 — remainder carries to the next run, logged

_REN_TS_RE = re.compile(r'^ren_ts:\s*"?([0-9TZ:.\-]+)"?\s*$', re.MULTILINE)


def watermark_path() -> Path:
    return ren_paths.state_dir() / "distiller-watermark.json"


def read_watermark() -> str | None:
    try:
        data = json.loads(watermark_path().read_text(encoding="utf-8"))
        ts = data.get("ts")
        return ts if isinstance(ts, str) else None
    except (OSError, ValueError):
        return None


def write_watermark(ts: str) -> None:
    path = watermark_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"ts": ts}), encoding="utf-8")
    os.replace(tmp, path)


def _frontmatter_ts(text: str) -> str:
    m = _REN_TS_RE.search(text[:2000])
    return m.group(1) if m else ""


def l1_batch(after: str | None) -> list[dict]:
    """Every L1 newer than `after` (ISO-string comparison — both sides are
    UTC Zulu stamps from the same writer), ascending. Quarantined pages are
    IN by design (spec §3.2); bodies come back pre-escaped."""
    root = ren_paths.wiki_root()
    pages: list[dict] = []
    for pattern, project_of in (
        ("l1/session-*.md", lambda p: None),
        ("projects/*/l1/session-*.md", lambda p: p.parts[-3]),
    ):
        for path in sorted(root.glob(pattern)):
            text = path.read_text(encoding="utf-8", errors="replace")
            ts = _frontmatter_ts(text)
            if after is not None and ts > "" and ts <= after:
                continue
            pages.append({
                "page": str(path.relative_to(root)),
                "session": path.stem.removeprefix("session-"),
                "ren_ts": ts,
                "project": project_of(path),
                "escaped_body": escape_untrusted(text),
            })
    pages.sort(key=lambda e: e["ren_ts"])
    return pages


def landed_pages(session: str) -> set[str]:
    """Pages the write door already recorded for `session` — the distiller
    must never re-propose what wrap (or pin) already landed (spec §3.2)."""
    return {
        e.get("page") for e in journal.entries()
        if e.get("session") == session and e.get("page")
    }


def _suggest_unplaced(item: str, source_session: str, idx: int, reason: str,
                      exc: PlacementError | None = None) -> dict:
    claimed = {}
    if exc is not None:
        claimed = {"claimed_scope": exc.claimed_scope,
                   "claimed_action": exc.claimed_action,
                   "claimed_target": exc.claimed_target}
    entry = record_suggestion(
        SuggestionSpec(
            producer="distiller",
            title=f"Place durable item from session {source_session}",
            rationale=reason,
            evidence={"item": item, "session": source_session, **claimed},
            kind="structured_action",
            payload={"action": "place_durable_item", "item": item,
                     "session": source_session},
            fingerprint=f"distiller-unplaced:{source_session}:{idx}",
        )
    )
    return {"item": item, "reason": reason,
            "sid": entry["sid"] if entry else None}


def _watermark_after(batch: list[dict] | None, unprocessed: list[dict]) -> str | None:
    """The watermark this run may safely advance to (controller ruling, #71
    review round 3): with no `batch`, always `None` — the lib never
    guesses at a watermark it wasn't handed the batch to compute from.

    No unprocessed (remainder) candidates: the batch's own max `ren_ts` — the
    whole batch was looked at, so everything up to its tail is safe to skip
    next time (spec §3.4). Sessions that produced zero candidates count as
    fully consumed by construction — they never appear in `unprocessed`.

    With a remainder: the sessions those unprocessed candidates came from
    must stay BEHIND the watermark (spec §3.4) so their source L1s get
    re-mined. That is the max `ren_ts` among batch entries strictly below
    the minimum `ren_ts` of any batch entry belonging to one of those
    sessions — `None` if even the batch's earliest entry belongs to one
    (nothing can safely advance)."""
    if batch is None:
        return None
    if not unprocessed:
        return max((e["ren_ts"] for e in batch), default=None)
    blocked_sessions = {c["source_session"] for c in unprocessed}
    blocked_ts = [e["ren_ts"] for e in batch if e.get("session") in blocked_sessions]
    if not blocked_ts:
        # The unprocessed candidates' sessions aren't in this batch at all
        # (shouldn't happen in practice) — nothing safe to compute.
        return None
    floor = min(blocked_ts)
    safe = [e["ren_ts"] for e in batch if e["ren_ts"] < floor]
    return max(safe) if safe else None


def apply_candidates(candidates: list[dict], *, run_session: str,
                     cap: int = WRITE_CAP,
                     batch: list[dict] | None = None,
                     watermark_before: str | None = None) -> dict:
    applied: list[dict] = []
    held: list[dict] = []
    suggested: list[dict] = []
    gated_out: list[dict] = []
    refused: list[dict] = []
    duplicates: list[dict] = []
    capped_remainder = 0
    unprocessed: list[dict] = []

    for idx, cand in enumerate(candidates):
        if len(applied) + len(held) >= cap:
            capped_remainder = len(candidates) - idx
            unprocessed = candidates[idx:]
            break
        item = cand["item"]
        source = cand["source_session"]
        try:
            decision = gate_precomputed(
                item, cand["verdict"],
                eligible_targets=eligible_update_targets(source),
                project=cand.get("project"),
            )
        except PlacementError as exc:
            suggested.append(_suggest_unplaced(item, source, idx, exc.reason, exc))
            continue
        if decision.verdict != "durable":
            gated_out.append({"item": item, "verdict": decision.verdict,
                              "reason": decision.reason})
            continue

        if decision.action == "update":
            page = decision.target_page
        else:
            page = cand.get("page") or _durable_create_page(
                item, decision.scope, cand.get("project"))
        if _target_trust(page) == "user":
            suggested.append(_suggest_unplaced(
                item, source, idx, f"target {page} is human-authored (trust=user)"))
            continue
        try:
            entry, prov = propose_and_apply(Proposal(
                op="UPDATE" if decision.action == "update" else "ADD",
                page=page, content=cand["content"], reason=decision.reason,
                producer="distiller", writer="llm-auto", session=run_session,
            ))
        except SecretsFound as exc:
            refused.append({"item": item, "reason": str(exc)})
            continue
        if entry.status == "noop-duplicate":
            # Excluded from the cap count (controller ruling, #71 review
            # round 3): a replay landing on already-current content is not
            # new work, so it must never burn a cap slot that a genuinely
            # new candidate needed.
            duplicates.append({"item": item, "page": page})
            continue
        if prov is not None:
            applied.append({"qid": entry.qid, "write_id": prov.write_id,
                            "page": page, "op": prov.op})
        else:
            held.append({"qid": entry.qid, "page": page,
                         "conflicts": entry.conflicts})

    created_project = sum(1 for a in applied if a["page"].startswith("projects/")
                          and a["op"] == "ADD")
    creates = [a for a in applied if a["op"] == "ADD"]
    updates = [a for a in applied if a["op"] == "UPDATE"]
    watermark_after = _watermark_after(batch, unprocessed)
    if batch is not None:
        sessions = len(batch)
    else:
        sessions = len({c["source_session"] for c in candidates})
    collect.record(collect.KIND_DISTILLER_RUN, {
        "run_session": run_session, "candidates": len(candidates),
        "applied": len(applied), "held": len(held),
        "suggested": len(suggested), "gated_out": len(gated_out),
        "refused": len(refused), "capped_remainder": capped_remainder,
        "sessions": sessions, "duplicates": len(duplicates),
        "watermark_before": watermark_before, "watermark_after": watermark_after,
    })
    collect.record(collect.KIND_DURABLE_OUTCOME, {
        "session": run_session, "producer": "distiller",
        "seen": len(candidates), "created": len(creates),
        "created_project": created_project,
        "created_global": len(creates) - created_project,
        "updated": len(updates), "gated_out": len(gated_out),
        "suggested": len(suggested), "held": len(held),
        "refused": len(refused), "unplaced": len(suggested),
    })
    return {"applied": applied, "held": held, "suggested": suggested,
            "gated_out": gated_out, "refused": refused,
            "duplicates": duplicates, "capped_remainder": capped_remainder,
            "watermark_after": watermark_after}
