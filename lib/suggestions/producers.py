"""
lib.suggestions.producers — promotion-candidate producer (Task 17, RenOS
0.4.2 "the suggestion pipeline").

`promotion_candidates` finds pages that keep getting reinforced by human
correction: a non-global page whose frontmatter `type` is `doctrine` or
`preference`, journaled as an UPDATE at least twice across at least two
distinct sessions, and not currently quarantined. That reinforcement pattern
is read as "this is behaving like a durable preference" — the page is
suggesting its own promotion to the global tier.

This module only DETECTS and PROPOSES the suggestion (a `SuggestionSpec`) —
it never writes wiki pages, mirroring `lib.suggestions`' own module
docstring. Applying the suggestion (calling `promotion.promote_to_global`
then `queue.approve_and_apply`) is Task 19.

Never raises: unreadable pages or an unreadable journal degrade to `[]`,
same fail-open posture as `lib.memory.quarantine.quarantined_rel_pages`.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib import companions, ren_paths
from lib.adapter.claude_md import MARKER_BEGIN, MARKER_END
from lib.memory import quarantine
from lib.memory.journal import entries as journal_entries
from lib.memory.promotion import GLOBAL_PREFIX
from lib.ren_paths import PathTraversalError
from lib.suggestions import SuggestionSpec
from lib.suggestions.gate import is_critical_page

_MIN_UPDATES = 2
_MIN_SESSIONS = 2

# Mirrors lib.memory.promotion._ALLOWED_TYPES (private there — the typed-tier
# rule that only doctrine/preference pages may promote to global).
_ALLOWED_TYPES = frozenset({"doctrine", "preference"})

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)

_MANAGED_BLOCK_RE = re.compile(
    re.escape(MARKER_BEGIN) + r"(.*?)" + re.escape(MARKER_END), re.DOTALL
)


def _frontmatter_type(text: str) -> str | None:
    """Minimal frontmatter `type:` reader — same small local re-implementation
    pattern as `lib.memory.promotion._frontmatter_field` and
    `skills/wiki-health/lib/__init__.py::_frontmatter_type` (that helper is
    private to its own module, so it's reimplemented here rather than
    imported)."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("type:"):
            value = stripped[len("type:"):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            return value or None
    return None


def promotion_candidates(wiki_root: Path | None = None) -> list[SuggestionSpec]:
    """Return one `SuggestionSpec` per reinforced doctrine/preference page.

    Never raises: any error walking the wiki or reading the journal degrades
    to `[]` rather than propagating.
    """
    root = wiki_root if wiki_root is not None else ren_paths.wiki_root()

    try:
        md_paths = sorted(root.rglob("*.md"))
    except OSError:
        return []

    specs: list[SuggestionSpec] = []
    for md_path in md_paths:
        try:
            rel = str(md_path.relative_to(root).as_posix())
        except ValueError:
            continue

        if rel.startswith(GLOBAL_PREFIX) or rel == "global":
            continue

        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if _frontmatter_type(text) not in _ALLOWED_TYPES:
            continue

        if quarantine.is_quarantined(text):
            continue

        try:
            page_entries = journal_entries(rel)
        except OSError:
            continue

        update_entries = [e for e in page_entries if e.get("op") == "UPDATE"]
        sessions = {e.get("session") for e in update_entries if e.get("session")}

        if len(update_entries) < _MIN_UPDATES or len(sessions) < _MIN_SESSIONS:
            continue

        specs.append(
            SuggestionSpec(
                producer="promotion",
                title=f"Promote {rel} to global",
                rationale=(
                    f"{rel} was updated {len(update_entries)} times across "
                    f"{len(sessions)} sessions — behaving like a durable preference"
                ),
                evidence={"updates": len(update_entries), "sessions": sorted(sessions)},
                kind="structured_action",
                payload={"action": "promote_to_global", "source_page": rel},
                fingerprint=f"promotion:{rel}",
            )
        )

    return specs


def doctrine_shaping(claude_md_path: Path | None = None) -> list[SuggestionSpec]:
    """Return one `SuggestionSpec` per accepted-and-installed companion whose
    title is missing from the CLAUDE.md managed block.

    Defaults to the same path `lib.adapter.claude_md.write_global_claude_md`
    targets. Never raises: a missing file or a torn/absent managed block
    degrades to `[]` rather than propagating or over-suggesting.
    """
    path = (
        Path(claude_md_path)
        if claude_md_path is not None
        else ren_paths.claude_user_dir() / "CLAUDE.md"
    )

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    match = _MANAGED_BLOCK_RE.search(text)
    if match is None:
        return []
    block = match.group(1)

    specs: list[SuggestionSpec] = []
    for offer in companions.reconcile():
        if not offer.installed or offer.decision != "accepted":
            continue
        if offer.companion.title in block:
            continue
        specs.append(
            SuggestionSpec(
                producer="doctrine",
                title=f"Refresh CLAUDE.md for {offer.companion.title}",
                rationale=(
                    f"{offer.companion.title} is installed and accepted but not "
                    "reflected in the managed CLAUDE.md block"
                ),
                evidence={"cid": offer.companion.cid, "title": offer.companion.title},
                kind="structured_action",
                payload={"action": "refresh_claude_md"},
                fingerprint=f"doctrine:claude-md:{offer.companion.cid}",
            )
        )

    return specs


def _page_type(wiki_root: Path, page: str) -> str | None:
    """Tolerant frontmatter `type:` read for a wiki-relative page path.
    Any resolution/read error yields `None` rather than raising."""
    try:
        text = ren_paths.safe_join(wiki_root, page).read_text(
            encoding="utf-8", errors="replace"
        )
    except (OSError, PathTraversalError):
        return None
    return _frontmatter_type(text)


def wiki_health_critical(sweep_result: dict) -> list[SuggestionSpec]:
    """Return one `SuggestionSpec` per critical contradiction pair from a
    `skills.wiki_health.lib.sweep()` result dict.

    A pair is critical iff either page is on the instruction plane
    (`gate.is_critical_page`, the `global/` prefix) or either page's
    frontmatter `type` is doctrine/preference. Non-critical pairs are left
    for the sweep report itself. Never raises: malformed input degrades to
    `[]`.
    """
    pairs = (sweep_result or {}).get("contradiction_pairs") or []
    wiki_root = ren_paths.wiki_root()

    specs: list[SuggestionSpec] = []
    for pair in pairs:
        try:
            page_a = pair["page"]
            page_b = pair["with"]
        except (KeyError, TypeError):
            continue
        evidence = pair.get("evidence") if isinstance(pair, dict) else None

        critical = (
            is_critical_page(page_a)
            or is_critical_page(page_b)
            or _page_type(wiki_root, page_a) in _ALLOWED_TYPES
            or _page_type(wiki_root, page_b) in _ALLOWED_TYPES
        )
        if not critical:
            continue

        specs.append(
            SuggestionSpec(
                producer="wiki-health",
                title=f"Review contradiction: {page_a} vs {page_b}",
                rationale=f"Critical-page contradiction between {page_a} and {page_b}",
                evidence={"page": page_a, "with": page_b, "evidence": evidence},
                kind="structured_action",
                payload={
                    "action": "review_contradiction",
                    "page": page_a,
                    "with": page_b,
                    "evidence": evidence,
                },
                fingerprint=f"wiki-health:contradiction:{'|'.join(sorted((page_a, page_b)))}",
            )
        )

    return specs


__all__ = ["doctrine_shaping", "promotion_candidates", "wiki_health_critical"]
