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
from pathlib import Path
from typing import Callable

from lib import ren_paths
from lib.instrument import collect
from lib.memory import queue
from lib.memory.queue import Proposal, propose_and_apply
from lib.memory.scrub import SecretsFound
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

    return {
        "l1_qid": l1_entry.qid,
        "applied": applied,
        "held": held,
        "gated_out": gated_out,
        "refused": refused,
        "fail_closed": fail_closed,
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


__all__ = ["wrap_session", "render_wrap_screen", "render_pending_list", "harvest_suggestions"]
