"""
skills.pin library — internal implementation for /ren:pin (Task 4.2, RenOS 0.2
Phase 4).

Public entries: `pin(text, page, session) -> QueueEntry`,
`correct(page, replacement, session) -> QueueEntry`.

Per spec §3.1 producer 3 (the pin/correction verb): reactive "remember it
like THIS" / "that's wrong, drop it". Human provenance, the `salience` flag
set (wake-up ranking boosts pinned/corrected pages per §3.2), and — like
every other data-plane producer — this goes through
`lib.memory.queue.propose_and_apply`, never a direct wiki write. It is NOT a
pipeline: one invocation, one `Proposal`, auto-applied through the data-plane
door (v2.2 pivot: any non-global page write auto-applies, provenance +
one-step revert are the accountability mechanism).

This is donor `skills/note`'s shape SHRUNK for 0.2: no `--instinct`, no
`instincts.md` hot tier, no `.session-notes/`, no template/scope machinery.
Where note appended directly to a file, pin proposes a queue entry — the
single write-queue (Task 2.1) is 0.2's one door to a wiki page.
"""

from __future__ import annotations

from lib import ren_paths
from lib.memory.queue import Proposal, QueueEntry, propose_and_apply


def _page_exists(page: str) -> bool:
    page_abs = ren_paths.safe_join(ren_paths.wiki_root(), page)
    return page_abs.exists()


def pin(text: str, page: str, session: str) -> QueueEntry:
    """Queue a pin: "remember it like THIS."

    `op` is `ADD` if `page` doesn't exist yet on disk, `UPDATE` if it does —
    the caller doesn't need to know or care which; pin always "just works."
    Always human-provenance, always salient (boosts wake-up ranking).
    """
    op = "UPDATE" if _page_exists(page) else "ADD"
    entry, _ = propose_and_apply(
        Proposal(
            op=op,
            page=page,
            content=text,
            reason="user pin",
            producer="pin",
            writer="human",
            session=session,
            salience=True,
        )
    )
    return entry


def correct(page: str, replacement: str | None, session: str) -> QueueEntry:
    """Queue a correction: "that's wrong" (`replacement=None` → DELETE) or
    "that's wrong, it should say THIS" (`replacement` given → UPDATE).

    Always human-provenance, always salient.
    """
    if replacement is None:
        entry, _ = propose_and_apply(
            Proposal(
                op="DELETE",
                page=page,
                content=None,
                reason="user correction",
                producer="pin",
                writer="human",
                session=session,
                salience=True,
            )
        )
        return entry
    entry, _ = propose_and_apply(
        Proposal(
            op="UPDATE",
            page=page,
            content=replacement,
            reason="user correction",
            producer="pin",
            writer="human",
            session=session,
            salience=True,
        )
    )
    return entry


__all__ = ["pin", "correct"]
