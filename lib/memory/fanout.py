"""Write-time fan-out (spec 2026-09-04 §5).

Karpathy's ingest "updates relevant entity and concept pages across the
wiki" — 10-15 pages per source. This module is that step: after a durable
item lands under `projects/<slug>/knowledge/`, rank the project's other
knowledge pages against it, ask ONE classifier-class call which of them
should now mention it, and apply every verdict through the write door.

The candidate count IS the bound on edits (§12 Q2) — a second cap would
only discard verdicts the classifier already made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Final

from lib import ren_paths
from lib.adapter.worker import WorkerOutputError, parse_worker_json
from lib.instrument import collect
from lib.memory import quarantine
from lib.memory.links import (
    CONCEPT_SPLIT_BULLETS,
    append_facts_bullet,
    build_link_index,
    count_facts_bullets,
    parse_page_links,
    upsert_related,
)
from lib.memory.page_types import _is_folder_note_hub
from lib.memory.queue import NOOP_DUPLICATE, Proposal, propose_and_apply
from lib.suggestions import SuggestionSpec
from lib.suggestions import record as record_suggestion

FANOUT_CANDIDATES: Final[int] = 12
#: Lines of each candidate shown to the classifier.
_CANDIDATE_HEAD_LINES: Final[int] = 40
_VALID_EDGES: Final[frozenset[str]] = frozenset({"relate", "fact", "none"})


@dataclass(frozen=True)
class LandedItem:
    page: str        # wiki-relative posix path of the page that just landed
    title: str
    text: str
    write_id: str | None


@dataclass(frozen=True)
class FanoutResult:
    applied: list[dict] = field(default_factory=list)
    held: list[dict] = field(default_factory=list)
    suggested: list[dict] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    verdicts: dict[str, int] = field(default_factory=lambda: {"relate": 0, "fact": 0, "none": 0})
    unknown_reason: str | None = None


def _stem(rel: str) -> str:
    return Path(rel).stem


def _trust(text: str) -> str | None:
    """`ren_trust` from a page's frontmatter, or None. Cheap line scan — the
    stamp is written by the write door, always on its own line."""
    for line in text.splitlines()[:20]:
        if line.startswith("ren_trust:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def _is_lesson(rel: str) -> bool:
    parts = Path(rel).parts
    return len(parts) >= 2 and parts[-2] == "lessons"


def _select_candidates(
    wiki_root: Path, item: LandedItem, project: str, limit: int
) -> list[tuple[str, str]]:
    """Top-`limit` `(rel_path, text)` pairs, ranked by recall's own scorer
    (§5.1 — the recall scorer, not a new one). Excluded: the item's own
    page, hubs, `lessons/lessons.md`, quarantined pages, and pages already
    in the item's `## Related`.

    The `skills.recall.lib` import is FUNCTION-LOCAL on purpose: `lib` must
    not import `skills` at module-import time (recall itself imports `lib`,
    and a top-level import would make the cycle load-order dependent).
    """
    from skills.recall.lib import _score_content, tokenize_query  # noqa: PLC0415

    index = build_link_index(wiki_root, project=project)
    item_text = index.pages.get(item.page, "")
    already = {stem for stem, _ in parse_page_links(item_text).related}
    tokens = tokenize_query(f"{item.title} {item.text}")

    scored: list[tuple[float, str, str]] = []
    prefix = f"projects/{project}/knowledge/"
    for rel, text in index.pages.items():
        if rel == item.page or not rel.startswith(prefix):
            continue
        parts = Path(rel).parts
        if _is_folder_note_hub(parts) or Path(rel).name == "lessons.md":
            continue
        if quarantine.is_quarantined(text):
            continue
        if _stem(rel) in already:
            continue
        scored.append((_score_content(text, tokens), rel, text))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [(rel, text) for _score, rel, text in scored[:limit] if _score > 0]


def build_fanout_prompt(item: LandedItem, candidates: list[tuple[str, str]]) -> str:
    """One classifier-class prompt (§5.2). Same shape as the wrap
    classifier's: strict JSON out, no prose, one verdict per candidate."""
    blocks = []
    for rel, text in candidates:
        head = "\n".join(text.splitlines()[:_CANDIDATE_HEAD_LINES])
        blocks.append(f"### {_stem(rel)}\n(path: {rel})\n{head}")
    joined = "\n\n".join(blocks)
    return (
        "A new knowledge page just landed in a wiki. Decide, for each existing\n"
        "page below, whether it should now mention the new one.\n\n"
        f"NEW PAGE: {item.title}\n{item.text}\n\n"
        f"EXISTING PAGES:\n{joined}\n\n"
        "Return ONLY this JSON, no prose, no fence:\n"
        '{"verdicts": [{"page": "<stem exactly as given>", '
        '"edge": "relate" | "fact" | "none", '
        '"reason": "<one clause saying why they are related>", '
        '"fact": "<one bullet to append — ONLY when edge is fact>"}]}\n'
        'Use "fact" only when the new page states something the existing page\n'
        'should record as its own fact; use "relate" for a plain cross-link;\n'
        'use "none" when they are unrelated.'
    )


