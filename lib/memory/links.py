"""The link convention and the shared link index (spec 2026-09-04 §3-§4).

Links live in the page BODY, never in frontmatter — that is the whole
point of the depth-cap ruling: depth 2 is a shelf, hierarchy is links, and
Obsidian plus `_orphan_pages` already read the body.

One module builds the graph; three consumers read it (wiki-health's
`_orphan_pages`/`asymmetric_links`, fan-out's candidate exclusions, recall's
inbound boost). There is exactly one resolver here so the three cannot drift.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

RELATED_HEADING: Final[str] = "## Related"
PARENT_PREFIX: Final[str] = "Parent: "

#: `Parent: [[stem]]` on its own line, anywhere in the body.
_PARENT_RE: Final = re.compile(r"^Parent:\s*\[\[\s*([^\]\n|]+?)\s*(?:\|[^\]\n]*)?\]\]\s*$", re.MULTILINE)
#: A `## Related` bullet: `- [[stem]] — reason` (em dash, en dash or `-`).
_RELATED_BULLET_RE: Final = re.compile(
    r"^-\s*\[\[\s*([^\]\n|]+?)\s*(?:\|[^\]\n]*)?\]\]\s*(?:[—–-]\s*(.*?))?\s*$"
)
#: Any wikilink, used for the `other` bucket.
_WIKILINK_RE: Final = re.compile(r"\[\[\s*([^\]\n|]+?)\s*(?:\|[^\]\n]*)?\]\]")
#: `](target.md)` — the same markdown-link tail wiki-health's `_MD_LINK_RE`
#: matches, kept in sync deliberately (angle brackets, `#fragment`, title).
_MD_LINK_RE: Final = re.compile(
    r"\]\(\s*<?([^()\s#>]+\.md)>?(?:#[^()\s]*)?(?:\s+\"[^\"]*\")?\s*\)"
)
_ANY_HEADING_RE: Final = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)
_H1_RE: Final = re.compile(r"^#\s+.*$", re.MULTILINE)

#: A concept node past this many `## Facts` bullets is too big to stay one
#: page — the split is a SUGGESTION, never an auto-apply (spec 2026-08-31 §3).
CONCEPT_SPLIT_BULLETS: Final[int] = 40

_FACTS_HEADING_RE: Final = re.compile(r"^##\s+Facts\s*$", re.MULTILINE)
_BULLET_LINE_RE: Final = re.compile(r"^-\s+\S.*$", re.MULTILINE)


def count_facts_bullets(text: str) -> int:
    """Bullets under `text`'s `## Facts` heading (0 when there is none)."""
    m = _FACTS_HEADING_RE.search(text)
    if m is None:
        return 0
    rest = text[m.end():]
    next_heading = _ANY_HEADING_RE.search(rest)
    section = rest[:next_heading.start()] if next_heading else rest
    return len(_BULLET_LINE_RE.findall(section))


def append_facts_bullet(text: str, item_text: str) -> str:
    """Mechanical (no-LLM) merge for a concept node accretion: append
    `- <item_text>` as the LAST bullet under `## Facts`, creating the heading
    at the end of the page when absent."""
    bullet = f"- {item_text}"
    m = _FACTS_HEADING_RE.search(text)
    if m is None:
        return text.rstrip("\n") + "\n\n## Facts\n\n" + bullet + "\n"
    rest = text[m.end():]
    next_heading = _ANY_HEADING_RE.search(rest)
    if next_heading is None:
        return text.rstrip("\n") + "\n" + bullet + "\n"
    insert_at = m.end() + next_heading.start()
    section = text[m.end():insert_at].rstrip("\n")
    return text[:m.end()] + section + "\n" + bullet + "\n\n" + text[insert_at:]


@dataclass(frozen=True)
class PageLinks:
    parent: str | None
    related: tuple[tuple[str, str], ...]
    other: tuple[str, ...]


@dataclass(frozen=True)
class LinkIndex:
    outbound: dict[str, set[str]] = field(default_factory=dict)
    inbound: dict[str, set[str]] = field(default_factory=dict)
    parent: dict[str, str | None] = field(default_factory=dict)
    related: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    pages: dict[str, str] = field(default_factory=dict)


def _related_span(text: str) -> tuple[int, int] | None:
    """`(start, end)` character offsets of the `## Related` SECTION BODY —
    everything after the heading line up to the next heading (or EOF)."""
    m = re.search(rf"^{re.escape(RELATED_HEADING)}\s*$", text, re.MULTILINE)
    if m is None:
        return None
    body_start = m.end()
    nxt = _ANY_HEADING_RE.search(text, body_start + 1)
    return body_start, nxt.start() if nxt else len(text)


def parse_page_links(text: str) -> PageLinks:
    """Tolerant parse of one page body (spec §3). A page with no `Parent:`
    line is `parent=None`, never an error — reading a link is not a
    behaviour change."""
    pm = _PARENT_RE.search(text)
    parent = pm.group(1) if pm else None

    related: list[tuple[str, str]] = []
    span = _related_span(text)
    if span is not None:
        for line in text[span[0]:span[1]].splitlines():
            bm = _RELATED_BULLET_RE.match(line.strip())
            if bm:
                related.append((bm.group(1), (bm.group(2) or "").strip()))

    claimed = {parent} | {stem for stem, _ in related}
    other: list[str] = []
    for stem in _WIKILINK_RE.findall(text):
        if stem not in claimed and stem not in other:
            other.append(stem)
    for target in _MD_LINK_RE.findall(text):
        if target not in claimed and target not in other:
            other.append(target)
    return PageLinks(parent=parent, related=tuple(related), other=tuple(other))


