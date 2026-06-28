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
    """One unified diff in a promotion plan — either a curated-page edit or the source marking."""

    target_file: str   # path for display / metadata
    unified_diff: str  # git-apply-compatible unified diff
    kind: str          # "page-edit" | "marking"
    rationale: str     # short justification shown to the user at the gate
