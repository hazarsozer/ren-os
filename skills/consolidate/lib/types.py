"""
sf-consolidate local types (C3b — governed promotion sweep).

Frozen dataclasses per dotfiles python/coding-style.md (immutability default).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstinctEntry:
    """One parsed bullet from an instincts.md hot-tier file."""

    kind: str        # worked | avoid | dont-repeat
    date: str        # YYYY-MM-DD (the capture date)
    text: str        # the instinct text, with any promotion marker stripped
    raw_line: str    # the full original line (used to build the in-place marking diff)
    promoted: bool = False  # True if the line already carries a `_(promoted …)_` marker


@dataclass(frozen=True)
class PromotionDiff:
    """One unified diff in a sweep plan — a curated-page edit, source marking, or link fix."""

    target_file: str   # path for display / metadata
    unified_diff: str  # git-apply-compatible unified diff
    kind: str          # "page-edit" | "marking" | "link-fix"
    rationale: str     # short justification shown to the user at the gate


@dataclass(frozen=True)
class DeadLink:
    """One dead link occurrence found in a wiki page (C3c link-repair sweep)."""

    source_relpath: str   # repo-relative path of the page that holds the link
    form: str             # "wikilink" | "mdlink"
    raw_target: str       # target as written ([[<t>]] / ](<t>)), anchor excluded
    alias: str | None     # the |alias of a wikilink, else None
    old_literal: str      # the exact matched link text (drives the in-line rewrite)
    line_no: int          # 0-based line index within the source page
    raw_line: str         # the full source line


@dataclass(frozen=True)
class LinkRepair:
    """A proposed, deterministic fix for one DeadLink (C3c). None-able upstream."""

    dead: DeadLink     # the dead link this repairs
    new_target: str    # resolved slug (wikilink) or relative path (mdlink)
    new_literal: str   # replacement for dead.old_literal
    rationale: str     # short justification shown at the gate
