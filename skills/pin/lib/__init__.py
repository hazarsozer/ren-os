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
from lib.memory.queue import Proposal, QueueEntry, approve_and_apply, get, propose_and_apply

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


_SPINE_ROOT_PAGES = frozenset({"log.md", "identity.md", "index.md"})


def _is_spine_page(page: str) -> bool:
    """True for the wiki's structural spine: the root `log.md`,
    `identity.md`, and `index.md`, plus any page whose final path component
    is `map.md` (L2 maps, e.g. `projects/<slug>/map.md`). These pages are
    never deleted via pin correction — see issue #58."""
    normalized = page.replace("\\", "/").strip("/")
    if normalized in _SPINE_ROOT_PAGES:
        return True
    return normalized.rsplit("/", 1)[-1] == "map.md"


def _complete_if_held(entry: QueueEntry, approved_by: str | None) -> QueueEntry:
    """Dogfood-2 finding H1: complete a human-approved correction that the
    instruction-plane hold left pending.

    A correction targeting an instruction-plane page (`global/`, `decisions/`,
    `patterns/`, `research/`) holds pending at the data-plane door
    (`propose_and_apply` case 1) — correct behavior for an unattended write,
    but wrong when the friend just approved the correction verbally (wrap's
    "Live pins" gate). With `approved_by` set, the pending entry is released
    through the sanctioned human-approval path (`queue.approve_and_apply`).

    A `contradicts`-conflict hold is deliberately NOT completed here — that
    hold exists so the live session reasons about the contradiction first;
    verbal approval of a delete/update is not that reasoning. The entry is
    returned still-pending and the caller must report it honestly."""
    if approved_by is None or entry.status != "pending":
        return entry
    if any(c.get("kind") == "contradicts" for c in entry.conflicts):
        return entry
    approve_and_apply(entry.qid, who=approved_by)
    return get(entry.qid)


def correct(
    page: str, replacement: str | None, session: str, *, approved_by: str | None = None
) -> QueueEntry:
    """Queue a correction: "that's wrong" (`replacement=None` → DELETE) or
    "that's wrong, it should say THIS" (`replacement` given → UPDATE).

    Always human-provenance, always salient.

    `approved_by` (keyword-only): the friend's handle when they explicitly
    approved this correction in conversation. When the proposal lands pending
    on the instruction-plane hold, the approval is completed immediately via
    `queue.approve_and_apply` instead of silently swallowing the confirmed
    correction — see `_complete_if_held`.

    Raises `ValueError` on a DELETE (`replacement=None`) targeting a spine
    page — refused before anything is queued, regardless of `approved_by`
    (issue #58).
    """
    if replacement is None:
        if _is_spine_page(page):
            raise ValueError(
                f"refusing DELETE of spine page '{page}': spine pages "
                "(log.md/identity.md/index.md/*/map.md) are never deleted "
                "via pin correction — see issue #58 (the 2026-08 "
                "log.md/identity.md deletion incident). approved_by does "
                "not override this."
            )
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
        return _complete_if_held(entry, approved_by)
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
    return _complete_if_held(entry, approved_by)


__all__ = ["pin", "correct"]
