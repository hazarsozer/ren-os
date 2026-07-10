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

import re

from lib import ren_paths
from lib.memory.promotion import GLOBAL_PREFIX
from lib.memory.queue import Proposal, QueueEntry, propose_and_apply

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_TYPE_FIELD_RE = re.compile(r"^type:\s*\S", re.MULTILINE)


def _page_exists(page: str) -> bool:
    page_abs = ren_paths.safe_join(ren_paths.wiki_root(), page)
    return page_abs.exists()


def _stamp_global_type(content: str, page: str) -> str:
    """Gate-0 finding: an approved pin/correction to a `global/`-prefixed
    page must satisfy the typed-global rule (`lib.memory.promotion.
    demote_check` — global pages must carry `type: doctrine` or `type:
    preference`), or the write the friend just approved immediately shows up
    as drift on the next `doctor` run.

    If `content` targets a non-global page, or already declares a `type:`
    field in its frontmatter, it's returned unchanged. Otherwise `type:
    preference` is stamped in — into the existing frontmatter fence if one
    exists (no double fence), or a new one if it doesn't. `preference` (not
    `doctrine`) because pin/correct is human-provenance ad hoc memory, not a
    deliberated rule — the friend can still hand-edit to `doctrine` later."""
    if not page.startswith(GLOBAL_PREFIX):
        return content

    match = _FRONTMATTER_RE.match(content)
    if match is None:
        return f"---\ntype: preference\n---\n{content}"

    fm_content = match.group(1)
    if _TYPE_FIELD_RE.search(fm_content):
        return content

    body = content[match.end():]
    rebuilt = (
        fm_content.rstrip("\n") + "\ntype: preference" if fm_content.strip() else "type: preference"
    )
    return f"---\n{rebuilt}\n---\n{body}"


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
            content=_stamp_global_type(text, page),
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
            content=_stamp_global_type(replacement, page),
            reason="user correction",
            producer="pin",
            writer="human",
            session=session,
            salience=True,
        )
    )
    return entry


__all__ = ["pin", "correct"]
