"""
lib.governance.tiers — the risk-tier gate model (Task 6.1, RenOS 0.2 Phase 6).

Spec §3.6 "Risk-tiered approval gates":
    reads free · routine bounded writes auto-apply with provenance tags +
    one-step revert · durable knowledge & code/config diff-approved ·
    destructive always ask.
Spec §3.5: destructive-tier actions BLOCK — never auto-approve — when no
human is present; routines and subagents may only PROPOSE durable-memory
writes (never auto-apply outside the narrow "auto" tier below).

Four tiers, strictly ordered by how much a human must be in the loop:

    free           — reads. No gate at all.
    auto           — a routine's BOUNDED memory write (non-global page).
                     Auto-applies, but always provenance-tagged (G2) and
                     one-step revertible (G4) — "bounded" means contained
                     enough that unattended auto-apply is safe, not that
                     it's unreviewed forever.
    diff_approved  — durable knowledge writes from anyone else (human, llm-auto,
                     retrospective, or a routine writing to a `global/` page),
                     plus ALL code/config writes. Queued, never auto-applied;
                     a human (or an explicit approval step) reviews the diff.
    ask            — destructive actions. Always requires an explicit human
                     ask; NEVER auto-approved. If no human is present
                     (`unattended=True`), the action is flatly refused
                     (`UnattendedBlocked`), not silently downgraded to a
                     lesser tier.

`unattended=True` never *relaxes* a tier — an unattended routine memory-write
that's already "auto" stays "auto" (that's the bounded+revertible case the
spec says is safe unattended); an unattended action that would be
"diff_approved" stays "diff_approved" (the caller's job is to PROPOSE via the
queue, never to auto-apply it) — only "ask" upgrades to a hard block when
unattended, because there is no lesser gate a destructive action can be
downgraded through safely.
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
    if _is_global_page(action.page):
        return "diff_approved"
    if action.writer == "routine":
        return "auto"
    return "diff_approved"


def queue_auto_apply_allowed(proposal) -> bool:
    """True iff `proposal` (a `lib.memory.queue.Proposal`) resolves to the
    "auto" tier: a routine's bounded (non-global) memory write. Used by
    `lib.memory.queue.apply_auto` to gate its own legality.
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