def _parse_verdicts(raw: str, by_stem: dict[str, str]) -> list[dict]:
    """Strict parse. ANY failure raises `ValueError`, which the caller turns
    into `unknown_reason` with zero edits — fail-closed, like every other
    classifier in RenOS."""
    data = parse_worker_json(raw)
    if not isinstance(data, dict) or not isinstance(data.get("verdicts"), list):
        raise ValueError("output has no 'verdicts' list")
    out: list[dict] = []
    for v in data["verdicts"]:
        if not isinstance(v, dict):
            raise ValueError(f"verdict is not an object: {v!r}")
        page, edge, reason = v.get("page"), v.get("edge"), v.get("reason")
        if not isinstance(page, str) or page not in by_stem:
            raise ValueError(f"verdict names an unknown page: {page!r}")
        if edge not in _VALID_EDGES:
            raise ValueError(f"invalid edge {edge!r} for {page!r}")
        if edge != "none" and not (isinstance(reason, str) and reason.strip()):
            raise ValueError(f"verdict for {page!r} has no reason")
        if edge == "fact" and not (isinstance(v.get("fact"), str) and v["fact"].strip()):
            raise ValueError(f"fact verdict for {page!r} carries no fact")
        out.append(v)
    return out


def _suggest_split(page: str, session: str, producer: str, result: FanoutResult) -> None:
    """Raise the oversized-concept-node split suggestion (spec §5.3).

    Deliberately the SAME `wrap-split:{page}` fingerprint wrap's own
    concept-update branch uses: the finding is identical ("this node is too
    big"), so it must dedup against wrap's, not sit beside it as a second
    nag. `lib.suggestions.record` returns None for a fingerprint already
    pending or decided, which is what makes a second fan-out over the same
    page a no-op.
    """
    entry = record_suggestion(SuggestionSpec(
        producer=producer,
        title=f"Split large concept node: {page}",
        rationale=f"{page} has more than {CONCEPT_SPLIT_BULLETS} Facts bullets",
        evidence={"page": page, "session": session},
        kind="structured_action",
        payload={"action": "split_concept_node", "page": page},
        fingerprint=f"wrap-split:{page}",
    ))
    if entry is not None:
        result.suggested.append({"page": page, "sid": entry["sid"]})


def _write(page: str, content: str, session: str, producer: str, reason: str,
           result: FanoutResult) -> None:
    entry, prov = propose_and_apply(Proposal(
        op="UPDATE", page=page, content=content, reason=reason,
        producer=producer, writer="llm-auto", session=session,
    ))
    if prov is not None:
        result.applied.append({"qid": entry.qid, "write_id": prov.write_id, "page": page})
    elif entry.status != NOOP_DUPLICATE:
        result.held.append({"qid": entry.qid, "page": page, "conflicts": entry.conflicts})


