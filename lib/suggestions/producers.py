"""
lib.suggestions.producers — promotion-candidate producer (Task 17, RenOS
0.4.2 "the suggestion pipeline").

`promotion_candidates` finds pages that keep getting reinforced by human
correction: a non-global page whose frontmatter `type` is `doctrine` or
`preference`, journaled as an UPDATE in enough recent sessions to clear the
ratified significance gate (`gate.recurs`, >= RECURRENCE_MIN_SESSIONS of the
last RECURRENCE_WINDOW_SESSIONS journal sessions — 0.4.5, replacing the old
ad-hoc 2/2 threshold), and not currently quarantined. That reinforcement pattern
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

from lib import ren_paths
from lib.adapter.claude_md import render_global_block, spliced_text
from lib.memory import quarantine
from lib.memory.journal import entries as journal_entries
from lib.memory.promotion import GLOBAL_PREFIX
from lib.memory.provenance import read_frontmatter_provenance
from lib.ren_paths import PathTraversalError
from lib.suggestions import SuggestionSpec
from lib.suggestions.gate import is_critical_page, recurs

# Mirrors lib.memory.promotion._ALLOWED_TYPES (private there — the typed-tier
# rule that only doctrine/preference pages may promote to global).
_ALLOWED_TYPES = frozenset({"doctrine", "preference"})

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


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


def _recent_sessions_newest_first() -> list[str]:
    """Distinct session ids across the whole journal, newest first — the
    `recent_sessions` input `lib.suggestions.gate.recurs` expects. The journal
    is append-ordered (newest-last), so walk it reversed and keep each
    session's first (i.e. most recent) occurrence."""
    seen: set[str] = set()
    out: list[str] = []
    for entry in reversed(journal_entries()):
        session = entry.get("session")
        if not session or session in seen:
            continue
        seen.add(session)
        out.append(session)
    return out


def promotion_candidates(wiki_root: Path | None = None) -> list[SuggestionSpec]:
    """Return one `SuggestionSpec` per reinforced doctrine/preference page.

    0.4.5: reinforcement is judged by the ratified significance gate
    (spec §5.2) — the page's UPDATE sessions must clear `recurs()`
    (>= RECURRENCE_MIN_SESSIONS of the last RECURRENCE_WINDOW_SESSIONS
    journal sessions), replacing the old ad-hoc 2-updates/2-sessions
    threshold.

    Never raises: any error walking the wiki or reading the journal degrades
    to `[]` rather than propagating.
    """
    root = wiki_root if wiki_root is not None else ren_paths.wiki_root()

    try:
        md_paths = sorted(root.rglob("*.md"))
        recent_sessions = _recent_sessions_newest_first()
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

        prov = read_frontmatter_provenance(text)
        if prov and prov.get("trust") == "foreign":
            continue

        try:
            page_entries = journal_entries(rel)
        except OSError:
            continue

        update_entries = [e for e in page_entries if e.get("op") == "UPDATE"]
        sessions = {e.get("session") for e in update_entries if e.get("session")}

        if not recurs(sessions, recent_sessions):
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


def doctrine_shaping(
    claude_md_path: Path | None = None,
    *,
    wiki_root: Path | None = None,
    doctrine_root: Path | None = None,
) -> list[SuggestionSpec]:
    """Return a single `SuggestionSpec` iff refreshing CLAUDE.md's managed
    block would actually change the file on disk.

    Gate-0 finding a: the previous predicate flagged accepted-and-installed
    companion TITLES absent from the managed block — but
    `lib.adapter.claude_md.render_global_block` never writes companion
    titles into that block in the first place, so the check was a pure
    false-positive generator (every accepted companion, forever). This is a
    render-and-compare check instead: render what a refresh WOULD write
    (`render_global_block` + `spliced_text`, the exact pure helper
    `apply_block` itself uses for the real write, so the two can never
    drift apart) and compare it byte-for-byte to what's on disk. Only a real
    diff earns a suggestion.

    Defaults to the same path `lib.adapter.claude_md.write_global_claude_md`
    targets. Never raises: any read/render error degrades to `[]` rather
    than propagating or over-suggesting.
    """
    path = (
        Path(claude_md_path)
        if claude_md_path is not None
        else ren_paths.claude_user_dir() / "CLAUDE.md"
    )

    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        content = render_global_block(
            existing_text=existing, doctrine_root=doctrine_root, wiki_root=wiki_root
        )
        prospective = spliced_text(existing, content)
    except OSError:
        return []

    if prospective == existing:
        return []

    return [
        SuggestionSpec(
            producer="doctrine",
            title="Refresh CLAUDE.md",
            rationale="your CLAUDE.md instruction block is out of date",
            evidence={},
            kind="structured_action",
            payload={"action": "refresh_claude_md"},
            fingerprint="doctrine:claude-md:refresh",
        )
    ]


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


def _page_trust(wiki_root: Path, page: str) -> str | None:
    """Tolerant `ren_trust` read for a wiki-relative page path. Any
    resolution/read error yields `None` rather than raising."""
    try:
        text = ren_paths.safe_join(wiki_root, page).read_text(
            encoding="utf-8", errors="replace"
        )
    except (OSError, PathTraversalError):
        return None
    prov = read_frontmatter_provenance(text)
    return prov.get("trust") if prov else None


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

        if _page_trust(wiki_root, page_a) == "foreign" or _page_trust(wiki_root, page_b) == "foreign":
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
