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
    diff_approved  — writes to a `global/` page (the instruction plane, from
                     any writer), plus ALL code/config writes. Queued, never
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
    if _is_global_page(action.page):
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
    "UnattendedBlocked",
    "Action",
    "tier_of",
    "queue_auto_apply_allowed",
]