def fan_out(
    item: LandedItem,
    project: str,
    session: str,
    llm_call: Callable[[str], str],
    *,
    producer: str = "wrap",
    candidates: int = FANOUT_CANDIDATES,
) -> FanoutResult:
    """Fan one landed item out across the pages that should now mention it.

    Never raises: a walk/read failure, a classifier failure, a malformed
    verdict, or a failure partway through applying the verdicts (an
    unreadable item page, a raised `propose_and_apply`/`record_suggestion`
    call) all come back as `unknown_reason` (§9). Edits already applied
    before such a failure stay in `applied` — they are queued and
    revertible, never rolled back here. One `fanout_event` is recorded per
    call, always.
    """
    result = FanoutResult()
    wiki_root = ren_paths.wiki_root()
    try:
        picked = _select_candidates(wiki_root, item, project, candidates)
    except Exception as exc:  # noqa: BLE001 - fail-closed: candidate selection failure is Unknown, never a raise (it walks the wiki AND runs recall's scorer through a function-local import — spec §9)
        result = FanoutResult(unknown_reason=f"fan-out candidate selection failed: {exc}")
        _record_event(item, result)
        return result

    result.candidates.extend(rel for rel, _ in picked)
    if not picked:
        _record_event(item, result)
        return result

    by_stem = {_stem(rel): rel for rel, _ in picked}
    texts = {rel: text for rel, text in picked}
    try:
        verdicts = _parse_verdicts(llm_call(build_fanout_prompt(item, picked)), by_stem)
    except (ValueError, WorkerOutputError, TypeError) as exc:
        result = FanoutResult(candidates=result.candidates,
                              unknown_reason=f"fan-out classifier output rejected: {exc}")
        _record_event(item, result)
        return result
    except Exception as exc:  # noqa: BLE001 - fail-closed: any classifier failure is Unknown, never a guess
        result = FanoutResult(candidates=result.candidates,
                              unknown_reason=f"fan-out classifier call failed: {exc}")
        _record_event(item, result)
        return result

    try:
        item_text = (wiki_root / item.page).read_text(encoding="utf-8")
        reason = f"fanout: {item.write_id}"
        item_stem = _stem(item.page)

        for verdict in verdicts:
            rel = by_stem[verdict["page"]]
            edge, clause = verdict["edge"], (verdict.get("reason") or "").strip()
            if edge == "none":
                result.verdicts["none"] += 1
                continue
            # §12 Q1: lessons are episodic and accrete badly — a `fact`
            # verdict on a `lessons/` page is downgraded to `relate`, never
            # dropped.
            if edge == "fact" and _is_lesson(rel):
                edge = "relate"
            result.verdicts[edge] += 1

            target_text = texts[rel]
            new_target = upsert_related(target_text, item_stem, clause)
            split_due = False
            if edge == "fact":
                new_target = append_facts_bullet(new_target, verdict["fact"])
                # Spec §5.3: "the 40-bullet split suggestion fires exactly as
                # it does today" — today's rule (wrap's concept-update
                # branch) is a strict `>` check AFTER the append, so a node
                # at exactly the threshold crosses it on this bullet and
                # fires.
                split_due = count_facts_bullets(new_target) > CONCEPT_SPLIT_BULLETS

            if _trust(target_text) == "user":
                # Same hold as the human-owned schema.md splice in 0.8.5:
                # the edit becomes a suggestion, the forward edge still
                # lands.
                entry = record_suggestion(SuggestionSpec(
                    producer=producer,
                    title=f"Fan-out edit on a human-authored page: {rel}",
                    rationale=f"{item.page} landed and relates to {rel}: {clause}",
                    evidence={"page": rel, "item": item.page, "session": session},
                    kind="page_write",
                    payload={"op": "UPDATE", "page": rel, "content": new_target,
                             "reason": reason, "producer": producer,
                             "writer": "llm-auto", "session": session},
                    fingerprint=f"fanout-edit:{item.page}:{rel}",
                ))
                result.suggested.append({"page": rel, "sid": entry["sid"] if entry else None})
            else:
                _write(rel, new_target, session, producer, reason, result)

            if split_due:
                _suggest_split(rel, session, producer, result)

            item_text = upsert_related(item_text, _stem(rel), clause)

        if item_text != (wiki_root / item.page).read_text(encoding="utf-8"):
            _write(item.page, item_text, session, producer, reason, result)
    except Exception as exc:  # noqa: BLE001 - fail-closed: the apply phase (item-page read, each write door call, each suggestion record) must never raise into the landing (spec §9); edits already applied stay listed — they are queued and revertible, never rolled back here
        n = len(result.applied)
        result = FanoutResult(
            applied=result.applied, held=result.held, suggested=result.suggested,
            candidates=result.candidates, verdicts=result.verdicts,
            unknown_reason=f"fan-out apply failed after {n} edits: {exc}",
        )

    _record_event(item, result)
    return result


def _record_event(item: LandedItem, result: FanoutResult) -> None:
    collect.record(collect.KIND_FANOUT_EVENT, {
        "item": item.page,
        "candidates": len(result.candidates),
        "verdicts": result.verdicts,
        "applied": len(result.applied),
        "held": len(result.held),
        "unknown_reason": result.unknown_reason,
    })


__all__ = [
    "FANOUT_CANDIDATES",
    "FanoutResult",
    "LandedItem",
    "build_fanout_prompt",
    "fan_out",
]