def render_related(items: list[tuple[str, str]]) -> str:
    """The whole `## Related` section. An EMPTY section is rendered, never
    omitted — a visible "nothing linked yet", same spirit as the empty
    taxonomy fence (spec §3)."""
    lines = [RELATED_HEADING]
    lines.extend(f"- [[{stem}]] — {reason}" for stem, reason in items)
    return "\n".join(lines) + "\n"


def upsert_related(text: str, stem: str, reason: str) -> str:
    """Add `- [[stem]] — reason` to `## Related`, creating the section if
    absent. Idempotent on `stem`: a stem already listed is left exactly as
    it is, reason included (insertion order is the contract)."""
    existing = parse_page_links(text)
    if any(s == stem for s, _ in existing.related):
        return text
    bullet = f"- [[{stem}]] — {reason}"
    span = _related_span(text)
    if span is None:
        return text.rstrip("\n") + "\n\n" + RELATED_HEADING + "\n" + bullet + "\n"
    body = text[span[0]:span[1]].rstrip("\n")
    new_body = (body + "\n" if body else "\n") + bullet + "\n\n"
    return text[:span[0]] + new_body + text[span[1]:]


def upsert_parent(text: str, stem: str) -> str:
    """Set the page's single `Parent:` line, replacing any existing one.
    Idempotent. A page with an H1 gets the line directly after it; a page
    without one gets it at the top of the body."""
    line = f"{PARENT_PREFIX}[[{stem}]]"
    pm = _PARENT_RE.search(text)
    if pm is not None:
        if pm.group(1) == stem:
            return text
        return text[:pm.start()] + line + text[pm.end():]
    h1 = _H1_RE.search(text)
    if h1 is None:
        return line + "\n\n" + text.lstrip("\n")
    insert_at = h1.end()
    return text[:insert_at] + "\n\n" + line + "\n\n" + text[insert_at:].lstrip("\n")


def _resolve(pages: dict[str, str], src: str, target: str) -> str | None:
    """Resolve one link body to a page in `pages`. Wikilinks resolve by
    BASENAME (exactly as `skills/wiki-health/lib/lint.py::_resolves` does);
    markdown targets resolve relative to the linking file first, then to the
    wiki root. Returns the rel posix path, or None."""
    if target.endswith(".md") and "/" in target:
        src_dir = Path(src).parent
        for cand in ((src_dir / target), Path(target)):
            norm = Path(os.path.normpath(cand.as_posix())).as_posix()
            if norm in pages:
                return norm
        return None
    basename = target if target.endswith(".md") else f"{target}.md"
    basename = Path(basename).name
    matches = [p for p in pages if Path(p).name == basename]
    return matches[0] if len(matches) == 1 else None


def build_link_index(wiki_root: Path, *, project: str | None = None) -> LinkIndex:
    """Walk `wiki_root` once and build the graph (spec §4).

    Walk and exemptions are `_orphan_pages`': EVERY page contributes links
    (dot-dirs skipped); `raw/`, `archive/` and quarantined pages stay in the
    corpus but are not candidates — that candidacy filter is the caller's,
    not this walk's, so `pages` carries everything.

    `project=` narrows to `projects/<slug>/` plus the wiki's ROOT-LEVEL
    files (which routinely link into a project); fan-out and recall use it,
    lint uses the whole wiki.
    """
    wiki_root = Path(wiki_root)
    pages: dict[str, str] = {}
    for md in sorted(wiki_root.rglob("*.md")):
        rel = md.relative_to(wiki_root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        posix = rel.as_posix()
        if project is not None and "/" in posix and not posix.startswith(f"projects/{project}/"):
            continue
        pages[posix] = md.read_text(encoding="utf-8", errors="replace")

    outbound: dict[str, set[str]] = {p: set() for p in pages}
    inbound: dict[str, set[str]] = {p: set() for p in pages}
    parent: dict[str, str | None] = {}
    related: dict[str, list[tuple[str, str]]] = {}
    for src, text in pages.items():
        links = parse_page_links(text)
        parent[src] = links.parent
        related[src] = list(links.related)
        targets = list(links.other) + [s for s, _ in links.related]
        if links.parent:
            targets.append(links.parent)
        for target in targets:
            dest = _resolve(pages, src, target)
            if dest is not None and dest != src:
                outbound[src].add(dest)
                inbound[dest].add(src)
    return LinkIndex(
        outbound=outbound, inbound=inbound, parent=parent, related=related, pages=pages
    )


__all__ = [
    "LinkIndex",
    "PageLinks",
    "PARENT_PREFIX",
    "RELATED_HEADING",
    "CONCEPT_SPLIT_BULLETS",
    "append_facts_bullet",
    "build_link_index",
    "count_facts_bullets",
    "parse_page_links",
    "render_related",
    "upsert_parent",
    "upsert_related",
]
