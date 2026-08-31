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
from datetime import date
from pathlib import Path, PurePosixPath

from lib import ren_paths
from lib.instrument import collect
from lib.memory import journal
from lib.memory.quarantine import escape_untrusted
from lib.memory.queue import NOOP_DUPLICATE, Proposal, propose_and_apply
from lib.memory.scrub import SecretsFound
from lib.memory.taxonomy import TaxonomyError, classify_placement, load_taxonomy, render_block
from lib.suggestions import SuggestionSpec
from lib.suggestions import record as record_suggestion
from skills.wrap.lib import (
    _apply_concept_create,
    _durable_create_page,
    _ensure_hub,
    _target_trust,
    eligible_update_targets,
)
from skills.wrap.lib.classifier import PlacementError, gate, gate_precomputed

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
            if prov.op == "ADD":
                # Distiller hub gap (spec 2026-08-31 §3 behavior 7): distiller
                # creates never maintained the folder-note hub for their own
                # directory — closed the same way wrap's own lesson-create
                # path does (skills/wrap/lib/__init__.py's `_durable_create_page`
                # call site).
                hub_dir = str(PurePosixPath(page).parent)
                _ensure_hub(
                    hub_dir, run_session,
                    cand.get("project") if page.startswith("projects/") else None,
                    heading="Lessons",
                )
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


# --- --seed-tree backfill mode (spec 2026-08-31 §3, Task 7) -----------------
#
# A manual-trigger-only mode (never the scheduled distill path — SKILL.md
# says so): mines EXISTING project lessons — written before concept-tree
# routing existed, or missed by a session's own wrap gate — for durable
# concepts, and places them into the taxonomy via Task 3's shared machinery
# (`_apply_concept_create`, which already maintains its own leaf/parent hubs
# and additively splices `schema.md`). A lesson that becomes a concept gets a
# `See: [[<node>]]` pointer appended to it, so a reader who lands on the old
# lesson can follow the pointer to the now-canonical concept page.

_LESSON_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)


def seed_tree_watermark_path(project: str) -> Path:
    """Beside the distiller's own watermark (spec 2026-08-31 §3 behavior 2),
    keyed per project — `--seed-tree` runs one project at a time and each
    project's lessons backlog is mined independently."""
    return ren_paths.state_dir() / f"seed-tree-watermark-{project}.json"


def read_seed_tree_watermark(project: str) -> str | None:
    try:
        data = json.loads(seed_tree_watermark_path(project).read_text(encoding="utf-8"))
        ts = data.get("ts")
        return ts if isinstance(ts, str) else None
    except (OSError, ValueError):
        return None


def write_seed_tree_watermark(project: str, ts: str) -> None:
    path = seed_tree_watermark_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"ts": ts}), encoding="utf-8")
    os.replace(tmp, path)


def _lesson_body(text: str) -> str:
    """`text` with its leading YAML frontmatter stripped — the classifier
    prompt and the concept page's own content (first sentence + Facts
    bullet) should carry the lesson's substance, not its `ren_*`/`type:`
    bookkeeping lines."""
    return _LESSON_FRONTMATTER_RE.sub("", text, count=1).strip()


_SEE_MARKER_RE = re.compile(r"^See: \[\[", re.MULTILINE)


def seed_tree_batch(project: str, after: str | None) -> list[dict]:
    """Every `projects/<project>/knowledge/lessons/*.md` page newer than
    `after`, ascending by `ren_ts` — same ISO-string-comparison convention as
    `l1_batch`. The lessons folder-note hub itself (`lessons/lessons.md`) is
    excluded: it is bookkeeping, not a lesson to mine. A project with no
    lessons directory yet returns `[]` rather than raising.

    Also excludes any lesson already carrying a `See: [[...]]` pointer line —
    seed_tree's own annotation UPDATE re-stamps that page's `ren_ts` (the
    write door restamps `ren_*` provenance on EVERY write, not just
    creation), which would otherwise make an already-routed lesson outrun its
    own watermark and get re-batched forever. This is the idempotency
    backstop for that self-referential case; ordinary un-annotated lessons
    are unaffected."""
    root = ren_paths.wiki_root()
    lessons_dir = root / "projects" / project / "knowledge" / "lessons"
    if not lessons_dir.is_dir():
        return []
    pages: list[dict] = []
    for path in sorted(lessons_dir.glob("*.md")):
        if path.name == "lessons.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _SEE_MARKER_RE.search(text):
            continue
        ts = _frontmatter_ts(text)
        if after is not None and ts > "" and ts <= after:
            continue
        pages.append({"page": str(path.relative_to(root)), "ren_ts": ts, "text": text})
    pages.sort(key=lambda e: e["ren_ts"])
    return pages


