"""
skills.wrap library — internal implementation for /ren:wrap (Task 4.1, RenOS
0.2 Phase 4).

Public entry: `wrap_session(narrative_md, durable_items, session, llm_call=None,
project=None, cwd=None) -> dict`.

Per spec §3.1 producer 1 (L1 session continuity) + §3.8 (unified wrap
surface) + §3.10 (quarantine): the live Claude session (SKILL.md) writes the
narrative and proposes candidate durable items; this module is the part that
actually touches the single write-queue (Task 2.1) and the classifier gate
(`.classifier.gate`).

Per the v2.2 two-plane governance pivot (data plane auto-applies), both the
L1 narrative and gated-durable items go through the single data-plane door,
`lib.memory.queue.propose_and_apply`, tagged `writer="llm-auto"`, which the
queue's auto-quarantine wiring quarantines on write — it is data, not
instruction, until a human reviews it. One-step revert is what makes
"auto-apply" safe here. `propose_and_apply` itself holds an entry pending
(rather than applying) when the target is instruction-plane (`global/`) or a
`contradicts` conflict was detected — those cases surface in this module's
`held` list for a human to reason about; items gated out as non-durable, or
refused for a planted secret, never reach the queue at all.

Donor `skills/wrap/lib/{classifier.py,types.py,diff_plan.py}` is NOT ported
wholesale — its CONTEXT.md-rewrite / diff_plan machinery assumed direct wiki
writes, which 0.2's single write-queue makes obsolete (every write, including
L1, goes through `lib.memory.queue` now). Only the classifier's prompt/parse
DISCIPLINE was adapted (see `.classifier`), reshaped for the different
question this module asks per item ("is this durable?") rather than donor's
whole-session multi-label classification.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Callable

import yaml

from lib import ren_paths
from lib.adapter.worker import parse_worker_json
from lib.instrument import collect
from lib.memory import queue
from lib.memory.judge import JUDGE_MIN_CONFIDENCE, JUDGE_PAIR_CAP, judge_pairs
from lib.memory.lifecycle import consolidate_duplicates, run_decay
from lib.memory.queue import Proposal, propose_and_apply
from lib.memory.scrub import SecretsFound
from lib.memory.semantics import shortlist_pairs
from lib.suggestions import expire_stale_pending, prune_decided
from lib.suggestions import record as record_suggestion
from lib.suggestions.producers import (
    doctrine_shaping,
    promotion_candidates,
    wiki_health_critical,
)

from .classifier import gate

_SLUG_WORD_RE = re.compile(r"[a-z0-9]+")
_PREVIEW_MAX_CHARS = 100
_PREVIEW_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)


def _content_preview(content: str | None) -> str:
    """First meaningful body line of a proposal's content — what the friend
    is actually saying yes/no to. Skips frontmatter and the quarantine
    banner; truncates to keep the wrap screen one legible screen."""
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


def _slugify(text: str, *, max_words: int = 8) -> str:
    """Kebab-case slug derived from `text`'s first few significant words.
    Falls back to "item" if nothing alphanumeric is found (e.g. all-emoji or
    all-punctuation input) so a durable item never fails to queue purely
    because it produced an empty page name."""
    words = _SLUG_WORD_RE.findall(text.lower())
    return "-".join(words[:max_words]) or "item"


def _judge_semantic_findings(
    focus_pages: list[str], llm_call: Callable[[str], str] | None
) -> list[dict]:
    """Judge (Task 4) the shortlist (Task 11) restricted to `focus_pages` —
    this session's applied writes — and return informational findings for
    the wrap screen only (0.5.3's consolidation is the future apply
    consumer; nothing here writes anything).

    Fail-closed like every other wrap sub-step: `focus_pages` empty means
    nothing was written this session, so there's nothing to compare and
    `llm_call` is never invoked; any exception anywhere in this path
    (shortlist scan, page read, judging) degrades to `[]` rather than
    raising — `judge_pairs` itself is already fail-closed per pair, but the
    shortlist scan and page reads are plain filesystem code with no such
    guarantee, so the whole function is wrapped for the same "wrap must
    never crash" discipline as the rest of this module.
    """
    if not focus_pages:
        return []

    try:
        root = ren_paths.wiki_root()
        pairs = shortlist_pairs(root, focus_pages=focus_pages)
        if not pairs:
            return []

        texts = [
            (
                (root / pair["page"]).read_text(encoding="utf-8", errors="replace"),
                (root / pair["with"]).read_text(encoding="utf-8", errors="replace"),
            )
            for pair in pairs
        ]
        verdicts = judge_pairs(texts, llm_call, cap=JUDGE_PAIR_CAP)

        findings: list[dict] = []
        for pair, verdict in zip(pairs, verdicts):
            if verdict is None or verdict.kind == "unrelated":
                continue
            if verdict.confidence < JUDGE_MIN_CONFIDENCE:
                continue
            findings.append(
                {
                    "page": pair["page"],
                    "with": pair["with"],
                    "verdict": verdict.kind,
                    "confidence": verdict.confidence,
                    "reason": verdict.reason,
                }
            )
        return findings
    except Exception:  # noqa: BLE001 - semantic findings are informational, must never break wrap
        return []


_OVERVIEW_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_OVERVIEW_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_OVERVIEW_PROMPT_TEMPLATE: str = """\
You maintain a project's overview page across sessions. Decide whether this
session's narrative represents a MATERIAL change to the project's stage,
direction, or key facts — not routine chatter, not a restatement of what the
overview already says.

