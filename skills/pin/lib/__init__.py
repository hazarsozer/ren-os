"""
skills.pin library — internal implementation for /ren:pin (Task 4.2, RenOS 0.2
Phase 4).

Public entries: `pin(text, page, session) -> QueueEntry`,
`correct(page, replacement, session) -> QueueEntry`.

Per spec §3.1 producer 3 (the pin/correction verb): reactive "remember it
like THIS" / "that's wrong, drop it". Human provenance, the `salience` flag
set (wake-up ranking boosts pinned/corrected pages per §3.2), and — like
every other producer — this goes through `lib.memory.queue.propose`, never a
direct wiki write. It is NOT a pipeline: one invocation, one `Proposal`,
queued for approve/apply exactly like wrap/retrospective/routine output.

This is donor `skills/note`'s shape SHRUNK for 0.2: no `--instinct`, no
`instincts.md` hot tier, no `.session-notes/`, no template/scope machinery.
Where note appended directly to a file, pin proposes a queue entry — the
single write-queue (Task 2.1) is 0.2's one door to a wiki page.
"""

from __future__ import annotations

from lib import ren_paths
from lib.memory.queue import Proposal, QueueEntry, propose


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
    return propose(
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


def correct(page: str, replacement: str | None, session: str) -> QueueEntry:
    """Queue a correction: "that's wrong" (`replacement=None` → DELETE) or
    "that's wrong, it should say THIS" (`replacement` given → UPDATE).

    Always human-provenance, always salient.
    """
    if replacement is None:
        return propose(
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
    return propose(
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


__all__ = ["pin", "correct"]