_NO_TAXONOMY_REFUSAL: str = "no taxonomy — run ingest's taxonomy draft first"


def seed_tree(project: str, llm_call, *, cap: int | None = None) -> dict:
    """`--seed-tree <project>` backfill (spec 2026-08-31 §3, Task 7):
    manual-trigger-only batch mining of EXISTING lessons into the concept
    tree. Result mirrors `apply_candidates`'s shape plus `"annotated"` and
    `"blind"`.

    Behavior 3: `TaxonomyError` from `load_taxonomy` refuses the WHOLE run —
    "blind, not a guess" (spec `lib/reporting.py` conventions) — zero writes,
    watermark untouched.

    Behavior 4: each lesson body is gated through the LIVE LLM path
    (`gate`, not `gate_precomputed` — this mode always has an `llm_call`).
    `kind == "concept"` (and a placement that resolves to a brand-new
    taxonomy leaf — `_apply_concept_create` is a NEW-LEAF create, spec §3
    behaviors 3+5) places the concept and then annotates the source lesson;
    anything else (kind == "lesson", non-durable, or a concept placement
    that isn't a new leaf) is skipped and the watermark still advances past
    it — there is nothing to write for an item that is already sitting on
    disk as a lesson.

    Behavior 5: cap is checked once per LESSON (not per write) — a lesson's
    concept-create and its `See:` annotation land as a pair, so a capped run
    never leaves a concept minted with no pointer back to it. Both writes
    still count toward the running total the NEXT lesson's cap check sees.

    Behavior 6: one `KIND_DISTILLER_RUN` event, `"mode": "seed_tree"`, carries
    Task 3's counter names (`created_concept`, `created_lesson`,
    `concept_updates`, `placement_rejected`) alongside this mode's own
    counts, even though several are structurally always 0 here (seed_tree
    never creates a lesson page or accretes onto an existing node) — kept for
    dashboard/counter-name parity with wrap's concept-routing metrics.

    Behavior 7: `_apply_concept_create` already calls `_ensure_hub` for its
    leaf and parent directories internally (Task 3) — no extra hub call is
    needed here; the gap this task closes is `apply_candidates`'s plain
    lesson-create path, fixed above.
    """
    watermark_before = read_seed_tree_watermark(project)

    try:
        taxonomy = load_taxonomy(project)
    except TaxonomyError:
        collect.record(collect.KIND_DISTILLER_RUN, {
            "mode": "seed_tree", "project": project,
            "blind": _NO_TAXONOMY_REFUSAL,
            "candidates": 0, "applied": 0, "annotated": 0, "held": 0,
            "suggested": 0, "gated_out": 0, "refused": 0, "duplicates": 0,
            "capped_remainder": 0, "created_concept": 0, "created_lesson": 0,
            "concept_updates": 0, "placement_rejected": 0,
            "watermark_before": watermark_before, "watermark_after": watermark_before,
        })
        return {
            "blind": _NO_TAXONOMY_REFUSAL,
            "applied": [], "annotated": [], "held": [], "suggested": [],
            "gated_out": [], "refused": [], "duplicates": [],
            "capped_remainder": 0,
            "watermark_before": watermark_before, "watermark_after": watermark_before,
        }

    write_cap = cap if cap is not None else WRITE_CAP
    batch = seed_tree_batch(project, watermark_before)
    taxonomy_block = render_block(taxonomy)
    run_session = f"seed-tree-{project}-{date.today().isoformat()}"

    applied: list[dict] = []
    annotated: list[dict] = []
    held: list[dict] = []
    suggested: list[dict] = []
    gated_out: list[dict] = []
    refused: list[dict] = []
    duplicates: list[dict] = []
    capped_remainder = 0
    placement_rejected = 0
    writes = 0
    processed_through = watermark_before

    for idx, lesson in enumerate(batch):
        if writes >= write_cap:
            capped_remainder = len(batch) - idx
            break

        body = _lesson_body(lesson["text"])
        decision = gate(body, llm_call, project=project, taxonomy=taxonomy,
                        taxonomy_block=taxonomy_block)

        is_new_leaf = False
        if decision.verdict == "durable" and decision.kind == "concept" \
                and decision.action == "create":
            try:
                is_new_leaf = classify_placement(taxonomy, decision.placement) == "new-leaf"
            except TaxonomyError:
                is_new_leaf = False

        if not is_new_leaf:
            if decision.verdict == "durable" and decision.kind == "concept":
                placement_rejected += 1
            gated_out.append({"page": lesson["page"], "kind": decision.kind,
                              "verdict": decision.verdict})
            processed_through = lesson["ren_ts"]
            continue

        try:
            concept_result = _apply_concept_create(body, decision, project, run_session)
        except SecretsFound as exc:
            refused.append({"page": lesson["page"], "reason": str(exc)})
            processed_through = lesson["ren_ts"]
            continue

        if concept_result["status"] == "applied":
            applied.append({"page": concept_result["page"], "qid": concept_result["qid"],
                            "write_id": concept_result["write_id"],
                            "op": concept_result["op"]})
            writes += 1
            if concept_result["schema_suggestion"]:
                suggested.append(concept_result["schema_suggestion"])

            lastseg = decision.placement.rsplit("/", 1)[-1]
            marker = f"See: [[{lastseg}]]"
            if marker in lesson["text"]:
                # Already annotated (watermark-reset re-run, or the same
                # placement landed via another path) — nothing new to write.
                duplicates.append({"page": lesson["page"]})
            elif _target_trust(lesson["page"]) == "user":
                # Lesson pages are model-trust by default, but the guard
                # still applies (a human may have released/claimed one).
                entry = record_suggestion(
                    SuggestionSpec(
                        producer="distiller",
                        title=f"Annotate lesson with concept pointer: {lesson['page']}",
                        rationale=f"{lesson['page']} is human-authored (trust=user)",
                        evidence={"page": lesson["page"], "placement": decision.placement},
                        kind="page_write",
                        payload={"op": "UPDATE", "page": lesson["page"],
                                 "append": f"\n{marker}\n"},
                        fingerprint=f"seed-tree-annotate:{project}:{lesson['page']}",
                    )
                )
                suggested.append({"page": lesson["page"],
                                  "sid": entry["sid"] if entry else None})
            else:
                annotate_content = lesson["text"].rstrip("\n") + f"\n{marker}\n"
                try:
                    a_entry, a_prov = propose_and_apply(Proposal(
                        op="UPDATE", page=lesson["page"], content=annotate_content,
                        reason=f"concept-tree routing: see {decision.placement}",
                        producer="distiller", writer="llm-auto", session=run_session,
                    ))
                except SecretsFound as exc:
                    refused.append({"page": lesson["page"], "reason": str(exc)})
                else:
                    if a_prov is not None:
                        annotated.append({"page": lesson["page"], "target": decision.placement,
                                          "qid": a_entry.qid, "write_id": a_prov.write_id})
                        writes += 1
                    elif a_entry.status == NOOP_DUPLICATE:
                        duplicates.append({"page": lesson["page"]})
                    else:
                        held.append({"qid": a_entry.qid, "page": lesson["page"],
                                     "conflicts": a_entry.conflicts})
        elif concept_result["status"] == "unchanged":
            duplicates.append({"page": concept_result["page"]})
        else:  # "held"
            held.append({"qid": concept_result["qid"], "page": concept_result["page"],
                         "conflicts": concept_result["conflicts"]})

        processed_through = lesson["ren_ts"]

    watermark_after = processed_through
    if watermark_after and watermark_after != watermark_before:
        write_seed_tree_watermark(project, watermark_after)

    created_concept = len(applied)
    collect.record(collect.KIND_DISTILLER_RUN, {
        "run_session": run_session, "mode": "seed_tree", "project": project,
        "blind": None,
        "candidates": len(batch), "applied": len(applied),
        "annotated": len(annotated), "held": len(held),
        "suggested": len(suggested), "gated_out": len(gated_out),
        "refused": len(refused), "duplicates": len(duplicates),
        "capped_remainder": capped_remainder,
        "created_concept": created_concept, "created_lesson": 0,
        "concept_updates": 0, "placement_rejected": placement_rejected,
        "watermark_before": watermark_before, "watermark_after": watermark_after,
    })

    return {
        "blind": None,
        "applied": applied, "annotated": annotated, "held": held,
        "suggested": suggested, "gated_out": gated_out, "refused": refused,
        "duplicates": duplicates, "capped_remainder": capped_remainder,
        "watermark_before": watermark_before, "watermark_after": watermark_after,
    }