Current overview body (may be empty/placeholder if none exists yet):
---
{current_overview}
---

This session's narrative:
---
{narrative}
---

If material_change is true, write a full replacement overview body: what the
project is, its current stage, and 3-5 load-bearing facts. Target <=600
tokens - a thesis, not a novel. If material_change is false, "overview" is
ignored and may be empty.

Output JSON ONLY (no surrounding prose, no code fence). Schema:

{{"material_change": true | false, "overview": "<full replacement body>"}}
"""


def _split_overview_frontmatter(text: str) -> tuple[dict, str]:
    """Return `(frontmatter_dict, body)` for `text`. Any parse failure (bad
    YAML, no frontmatter) degrades to an empty dict rather than raising —
    frontmatter here is only used to carry a few cosmetic fields (title,
    created date) forward across overview UPDATEs, never load-bearing."""
    match = _OVERVIEW_FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        data = None
    return (data if isinstance(data, dict) else {}), text[match.end():]


def _is_skeleton_or_empty_body(body: str) -> bool:
    """True if `body` (frontmatter already stripped) carries no real content
    of its own — i.e. it's the shipped skeleton (a heading plus an HTML
    comment) or genuinely empty/whitespace. Same idea as `read_identity`'s
    skeleton check (Task 1), adapted for overview's comment-only body shape
    rather than a byte-for-byte template match."""
    without_comments = _OVERVIEW_HTML_COMMENT_RE.sub("", body)
    lines = [line.strip() for line in without_comments.splitlines() if line.strip()]
    if not lines:
        return True
    return len(lines) == 1 and lines[0].startswith("#")


def _build_overview_content(existing_text: str, overview_body: str) -> str:
    """Build the full page content (frontmatter + body) for an overview
    ADD/UPDATE. Carries `title`/`created`/`framework_version` forward from
    the existing page's frontmatter when present (a fresh CREATE falls back
    to the skeleton template's defaults); `updated` is always today.
    `ren_*` provenance keys are stamped downstream by `write_apply`, not
    here."""
    fm, _ = _split_overview_frontmatter(existing_text)
    today = date.today().isoformat()
    lines = [
        "---",
        f'title: "{fm.get("title", "Project Overview")}"',
        "type: overview",
        "schema_version: 1",
        f'framework_version: "{fm.get("framework_version") or ren_paths.framework_version()}"',
        f"created: {fm.get('created', today)}",
        f"updated: {today}",
        "---",
        "",
    ]
    return "\n".join(lines) + overview_body.strip() + "\n"


def maintain_overview(
    project: str,
    session: str,
    narrative: str,
    llm_call: Callable[[str], str] | None,
) -> dict | None:
    """Maintain `projects/<project>/overview.md`: CREATE it when absent or
    still skeleton-only, UPDATE it when the LLM judges this session's
    narrative a material change to stage/direction/key facts. Never writes
    on a merely-session-only narrative, and never writes at all if the LLM
    call or its output can't be trusted (fail-closed, per anti-Goodhart
    doctrine — an LLM error must never silently produce no write AND no
    signal; a `KIND_OVERVIEW_EVENT` "skipped" event is recorded so
    `wrap_session` can surface it on the wrap report rather than the
    outcome vanishing into an indistinguishable no-op).

    Returns the queue-apply result (`{"qid", "write_id", "page"}`) when a
    write actually landed; `None` when nothing changed (no material change)
    or the LLM path failed. `propose_and_apply` holding the entry pending
    instead of auto-applying (shouldn't happen for a data-plane `projects/`
    target, but treated the same as "not written" if it ever does) also
    returns `None`.
    """
    page = f"projects/{project}/overview.md"
    path = ren_paths.safe_join(ren_paths.wiki_root(), page)

    existing_text = ""
    exists = path.is_file()
    if exists:
        try:
            existing_text = path.read_text(encoding="utf-8")
        except OSError:
            existing_text = ""

    _, existing_body = _split_overview_frontmatter(existing_text)
    prompt = _OVERVIEW_PROMPT_TEMPLATE.format(
        current_overview=existing_body.strip() if not _is_skeleton_or_empty_body(existing_body) else "(none yet)",
        narrative=narrative,
    )

    if llm_call is None:
        collect.record(
            collect.KIND_OVERVIEW_EVENT,
            {"event": "skipped", "reason": "no llm_call available"},
        )
        return None

    try:
        raw = llm_call(prompt)
        if not isinstance(raw, str):
            raise ValueError(f"llm_call must return str, got {type(raw).__name__}")
        data = parse_worker_json(raw)
        if not isinstance(data, dict):
            raise ValueError(f"overview output must be a JSON object, got {type(data).__name__}")
        material_change = data.get("material_change")
        if not isinstance(material_change, bool):
            raise ValueError(f"'material_change' must be a bool, got {material_change!r}")
        overview_body = data.get("overview")
        if material_change and (not isinstance(overview_body, str) or not overview_body.strip()):
            raise ValueError("'overview' must be a non-empty string when material_change is true")
    except Exception as exc:  # noqa: BLE001 - fail-closed: never write, never stay silent
        collect.record(
            collect.KIND_OVERVIEW_EVENT,
            {"event": "skipped", "reason": str(exc)},
        )
        return None

    if not material_change:
        return None

    content = _build_overview_content(existing_text, overview_body)
    entry, prov = propose_and_apply(
        Proposal(
            op="UPDATE" if exists else "ADD",
            page=page,
            content=content,
            reason="overview maintenance (material change)",
            producer="wrap",
            writer="llm-auto",
            session=session,
        )
    )
    if prov is None:
        return None
    return {"qid": entry.qid, "write_id": prov.write_id, "page": page}


def wrap_session(
    narrative_md: str,
    durable_items: list[str],
    session: str,
    llm_call: Callable[[str], str] | None = None,
    project: str | None = None,
    cwd: Path | None = None,
) -> dict:
    """Run the wrap write path for one session close-out.

    Returns a dict:
      - "l1_qid": qid of the (already applied + quarantined) L1 entry
      - "applied": [{"qid", "write_id", "page"}] for items gated "durable"
        that auto-applied through the data-plane door
      - "held": [{"qid", "page", "conflicts"}] for items gated "durable" that
        `propose_and_apply` held pending instead of applying (instruction-
        plane target, or a detected `contradicts` conflict — a human/the live
        session needs to reason about these)
      - "gated_out": [{"item", "verdict", "reason"}] for non-durable items
      - "refused": [{"item", "reason"}] for durable items the queue itself
        refused (currently: a planted secret — `SecretsFound` propagates from
        `lib.memory.scrub` via `queue.propose`'s door-side scrub, and is
        caught here so ONE bad item doesn't crash the whole wrap)
      - "fail_closed": True if the classifier gate fell back to the
        deterministic path (due to an LLM error) for at least one durable
        candidate during this call
      - "semantic_findings": [{"page", "with", "verdict", "confidence",
        "reason"}] — LLM-judged (Task 4) verdicts over the shortlist (Task
        11) restricted to this session's applied writes (`applied`'s pages).
        INFORMATIONAL ONLY — rendered on the wrap screen, nothing here
        writes or applies anything; that's 0.5.3's consolidation. `[]` when
        nothing was applied this session, `llm_call` is `None`, or judging
        fails for any reason (fail-closed, never raises)
      - "decayed": [{"archive_page", "add_write_id", "delete_write_id"}] —
        `lib.memory.lifecycle.run_decay`'s moves for this wrap's close-out
        (Task 17): up to `DECAY_MAX_PER_WRAP` stale, unrecalled, non-salient
        data-plane pages archived (never deleted, revertible). Isolated like
        `semantic_findings` — any exception anywhere in the decay path
        degrades to `[]` rather than raising; wrap must never fail to close
        out a session because of a housekeeping sweep.
      - "consolidated": [{"status": "merged", "archived", "archive_page",
        "merged_into", "write_id"} | {"status": "partial", "archived",
        "archive_page", "update_failed", "error"}] —
        `lib.memory.lifecycle.consolidate_duplicates`'s moves for this
        wrap's close-out (Task 18): up to `CONSOLIDATE_MAX_PER_WRAP`
        judge-confirmed (`semantic_findings`, this same call) duplicate
        pairs auto-merged on the data plane — the older page archives, the
        newer carries a `Merged from [[...]]` provenance line. A `"partial"`
        entry means the older page archived but the newer-page UPDATE then
        failed (concurrent write); it is not silently dropped. Isolated
        like `decayed`; degrades to `[]` rather than raising.
      - "overview": one of "created" | "updated" | "unchanged" | "skipped" —
        `maintain_overview`'s (Task 3, 0.5.5) outcome for
        `projects/<project>/overview.md`, called right after the L1 write.
        "created"/"updated" mean a write landed (page was absent/skeleton vs.
        already had real content); "unchanged" means the LLM judged this
        session's narrative not a material change; "skipped" means either no
        `project` is in scope for this wrap, or the LLM call/output failed
        and `maintain_overview` fail-closed (never silent — always one of
        these four values, never omitted).

    `project` (codex D4): when the wrap is scoped to a project, the L1 page
    is written to `projects/<project>/l1/session-<id>.md`, the EXACT path
    `hooks.wake-up.wakeup.read_l1` reads for that project (`project_dir /
    "l1"`, where `project_dir = wiki_root / "projects" / project`) — mirrors
    that resolution exactly rather than reimplementing it. `None` (the
    default) preserves the original global `l1/session-<id>.md` path.

    `cwd` (codex D4 live wiring): the live `/ren:wrap` invocation has no
    reason to know its own project slug — SKILL.md's instructions call
    `wrap_session(narrative_md, durable_items, session, llm_call=...)` with
    no `project=` kwarg at all, same as every other caller. So when
    `project` is not given explicitly, this derives it from `cwd` (defaults
    to `Path.cwd()`, the real process cwd at wrap time — the live session
    IS running with its cwd inside the project directory, exactly the signal
    `hooks/wake-up/ren-wake-up.py` falls back to via `event.get("cwd") or
    os.getcwd()`) via `lib.ren_paths.detect_project` — the SAME shared
    helper `hooks.wake-up.wakeup.compose_wake_up_context` uses to resolve
    its read-side project. Write and read paths can now never drift onto
    different project slugs for the same cwd. An explicit `project=` kwarg
    (as tests use) still overrides detection entirely.
    """
    if project is None:
        project = ren_paths.detect_project(cwd or Path.cwd(), ren_paths.wiki_root())

    l1_page = (
        f"projects/{project}/l1/session-{session}.md"
        if project
        else f"l1/session-{session}.md"
    )
    l1_entry, _ = propose_and_apply(
        Proposal(
            op="ADD",
            page=l1_page,
            content=narrative_md,
            reason="end-of-session L1 narrative summary",
            producer="wrap",
            writer="llm-auto",
            session=session,
        )
    )

    overview_status = "skipped"
    if project:
        overview_path = ren_paths.safe_join(
            ren_paths.wiki_root(), f"projects/{project}/overview.md"
        )
        overview_had_real_content = False
        if overview_path.is_file():
            try:
                _, existing_body = _split_overview_frontmatter(
                    overview_path.read_text(encoding="utf-8")
                )
                overview_had_real_content = not _is_skeleton_or_empty_body(existing_body)
            except OSError:
                overview_had_real_content = False

        ov_events_before = collect.read(kind=collect.KIND_OVERVIEW_EVENT)
        overview_result = maintain_overview(project, session, narrative_md, llm_call)
        ov_events_after = collect.read(kind=collect.KIND_OVERVIEW_EVENT)
        new_ov_events = ov_events_after[len(ov_events_before):]
        overview_skipped = any(e.get("event") == "skipped" for e in new_ov_events)

        if overview_result is not None:
            overview_status = "updated" if overview_had_real_content else "created"
        elif overview_skipped:
            overview_status = "skipped"
        else:
            overview_status = "unchanged"

    events_before = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)

    applied: list[dict] = []
    held: list[dict] = []
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
            entry, prov = propose_and_apply(
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

        if prov is not None:
            applied.append({"qid": entry.qid, "write_id": prov.write_id, "page": page})
        else:
            held.append({"qid": entry.qid, "page": page, "conflicts": entry.conflicts})

    events_after = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    new_events = events_after[len(events_before):]
    fail_closed = any(e.get("event") == "fail_closed" for e in new_events)

    semantic_findings = _judge_semantic_findings(
        [a["page"] for a in applied], llm_call
    )

    try:
        decayed = run_decay(session)
    except Exception:  # noqa: BLE001 - a housekeeping sweep must never fail wrap close-out
        decayed = []

    try:
        consolidated = consolidate_duplicates(semantic_findings, session)
    except Exception:  # noqa: BLE001 - a housekeeping sweep must never fail wrap close-out
        consolidated = []

    return {
        "l1_qid": l1_entry.qid,
        "applied": applied,
        "held": held,
        "gated_out": gated_out,
        "refused": refused,
        "fail_closed": fail_closed,
        "semantic_findings": semantic_findings,
        "decayed": decayed,
        "consolidated": consolidated,
        "overview": overview_status,
    }


def _run_wiki_health_sweep() -> dict:
    """Run `skills.wiki_health.lib.sweep()` (imported via importlib for the
    hyphen in `skills/wiki-health`, same pattern as
    `hooks/wake-up/wakeup/__init__.py::rank_extras`).

    Wrap's close-out does NOT otherwise run the wiki-health sweep (it's
    normally a live-session-invoked auditor per `skills/wiki-health/SKILL.md`)
    — this is the one place `wiki_health_critical`'s input gets produced at
    wrap time. Left as its own function so `harvest_suggestions` can isolate
    a sweep failure from the three producer calls."""
    import importlib

    wiki_health_lib = importlib.import_module("skills.wiki-health.lib")
    return wiki_health_lib.sweep()


def harvest_suggestions(session: str, cwd: str | None = None) -> int:
    """Run the three wrap-time suggestion producers (Task 17's
    `promotion_candidates`, `doctrine_shaping`, `wiki_health_critical`) and
    record each `SuggestionSpec` via `lib.suggestions.record`. The
    retrospective producer runs inside `/ren:retrospective` (Task 16), not
    here.

    Each producer call (and the wiki-health sweep it depends on) is isolated
    in its own try/except — one producer failing must never starve the
    others. Never raises.

    Returns the count of `record()` calls that returned non-None (a spec
    whose fingerprint was already pending/decided returns None and doesn't
    count — see `lib.suggestions.record`'s never-re-nag contract).

    `cwd` is accepted for interface symmetry with other wrap-time hooks but
    unused: none of the three producers are cwd-scoped (wiki state is
    process-global via `lib.ren_paths`, not per-directory).
    """
    del cwd  # unused — see docstring

    try:
        prune_decided()
    except Exception:  # noqa: BLE001 - store maintenance must not starve the producers
        pass

    try:
        expire_stale_pending()
    except Exception:  # noqa: BLE001 - store maintenance must not starve the producers
        pass

    specs: list = []

    try:
        specs.extend(promotion_candidates())
    except Exception:  # noqa: BLE001 - one producer's failure must not starve the others
        pass

    try:
        specs.extend(doctrine_shaping())
    except Exception:  # noqa: BLE001 - one producer's failure must not starve the others
        pass

    try:
        sweep_result = _run_wiki_health_sweep()
    except Exception:  # noqa: BLE001 - sweep failure must not starve the other producers
        sweep_result = None

    if sweep_result is not None:
        try:
            specs.extend(wiki_health_critical(sweep_result))
        except Exception:  # noqa: BLE001 - one producer's failure must not starve the others
            pass

    count = 0
    for spec in specs:
        if record_suggestion(spec) is not None:
            count += 1
    return count


def _session_queue_entries(session: str) -> list[dict]:
    """Every queue entry for `session`, regardless of status (the wrap screen
    needs BOTH pending and already-applied entries, incl. auto-tier applies).

    Reads via `queue.all_entries()` (public read API, 0.4.0) instead of
    parsing `state_dir()/queue/*.json` raw, then converts to dict so the
    presentation code below (`e["qid"]`, `e["proposal"]["page"]`, etc.) keeps
    its existing shape. Read-only; never mutates a queue entry."""
    return [
        asdict(entry)
        for entry in sorted(queue.all_entries(), key=lambda e: e.qid)
        if entry.proposal.session == session
    ]


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


def render_pending_list() -> str:
    """Every pending queue entry, ALL sessions, oldest first — the
    deterministic backing for wake-up's 'ask me to list them'. Read-only."""
    entries = queue.pending()
    if not entries:
        return "No pending suggestions."
    lines = [f"{len(entries)} pending entr{'y' if len(entries) == 1 else 'ies'} (all sessions, oldest first):"]
    for entry in entries:
        reason = entry.proposal.reason or ""
        lines.append(f"- {entry.qid} → {entry.proposal.page} — {reason}")
        preview = _content_preview(entry.proposal.content)
        if preview:
            lines.append(f"  > {preview}")
    return "\n".join(lines)


def render_wrap_screen(wrap_result: dict, session: str) -> str:
    """Render the unified end-of-wrap screen (spec §3.8 A-10 / G15): one
    legible screen naming what happened this session even though risk tiers
    fragment the underlying writes across auto-applied and pending entries.

    PURE PRESENTATION: reads queue state on disk via `_session_queue_entries`
    and the given `wrap_result` (the return value of `wrap_session`); writes
    NOTHING. Per the v2.2 two-plane pivot's conversational gate (no
    slash-command hints anywhere on this screen):
      - "What I learned" — the L1 entry's qid + one-line status.
      - "Saved this session (revertible)" — this session's entries with
        `status == "applied"` and `approved_by in ("auto-tier",
        "model-resolved")`, each with its write_id and a spoken revert hint
        ("say ... to revert" — never a slash command).
      - "Held — contradictions to resolve" — still-PENDING entries with a
        detected `contradicts` conflict; the section is OMITTED entirely
        when there are none (nothing to resolve, nothing to show). Each item
        carries a one-line content preview (`  > …`) showing what the friend
        is approving.
      - "Suggestions" — still-PENDING entries targeting an instruction-plane
        `global/` page, plus any other pending residue that isn't a
        contradiction hold; renders "- (none)" when empty. Each item carries
        a one-line content preview (`  > …`) showing what the friend is
        approving. These are resolved by asking the friend in chat (see
        SKILL.md), never by a slash command.
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
    lines.append(f"- project overview: {wrap_result.get('overview', 'skipped')}")
    lines.append("")

    # --- Saved this session (revertible) ---
    lines.append("## Saved this session (revertible)")
    saved_entries = [
        e for e in entries
        if e.get("status") == "applied" and e.get("approved_by") in ("auto-tier", "model-resolved")
    ]
    if saved_entries:
        for entry in saved_entries:
            write_id = entry.get("write_id")
            page = entry["proposal"]["page"]
            lines.append(f'- {page} (write_id={write_id}) — say "undo {write_id}" to revert')
    else:
        lines.append("- (none this session)")
    decayed = wrap_result.get("decayed") or []
    if decayed:
        n = len(decayed)
        lines.append(f"- {n} stale page{'s' if n != 1 else ''} archived — revertible")
    consolidated = wrap_result.get("consolidated") or []
    merged = [m for m in consolidated if m.get("status") != "partial"]
    partial = [m for m in consolidated if m.get("status") == "partial"]
    if merged:
        n = len(merged)
        lines.append(f"- {n} duplicate{'s' if n != 1 else ''} consolidated — revertible")
    if partial:
        n = len(partial)
        lines.append(f"- {n} consolidation{'s' if n != 1 else ''} partial — see journal")
    lines.append("")

    # --- Classify this session's still-pending entries into held/suggestions ---
    # A pending entry is a *hold* iff any conflict is a `contradicts` —
    # checked FIRST, so a contradiction-held candidate never renders as a
    # "yes"-able suggestion (that path skips recording a
    # contradiction_resolution). Every other pending entry (instruction-plane
    # global/ targets, or any other residue such as a plain pin awaiting a
    # human) lists under suggestions.
    pending_entries = [e for e in entries if e.get("status") == "pending"]
    held_entries: list[dict] = []
    suggestion_entries: list[dict] = []
    for entry in pending_entries:
        if any(c.get("kind") == "contradicts" for c in (entry.get("conflicts") or [])):
            held_entries.append(entry)
        else:
            suggestion_entries.append(entry)

    # --- Held — contradictions to resolve (omitted entirely when empty) ---
    if held_entries:
        lines.append("## Held — contradictions to resolve")
        for entry in held_entries:
            page = entry["proposal"]["page"]
            reason = entry["proposal"].get("reason", "")
            flags = _conflict_flags(entry.get("conflicts") or [])
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"- {entry['qid']} → {page} — {reason}{flag_str}")
            preview = _content_preview(entry["proposal"].get("content"))
            if preview:
                lines.append(f"  > {preview}")
        lines.append("")

    # --- Suggestions ---
    lines.append("## Suggestions")
    if suggestion_entries:
        for entry in suggestion_entries:
            page = entry["proposal"]["page"]
            reason = entry["proposal"].get("reason", "")
            flags = _conflict_flags(entry.get("conflicts") or [])
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"- {entry['qid']} → {page} — {reason}{flag_str}")
            preview = _content_preview(entry["proposal"].get("content"))
            if preview:
                lines.append(f"  > {preview}")
    else:
        lines.append("- (none)")
    lines.append("")

    # --- Possible connections (informational, judge-sourced) ---
    # Task 12: LLM-judged verdicts over this session's applied writes vs. the
    # rest of the wiki. Purely informational — omitted entirely when empty,
    # never a slash-command hint; acting on one is 0.5.3's job.
    semantic_findings = wrap_result.get("semantic_findings") or []
    if semantic_findings:
        lines.append("## Possible connections (unverified)")
        for finding in semantic_findings:
            lines.append(
                f"- {finding['page']} ↔ {finding['with']}: {finding['verdict']} "
                f"(confidence {finding['confidence']:.2f}) — {finding['reason']}"
            )
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

    lines.append("Answers to the suggestions above happen in chat — just tell me what to do.")
    return "\n".join(lines) + "\n"


__all__ = [
    "wrap_session",
    "maintain_overview",
    "render_wrap_screen",
    "render_pending_list",
    "harvest_suggestions",
]
