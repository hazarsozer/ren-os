"""
lib.suggestions.gate — significance gate for the suggestion pipeline (Task 15,
RenOS 0.4.2).

Two pure functions gate whether a pattern is rare and high-stakes enough to
warrant becoming a suggestion:

1. recurs() — checks recurrence threshold: a pattern is deemed recurring iff
   it appears in >= RECURRENCE_MIN_SESSIONS of the last RECURRENCE_WINDOW_SESSIONS
   sessions (per spec §1.2).

2. is_critical_page() — checks if a page target is instruction-plane or
   load-bearing. Instruction-plane pages (global/) are always gated by human
   review per spec §10; data-plane pages auto-apply. This predicate reuses
   lib.governance.tiers.GLOBAL_PREFIX for the prefix check.

DOCTRINE (ratified §1.2, verbatim): "suggestions are rare and high-stakes;
below-threshold patterns accumulate silently; staleness and low-risk
contradictions resolve by recency at write time (queue supersedes) — only
behavior-changing or breakage-critical items may become suggestions."

The split between recurs() and is_critical_page() reflects the caller's
asymmetry: recurs() is pure and stateless; is_critical_page() only checks
the path prefix. When the caller has the page text, it provides the type
(doctrine/preference) to is_critical_page as a separate call.
"""

from __future__ import annotations

from typing import Final

from lib.governance.tiers import GLOBAL_PREFIX

RECURRENCE_MIN_SESSIONS: Final[int] = 3
RECURRENCE_WINDOW_SESSIONS: Final[int] = 5


def recurs(evidence_sessions: set[str], recent_sessions: list[str]) -> bool:
    """True iff >= RECURRENCE_MIN_SESSIONS of the last RECURRENCE_WINDOW_SESSIONS
    (recent_sessions, newest first) are in evidence_sessions.

    recent_sessions is a list ordered newest-first. Only the first
    RECURRENCE_WINDOW_SESSIONS (leading elements — the most recent sessions) are
    considered; earlier sessions are ignored.

    Args:
        evidence_sessions: Set of session IDs where the pattern appeared.
        recent_sessions: List of recent session IDs, newest first.

    Returns:
        True if the pattern recurs at least RECURRENCE_MIN_SESSIONS times in
        the last RECURRENCE_WINDOW_SESSIONS sessions; False otherwise.
    """
    # Empty evidence or recent → no recurrence
    if not evidence_sessions or not recent_sessions:
        return False

    # Take only the first RECURRENCE_WINDOW_SESSIONS sessions (leading elements = newest first)
    window = recent_sessions[:RECURRENCE_WINDOW_SESSIONS]

    # Count how many sessions in the window are in evidence_sessions
    count = sum(1 for session in window if session in evidence_sessions)

    return count >= RECURRENCE_MIN_SESSIONS


def is_critical_page(page: str) -> bool:
    """True for instruction-plane / load-bearing pages: pages that start with
    GLOBAL_PREFIX ("global/") or are the root global page itself.

    The instruction plane (spec §10) is human-review gated; data-plane pages
    auto-apply. This predicate checks the path prefix only. When the caller has
    the page text and can determine the frontmatter type (doctrine/preference),
    that is the caller's responsibility — is_critical_page itself does not read
    page bodies.

    Args:
        page: Wiki-relative page path (e.g., "global/rules.md", "projects/x.md")

    Returns:
        True if the page is on the instruction plane (global/* or global);
        False otherwise.
    """
    # Match lib.governance.tiers._is_global_page logic exactly
    if not page:
        return False
    return page == "global" or page.startswith(GLOBAL_PREFIX)


__all__ = [
    "RECURRENCE_MIN_SESSIONS",
    "RECURRENCE_WINDOW_SESSIONS",
    "recurs",
    "is_critical_page",
]
