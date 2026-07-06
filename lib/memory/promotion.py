"""
lib.memory.promotion — typed global-tier promotion (Task 4.5, RenOS 0.2 Phase 4).

Spec §3.1 "Global tier — typed, not flat": global holds DOCTRINE AND
PREFERENCES ONLY, never project facts; promotion is always explicit, always
human-approved, never routine-written; the global tier uses the same
map/pointer mechanism as projects.

Donor `skills/consolidate/lib/__init__.py`'s `--to-global` flow (C3b) is the
shape reference, not a port: donor's promotion moves hot-tier INSTINCT
BULLETS into a curated instincts page via a bespoke diff-pair (curated-page
edit + in-place source marking) with its own gate. 0.2 folds page-level
promotion into the single write-queue instead — `promote_to_global` builds
ONE `Proposal` and calls `queue.propose`; the normal propose -> approve ->
apply flow (writer="human") is what makes "always human-approved" true, not a
bespoke gate. There is no in-place source marking here either — donor's
`_(promoted …)_` marker exists because instinct bullets accumulate in one
file and need de-duplication on re-sweep; a whole-page promotion has no such
accumulation problem, so the analogous provenance is a single
`promoted-from: <source> (<write_id>)` line on the target instead.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib import ren_paths
from lib.memory import quarantine
from lib.memory.provenance import read_frontmatter_provenance
from lib.memory.queue import Proposal, QueueEntry, propose

GLOBAL_PREFIX = "global/"

_ALLOWED_TYPES = frozenset({"doctrine", "preference"})

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


class PromotionError(Exception):
    """Raised when a source page can't be promoted to the global tier."""


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_prefix, body); prefix is "" if absent.
    `frontmatter_prefix + body == text` always holds."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return "", text
    return text[: match.end()], text[match.end():]


def _frontmatter_field(text: str, field: str) -> str | None:
    """Minimal frontmatter field reader (same shape used elsewhere in
    lib.memory — see provenance.py/semantics.py's module docstrings for why
    this is a small local re-implementation rather than a shared private
    import)."""
    prefix, _ = _split_frontmatter(text)
    if not prefix:
        return None
    prefix_lookup = f"{field}:"
    for line in prefix.splitlines()[1:-1]:  # skip the "---" fences themselves
        stripped = line.strip()
        if stripped.startswith(prefix_lookup):
            value = stripped[len(prefix_lookup):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            return value or None
    return None


def _read_page(rel_page: str) -> str:
    path = ren_paths.safe_join(ren_paths.wiki_root(), rel_page)
    if not path.is_file():
        raise PromotionError(f"source page {rel_page!r} does not exist")
    return path.read_text(encoding="utf-8")


def _page_exists(rel_page: str) -> bool:
    return ren_paths.safe_join(ren_paths.wiki_root(), rel_page).is_file()


def promote_to_global(
    source_page: str, session: str, target_page: str | None = None
) -> QueueEntry:
    """Propose promoting `source_page` to the global tier.

    Raises `PromotionError` if:
      - `source_page` doesn't exist.
      - the source's frontmatter `type` isn't `"doctrine"` or `"preference"`
        (the typed-tier rule — project facts, l2-maps, untyped lessons, etc.
        can never promote).
      - the source is quarantined (unreviewed LLM-auto content can never
        promote to global doctrine on its own).

    Returns a PENDING `QueueEntry` — promotion goes through the SAME
    approve/apply flow as every other write; `writer="human"` here is what
    makes "always human-approved" true (§3.1), not a bespoke gate.
    """
    source_text = _read_page(source_page)

    page_type = _frontmatter_field(source_text, "type")
    if page_type not in _ALLOWED_TYPES:
        raise PromotionError(
            f"global tier is typed (spec §3.1): only pages with frontmatter "
            f"type 'doctrine' or 'preference' may be promoted; "
            f"{source_page!r} has type {page_type!r}"
        )

    if quarantine.is_quarantined(source_text):
        raise PromotionError(
            f"{source_page!r} is quarantined (unreviewed LLM-auto content); "
            "it must be human-reviewed before it can promote to global"
        )

    target = target_page if target_page is not None else GLOBAL_PREFIX + Path(source_page).name
    op = "UPDATE" if _page_exists(target) else "ADD"

    source_prov = read_frontmatter_provenance(source_text)
    source_write_id = source_prov["write_id"] if source_prov else "unstamped"
    promoted_from_line = f"promoted-from: {source_page} ({source_write_id})\n"

    prefix, body = _split_frontmatter(source_text)
    content = prefix + promoted_from_line + body

    return propose(
        Proposal(
            op=op,
            page=target,
            content=content,
            reason="promote-to-global",
            producer="promotion",
            writer="human",
            session=session,
        )
    )


def demote_check(page: str = GLOBAL_PREFIX) -> list[str]:
    """Drift detection for doctor (Phase 7): scan `page` (a directory,
    defaulting to the whole global tier at `wiki_root()/global/`) for pages
    whose frontmatter `type` is NOT `"doctrine"`/`"preference"`.

    Returns wiki-relative paths of every violating page; `[]` means the tier
    is clean (including when the directory doesn't exist yet).
    """
    root = ren_paths.safe_join(ren_paths.wiki_root(), page)
    if not root.is_dir():
        return []

    violations: list[str] = []
    for md_path in sorted(root.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        if _frontmatter_field(text, "type") not in _ALLOWED_TYPES:
            violations.append(str(md_path.relative_to(ren_paths.wiki_root())))
    return violations


__all__ = ["GLOBAL_PREFIX", "PromotionError", "promote_to_global", "demote_check"]
