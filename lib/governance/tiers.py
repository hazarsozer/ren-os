"""
lib.governance.tiers — the risk-tier gate model (Task 6.1, RenOS 0.2 Phase 6;
pivoted to the two-plane model in v2.2, spec §10).

Spec §10's two-plane governance pivot: the DATA plane (descriptive memory —
any non-global page) auto-applies for every writer, attended or not;
provenance + snapshot + one-step revert are the accountability mechanism, not
a human diff. The INSTRUCTION plane (`global/` pages) keeps the human gate —
promotion through a human is the only door from remembered to obeyed. All
code/config writes and destructive actions are unaffected by the pivot.

Four tiers, strictly ordered by how much a human must be in the loop:

    free           — reads. No gate at all.
    auto           — any BOUNDED memory write (non-global page), from any
                     writer class. Auto-applies, but always provenance-tagged
                     (G2) and one-step revertible (G4) — "bounded" means
                     contained enough that unattended auto-apply is safe, not
                     that it's unreviewed forever.
    diff_approved  — writes to an instruction-plane page (`global/` plus the
                     root-level global tier `decisions/`·`patterns/`·
                     `research/` — see `INSTRUCTION_PLANE_PREFIXES`, issue
                     #18), from any writer, plus ALL code/config writes.
                     Queued, never
                     auto-applied; a human (or an explicit approval step)
                     reviews the diff.
    ask            — destructive actions. Always requires an explicit human
                     ask; NEVER auto-approved. If no human is present
                     (`unattended=True`), the action is flatly refused
                     (`UnattendedBlocked`), not silently downgraded to a
                     lesser tier.

`unattended=True` never *relaxes* a tier — an unattended non-global
memory-write that's already "auto" stays "auto" (that's the
bounded+revertible case the spec says is safe unattended); an unattended
action that would be "diff_approved" stays "diff_approved" (the caller's job
is to PROPOSE via the queue, never to auto-apply it) — only "ask" upgrades to
a hard block when unattended, because there is no lesser gate a destructive
action can be downgraded through safely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["free", "auto", "diff_approved", "ask"]

ActionKind = Literal["read", "memory_write", "code_write", "config_write", "destructive"]

_VALID_KINDS: tuple[str, ...] = ("read", "memory_write", "code_write", "config_write", "destructive")

GLOBAL_PREFIX = "global/"
"""Pages at or under this prefix are the strictest gate, ALWAYS
`diff_approved` regardless of writer — spec §3.1's typed global tier is
promotion-gated by construction, never auto-applied."""

INSTRUCTION_PLANE_PREFIXES: tuple[str, ...] = (
    GLOBAL_PREFIX,
    "decisions/",
    "patterns/",
    "research/",
)
"""THE canonical encoding of the instruction plane — the global tier as the
README's memory-hierarchy diagram draws it: `global/` (typed doctrine and
preferences) plus the three durable global-tier content dirs
`decisions/` · `patterns/` · `research/`.

Issue #18 (2026-07-31, surfaced dogfooding the Flux ingest): the diagram said
the global tier is reached by "promotion (gated, never automatic)", but only
`global/` was mechanically gated — a `producer="ingest", writer="llm-auto"`
proposal targeting `decisions/<x>.md` auto-applied like any data-plane write.
Founder doctrine, encoded here: global-tier `decisions/`/`patterns/` are ONLY
for practices general enough to apply across projects; project-specific
decisions live under `projects/<slug>/` and reach the global tier only
through the human-gated promotion path (propose -> approve -> apply).

Every other module that needs "is this the instruction plane?" delegates to
`is_instruction_plane_page` rather than re-spelling the prefixes
(`lib.suggestions.gate.is_critical_page`, `lib.memory.lifecycle
._data_plane_pages`, `skills.wiki-health.lib`) — see
`tests/lib/governance/test_tiers.py`'s drift test."""


class UnattendedBlocked(Exception):
    """Raised when a destructive action is attempted with no human present
    (`unattended=True`). This is a hard refusal, not a downgrade — per spec
    §3.5, destructive actions never auto-approve, attended or not."""


@dataclass(frozen=True)
class Action:
    kind: str            # "read" | "memory_write" | "code_write" | "config_write" | "destructive"
    writer: str           # WriterClass value: "human"|"llm-auto"|"retrospective"|"routine"
    page: str | None = None       # memory_write target page (wiki-relative), if applicable
    unattended: bool = False      # True when no human is present (routine/cron context)


def _is_global_page(page: str | None) -> bool:
    if not page:
        return False
    return page == "global" or page.startswith(GLOBAL_PREFIX)


def is_instruction_plane_page(page: str | None) -> bool:
    """True iff `page` is on the INSTRUCTION plane — `global/` or any of the
    root-level global-tier dirs (`decisions/`, `patterns/`, `research/`).
    Path-prefix only; never reads page bodies. This is the single source of
    truth for the plane split (issue #18) — callers must not re-spell the
    prefix list."""
    if not page:
        return False
    if any(page.startswith(prefix) for prefix in INSTRUCTION_PLANE_PREFIXES):
        return True
    # A bare dir name with no trailing slash ("global", "decisions") is the
    # tier page itself, not a data-plane page that merely starts with it.
    return f"{page}/" in INSTRUCTION_PLANE_PREFIXES


def tier_of(action: Action) -> Tier:
    """Resolve the gate tier for `action`. See module docstring for the full
    table. Raises `UnattendedBlocked` for a destructive action with
    `unattended=True` — that's a refusal, not a return value, since there is
    no tier a destructive action can be safely downgraded to when no human
    can approve it.
    """
    if action.kind not in _VALID_KINDS:
        raise ValueError(f"unknown action kind {action.kind!r}; must be one of {_VALID_KINDS}")

    if action.kind == "read":
        return "free"

    if action.kind == "destructive":
        if action.unattended:
            raise UnattendedBlocked(
                "destructive actions require a human present; refused unattended"
            )
        return "ask"

    if action.kind in ("code_write", "config_write"):
        return "diff_approved"

    # action.kind == "memory_write"
    # v2.2 (spec §10): the DATA plane — descriptive memory — auto-applies for
    # every writer class, attended or not; provenance + snapshot + one-step
    # revert (§3.10) are the accountability mechanism, not a human diff.
    # The INSTRUCTION plane (global/) keeps diff_approved: promotion through
    # a human is the only door from remembered to obeyed.
    # Issue #18: the instruction plane is the WHOLE global tier — `global/`
    # plus `decisions/`/`patterns/`/`research/` — not just `global/`. A
    # non-promotion producer's write to any of them holds pending instead of
    # auto-applying; the human-gated promotion path is the only door.
    if is_instruction_plane_page(action.page):
        return "diff_approved"
    return "auto"


def queue_auto_apply_allowed(proposal) -> bool:
    """True iff `proposal` (a `lib.memory.queue.Proposal`) resolves to the
    "auto" tier: a bounded (non-global) memory write, from any writer class.
    Thin wrapper around `tier_of` — used by `lib.memory.queue.apply_auto` to
    gate its own legality.
    """
    action = Action(kind="memory_write", writer=proposal.writer, page=proposal.page, unattended=False)
    return tier_of(action) == "auto"


__all__ = [
    "Tier",
    "ActionKind",
    "GLOBAL_PREFIX",
    "INSTRUCTION_PLANE_PREFIXES",
    "is_instruction_plane_page",
    "UnattendedBlocked",
    "Action",
    "tier_of",
    "queue_auto_apply_allowed",
]
