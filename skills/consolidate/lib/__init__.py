"""
sf-consolidate library — internal implementation for /ren:consolidate (C3b).

The governed promotion sweep: read the hot-tier instincts, let the LLM (prompt
layer) propose which durable instincts graduate into the curated wiki, build the
diff pair (curated-page edit + in-place source marking), gate each diff, and apply
atomically. Pure-logic + git-apply primitives; no LLM calls in this module.

Public surface filled in over the TDD build. Per dotfiles python/coding-style.md.
"""

from __future__ import annotations

import re

from .diffs import create_file_diff as _create_file_diff
from .diffs import mark_line as _mark_line
from .diffs import unified_diff as _unified_diff
from .types import DeadLink, InstinctEntry, LinkRepair, PromotionDiff

# A hot-tier bullet: `- **[kind]** YYYY-MM-DD — text` (em-dash separator, per note's writer).
_BULLET_RE = re.compile(
    r"^- \*\*\[(?P<kind>worked|avoid|dont-repeat)\]\*\* "
    r"(?P<date>\d{4}-\d{2}-\d{2}) — (?P<text>.+)$"
)
# The in-place promotion marker appended by the sweep (see build_promotion_diffs).
_MARKER = "_(promoted"


def parse_instincts(text: str) -> tuple[InstinctEntry, ...]:
    """
    Parse an `instincts.md` body into typed entries.

    Only well-formed typed bullets are returned; frontmatter, headers, prose, and
    malformed lines are ignored. A line carrying a `_(promoted …)_` marker is
    parsed with `promoted=True` and the marker stripped from `text` (preserved in
    `raw_line`).
    """
    entries: list[InstinctEntry] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        m = _BULLET_RE.match(line)
        if not m:
            continue
        body = m.group("text")
        promoted = _MARKER in body
        clean = body.split(_MARKER, 1)[0].rstrip() if promoted else body.rstrip()
        entries.append(
            InstinctEntry(
                kind=m.group("kind"),
                date=m.group("date"),
                text=clean,
                raw_line=line,
                promoted=promoted,
            )
        )
    return tuple(entries)


def unpromoted(entries: tuple[InstinctEntry, ...]) -> tuple[InstinctEntry, ...]:
    """Return only the entries not yet promoted (idempotency filter for the sweep)."""
    return tuple(e for e in entries if not e.promoted)


# ---------------------------------------------------------------------------
# Promotion diff construction (deterministic, git-apply-compatible)
# ---------------------------------------------------------------------------


def build_promotion_diffs(
    entry: InstinctEntry,
    *,
    target_relpath: str,
    target_current: str | None,
    curated_addition: str,
    instincts_relpath: str,
    instincts_current: str,
    promoted_on: str,
) -> tuple[PromotionDiff, PromotionDiff]:
    """
    Build the diff PAIR for one promotion:
      1. page-edit — append `curated_addition` to the curated target (or create it
         when `target_current` is None/empty).
      2. marking   — annotate the source instinct line in place with a
         `_(promoted <date> → <target>)_` marker so the sweep is idempotent.

    Both are git-apply-compatible unified diffs (repo-root-relative paths). The
    `curated_addition` text is supplied by the prompt layer (the LLM's proposed
    curated wording); this function only constructs the diffs.
    """
    if not target_current:
        page_diff = _create_file_diff(target_relpath, curated_addition)
    else:
        new_target = target_current if target_current.endswith("\n") else target_current + "\n"
        new_target = new_target + curated_addition
        page_diff = _unified_diff(target_relpath, target_current, new_target)

    page = PromotionDiff(
        target_file=target_relpath,
        unified_diff=page_diff,
        kind="page-edit",
        rationale=f"promote [{entry.kind}] instinct → {target_relpath}",
    )

    marker = f"  _(promoted {promoted_on} → {target_relpath})_"
    marked = _mark_line(instincts_current, entry.raw_line, entry.raw_line + marker)
    marking = PromotionDiff(
        target_file=instincts_relpath,
        unified_diff=_unified_diff(instincts_relpath, instincts_current, marked),
        kind="marking",
        rationale=f"mark instinct promoted → {target_relpath}",
    )
    return page, marking


from .apply import ApplyResult, apply_diff_entries  # re-export the atomic-apply primitive
from .links import (
    build_basename_index,
    build_link_repair_diffs,
    build_slug_index,
    find_dead_links,
    propose_link_repair,
)

__all__ = [
    "InstinctEntry",
    "PromotionDiff",
    "DeadLink",
    "LinkRepair",
    "parse_instincts",
    "unpromoted",
    "build_promotion_diffs",
    "ApplyResult",
    "apply_diff_entries",
    "find_dead_links",
    "build_slug_index",
    "build_basename_index",
    "propose_link_repair",
    "build_link_repair_diffs",
]
