# The Graph Is The Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the wiki's cross-reference graph a first-class object — a body-text `Parent:`/`## Related` convention every producer emits, a shared link index, a write-time fan-out that updates the existing pages a new item should touch, and graph-aware lint and recall.

**Architecture:** One new module `lib/memory/links.py` parses and renders the convention and builds a `LinkIndex` (outbound/inbound/parent/related) from a single regex walk; `skills/wiki-health/lib/__init__.py::_orphan_pages` is refactored onto it so there is one resolver, not two. A second new module `lib/memory/fanout.py` ranks the project's knowledge pages against a just-landed item with recall's own `_score_content`, asks one classifier-class LLM call for a `relate`/`fact`/`none` verdict per candidate, and applies every non-`none` verdict through `lib.memory.queue.propose_and_apply`. wrap, distill and ingest emit the convention; wiki-health audits it; recall ranks with it.

**Tech Stack:** Python ≥3.11 stdlib-only (`re`, `dataclasses`, `pathlib`), uv, pytest. All wiki writes via `propose_and_apply(Proposal(...))`. Metrics via `lib.instrument.collect.record`. Suggestions via `lib.suggestions.record(SuggestionSpec(...))`.

**Spec:** `docs/superpowers/specs/2026-09-04-graph-is-the-hierarchy-design.md`

## Global Constraints

- Python ≥3.11, stdlib-first — no new third-party dependency in any task.
- Run tests with `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests -q`. NEVER create a `.venv` in the repo root; the env var is what keeps it out.
- Every wiki write goes through `lib.memory.queue.propose_and_apply` — never a direct file write, in any task.
- Fail-closed classifiers: any parse failure, missing field, or wrong type in an LLM verdict means the WHOLE fan-out is `unknown` — zero edits, reason recorded. Never a partial application of a half-parsed verdict.
- Unknown-is-an-outcome reporting (`lib/reporting.py`): a check that could not run returns/reports `Unknown(reason=...)` and is rendered as a named line, never as a clean result.
- No frontmatter `parent:`/`related:` fields. Links live in the page BODY only.
- `lib.memory.taxonomy.MAX_DEPTH` is untouched by this train. No directory nesting beyond depth 2, no per-project override.
- Every broad `except Exception` / `except BaseException` must carry `# noqa: BLE001 - <reason>` on the handler line — enforced by `tests/audit/test_fail_open_declared.py`.
- Conventional commits. Every commit message ends with the two trailer lines:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
```

- Match house style: `Final` constants, `@dataclass(frozen=True)`, docstrings citing the spec section, `__all__` on new modules.

---

### Task 1: `lib/memory/links.py` — the convention and the index

**Files:**
- Create: `lib/memory/links.py`
- Test: `tests/lib/memory/test_links.py`

**Interfaces:**
- Consumes: nothing from earlier tasks. Uses `lib.ren_paths` only for nothing in this task (the index takes an explicit `wiki_root`).
- Produces (Tasks 2, 3, 4, 5, 6, 7, 8 all rely on these exact names):
  - `@dataclass(frozen=True) PageLinks` with `parent: str | None`, `related: tuple[tuple[str, str], ...]` (stem, reason), `other: tuple[str, ...]`.
  - `@dataclass(frozen=True) LinkIndex` with `outbound: dict[str, set[str]]`, `inbound: dict[str, set[str]]`, `parent: dict[str, str | None]`, `related: dict[str, list[tuple[str, str]]]`, `pages: dict[str, str]` (rel posix path -> raw text, EVERY page including exempt ones — Task 2's `_orphan_pages` needs the corpus).
  - `parse_page_links(text: str) -> PageLinks`
  - `render_related(items: list[tuple[str, str]]) -> str` — the whole `## Related` section including the heading, trailing newline.
  - `upsert_related(text: str, stem: str, reason: str) -> str` — idempotent on `stem`.
  - `upsert_parent(text: str, stem: str) -> str` — idempotent.
  - `build_link_index(wiki_root: Path, *, project: str | None = None) -> LinkIndex`
  - `RELATED_HEADING: Final[str] = "## Related"`
  - `PARENT_PREFIX: Final[str] = "Parent: "`

- [ ] **Step 1: Write the failing tests**

```python
# tests/lib/memory/test_links.py
"""Spec 2026-09-04 §3-§4 — the link convention and the shared link index."""

from __future__ import annotations

from pathlib import Path

from lib.memory.links import (
    LinkIndex,
    PageLinks,
    build_link_index,
    parse_page_links,
    render_related,
    upsert_parent,
    upsert_related,
)

PAGE = """---
type: project-knowledge
---
# Write Door

Parent: [[memory-plane]]

The queue is the only write door. See also [[provenance]] in passing.

## Related
- [[queue-holds]] — the hold rules live next door
- [[journal]] — every applied write lands here

## Facts

- one fact
"""


def test_parse_extracts_parent_related_and_other():
    links = parse_page_links(PAGE)
    assert links.parent == "memory-plane"
    assert links.related == (
        ("queue-holds", "the hold rules live next door"),
        ("journal", "every applied write lands here"),
    )
    assert "provenance" in links.other
    # Related stems are NOT repeated in `other`.
    assert "queue-holds" not in links.other


def test_parse_no_parent_line_is_not_an_error():
    links = parse_page_links("# Bare\n\nnothing here.\n")
    assert links.parent is None
    assert links.related == ()
    assert links.other == ()


def test_parse_empty_related_section_is_empty_not_missing():
    links = parse_page_links("# T\n\nParent: [[h]]\n\n## Related\n")
    assert links.parent == "h"
    assert links.related == ()


def test_parse_markdown_links_land_in_other():
    links = parse_page_links("# T\n\nsee [the map](projects/x/map.md) for more.\n")
    assert links.other == ("projects/x/map.md",)


def test_render_related_shape():
    assert render_related([("a", "because a"), ("b", "because b")]) == (
        "## Related\n- [[a]] — because a\n- [[b]] — because b\n"
    )


def test_render_related_empty_keeps_the_heading():
    assert render_related([]) == "## Related\n"


def test_upsert_related_appends_then_is_idempotent():
    once = upsert_related(PAGE, "provenance", "stamps every applied page")
    assert "- [[provenance]] — stamps every applied page" in once
    twice = upsert_related(once, "provenance", "a different reason entirely")
    assert twice == once
    assert once.count("[[provenance]] —") == 1


def test_upsert_related_creates_the_section_when_absent():
    out = upsert_related("# T\n\nParent: [[h]]\n\nbody.\n", "x", "why")
    assert out.endswith("## Related\n- [[x]] — why\n")


def test_upsert_related_inserts_before_facts_not_after():
    out = upsert_related(PAGE, "provenance", "stamps pages")
    assert out.index("[[provenance]]") < out.index("## Facts")


def test_upsert_parent_adds_then_is_idempotent():
    once = upsert_parent("---\ntype: lesson\n---\n# T\n\nbody.\n", "memory-plane")
    assert "# T\n\nParent: [[memory-plane]]\n\nbody.\n" in once
    assert upsert_parent(once, "memory-plane") == once


def test_upsert_parent_replaces_an_existing_parent():
    out = upsert_parent(PAGE, "instrumentation")
    assert "Parent: [[instrumentation]]" in out
    assert "Parent: [[memory-plane]]" not in out
    assert out.count("Parent: ") == 1


def _wiki(tmp_path: Path) -> Path:
    root = tmp_path / "wiki"
    (root / "projects/demo/knowledge/architecture").mkdir(parents=True)
    (root / "projects/demo/knowledge/architecture/architecture.md").write_text(
        "# Architecture\n\n- [write-door](write-door.md)\n", encoding="utf-8"
    )
    (root / "projects/demo/knowledge/architecture/write-door.md").write_text(
        "# Write Door\n\nParent: [[architecture]]\n\n"
        "## Related\n- [[journal]] — lineage\n",
        encoding="utf-8",
    )
    (root / "projects/demo/knowledge/architecture/journal.md").write_text(
        "# Journal\n\nParent: [[architecture]]\n\n## Related\n", encoding="utf-8"
    )
    (root / ".ren").mkdir()
    (root / ".ren/hidden.md").write_text("# Hidden\n\n[[write-door]]\n", encoding="utf-8")
    return root


def test_build_link_index_resolves_stems_to_paths(tmp_path):
    idx = build_link_index(_wiki(tmp_path))
    assert isinstance(idx, LinkIndex)
    wd = "projects/demo/knowledge/architecture/write-door.md"
    jr = "projects/demo/knowledge/architecture/journal.md"
    hub = "projects/demo/knowledge/architecture/architecture.md"
    assert idx.outbound[wd] == {hub, jr}
    assert idx.inbound[jr] == {wd}
    assert idx.inbound[wd] == {hub}
    assert idx.parent[wd] == "architecture"
    assert idx.related[wd] == [("journal", "lineage")]


def test_build_link_index_skips_dot_dirs(tmp_path):
    idx = build_link_index(_wiki(tmp_path))
    assert not any(p.startswith(".ren/") for p in idx.pages)


def test_build_link_index_project_narrows_the_walk(tmp_path):
    root = _wiki(tmp_path)
    (root / "projects/other").mkdir(parents=True)
    (root / "projects/other/map.md").write_text("# Other\n", encoding="utf-8")
    idx = build_link_index(root, project="demo")
    assert "projects/other/map.md" not in idx.pages
    assert "projects/demo/knowledge/architecture/write-door.md" in idx.pages
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/lib/memory/test_links.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.memory.links'`

- [ ] **Step 3: Implement `lib/memory/links.py`**

```python
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
    return text[:insert_at] + "\n\n" + line + text[insert_at:].lstrip("\n").rjust(0) + (
        "" if text[insert_at:].startswith("\n\n") else ""
    ) if False else text[:insert_at] + "\n\n" + line + "\n" + text[insert_at:].lstrip("\n")


def _resolve(wiki_root: Path, pages: dict[str, str], src: str, target: str) -> str | None:
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
            dest = _resolve(wiki_root, pages, src, target)
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
    "build_link_index",
    "parse_page_links",
    "render_related",
    "upsert_parent",
    "upsert_related",
]
```

Note on `upsert_parent`: the sketch above contains a deliberate
simplification the implementer must clean up — write the no-existing-parent
branch as exactly this, and delete the dead conditional:

```python
    h1 = _H1_RE.search(text)
    if h1 is None:
        return line + "\n\n" + text.lstrip("\n")
    insert_at = h1.end()
    return text[:insert_at] + "\n\n" + line + "\n\n" + text[insert_at:].lstrip("\n")
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/lib/memory/test_links.py -q`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add lib/memory/links.py tests/lib/memory/test_links.py
git commit -m "$(cat <<'EOF'
feat(links): parse/render/index the Parent + Related body convention

Spec 2026-09-04 §3-§4. One resolver for the whole wiki graph.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 2: Refactor `_orphan_pages` onto `build_link_index`

**Files:**
- Modify: `skills/wiki-health/lib/__init__.py:435-535` (`_orphan_pages`)
- Test: `tests/skills/wiki_health/test_orphan_regression.py` (create)
- Existing regression fixtures (do NOT edit): `tests/skills/wiki_health/test_orphan_pages.py`, `tests/skills/wiki_health/test_orphan_pages_dogfood.py`

**Interfaces:**
- Consumes: `build_link_index(wiki_root) -> LinkIndex` with `.inbound`, `.pages` (Task 1).
- Produces: `_orphan_pages(wiki_root: Path) -> list[str]` — signature and output UNCHANGED. Task 7 relies on `sweep()` being able to build the index once and reuse it, so `_orphan_pages` gains an optional second parameter: `_orphan_pages(wiki_root: Path, index: LinkIndex | None = None) -> list[str]`.

- [ ] **Step 1: Write the failing regression test**

The contract is "byte-identical findings on the existing fixtures". Pin it by
capturing the CURRENT output and asserting the refactored function still
produces it, using the same dogfood shapes the existing tests build.

```python
# tests/skills/wiki_health/test_orphan_regression.py
"""Spec 2026-09-04 §4 — `_orphan_pages` refactored onto `build_link_index`
must stay byte-identical. These are the shapes the #55 fixtures cover, plus
the new-convention shapes the refactor introduces."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from lib.memory.links import build_link_index

wiki_health = importlib.import_module("skills.wiki-health.lib")


@pytest.fixture
def graph_wiki(tmp_path: Path) -> Path:
    root = tmp_path / "wiki"
    (root / "projects/demo/knowledge/architecture").mkdir(parents=True)
    (root / "projects/demo/knowledge/lessons").mkdir(parents=True)
    (root / "projects/demo/raw").mkdir(parents=True)
    (root / "archive").mkdir(parents=True)
    (root / "index.md").write_text("# Index\n\n- [demo](projects/demo/map.md)\n", encoding="utf-8")
    (root / "log.md").write_text("# Log\n", encoding="utf-8")
    (root / "projects/demo/map.md").write_text(
        "# Demo\n\n- [architecture](knowledge/architecture/architecture.md)\n", encoding="utf-8"
    )
    (root / "projects/demo/knowledge/architecture/architecture.md").write_text(
        "# Architecture\n\n- [write-door](write-door.md)\n", encoding="utf-8"
    )
    (root / "projects/demo/knowledge/architecture/write-door.md").write_text(
        "# Write Door\n\nParent: [[architecture]]\n\n## Related\n"
        "- [[journal]] — lineage\n",
        encoding="utf-8",
    )
    # Reached ONLY by a `## Related` wikilink — the new convention must save it.
    (root / "projects/demo/knowledge/architecture/journal.md").write_text(
        "# Journal\n\nParent: [[architecture]]\n\n## Related\n", encoding="utf-8"
    )
    # Nothing links to this one — a genuine orphan.
    (root / "projects/demo/knowledge/lessons/stray.md").write_text(
        "# Stray\n\nnobody points here.\n", encoding="utf-8"
    )
    # Exempt shapes: raw/ and archive/ are never orphan candidates.
    (root / "projects/demo/raw/dump.md").write_text("# Dump\n", encoding="utf-8")
    (root / "archive/old.md").write_text("# Old\n", encoding="utf-8")
    return root


def test_related_wikilink_saves_a_page_from_orphanhood(graph_wiki):
    orphans = wiki_health._orphan_pages(graph_wiki)
    assert "projects/demo/knowledge/architecture/journal.md" not in orphans


def test_genuine_orphan_still_found(graph_wiki):
    assert wiki_health._orphan_pages(graph_wiki) == [
        "projects/demo/knowledge/lessons/stray.md"
    ]


def test_raw_and_archive_stay_exempt(graph_wiki):
    orphans = wiki_health._orphan_pages(graph_wiki)
    assert "projects/demo/raw/dump.md" not in orphans
    assert "archive/old.md" not in orphans


def test_accepts_a_prebuilt_index_and_agrees_with_building_its_own(graph_wiki):
    index = build_link_index(graph_wiki)
    assert wiki_health._orphan_pages(graph_wiki, index) == wiki_health._orphan_pages(graph_wiki)
```

- [ ] **Step 2: Run the new test AND the existing orphan suites, verify the new one fails**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/wiki_health/test_orphan_regression.py tests/skills/wiki_health/test_orphan_pages.py tests/skills/wiki_health/test_orphan_pages_dogfood.py -q`
Expected: the existing two files PASS; `test_orphan_regression.py` fails on
`test_accepts_a_prebuilt_index...` (`_orphan_pages() takes 1 positional argument`)
and on `test_related_wikilink_saves_a_page_from_orphanhood` (wikilinks are not
currently resolved by `_MD_LINK_RE`).

- [ ] **Step 3: Refactor `_orphan_pages`**

Replace the page-walk and the markdown-link resolution loop (the `pages`,
`linked` and per-target `for cand in (...)` block) with the shared index.
Keep the arrow-pointer pass, the `_MD_FULL_LINK_RE` corpus scrub, and the
whole mention-fallback block EXACTLY as they are — those are the parts the
#55 fixtures pin.

```python
def _orphan_pages(wiki_root: Path, index: LinkIndex | None = None) -> list[str]:
    """#55 — durable pages with no incoming links, wiki-wide (spec
    2026-08-12-orphan-detection-design.md; the design's Candidates/Corpus
    rules are the contract).

    Refactored 2026-09-04 (§4) onto `lib.memory.links.build_link_index`, so
    the wiki has ONE link resolver instead of two. The index also resolves
    `[[wikilinks]]` — `Parent:` and `## Related` lines now save a page from
    orphanhood, which is the entire point of the convention. Everything
    below the resolution step (arrow pointers, the corpus scrub, the
    word-bounded prose-mention fallback, the exemptions) is unchanged.

    `index` (optional) lets a caller that already built the graph — `sweep`,
    which needs it for `asymmetric_links` too — pay for the walk once.
    """
    index = index if index is not None else build_link_index(wiki_root)
    pages = index.pages
    linked: set[str] = {rel for rel, srcs in index.inbound.items() if srcs}

    corpus: dict[str, str] = {}
    for src, text in pages.items():
        mention_lines: list[str] = []
        for line in text.splitlines():
            ptr = parse_pointer_line(line)
            if ptr and ptr.form == "arrow" and ptr.path:
                if ptr.path in pages and ptr.path != src:
                    linked.add(ptr.path)
                line = ""
            mention_lines.append(line)
        corpus[src] = _MD_FULL_LINK_RE.sub(" ", "\n".join(mention_lines))
    # ... the rest of the function (the _EXEMPT_ROOT loop) is UNCHANGED ...
```

Add the import at the top of the module, alongside the existing
`from skills.recall.lib import rank as _recall_rank`:

```python
from lib.memory.links import LinkIndex, build_link_index
```

- [ ] **Step 4: Run all three orphan suites, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/wiki_health/ -q`
Expected: PASS, no regressions in `test_sweep.py` either.

- [ ] **Step 5: Commit**

```bash
git add skills/wiki-health/lib/__init__.py tests/skills/wiki_health/test_orphan_regression.py
git commit -m "$(cat <<'EOF'
refactor(wiki-health): _orphan_pages reads the shared link index

Spec 2026-09-04 §4 — one resolver, not two. Wikilinks now count as
inbound links, so Parent:/## Related save a page from orphanhood.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 3: `lib/memory/fanout.py` — write-time fan-out

**Files:**
- Create: `lib/memory/fanout.py`
- Modify: `lib/instrument/collect.py` (add `KIND_FANOUT_EVENT`)
- Test: `tests/lib/memory/test_fanout.py`

**Interfaces:**
- Consumes: `build_link_index`, `parse_page_links`, `upsert_related` (Task 1); `skills.recall.lib._score_content` and `tokenize_query`; `lib.adapter.worker.parse_worker_json`; `lib.memory.queue.propose_and_apply` / `Proposal` / `NOOP_DUPLICATE`; `lib.suggestions.record` / `SuggestionSpec`; `lib.instrument.collect.record`; `lib.memory.page_types._is_folder_note_hub`.
- Produces (Tasks 4, 5, 9 rely on these exact names):
  - `FANOUT_CANDIDATES: Final[int] = 12`
  - `@dataclass(frozen=True) LandedItem` with `page: str`, `title: str`, `text: str`, `write_id: str | None`.
  - `@dataclass(frozen=True) FanoutResult` with `applied: list[dict]`, `held: list[dict]`, `suggested: list[dict]`, `candidates: list[str]`, `verdicts: dict[str, int]`, `unknown_reason: str | None`.
  - `fan_out(item: LandedItem, project: str, session: str, llm_call, *, producer: str = "wrap", candidates: int = FANOUT_CANDIDATES) -> FanoutResult`
  - `build_fanout_prompt(item: LandedItem, candidates: list[tuple[str, str]]) -> str`
  - `KIND_FANOUT_EVENT = "fanout_event"` in `lib/instrument/collect.py`.
  - **RELOCATED into `lib/memory/links.py`** (step 3 below), re-exported from
    `skills/wrap/lib/__init__.py` under their existing names so every current
    call site and test keeps working: `CONCEPT_SPLIT_BULLETS: Final[int] = 40`
    (wrap keeps `_CONCEPT_SPLIT_BULLETS` as an alias), `count_facts_bullets(text)
    -> int` (wrap alias `_count_facts_bullets`), `append_facts_bullet(text,
    item_text) -> str` (wrap alias `_append_facts_bullet`).

**Layering note.** `lib/` currently imports `skills/` NOWHERE (only docstring
references). This task must not break that: the Facts helpers move DOWN into
`lib/memory/links.py` rather than being imported UP from wrap. The one
remaining exception is `_select_candidates`' function-local
`from skills.recall.lib import _score_content, tokenize_query` — spec §5.1
mandates that exact scorer ("the recall scorer, not a new one"), the import is
deliberately function-local so module import order stays acyclic, and it is
commented as such in the code below.

- [ ] **Step 1: Write the failing tests**

```python
# tests/lib/memory/test_fanout.py
"""Spec 2026-09-04 §5 — write-time fan-out."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.instrument import collect
from lib.memory.fanout import FANOUT_CANDIDATES, LandedItem, fan_out
from lib.memory.links import parse_page_links


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    kn = root / "projects/demo/knowledge"
    (kn / "architecture").mkdir(parents=True)
    (kn / "lessons").mkdir(parents=True)
    (kn / "architecture/architecture.md").write_text(
        "---\ntype: hub\n---\n# Architecture\n", encoding="utf-8"
    )
    (kn / "architecture/write-door.md").write_text(
        "---\ntype: project-knowledge\n---\n# Write Door\n\n"
        "Parent: [[architecture]]\n\nThe queue is the write door.\n\n"
        "## Related\n\n## Facts\n\n- the queue holds contradictions\n",
        encoding="utf-8",
    )
    (kn / "architecture/journal.md").write_text(
        "---\ntype: project-knowledge\n---\n# Journal\n\n"
        "Parent: [[architecture]]\n\nThe journal records every applied write.\n\n"
        "## Related\n",
        encoding="utf-8",
    )
    (kn / "lessons/queue-lesson.md").write_text(
        "---\ntype: lesson\n---\n# Queue Lesson\n\nThe queue surprised us once.\n\n"
        "## Related\n",
        encoding="utf-8",
    )
    (kn / "architecture/human-owned.md").write_text(
        "---\ntype: project-knowledge\nren_trust: \"user\"\n---\n# Human Owned\n\n"
        "The queue is described here by a human.\n\n## Related\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    return root


ITEM = LandedItem(
    page="projects/demo/knowledge/architecture/queue-holds.md",
    title="Queue Holds",
    text="A contradicts conflict holds the write for the live session to reason about.",
    write_id="w-TEST01",
)


def _llm(verdicts):
    def call(prompt: str) -> str:
        return json.dumps({"verdicts": verdicts})
    return call


def test_relate_verdict_edits_both_pages(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\n"
        "Parent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "journal", "edge": "relate", "reason": "holds precede applies"},
    ]))
    assert result.unknown_reason is None
    assert result.verdicts["relate"] == 1
    item_links = parse_page_links((wiki / ITEM.page).read_text(encoding="utf-8"))
    other = parse_page_links(
        (wiki / "projects/demo/knowledge/architecture/journal.md").read_text(encoding="utf-8")
    )
    assert ("journal", "holds precede applies") in item_links.related
    assert ("queue-holds", "holds precede applies") in other.related


def test_fact_verdict_appends_a_facts_bullet_on_a_concept_page(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    fan_out(ITEM, "demo", "s1", _llm([
        {"page": "write-door", "edge": "fact",
         "reason": "the door is where holds happen",
         "fact": "A contradicts conflict holds the write."},
    ]))
    target = (wiki / "projects/demo/knowledge/architecture/write-door.md").read_text(encoding="utf-8")
    assert "- A contradicts conflict holds the write." in target
    assert "[[queue-holds]]" in target  # fact implies the relate edge too


def test_fact_on_a_lesson_downgrades_to_relate(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "queue-lesson", "edge": "fact", "reason": "same queue",
         "fact": "should never land"},
    ]))
    lesson = (wiki / "projects/demo/knowledge/lessons/queue-lesson.md").read_text(encoding="utf-8")
    assert "should never land" not in lesson
    assert "[[queue-holds]]" in lesson
    assert result.verdicts["relate"] == 1
    assert result.verdicts["fact"] == 0


def test_human_owned_candidate_becomes_a_suggestion_not_an_edit(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "human-owned", "edge": "relate", "reason": "same subject"},
    ]))
    page = (wiki / "projects/demo/knowledge/architecture/human-owned.md").read_text(encoding="utf-8")
    assert "[[queue-holds]]" not in page
    assert len(result.suggested) == 1
    assert result.suggested[0]["page"] == "projects/demo/knowledge/architecture/human-owned.md"


def test_unparseable_output_is_unknown_with_zero_writes(wiki):
    before = (wiki / "projects/demo/knowledge/architecture/journal.md").read_text(encoding="utf-8")
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", lambda p: "not json at all")
    assert result.unknown_reason is not None
    assert result.applied == []
    assert (wiki / "projects/demo/knowledge/architecture/journal.md").read_text(encoding="utf-8") == before


def test_missing_field_is_unknown_not_a_partial_apply(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    result = fan_out(ITEM, "demo", "s1", _llm([
        {"page": "journal", "edge": "relate", "reason": "fine"},
        {"page": "write-door", "edge": "fact", "reason": "no fact field given"},
    ]))
    assert result.unknown_reason is not None
    assert result.applied == []


def test_hubs_and_self_are_excluded_from_candidates(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    def call(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps({"verdicts": []})

    fan_out(ITEM, "demo", "s1", call)
    assert "architecture/architecture.md" not in seen[0]
    assert "queue-holds.md" not in seen[0]


def test_already_related_candidate_is_excluded(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n"
        "## Related\n- [[journal]] — already linked\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    def call(prompt: str) -> str:
        seen.append(prompt)
        return json.dumps({"verdicts": []})

    fan_out(ITEM, "demo", "s1", call)
    assert "journal.md" not in seen[0]


def test_zero_candidates_makes_no_llm_call_and_records_the_event(wiki, monkeypatch):
    (wiki / ITEM.page).write_text("# Queue Holds\n\n## Related\n", encoding="utf-8")
    monkeypatch.setattr("lib.memory.fanout.FANOUT_CANDIDATES", 0)

    def boom(prompt: str) -> str:
        raise AssertionError("llm_call must not run with zero candidates")

    result = fan_out(ITEM, "demo", "s1", boom, candidates=0)
    assert result.candidates == []
    events = collect.read(kind=collect.KIND_FANOUT_EVENT)
    assert events and events[-1]["candidates"] == 0


def test_fanout_event_shape(wiki):
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    fan_out(ITEM, "demo", "s1", _llm([
        {"page": "journal", "edge": "relate", "reason": "r"},
    ]))
    event = collect.read(kind=collect.KIND_FANOUT_EVENT)[-1]
    assert event["item"] == ITEM.page
    assert event["verdicts"] == {"relate": 1, "fact": 0, "none": 0}
    assert event["applied"] >= 1
    assert event["unknown_reason"] is None


def test_candidate_count_bounds_the_edits(wiki):
    assert FANOUT_CANDIDATES == 12


def _fatten(page: Path, bullets: int) -> None:
    """Give a page exactly `bullets` Facts bullets."""
    body = page.read_text(encoding="utf-8").split("## Facts")[0]
    facts = "\n".join(f"- existing fact {i}" for i in range(bullets))
    page.write_text(body + "## Facts\n\n" + facts + "\n", encoding="utf-8")


def test_fact_verdict_past_the_split_threshold_raises_one_suggestion(wiki):
    """Spec §5.3 — 'the 40-bullet split suggestion fires exactly as it does
    today'. Today's rule is `> CONCEPT_SPLIT_BULLETS` AFTER the append, so a
    page at exactly 40 crosses to 41 and fires."""
    from lib.memory.links import CONCEPT_SPLIT_BULLETS
    from lib import suggestions

    target = wiki / "projects/demo/knowledge/architecture/write-door.md"
    _fatten(target, CONCEPT_SPLIT_BULLETS)
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    fan_out(ITEM, "demo", "s1", _llm([
        {"page": "write-door", "edge": "fact", "reason": "holds happen at the door",
         "fact": "A contradicts conflict holds the write."},
    ]))
    splits = [
        s for s in suggestions.pending_suggestions()
        if s["fingerprint"] == f"wrap-split:{target.relative_to(wiki).as_posix()}"
    ]
    assert len(splits) == 1


def test_split_suggestion_is_not_duplicated_on_a_second_run(wiki):
    from lib.memory.links import CONCEPT_SPLIT_BULLETS
    from lib import suggestions

    target = wiki / "projects/demo/knowledge/architecture/write-door.md"
    _fatten(target, CONCEPT_SPLIT_BULLETS)
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    verdict = [{"page": "write-door", "edge": "fact", "reason": "holds happen at the door",
                "fact": "A contradicts conflict holds the write."}]
    fan_out(ITEM, "demo", "s1", _llm(verdict))
    fan_out(ITEM, "demo", "s2", _llm(verdict))
    fp = f"wrap-split:{target.relative_to(wiki).as_posix()}"
    assert len([s for s in suggestions.pending_suggestions() if s["fingerprint"] == fp]) == 1


def test_fact_verdict_under_the_threshold_raises_no_split(wiki):
    from lib import suggestions

    target = wiki / "projects/demo/knowledge/architecture/write-door.md"
    _fatten(target, 3)
    (wiki / ITEM.page).write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    fan_out(ITEM, "demo", "s1", _llm([
        {"page": "write-door", "edge": "fact", "reason": "r", "fact": "one more"},
    ]))
    assert not [s for s in suggestions.pending_suggestions() if s["fingerprint"].startswith("wrap-split:")]
```

Add `from pathlib import Path` to this test file's imports (used by `_fatten`).
`lib.suggestions.pending_suggestions()` is the verified read verb (defined at
`lib/suggestions/__init__.py:190`, returns `list[dict]` oldest-first with a
`"fingerprint"` key on each entry) — the fingerprint dedup that makes the
second-run test pass lives in `record` at line 172.

- [ ] **Step 2: Run the tests, verify they fail**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/lib/memory/test_fanout.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.memory.fanout'`

- [ ] **Step 3: Add the metric kind**

In `lib/instrument/collect.py`, after `KIND_PLACEMENT_EVENT`:

```python
#: One per durable item landed under `projects/<slug>/knowledge/` (spec
#: 2026-09-04 §5.5): `{item, candidates, verdicts: {relate, fact, none},
#: applied, held, unknown_reason}`. Zero-candidate events over a week are
#: metric-watch's "fan-out silent" signal — a broken scorer or walk, not an
#: unrelated item.
KIND_FANOUT_EVENT = "fanout_event"
```

- [ ] **Step 4: Move the Facts helpers down into `lib/memory/links.py`**

`lib/` imports `skills/` nowhere today (verified: only docstring mentions).
Fan-out needs `_append_facts_bullet` and the 40-bullet split threshold, so the
helpers move DOWN rather than being imported UP. They are pure body-section
text edits — the same job `upsert_related` already does in this module.

CUT these three from `skills/wrap/lib/__init__.py` (`_CONCEPT_SPLIT_BULLETS`,
`_count_facts_bullets` at ~line 1590, `_append_facts_bullet` at line 933) along
with the `_FACTS_HEADING_RE` / `_BULLET_LINE_RE` / `_ANY_HEADING_RE` patterns
they use, and PASTE them into `lib/memory/links.py` renamed public:

```python
#: A concept node past this many `## Facts` bullets is too big to stay one
#: page — the split is a SUGGESTION, never an auto-apply (spec 2026-08-31 §3).
CONCEPT_SPLIT_BULLETS: Final[int] = 40

_FACTS_HEADING_RE: Final = re.compile(r"^##\s+Facts\s*$", re.MULTILINE)
_BULLET_LINE_RE: Final = re.compile(r"^-\s+\S.*$", re.MULTILINE)


def count_facts_bullets(text: str) -> int:
    """Bullets under `text`'s `## Facts` heading (0 when there is none)."""
    # body identical to wrap's `_count_facts_bullets`


def append_facts_bullet(text: str, item_text: str) -> str:
    """Mechanical (no-LLM) merge for a concept node accretion: append
    `- <item_text>` as the LAST bullet under `## Facts`, creating the heading
    at the end of the page when absent."""
    # body identical to wrap's `_append_facts_bullet`
```

Then in `skills/wrap/lib/__init__.py`, re-export under the old private names so
every existing call site and test keeps working unchanged:

```python
from lib.memory.links import (
    CONCEPT_SPLIT_BULLETS as _CONCEPT_SPLIT_BULLETS,
    append_facts_bullet as _append_facts_bullet,
    count_facts_bullets as _count_facts_bullets,
)
```

Add the three public names to `lib/memory/links.py`'s `__all__`.

Run the wrap suite before going further — this move must be behaviour-neutral:

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/wrap/ tests/lib/memory/test_links.py -q`
Expected: PASS, unchanged.

- [ ] **Step 5: Implement `lib/memory/fanout.py`**

```python
"""Write-time fan-out (spec 2026-09-04 §5).

Karpathy's ingest "updates relevant entity and concept pages across the
wiki" — 10-15 pages per source. This module is that step: after a durable
item lands under `projects/<slug>/knowledge/`, rank the project's other
knowledge pages against it, ask ONE classifier-class call which of them
should now mention it, and apply every verdict through the write door.

The candidate count IS the bound on edits (§12 Q2) — a second cap would
only discard verdicts the classifier already made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Final

from lib import ren_paths
from lib.adapter.worker import WorkerOutputError, parse_worker_json
from lib.instrument import collect
from lib.memory import quarantine
from lib.memory.links import (
    CONCEPT_SPLIT_BULLETS,
    append_facts_bullet,
    build_link_index,
    count_facts_bullets,
    parse_page_links,
    upsert_related,
)
from lib.memory.page_types import _is_folder_note_hub
from lib.memory.queue import NOOP_DUPLICATE, Proposal, propose_and_apply
from lib.suggestions import SuggestionSpec
from lib.suggestions import record as record_suggestion

FANOUT_CANDIDATES: Final[int] = 12
#: Lines of each candidate shown to the classifier.
_CANDIDATE_HEAD_LINES: Final[int] = 40
_VALID_EDGES: Final[frozenset[str]] = frozenset({"relate", "fact", "none"})


@dataclass(frozen=True)
class LandedItem:
    page: str        # wiki-relative posix path of the page that just landed
    title: str
    text: str
    write_id: str | None


@dataclass(frozen=True)
class FanoutResult:
    applied: list[dict] = field(default_factory=list)
    held: list[dict] = field(default_factory=list)
    suggested: list[dict] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    verdicts: dict[str, int] = field(default_factory=lambda: {"relate": 0, "fact": 0, "none": 0})
    unknown_reason: str | None = None


def _stem(rel: str) -> str:
    return Path(rel).stem


def _trust(text: str) -> str | None:
    """`ren_trust` from a page's frontmatter, or None. Cheap line scan — the
    stamp is written by the write door, always on its own line."""
    for line in text.splitlines()[:20]:
        if line.startswith("ren_trust:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def _is_lesson(rel: str) -> bool:
    parts = Path(rel).parts
    return len(parts) >= 2 and parts[-2] == "lessons"


def _select_candidates(
    wiki_root: Path, item: LandedItem, project: str, limit: int
) -> list[tuple[str, str]]:
    """Top-`limit` `(rel_path, text)` pairs, ranked by recall's own scorer
    (§5.1 — the recall scorer, not a new one). Excluded: the item's own
    page, hubs, `lessons/lessons.md`, quarantined pages, and pages already
    in the item's `## Related`.

    The `skills.recall.lib` import is FUNCTION-LOCAL on purpose: `lib` must
    not import `skills` at module-import time (recall itself imports `lib`,
    and a top-level import would make the cycle load-order dependent).
    """
    from skills.recall.lib import _score_content, tokenize_query  # noqa: PLC0415

    index = build_link_index(wiki_root, project=project)
    item_text = index.pages.get(item.page, "")
    already = {stem for stem, _ in parse_page_links(item_text).related}
    tokens = tokenize_query(f"{item.title} {item.text}")

    scored: list[tuple[float, str, str]] = []
    prefix = f"projects/{project}/knowledge/"
    for rel, text in index.pages.items():
        if rel == item.page or not rel.startswith(prefix):
            continue
        parts = Path(rel).parts
        if _is_folder_note_hub(parts) or Path(rel).name == "lessons.md":
            continue
        if quarantine.is_quarantined(text):
            continue
        if _stem(rel) in already:
            continue
        scored.append((_score_content(text, tokens), rel, text))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [(rel, text) for _score, rel, text in scored[:limit] if _score > 0]


def build_fanout_prompt(item: LandedItem, candidates: list[tuple[str, str]]) -> str:
    """One classifier-class prompt (§5.2). Same shape as the wrap
    classifier's: strict JSON out, no prose, one verdict per candidate."""
    blocks = []
    for rel, text in candidates:
        head = "\n".join(text.splitlines()[:_CANDIDATE_HEAD_LINES])
        blocks.append(f"### {_stem(rel)}\n(path: {rel})\n{head}")
    joined = "\n\n".join(blocks)
    return (
        "A new knowledge page just landed in a wiki. Decide, for each existing\n"
        "page below, whether it should now mention the new one.\n\n"
        f"NEW PAGE: {item.title}\n{item.text}\n\n"
        f"EXISTING PAGES:\n{joined}\n\n"
        "Return ONLY this JSON, no prose, no fence:\n"
        '{"verdicts": [{"page": "<stem exactly as given>", '
        '"edge": "relate" | "fact" | "none", '
        '"reason": "<one clause saying why they are related>", '
        '"fact": "<one bullet to append — ONLY when edge is fact>"}]}\n'
        'Use "fact" only when the new page states something the existing page\n'
        'should record as its own fact; use "relate" for a plain cross-link;\n'
        'use "none" when they are unrelated.'
    )


def _parse_verdicts(raw: str, by_stem: dict[str, str]) -> list[dict]:
    """Strict parse. ANY failure raises `ValueError`, which the caller turns
    into `unknown_reason` with zero edits — fail-closed, like every other
    classifier in RenOS."""
    data = parse_worker_json(raw)
    if not isinstance(data, dict) or not isinstance(data.get("verdicts"), list):
        raise ValueError("output has no 'verdicts' list")
    out: list[dict] = []
    for v in data["verdicts"]:
        if not isinstance(v, dict):
            raise ValueError(f"verdict is not an object: {v!r}")
        page, edge, reason = v.get("page"), v.get("edge"), v.get("reason")
        if not isinstance(page, str) or page not in by_stem:
            raise ValueError(f"verdict names an unknown page: {page!r}")
        if edge not in _VALID_EDGES:
            raise ValueError(f"invalid edge {edge!r} for {page!r}")
        if edge != "none" and not (isinstance(reason, str) and reason.strip()):
            raise ValueError(f"verdict for {page!r} has no reason")
        if edge == "fact" and not (isinstance(v.get("fact"), str) and v["fact"].strip()):
            raise ValueError(f"fact verdict for {page!r} carries no fact")
        out.append(v)
    return out


def _suggest_split(page: str, session: str, producer: str, result: FanoutResult) -> None:
    """Raise the oversized-concept-node split suggestion (spec §5.3).

    Deliberately the SAME `wrap-split:{page}` fingerprint wrap's own
    concept-update branch uses: the finding is identical ("this node is too
    big"), so it must dedup against wrap's, not sit beside it as a second
    nag. `lib.suggestions.record` returns None for a fingerprint already
    pending or decided, which is what makes a second fan-out over the same
    page a no-op.
    """
    entry = record_suggestion(SuggestionSpec(
        producer=producer,
        title=f"Split large concept node: {page}",
        rationale=f"{page} has more than {CONCEPT_SPLIT_BULLETS} Facts bullets",
        evidence={"page": page, "session": session},
        kind="structured_action",
        payload={"action": "split_concept_node", "page": page},
        fingerprint=f"wrap-split:{page}",
    ))
    if entry is not None:
        result.suggested.append({"page": page, "sid": entry["sid"]})


def _write(page: str, content: str, session: str, producer: str, reason: str,
           result: FanoutResult) -> None:
    entry, prov = propose_and_apply(Proposal(
        op="UPDATE", page=page, content=content, reason=reason,
        producer=producer, writer="llm-auto", session=session,
    ))
    if prov is not None:
        result.applied.append({"qid": entry.qid, "write_id": prov.write_id, "page": page})
    elif entry.status != NOOP_DUPLICATE:
        result.held.append({"qid": entry.qid, "page": page, "conflicts": entry.conflicts})


def fan_out(
    item: LandedItem,
    project: str,
    session: str,
    llm_call: Callable[[str], str],
    *,
    producer: str = "wrap",
    candidates: int = FANOUT_CANDIDATES,
) -> FanoutResult:
    """Fan one landed item out across the pages that should now mention it.

    Never raises: a walk/read failure, a classifier failure, or a malformed
    verdict all come back as `unknown_reason` with zero edits (§9). One
    `fanout_event` is recorded per call, always.
    """
    result = FanoutResult()
    wiki_root = ren_paths.wiki_root()
    try:
        picked = _select_candidates(wiki_root, item, project, candidates)
    except OSError as exc:
        result = FanoutResult(unknown_reason=f"link index could not walk the wiki: {exc}")
        _record_event(item, result)
        return result

    result.candidates.extend(rel for rel, _ in picked)
    if not picked:
        _record_event(item, result)
        return result

    by_stem = {_stem(rel): rel for rel, _ in picked}
    texts = {rel: text for rel, text in picked}
    try:
        verdicts = _parse_verdicts(llm_call(build_fanout_prompt(item, picked)), by_stem)
    except (ValueError, WorkerOutputError, TypeError) as exc:
        result = FanoutResult(candidates=result.candidates,
                              unknown_reason=f"fan-out classifier output rejected: {exc}")
        _record_event(item, result)
        return result
    except Exception as exc:  # noqa: BLE001 - fail-closed: any classifier failure is Unknown, never a guess
        result = FanoutResult(candidates=result.candidates,
                              unknown_reason=f"fan-out classifier call failed: {exc}")
        _record_event(item, result)
        return result

    item_text = (wiki_root / item.page).read_text(encoding="utf-8")
    reason = f"fanout: {item.write_id}"
    item_stem = _stem(item.page)

    for verdict in verdicts:
        rel = by_stem[verdict["page"]]
        edge, clause = verdict["edge"], (verdict.get("reason") or "").strip()
        if edge == "none":
            result.verdicts["none"] += 1
            continue
        # §12 Q1: lessons are episodic and accrete badly — a `fact` verdict
        # on a `lessons/` page is downgraded to `relate`, never dropped.
        if edge == "fact" and _is_lesson(rel):
            edge = "relate"
        result.verdicts[edge] += 1

        target_text = texts[rel]
        new_target = upsert_related(target_text, item_stem, clause)
        split_due = False
        if edge == "fact":
            new_target = append_facts_bullet(new_target, verdict["fact"])
            # Spec §5.3: "the 40-bullet split suggestion fires exactly as it
            # does today" — today's rule (wrap's concept-update branch) is a
            # strict `>` check AFTER the append, so a node at exactly the
            # threshold crosses it on this bullet and fires.
            split_due = count_facts_bullets(new_target) > CONCEPT_SPLIT_BULLETS

        if _trust(target_text) == "user":
            # Same hold as the human-owned schema.md splice in 0.8.5: the
            # edit becomes a suggestion, the forward edge still lands.
            entry = record_suggestion(SuggestionSpec(
                producer=producer,
                title=f"Fan-out edit on a human-authored page: {rel}",
                rationale=f"{item.page} landed and relates to {rel}: {clause}",
                evidence={"page": rel, "item": item.page, "session": session},
                kind="page_write",
                payload={"op": "UPDATE", "page": rel, "content": new_target,
                         "reason": reason, "producer": producer,
                         "writer": "llm-auto", "session": session},
                fingerprint=f"fanout-edit:{item.page}:{rel}",
            ))
            result.suggested.append({"page": rel, "sid": entry["sid"] if entry else None})
        else:
            _write(rel, new_target, session, producer, reason, result)

        if split_due:
            _suggest_split(rel, session, producer, result)

        item_text = upsert_related(item_text, _stem(rel), clause)

    if item_text != (wiki_root / item.page).read_text(encoding="utf-8"):
        _write(item.page, item_text, session, producer, reason, result)

    _record_event(item, result)
    return result


def _record_event(item: LandedItem, result: FanoutResult) -> None:
    collect.record(collect.KIND_FANOUT_EVENT, {
        "item": item.page,
        "candidates": len(result.candidates),
        "verdicts": result.verdicts,
        "applied": len(result.applied),
        "held": len(result.held),
        "unknown_reason": result.unknown_reason,
    })


__all__ = [
    "FANOUT_CANDIDATES",
    "FanoutResult",
    "LandedItem",
    "build_fanout_prompt",
    "fan_out",
]
```

Note: `FanoutResult` is `frozen=True` but its list/dict fields are mutated in
place (`result.applied.append(...)`) — that is legal and intentional; frozen
only forbids rebinding the attribute.

- [ ] **Step 6: Run the tests, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/lib/memory/ tests/skills/wrap/ tests/audit/test_fail_open_declared.py -q`
Expected: PASS (15 fan-out tests, the links tests, the whole wrap suite
unchanged after the helper move, and the fail-open audit)

- [ ] **Step 7: Commit**

```bash
git add lib/memory/fanout.py lib/memory/links.py lib/instrument/collect.py skills/wrap/lib/__init__.py tests/lib/memory/test_fanout.py
git commit -m "$(cat <<'EOF'
feat(fanout): write-time fan-out across the pages a landed item touches

Spec 2026-09-04 §5. One classifier call, 12 candidates, every edit through
the write door. Fail-closed: a bad verdict is unknown with zero writes.
A fact edge past 40 bullets raises the split suggestion on wrap's own
wrap-split:{page} fingerprint, so it dedups instead of double-nagging.
The Facts helpers move down into lib/memory/links.py (wrap re-exports the
private aliases) to keep lib/ free of skills/ imports.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 4: wrap emits the convention and calls fan-out

**Files:**
- Modify: `skills/wrap/lib/__init__.py` — `_durable_create_page` call sites, `_apply_concept_create` (line ~982, the `content` template), `_route_concept_result` (line ~954), `wrap_session`'s result dict (~line 1850), `render_wrap_screen` (~line 2425)
- Test: `tests/skills/wrap/test_fanout_wiring.py` (create)

**Interfaces:**
- Consumes: `fan_out`, `LandedItem`, `FanoutResult` (Task 3); `render_related`, `upsert_parent` (Task 1).
- Produces (Task 10's docs describe these; nothing else depends on them):
  - `_concept_page_content(item, title, project, parent_stem) -> str` — the concept page body, now carrying `Parent:` and an empty `## Related`.
  - `_parent_stem_for(placement: str, project: str) -> str` — the placement leaf's own hub stem, i.e. `placement.rsplit("/", 1)[-1]`; for a lesson create, the lessons hub stem `"lessons"`.
  - `wrap_session`'s result gains `"fanout": {"unknown": [<reason str>, ...], "applied": int, "suggested": int}` — always present, empty lists/zeros when nothing fanned out.
  - `render_wrap_screen` renders `- ⚠ fan-out unknown: <reason>` per unknown, directly after the existing `concept routing blind` line.

- [ ] **Step 1: Write the failing tests**

```python
# tests/skills/wrap/test_fanout_wiring.py
"""Spec 2026-09-04 §7 — wrap renders Parent:/## Related and fans out."""

from __future__ import annotations

import importlib

import pytest

from lib.memory.fanout import FanoutResult
from lib.memory.links import parse_page_links

wrap = importlib.import_module("skills.wrap.lib")


def test_concept_page_content_carries_parent_and_empty_related():
    body = wrap._concept_page_content(
        "The queue holds contradictions.", "Queue Holds", "demo", "architecture"
    )
    links = parse_page_links(body)
    assert links.parent == "architecture"
    assert "## Related\n" in body
    assert links.related == ()
    assert "## Facts" in body
    # convention order: H1, Parent, body, Related — Related before Facts
    assert body.index("## Related") < body.index("## Facts")


def test_parent_stem_for_uses_the_leaf_hub():
    assert wrap._parent_stem_for("architecture/memory-plane", "demo") == "memory-plane"
    assert wrap._parent_stem_for("architecture", "demo") == "architecture"


def test_render_wrap_screen_reports_fanout_unknown():
    screen = wrap.render_wrap_screen(
        {"fanout": {"unknown": ["classifier output rejected: bad edge"],
                    "applied": 0, "suggested": 0}},
        "s1",
    )
    assert "fan-out unknown: classifier output rejected: bad edge" in screen


def test_render_wrap_screen_omits_the_line_when_nothing_unknown():
    screen = wrap.render_wrap_screen({"fanout": {"unknown": [], "applied": 2, "suggested": 0}}, "s1")
    assert "fan-out unknown" not in screen


def test_route_concept_result_runs_fanout_after_an_applied_create(monkeypatch):
    calls: list[tuple] = []

    def fake_fan_out(item, project, session, llm_call, *, producer="wrap", candidates=12):
        calls.append((item.page, project, producer))
        return FanoutResult(applied=[{"page": "other.md"}])

    monkeypatch.setattr(wrap, "fan_out", fake_fan_out)
    applied, unchanged, held, suggested = [], [], [], []
    fanout_acc = {"unknown": [], "applied": 0, "suggested": 0}
    created = wrap._route_concept_result(
        {"status": "applied", "qid": "q1", "write_id": "w1",
         "page": "projects/demo/knowledge/architecture/x.md", "op": "ADD",
         "schema_suggestion": None},
        applied, unchanged, held, suggested,
        item="the item text", title="X", project="demo", session="s1",
        llm_call=lambda p: "{}", fanout=fanout_acc,
    )
    assert created == 1
    assert calls == [("projects/demo/knowledge/architecture/x.md", "demo", "wrap")]
    assert fanout_acc["applied"] == 1


def test_route_concept_result_skips_fanout_for_a_held_create(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("fan-out must not run for a held write")

    monkeypatch.setattr(wrap, "fan_out", boom)
    fanout_acc = {"unknown": [], "applied": 0, "suggested": 0}
    created = wrap._route_concept_result(
        {"status": "held", "qid": "q1", "page": "p.md", "conflicts": ["contradicts"],
         "schema_suggestion": None},
        [], [], [], [],
        item="i", title="T", project="demo", session="s1",
        llm_call=lambda p: "{}", fanout=fanout_acc,
    )
    assert created == 0


def test_route_concept_result_collects_the_unknown_reason(monkeypatch):
    monkeypatch.setattr(
        wrap, "fan_out",
        lambda *a, **k: FanoutResult(unknown_reason="classifier output rejected: nope"),
    )
    fanout_acc = {"unknown": [], "applied": 0, "suggested": 0}
    wrap._route_concept_result(
        {"status": "applied", "qid": "q", "write_id": "w",
         "page": "projects/demo/knowledge/a/x.md", "op": "ADD", "schema_suggestion": None},
        [], [], [], [],
        item="i", title="T", project="demo", session="s1",
        llm_call=lambda p: "x", fanout=fanout_acc,
    )
    assert fanout_acc["unknown"] == ["classifier output rejected: nope"]
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/wrap/test_fanout_wiring.py -q`
Expected: FAIL — `AttributeError: module 'skills.wrap.lib' has no attribute '_concept_page_content'`

- [ ] **Step 3: Implement the wrap wiring**

Add the imports near the existing `from lib.suggestions import ...` block:

```python
from lib.memory.fanout import FanoutResult, LandedItem, fan_out
from lib.memory.links import render_related, upsert_parent
```

Extract the page body from `_apply_concept_create` into a helper, so the
convention has one renderer:

```python
def _parent_stem_for(placement: str, project: str) -> str:
    """The `Parent:` stem for a page landing at `placement` (spec §3): the
    page's own folder-note hub, which is named after the leaf segment. The
    classifier may override this later; the default is the shelf the page
    sits on."""
    return placement.rsplit("/", 1)[-1]


def _concept_page_content(item: str, title: str, project: str, parent_stem: str) -> str:
    """The concept page body, carrying the 2026-09-04 §3 link convention:
    H1, then `Parent:`, then the body, then a `## Related` section that is
    rendered EVEN WHEN EMPTY (a visible "nothing linked yet")."""
    sentence_match = _SENTENCE_SPLIT_RE.split(item.strip(), maxsplit=1)
    first_sentence = sentence_match[0] if sentence_match else item.strip()
    return (
        "---\n"
        "type: project-knowledge\n"
        "schema_version: 1\n"
        f"project: {project}\n"
        f'title: "{title}"\n'
        "---\n\n"
        f"# {title}\n\n"
        f"Parent: [[{parent_stem}]]\n\n"
        f"{first_sentence}\n\n"
        f"{render_related([])}\n"
        "## Facts\n\n"
        f"- {item}\n"
    )
```

In `_apply_concept_create`, replace the inline `content = (...)` block with:

```python
    content = _concept_page_content(item, title, project, _parent_stem_for(placement, project))
```

For the LESSON create path, stamp the parent on the rendered lesson body just
before it is proposed — find the `_durable_create_page(item, decision.scope,
project)` call site in `wrap_session`'s create branch and apply
`upsert_parent` to the content it queues, using the lessons hub stem:

```python
    lesson_parent = "lessons" if not page.startswith("projects/") else "lessons"
    content = upsert_parent(content, lesson_parent)
    if RELATED_HEADING not in content:
        content = content.rstrip("\n") + "\n\n" + render_related([])
```

(import `RELATED_HEADING` alongside `render_related`.)

Extend `_route_concept_result` with the fan-out call — it is the ONE place
both concept-create call sites converge, which is why the fan-out hangs here
and not in `_apply_concept_create` (a held write has nothing on disk to fan
out from):

```python
def _route_concept_result(
    concept_result: dict, applied: list[dict], unchanged: list[dict],
    held: list[dict], suggested: list[dict], *,
    item: str = "", title: str = "", project: str | None = None,
    session: str = "", llm_call=None, fanout: dict | None = None,
) -> int:
    """... (existing docstring) ...

    2026-09-04 §5/§7: when the page actually LANDED (never for a held or
    unchanged write — there is nothing new on disk to fan out from) and an
    `llm_call` is available, fan the item out across the project's other
    knowledge pages. Never raises: `fan_out` returns `unknown_reason`
    instead, which is accumulated in `fanout["unknown"]` for the close-out.
    """
```

and, in the `status == "applied"` branch, after `created = 1`:

```python
        if llm_call is not None and project and fanout is not None:
            fanout_result = fan_out(
                LandedItem(page=concept_result["page"], title=title, text=item,
                           write_id=concept_result["write_id"]),
                project, session, llm_call, producer="wrap",
            )
            fanout["applied"] += len(fanout_result.applied)
            fanout["suggested"] += len(fanout_result.suggested)
            suggested.extend(fanout_result.suggested)
            if fanout_result.unknown_reason:
                fanout["unknown"].append(fanout_result.unknown_reason)
```

In `wrap_session`, initialise `fanout = {"unknown": [], "applied": 0,
"suggested": 0}` next to the other accumulators, pass it (plus `item`,
`title=decision.title`, `project`, `session`, `llm_call`) at BOTH
`_route_concept_result` call sites, and add `result["fanout"] = fanout`
alongside the existing `result["concept_routing"] = ...` assignment.

In `render_wrap_screen`, directly after the `concept routing blind` line:

```python
    # §9: an unparseable fan-out verdict is Unknown, not silence — the
    # friend sees exactly which item's fan-out produced no edits and why.
    for reason in (wrap_result.get("fanout") or {}).get("unknown") or []:
        lines.append(f"- ⚠ fan-out unknown: {Unknown(reason=reason).reason}")
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/wrap/ -q`
Expected: PASS, including the pre-existing wrap suites.

- [ ] **Step 5: Commit**

```bash
git add skills/wrap/lib/__init__.py tests/skills/wrap/test_fanout_wiring.py
git commit -m "$(cat <<'EOF'
feat(wrap): render Parent:/## Related on creates and fan out after landing

Spec 2026-09-04 §7. Fan-out runs only for writes that actually landed;
an unknown verdict surfaces on the close-out screen.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 5: distill — landing path, `seed_tree`, and `WRITE_CAP`

**Files:**
- Modify: `skills/distill/lib/__init__.py` — `apply_candidates` (line 166, the `prov is not None` branch at ~line 226), `seed_tree` (line 379, the `See: [[node]]` marker at ~line 559)
- Test: `tests/skills/distill/test_fanout_wiring.py` (create)

**Interfaces:**
- Consumes: `fan_out`, `LandedItem` (Task 3); `upsert_parent`, `render_related`, `RELATED_HEADING`, `parse_page_links` (Task 1); `_concept_page_content` (Task 4, via `_apply_concept_create`).
- Produces: `apply_candidates` and `seed_tree` both gain an `llm_call` path to fan-out; `WRITE_CAP` now counts fan-out edits (`len(applied) + len(held) + fanout_writes >= cap`). `seed_tree`'s result dict gains `"fanout": {"unknown": [...], "applied": int, "suggested": int}`; `apply_candidates` gains the same key.

- [ ] **Step 1: Write the failing tests**

```python
# tests/skills/distill/test_fanout_wiring.py
"""Spec 2026-09-04 §7 — distill emits the convention and pays for fan-out
edits out of WRITE_CAP."""

from __future__ import annotations

import importlib

from lib.memory.fanout import FanoutResult
from lib.memory.links import parse_page_links

distill = importlib.import_module("skills.distill.lib")


def test_seed_tree_marker_is_a_parent_line_not_a_see_line():
    body = "---\ntype: lesson\n---\n# A Lesson\n\nSomething happened.\n"
    annotated = distill._annotate_lesson(body, "memory-plane")
    assert parse_page_links(annotated).parent == "memory-plane"
    assert "See: [[memory-plane]]" not in annotated


def test_annotate_lesson_is_idempotent():
    body = "---\ntype: lesson\n---\n# A Lesson\n\nSomething happened.\n"
    once = distill._annotate_lesson(body, "memory-plane")
    assert distill._annotate_lesson(once, "memory-plane") == once


def test_annotate_lesson_adds_an_empty_related_section():
    out = distill._annotate_lesson("# L\n\nbody.\n", "memory-plane")
    assert "## Related" in out
    assert parse_page_links(out).related == ()


def test_fanout_edits_count_against_write_cap(monkeypatch):
    """A capped run must land FEWER items, not MORE writes (spec §5 budget)."""
    monkeypatch.setattr(
        distill, "fan_out",
        lambda *a, **k: FanoutResult(applied=[{"page": "x.md"}, {"page": "y.md"}]),
    )
    counted = distill._fanout_write_count(FanoutResult(applied=[{"page": "x"}, {"page": "y"}]))
    assert counted == 2


def test_fanout_write_count_ignores_held_and_suggested():
    assert distill._fanout_write_count(
        FanoutResult(applied=[{"page": "x"}], held=[{"page": "y"}], suggested=[{"page": "z"}])
    ) == 1
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/distill/test_fanout_wiring.py -q`
Expected: FAIL — `AttributeError: module 'skills.distill.lib' has no attribute '_annotate_lesson'`

- [ ] **Step 3: Implement the distill wiring**

Add the imports:

```python
from lib.memory.fanout import FanoutResult, LandedItem, fan_out
from lib.memory.links import RELATED_HEADING, parse_page_links, render_related, upsert_parent
```

Two small helpers:

```python
def _annotate_lesson(text: str, node_stem: str) -> str:
    """Point a distilled lesson at the concept node it seeded (spec
    2026-09-04 §7). This REPLACES the old `See: [[<node>]]` marker line: the
    pointer is the same edge, now expressed in the convention every consumer
    reads. Idempotent — `upsert_parent` replaces the single `Parent:` line
    and `## Related` is created only once."""
    out = upsert_parent(text, node_stem)
    if RELATED_HEADING not in out:
        out = out.rstrip("\n") + "\n\n" + render_related([])
    return out


def _fanout_write_count(result: FanoutResult) -> int:
    """Fan-out writes that actually landed — what `WRITE_CAP` charges for
    (spec §5 budget: a capped run lands fewer ITEMS, never more writes).
    Held and suggested edits are not writes on disk, so they are free."""
    return len(result.applied)
```

In `seed_tree`, replace the marker block. The old code computed
`lastseg = decision.placement.rsplit("/", 1)[-1]`, then
`marker = f"See: [[{lastseg}]]"` and tested `marker in lesson["text"]`.
The new code:

```python
            lastseg = decision.placement.rsplit("/", 1)[-1]
            annotate_content = _annotate_lesson(lesson["text"], lastseg)
            if annotate_content == lesson["text"]:
                # Already carries this Parent: — a watermark-reset re-run,
                # or the same placement landed via another path.
                duplicates.append({"page": lesson["page"]})
            elif _target_trust(lesson["page"]) == "user":
                ...  # unchanged suggestion branch, but with:
                #     payload={"op": "UPDATE", "page": lesson["page"],
                #              "content": annotate_content},
            else:
                ...  # unchanged propose_and_apply branch, `content=annotate_content`
```

Note the suggestion payload changes from `"append"` to `"content"` — the old
append form cannot express an idempotent `Parent:` replacement.

Then, in `seed_tree`, immediately after `writes += 1` on the applied branch,
fan out and charge the cap:

```python
            if llm_call is not None:
                fanout_result = fan_out(
                    LandedItem(page=concept_result["page"],
                               title=decision.title or lastseg,
                               text=body, write_id=concept_result["write_id"]),
                    project, run_session, llm_call, producer="distiller",
                )
                writes += _fanout_write_count(fanout_result)
                fanout["applied"] += len(fanout_result.applied)
                fanout["suggested"] += len(fanout_result.suggested)
                suggested.extend(fanout_result.suggested)
                if fanout_result.unknown_reason:
                    fanout["unknown"].append(fanout_result.unknown_reason)
```

Initialise `fanout = {"unknown": [], "applied": 0, "suggested": 0}` next to the
other accumulators in `seed_tree` and include `"fanout": fanout` in its return
dict.

Do the same in `apply_candidates`' `prov is not None` branch (after the
`_ensure_hub` call), guarding on `cand.get("project")` being set — a global
lesson has no project and therefore no fan-out corpus. `apply_candidates` gains
an `llm_call=None` keyword parameter and the same `"fanout"` result key, and
its cap check becomes:

```python
        if len(applied) + len(held) + fanout_writes >= cap:
```

with `fanout_writes` accumulated by `_fanout_write_count`.

Also stamp the convention on distiller CREATE content before it is proposed,
in the same `else:` branch that computes `page`:

```python
            content = _annotate_lesson(cand["content"], "lessons")
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/distill/ -q`
Expected: PASS. Existing `seed_tree` tests that assert on the `See: [[...]]`
marker must be updated in place to assert on `Parent: [[...]]` — that string
change is part of this task, not a separate one.

- [ ] **Step 5: Commit**

```bash
git add skills/distill/lib/__init__.py tests/skills/distill/
git commit -m "$(cat <<'EOF'
feat(distill): Parent: replaces See:, and WRITE_CAP charges fan-out edits

Spec 2026-09-04 §7. A capped run lands fewer items rather than more writes.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 6: ingest — the drafting spec requires the convention, `ingest()` validates it

**Files:**
- Modify: `skills/ingest-project/lib/__init__.py` — `ingest()` signature and body (lines 145-345)
- Modify: `skills/ingest-project/SKILL.md` — steps 3, 4, 5 and the failure-mode table (line ~110)
- Test: `tests/skills/ingest_project/test_link_validation.py` (create)

**Interfaces:**
- Consumes: `parse_page_links` (Task 1).
- Produces:
  - `ingest(..., leaf_pages: list[dict] | None = None)` — each entry `{"name": "<relative path under knowledge/>", "body": "<markdown>"}`, the exact shape SKILL.md step 5 already describes. `ingest()` queues each leaf itself (`producer="ingest"`, `writer="llm-auto"`) after the hubs and before the map.
  - `result["link_errors"]: list[dict]` — always present, `[]` when clean. Each entry `{"page": <rel path>, "error": <str>}`.
  - Ingest does NOT call `fan_out` (spec §5: the draft already touches many pages).

- [ ] **Step 1: Write the failing tests**

```python
# tests/skills/ingest_project/test_link_validation.py
"""Spec 2026-09-04 §7 — ingest validates the link convention on drafted
leaves and reports errors WITHOUT dropping the leaf."""

from __future__ import annotations

import importlib

import pytest

ingest_lib = importlib.import_module("skills.ingest-project.lib")

SCHEMA = """---
type: project-schema
---
# Schema

```taxonomy
architecture/
```
"""
HUBS = {"architecture": "---\ntype: hub\nhub: true\n---\n# Architecture\n"}


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    root.mkdir()
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(ingest_lib, "require_backup", lambda *a, **k: None)
    return root


GOOD_LEAF = {
    "name": "architecture/write-door.md",
    "body": "---\ntype: project-knowledge\n---\n# Write Door\n\n"
            "Parent: [[architecture]]\n\nThe queue.\n\n"
            "## Related\n- [[journal]] — lineage\n",
}
NO_PARENT_LEAF = {
    "name": "architecture/journal.md",
    "body": "---\ntype: project-knowledge\n---\n# Journal\n\nrecords writes.\n",
}


def test_clean_leaves_report_no_link_errors(wiki):
    result = ingest_lib.ingest(
        "demo", ["a fact"], [], "s1",
        schema_page=SCHEMA, hub_pages=HUBS, leaf_pages=[GOOD_LEAF],
    )
    assert result["link_errors"] == []


def test_leaf_without_parent_is_reported_but_still_written(wiki):
    result = ingest_lib.ingest(
        "demo", ["a fact"], [], "s1",
        schema_page=SCHEMA, hub_pages=HUBS, leaf_pages=[NO_PARENT_LEAF],
    )
    errors = {e["page"]: e["error"] for e in result["link_errors"]}
    assert "projects/demo/knowledge/architecture/journal.md" in errors
    assert "Parent:" in errors["projects/demo/knowledge/architecture/journal.md"]
    # Missing links are lint's job to find, never a reason to lose knowledge.
    assert (wiki / "projects/demo/knowledge/architecture/journal.md").is_file()


def test_leaf_without_related_is_reported_too(wiki):
    leaf = {
        "name": "architecture/x.md",
        "body": "# X\n\nParent: [[architecture]]\n\nbody.\n",
    }
    result = ingest_lib.ingest(
        "demo", ["f"], [], "s1", schema_page=SCHEMA, hub_pages=HUBS, leaf_pages=[leaf]
    )
    errors = {e["page"]: e["error"] for e in result["link_errors"]}
    assert "Related" in errors["projects/demo/knowledge/architecture/x.md"]


def test_link_errors_key_is_always_present_on_a_legacy_call(wiki):
    result = ingest_lib.ingest("demo", ["a fact"], [], "s1")
    assert result["link_errors"] == []
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/ingest_project/test_link_validation.py -q`
Expected: FAIL — `TypeError: ingest() got an unexpected keyword argument 'leaf_pages'`

- [ ] **Step 3: Implement the ingest validation**

Add the import:

```python
from lib.memory.links import parse_page_links
```

Add the parameter and the validation-plus-queue block. Place it AFTER the hub
writes and BEFORE the map write, so a leaf's `Parent:` points at a hub that is
already on disk:

```python
def ingest(
    project_slug: str,
    knowledge: list[str],
    pointers: list[dict],
    session: str,
    repo_root: Path | None = None,
    schema_page: str | None = None,
    hub_pages: dict[str, str] | None = None,
    leaf_pages: list[dict] | None = None,
) -> dict:
```

```python
def _validate_leaf_links(page: str, body: str) -> str | None:
    """The link convention's drafting contract (spec 2026-09-04 §7): every
    leaf needs a `Parent:` line and a `## Related` with at least one
    sibling. Returns the error string, or None when clean.

    A failure is a DRAFTING error, reported — never a reason to drop the
    leaf. Missing links are lint's job to find; lost knowledge is nobody's.
    """
    links = parse_page_links(body)
    if links.parent is None:
        return "leaf has no `Parent:` line"
    if not links.related:
        return "leaf has no `## Related` sibling"
    return None
```

```python
    link_errors: list[dict] = []
    for leaf in leaf_pages or []:
        name = str(leaf.get("name", "")).lstrip("/")
        body = leaf.get("body") or ""
        leaf_page = f"projects/{project_slug}/knowledge/{name}"
        error = _validate_leaf_links(leaf_page, body)
        if error is not None:
            link_errors.append({"page": leaf_page, "error": error})
        propose_and_apply(Proposal(
            op="ADD", page=leaf_page, content=body, reason="ingest-project leaf",
            producer="ingest", writer="llm-auto", session=session, salience=False,
        ))
```

and add `"link_errors": link_errors,` to the returned dict.

- [ ] **Step 4: Update `skills/ingest-project/SKILL.md`**

In step 3's leaf-drafting bullet (the "Leaf pages" stage) and in step 5, replace
the drafting instruction with:

> 5. **Pass the drafted leaf pages to `ingest()` as `leaf_pages`** — a list of
>    `{"name": "<relative path under knowledge/>", "body": "<markdown>"}`.
>    Every leaf body MUST carry, after its H1: a `Parent: [[<stem>]]` line
>    naming its hub (or the concept page that is its real conceptual parent),
>    and a `## Related` section with at least one sibling bullet in the form
>    `- [[<stem>]] — <one clause saying why>`. Every hub body MUST carry a
>    `Parent:` line too — its parent hub, or the project `map.md` for a
>    top-level hub. `ingest()` validates each leaf with
>    `lib.memory.links.parse_page_links` and reports failures in
>    `result["link_errors"]`; the leaf is queued either way — missing links
>    are lint's job to find, not a reason to lose knowledge. Do NOT queue
>    leaves yourself with `propose_and_apply`.

Add the failure-mode table row:

| A drafted leaf has no `Parent:` or no `## Related` sibling | reported, leaf still written | `result["link_errors"]`, and `/ren:wiki-health`'s `asymmetric_links`/`orphan_pages` next sweep |

- [ ] **Step 5: Run the tests, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/ingest_project/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add skills/ingest-project/lib/__init__.py skills/ingest-project/SKILL.md tests/skills/ingest_project/test_link_validation.py
git commit -m "$(cat <<'EOF'
feat(ingest): drafting spec requires Parent:/Related, ingest validates it

Spec 2026-09-04 §7. A leaf with missing links is reported in link_errors
and written anyway.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 7: wiki-health — `asymmetric_links` and `unpaged_concepts`

**Files:**
- Modify: `skills/wiki-health/lib/__init__.py` — `sweep()` (line 848), `render_report()` (line 978)
- Modify: `skills/wiki-health/lib/lint.py` — `_lint_page` (line 376), a new `_asymmetric_link_findings`
- Modify: `agents/ren-wiki-lint.md` — declare the new safe-fix class
- Test: `tests/skills/wiki_health/test_graph_findings.py` (create)

**Interfaces:**
- Consumes: `build_link_index`, `parse_page_links`, `upsert_related` (Task 1); `lib.memory.taxonomy.load_taxonomy` / `TaxonomyError`.
- Produces:
  - `_asymmetric_links(wiki_root: Path, index: LinkIndex) -> list[dict]` — `{"page", "with", "reason"}`, sorted by `(page, with)`.
  - `_unpaged_concepts(wiki_root: Path, index: LinkIndex) -> list[dict]` — `{"node": <taxonomy path or stem>, "kind": "hub-only" | "unresolved-link", "linkers": [<rel paths>]}`.
  - `sweep()` gains keys `"asymmetric_links"` and `"unpaged_concepts"`, both always present.
  - `render_report()` gains the two sections, `- none` when empty.
  - `lint._asymmetric_link_findings(wiki_root, page, text, index) -> tuple[str, list[str]]` returning `(new_text, fix_classes)`; the fix class name is `"asymmetric-link-reversed"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/skills/wiki_health/test_graph_findings.py
"""Spec 2026-09-04 §6 — asymmetric_links and unpaged_concepts."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from lib.memory.links import build_link_index

wiki_health = importlib.import_module("skills.wiki-health.lib")
lint = importlib.import_module("skills.wiki-health.lib.lint")


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    root = tmp_path / "wiki"
    kn = root / "projects/demo/knowledge/architecture"
    kn.mkdir(parents=True)
    (root / "projects/demo/schema.md").write_text(
        "---\ntype: project-schema\n---\n# Schema\n\n"
        "```taxonomy\narchitecture/\n  memory-plane/\n```\n",
        encoding="utf-8",
    )
    (kn / "architecture.md").write_text("---\ntype: hub\n---\n# Architecture\n", encoding="utf-8")
    (kn / "a.md").write_text(
        "---\ntype: project-knowledge\n---\n# A\n\nParent: [[architecture]]\n\n"
        "## Related\n- [[b]] — a knows b\n",
        encoding="utf-8",
    )
    (kn / "b.md").write_text(
        "---\ntype: project-knowledge\n---\n# B\n\nParent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    (kn / "human.md").write_text(
        "---\ntype: project-knowledge\nren_trust: \"user\"\n---\n# Human\n\n"
        "Parent: [[architecture]]\n\n## Related\n",
        encoding="utf-8",
    )
    (kn / "c.md").write_text(
        "---\ntype: project-knowledge\n---\n# C\n\nParent: [[architecture]]\n\n"
        "## Related\n- [[human]] — c knows human\n",
        encoding="utf-8",
    )
    # `memory-plane` is a taxonomy node with a hub only — no content page.
    mp = kn / "memory-plane"
    mp.mkdir()
    (mp / "memory-plane.md").write_text("---\ntype: hub\n---\n# Memory Plane\n", encoding="utf-8")
    return root


def test_asymmetric_link_found(wiki):
    findings = wiki_health._asymmetric_links(wiki, build_link_index(wiki))
    pairs = {(f["page"], f["with"]) for f in findings}
    assert ("projects/demo/knowledge/architecture/b.md",
            "projects/demo/knowledge/architecture/a.md") in pairs


def test_symmetric_pair_is_not_a_finding(wiki):
    p = wiki / "projects/demo/knowledge/architecture/b.md"
    p.write_text(p.read_text(encoding="utf-8") + "- [[a]] — b knows a\n", encoding="utf-8")
    findings = wiki_health._asymmetric_links(wiki, build_link_index(wiki))
    pairs = {(f["page"], f["with"]) for f in findings}
    assert ("projects/demo/knowledge/architecture/b.md",
            "projects/demo/knowledge/architecture/a.md") not in pairs


def test_human_owned_page_is_reported_never_fixed(wiki):
    index = build_link_index(wiki)
    findings = wiki_health._asymmetric_links(wiki, index)
    human = "projects/demo/knowledge/architecture/human.md"
    assert any(f["page"] == human for f in findings)
    assert lint.is_fixable_page(human) is True  # path-fixable...
    text = (wiki / human).read_text(encoding="utf-8")
    new_text, fixes = lint._asymmetric_link_findings(wiki, human, text, index)
    assert fixes == []          # ...but trust=user blocks the WRITE
    assert new_text == text


def test_reverse_bullet_is_applied_with_the_reverse_reason(wiki):
    index = build_link_index(wiki)
    page = "projects/demo/knowledge/architecture/b.md"
    text = (wiki / page).read_text(encoding="utf-8")
    new_text, fixes = lint._asymmetric_link_findings(wiki, page, text, index)
    assert fixes == ["asymmetric-link-reversed"]
    assert "- [[a]] — (reverse of [[a]])" in new_text


def test_unpaged_concepts_finds_a_hub_only_taxonomy_node(wiki, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))
    findings = wiki_health._unpaged_concepts(wiki, build_link_index(wiki))
    assert any(f["node"] == "architecture/memory-plane" and f["kind"] == "hub-only"
               for f in findings)


def test_unpaged_concepts_finds_a_link_three_pages_share(wiki, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))
    kn = wiki / "projects/demo/knowledge/architecture"
    for name in ("d.md", "e.md", "f.md"):
        (kn / name).write_text(
            f"---\ntype: project-knowledge\n---\n# {name}\n\nParent: [[architecture]]\n\n"
            "## Related\n- [[ghost-concept]] — everyone means this\n",
            encoding="utf-8",
        )
    findings = wiki_health._unpaged_concepts(wiki, build_link_index(wiki))
    ghost = [f for f in findings if f["node"] == "ghost-concept"]
    assert ghost and ghost[0]["kind"] == "unresolved-link"
    assert len(ghost[0]["linkers"]) == 3


def test_unpaged_concepts_ignores_a_link_only_two_pages_share(wiki, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))
    kn = wiki / "projects/demo/knowledge/architecture"
    for name in ("d.md", "e.md"):
        (kn / name).write_text(
            f"---\ntype: project-knowledge\n---\n# {name}\n\nParent: [[architecture]]\n\n"
            "## Related\n- [[rare-ghost]] — only two of us\n",
            encoding="utf-8",
        )
    findings = wiki_health._unpaged_concepts(wiki, build_link_index(wiki))
    assert not any(f["node"] == "rare-ghost" for f in findings)


def test_sweep_carries_both_keys(wiki, monkeypatch):
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))
    findings = wiki_health.sweep(wiki)
    assert "asymmetric_links" in findings
    assert "unpaged_concepts" in findings


def test_render_report_renders_both_sections_with_none():
    text = wiki_health.render_report({
        "generated_at": "2026-09-04T00:00:00Z",
        "asymmetric_links": [], "unpaged_concepts": [],
    })
    assert "## Asymmetric links" in text
    assert "## Unpaged concepts" in text
    assert text.count("- none") >= 2
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/wiki_health/test_graph_findings.py -q`
Expected: FAIL — `AttributeError: ... has no attribute '_asymmetric_links'`

- [ ] **Step 3: Implement the two findings in `skills/wiki-health/lib/__init__.py`**

```python
def _asymmetric_links(wiki_root: Path, index: LinkIndex) -> list[dict]:
    """Spec 2026-09-04 §6 — page A lists B under `## Related` and B's own
    `## Related` does not list A.

    The finding is on B (the page MISSING the bullet), naming A as `with`:
    that is the page the fix would write. Human-owned pages are still
    REPORTED here — the write-side guard lives in the lint, so the sweep's
    report stays complete."""
    by_stem: dict[str, list[str]] = {}
    for rel in index.pages:
        by_stem.setdefault(Path(rel).stem, []).append(rel)

    findings: list[dict] = []
    for src, related in index.related.items():
        for stem, reason in related:
            targets = by_stem.get(stem, [])
            if len(targets) != 1:
                continue  # ambiguous or dangling — that's the lint's rule, not this one
            dest = targets[0]
            if dest == src:
                continue
            if any(s == Path(src).stem for s, _ in index.related.get(dest, [])):
                continue
            findings.append({"page": dest, "with": src, "reason": reason})
    return sorted(findings, key=lambda f: (f["page"], f["with"]))


def _unpaged_concepts(wiki_root: Path, index: LinkIndex) -> list[dict]:
    """Spec 2026-09-04 §6 — a concept nothing has a page for.

    Two shapes:
      * `hub-only` — a taxonomy node from `schema.md` whose directory holds
        only its folder-note hub (the "legacy hand-seeded node" case 0.8.5
        special-cases).
      * `unresolved-link` — a `[[stem]]` that at least three DISTINCT pages
        link and that resolves to nothing.

    Reported as a suggestion, never auto-created: minting a page is model
    work, not a mechanical fix. Unreadable/unparseable schemas are skipped
    silently — the taxonomy's own health is `/ren:doctor`'s finding, not
    this one's."""
    findings: list[dict] = []
    for schema in sorted(wiki_root.glob("projects/*/schema.md")):
        slug = schema.parent.name
        try:
            tax = parse_taxonomy(schema.read_text(encoding="utf-8"))
        except (TaxonomyError, OSError):
            continue
        for node in tax.nodes:
            node_dir = wiki_root / "projects" / slug / "knowledge" / node
            if not node_dir.is_dir():
                continue
            hub_name = f"{node.rsplit('/', 1)[-1]}.md"
            contents = [p.name for p in node_dir.glob("*.md")]
            if contents == [hub_name]:
                findings.append({"node": node, "kind": "hub-only", "linkers": []})

    linkers: dict[str, set[str]] = {}
    stems = {Path(rel).stem for rel in index.pages}
    for src, text in index.pages.items():
        links = parse_page_links(text)
        for stem in [s for s, _ in links.related] + list(links.other):
            if "/" in stem or stem.endswith(".md") or stem in stems:
                continue
            linkers.setdefault(stem, set()).add(src)
    for stem, srcs in linkers.items():
        if len(srcs) >= _UNPAGED_LINKER_THRESHOLD:
            findings.append({"node": stem, "kind": "unresolved-link",
                             "linkers": sorted(srcs)})
    return sorted(findings, key=lambda f: (f["kind"], f["node"]))
```

Add the module constant and imports:

```python
from lib.memory.links import LinkIndex, build_link_index, parse_page_links
from lib.memory.taxonomy import TaxonomyError, parse_taxonomy

#: How many distinct pages must link an unresolvable `[[stem]]` before it
#: counts as a concept the wiki wants a page for (spec 2026-09-04 §6).
_UNPAGED_LINKER_THRESHOLD: Final[int] = 3
```

In `sweep()`, build the index ONCE and pass it to both consumers:

```python
    link_index = build_link_index(wiki_root)
```

then in the returned dict:

```python
        "orphan_pages": _orphan_pages(wiki_root, link_index),
        "asymmetric_links": _asymmetric_links(wiki_root, link_index),
        "unpaged_concepts": _unpaged_concepts(wiki_root, link_index),
```

Extend the `sweep()` docstring with the two new keys (a 14th and 15th key),
matching the numbering style already there.

In `render_report()`, after the "Knowledge dirs without a hub" section:

```python
    lines.append("## Asymmetric links")
    asym = findings.get("asymmetric_links") or []
    if asym:
        lines.extend(
            f"- {a['page']} is missing the reverse of {a['with']}: {a['reason']}"
            for a in asym
        )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Unpaged concepts")
    unpaged = findings.get("unpaged_concepts") or []
    if unpaged:
        lines.extend(
            f"- {u['node']} ({u['kind']})"
            + (f" — linked by {len(u['linkers'])} pages" if u["linkers"] else "")
            for u in unpaged
        )
    else:
        lines.append("- none")
    lines.append("")
```

- [ ] **Step 4: Implement the safe auto-fix in `skills/wiki-health/lib/lint.py`**

```python
def _asymmetric_link_findings(
    wiki_root: Path, page: str, text: str, index: LinkIndex
) -> tuple[str, list[str]]:
    """Add the missing reverse `## Related` bullet (spec 2026-09-04 §6).

    Mechanically safe: the forward edge is already on disk and says these
    two pages are related; the reverse bullet asserts nothing new. Reason
    is the fixed clause `(reverse of [[A]])` so the fix is self-describing
    and re-running it is a no-op (`upsert_related` is idempotent).

    Human-owned pages (`ren_trust: "user"`) are NEVER written — the sweep
    still reports them, the lint just refuses the edit, exactly like
    `_ensure_hub`'s trust guard."""
    if _page_trust(text) == "user":
        return text, []
    new_text = text
    for stem, _reason in _missing_reverse_stems(page, index):
        new_text = upsert_related(new_text, stem, f"(reverse of [[{stem}]])")
    return new_text, (["asymmetric-link-reversed"] if new_text != text else [])


def _missing_reverse_stems(page: str, index: LinkIndex) -> list[tuple[str, str]]:
    """`(stem, reason)` for every page that lists `page` under `## Related`
    while `page` does not list it back."""
    own = {s for s, _ in index.related.get(page, [])}
    out: list[tuple[str, str]] = []
    for src, related in index.related.items():
        if src == page:
            continue
        if any(s == Path(page).stem for s, _ in related) and Path(src).stem not in own:
            out.append((Path(src).stem, ""))
    return sorted(set(out))
```

Import `_page_trust` (currently in `skills/wiki-health/lib/__init__.py:1210`) —
move it to `lint.py` and re-export it from `__init__.py` so the two callers
share one predicate, or import it lazily inside the function to avoid a
circular import. Prefer the lazy import: `from skills.wiki-health.lib import
_page_trust` cannot be written as a normal import (the dash), so define a
local copy in `lint.py`:

```python
def _page_trust(md_text: str) -> str | None:
    """`ren_trust` from a page's frontmatter, or None. Local copy of the
    `__init__` helper — the dashed package name makes a cross-import
    awkward, and the predicate is three lines."""
    for line in md_text.splitlines()[:20]:
        if line.startswith("ren_trust:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None
```

Wire it into `_lint_page` — it needs the index, so `_lint_page` and
`run_incremental_lint` both gain an `index: LinkIndex` parameter, built once in
`run_incremental_lint` right after `all_pages`:

```python
    link_index = build_link_index(wiki_root)
```

and in `_lint_page`, after the `_link_findings` call:

```python
    text, asym_fixes = _asymmetric_link_findings(wiki_root, page, text, index)
    fixes.extend(asym_fixes)
```

- [ ] **Step 5: Declare the fix class in `agents/ren-wiki-lint.md`**

In the section listing what the engine auto-fixes, add:

> - `asymmetric-link-reversed` — page A's `## Related` lists B but B's does
>   not list A; the engine adds the reverse bullet with the fixed reason
>   `(reverse of [[A]])`. Mechanically safe: the forward edge is already on
>   disk, so the reverse asserts nothing new. Never applied to a page whose
>   `ren_trust` is `"user"` — those come back as findings for a human.

- [ ] **Step 6: Run the tests, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/wiki_health/ -q`
Expected: PASS, including `test_incremental_lint.py` and `test_sweep.py`.

- [ ] **Step 7: Commit**

```bash
git add skills/wiki-health/lib/__init__.py skills/wiki-health/lib/lint.py agents/ren-wiki-lint.md tests/skills/wiki_health/test_graph_findings.py
git commit -m "$(cat <<'EOF'
feat(wiki-health): audit the graph — asymmetric_links, unpaged_concepts

Spec 2026-09-04 §6. The reverse bullet is a safe auto-fix through the
queue; a human-owned page is reported, never edited.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 8: recall — the inbound-link boost

**Files:**
- Modify: `skills/recall/lib/__init__.py` — `rank()` (line 161), new `_inbound_index` memo
- Modify: `lib/evalkit/fixtures/retrieval_fixture.json` — two new cases
- Test: `tests/skills/recall/test_inbound_boost.py` (create)

**Interfaces:**
- Consumes: `build_link_index`, `LinkIndex` (Task 1); `lib.memory.page_types._is_folder_note_hub`.
- Produces:
  - `INBOUND_BOOST_PER_LINK: Final[float] = 0.1`
  - `INBOUND_BOOST_CAP: Final[int] = 5`
  - `_inbound_counts(wiki_root: Path) -> dict[str, int]` — memoised on `(wiki_root, wiki_root.stat().st_mtime)`.
  - `rank(query, candidate_pages, wiki_root)` — signature UNCHANGED (the eval harness's `ranker_fn` contract depends on it).

- [ ] **Step 1: Write the failing tests**

```python
# tests/skills/recall/test_inbound_boost.py
"""Spec 2026-09-04 §8 — recall ranks with the graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from skills.recall.lib import (
    INBOUND_BOOST_CAP,
    INBOUND_BOOST_PER_LINK,
    _inbound_counts,
    rank,
)


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    root = tmp_path / "wiki"
    kn = root / "projects/demo/knowledge/architecture"
    kn.mkdir(parents=True)
    body = ("---\ntype: project-knowledge\n---\n# {t}\n\n"
            "Parent: [[architecture]]\n\nThe write door queues every proposal.\n\n"
            "## Related\n")
    (kn / "linked.md").write_text(body.format(t="Linked"), encoding="utf-8")
    (kn / "twin.md").write_text(body.format(t="Twin"), encoding="utf-8")
    (kn / "architecture.md").write_text(
        "---\ntype: hub\n---\n# Architecture\n\n"
        "The write door queues every proposal.\n\n"
        "## Related\n- [[linked]] — hub link\n",
        encoding="utf-8",
    )
    for i in range(3):
        (kn / f"src{i}.md").write_text(
            f"# Src{i}\n\nParent: [[architecture]]\n\n"
            "## Related\n- [[linked]] — points at linked\n",
            encoding="utf-8",
        )
    return root


def test_well_linked_page_outranks_its_unlinked_twin(wiki):
    ranked = rank("write door queues proposal", [
        "projects/demo/knowledge/architecture/twin.md",
        "projects/demo/knowledge/architecture/linked.md",
    ], wiki)
    assert ranked[0] == "projects/demo/knowledge/architecture/linked.md"


def test_hub_is_excluded_from_the_boost(wiki):
    counts = _inbound_counts(wiki)
    assert counts.get("projects/demo/knowledge/architecture/architecture.md", 0) == 0
    assert counts["projects/demo/knowledge/architecture/linked.md"] >= 3


def test_boost_is_capped(wiki):
    kn = wiki / "projects/demo/knowledge/architecture"
    for i in range(3, 12):
        (kn / f"src{i}.md").write_text(
            f"# Src{i}\n\n## Related\n- [[linked]] — more\n", encoding="utf-8"
        )
    counts = _inbound_counts(wiki)
    assert min(counts["projects/demo/knowledge/architecture/linked.md"],
               INBOUND_BOOST_CAP) == INBOUND_BOOST_CAP
    assert INBOUND_BOOST_PER_LINK == 0.1


def test_rank_signature_is_unchanged(wiki):
    ranked = rank("write door", ["projects/demo/knowledge/architecture/linked.md"], wiki)
    assert ranked == ["projects/demo/knowledge/architecture/linked.md"]


def test_index_is_memoised_on_wiki_root_mtime(wiki, monkeypatch):
    calls: list[Path] = []
    import lib.memory.links as links_mod
    real = links_mod.build_link_index

    def counting(root, **kw):
        calls.append(Path(root))
        return real(root, **kw)

    monkeypatch.setattr("skills.recall.lib.build_link_index", counting)
    _inbound_counts.cache_clear()
    _inbound_counts(wiki)
    _inbound_counts(wiki)
    assert len(calls) == 1


def test_unreadable_wiki_root_scores_zero_boost_not_a_crash(tmp_path):
    missing = tmp_path / "nope"
    assert rank("anything", [], missing) == []
    assert _inbound_counts(missing) == {}
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/recall/test_inbound_boost.py -q`
Expected: FAIL — `ImportError: cannot import name 'INBOUND_BOOST_PER_LINK'`

- [ ] **Step 3: Implement the boost**

Add to the imports and constants block of `skills/recall/lib/__init__.py`:

```python
from functools import lru_cache

from lib.memory.links import build_link_index
from lib.memory.page_types import _is_folder_note_hub

#: Spec 2026-09-04 §8 — inbound-link count is the signal for "which pages
#: are hubs of MEANING". Multiplicative, small, and capped: a well-linked
#: page beats a fresh unlinked twin, but no amount of linking beats a real
#: token match.
INBOUND_BOOST_PER_LINK: Final[float] = 0.1
INBOUND_BOOST_CAP: Final[int] = 5
```

```python
@lru_cache(maxsize=8)
def _inbound_counts_cached(wiki_root_str: str, _mtime: float) -> dict[str, int]:
    """Inbound-link count per page. Structural hubs are excluded (their
    inbound count is architecture, not earned attention) — the same
    exclusion the 0.8.5 concept-tree boost uses.

    Keyed on `wiki_root`'s own mtime so wake-up's single `rank` call pays
    exactly one walk, and a wiki that changed gets a fresh index.
    """
    root = Path(wiki_root_str)
    try:
        index = build_link_index(root)
    except OSError:  # the wiki could not be walked — no boost, never a crash
        return {}
    counts: dict[str, int] = {}
    for rel, srcs in index.inbound.items():
        if _is_folder_note_hub(Path(rel).parts):
            counts[rel] = 0
            continue
        counts[rel] = len(srcs)
    return counts


def _inbound_counts(wiki_root: Path) -> dict[str, int]:
    root = Path(wiki_root)
    try:
        mtime = root.stat().st_mtime
    except OSError:
        return {}
    return _inbound_counts_cached(root.as_posix(), mtime)


# Tests reach for `_inbound_counts.cache_clear()`; forward it.
_inbound_counts.cache_clear = _inbound_counts_cached.cache_clear  # type: ignore[attr-defined]
```

In `rank`, after `recency = _recency_bonus(path)`:

```python
    inbound = _inbound_counts(wiki_root)
    ...
        boost = 1.0 + INBOUND_BOOST_PER_LINK * min(inbound.get(rel, 0), INBOUND_BOOST_CAP)
        final_score = (token_score * kind_mult + recency) * boost
```

Hoist `inbound = _inbound_counts(wiki_root)` ABOVE the `for rel in
candidate_pages` loop — one index build per `rank` call, per spec §8.

Add `"INBOUND_BOOST_CAP"` and `"INBOUND_BOOST_PER_LINK"` to `__all__`.

- [ ] **Step 4: Add the two retrieval-eval cases**

The frozen fixture wiki lives alongside `lib/evalkit/fixtures/retrieval_fixture.json`;
find it with `python -c "import lib.evalkit.runner as r; print(r.__file__)"` and
read `run_retrieval_eval`'s `wiki_root` default. Add the two cases from spec §8
to the `cases` array:

```json
    {
      "query": "Which page is the hub of what we know about Postgres choices?",
      "expected_page": "decisions/use-postgres.md"
    },
    {
      "query": "What do the most-referenced notes say about retry backoff?",
      "expected_page": "lessons/retry-with-backoff.md"
    }
```

Then add the boost's own pair of fixture pages to that wiki: a well-linked page
and a fresh unlinked twin with identical body text, plus a hub that links both,
so the eval exercises "well-linked outranks twin" and "hub does not". Name them
`decisions/use-postgres.md` (already exists — add three `## Related` inbound
bullets to other fixture pages pointing at it) and leave the hub unlinked-to.

- [ ] **Step 5: Run the tests and the eval, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/recall/ tests/evalkit/ -q`
Expected: PASS, and `run_retrieval_eval`'s hit rate must not DROP versus the
pre-change run — record the before/after hit rate in the commit body.

- [ ] **Step 6: Commit**

```bash
git add skills/recall/lib/__init__.py lib/evalkit/fixtures/ tests/skills/recall/test_inbound_boost.py
git commit -m "$(cat <<'EOF'
feat(recall): rank with the graph — inbound-link boost, hubs excluded

Spec 2026-09-04 §8: score * (1 + 0.1 * min(inbound, 5)). Index memoised on
wiki_root mtime, so wake-up's single rank() call pays one walk. rank()'s
signature is unchanged (the eval harness's ranker_fn contract).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 9: metric-watch — the "fan-out silent" signal

**Files:**
- Modify: `skills/metric-watch/lib/__init__.py` — new `_check_fanout_silent`, added to `watch`'s `checks` list (line ~226)
- Modify: `skills/metric-watch/SKILL.md` — "five signals" becomes six
- Test: `tests/skills/metric_watch/test_fanout_silent.py` (create)

**Interfaces:**
- Consumes: `collect.KIND_FANOUT_EVENT` (Task 3).
- Produces: `_check_fanout_silent(state: dict) -> dict | None` returning `{"kind": "fan-out-silent", "count": <int>, "days": 7}`; `FANOUT_SILENT_DAYS: Final[int] = 7`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/skills/metric_watch/test_fanout_silent.py
"""Spec 2026-09-04 §5.5/§9 — items landing with zero candidates for a week
means the scorer or the walk is broken, not that nothing was related."""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest

from lib.instrument import collect

mw = importlib.import_module("skills.metric-watch.lib")


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("REN_WIKI_ROOT", str(tmp_path / "wiki"))
    (tmp_path / "wiki").mkdir()


def _event(candidates: int, days_ago: int) -> None:
    collect.record(collect.KIND_FANOUT_EVENT, {
        "item": "p.md", "candidates": candidates,
        "verdicts": {"relate": 0, "fact": 0, "none": 0},
        "applied": 0, "held": 0, "unknown_reason": None,
    })


def test_all_zero_candidate_events_fire_the_signal():
    for _ in range(3):
        _event(0, 1)
    assert mw._check_fanout_silent({}) == {"kind": "fan-out-silent", "count": 3, "days": 7}


def test_any_nonzero_candidate_event_silences_it():
    _event(0, 1)
    _event(4, 1)
    assert mw._check_fanout_silent({}) is None


def test_no_events_at_all_is_not_a_finding():
    assert mw._check_fanout_silent({}) is None


def test_watch_includes_the_check():
    for _ in range(2):
        _event(0, 1)
    findings = mw.watch("s1")
    assert any(f["kind"] == "fan-out-silent" for f in findings)
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/metric_watch/test_fanout_silent.py -q`
Expected: FAIL — `AttributeError: ... has no attribute '_check_fanout_silent'`

- [ ] **Step 3: Implement the check**

```python
FANOUT_SILENT_DAYS: Final[int] = 7


def _check_fanout_silent(state: dict) -> dict | None:
    """Spec 2026-09-04 §5.5 — every `fanout_event` in the last
    `FANOUT_SILENT_DAYS` had ZERO candidates.

    An item with no candidates is not "nothing was related"; it means the
    scorer found no token overlap anywhere, or the walk returned nothing —
    a broken instrument, which is exactly the class of thing this routine
    exists to notice. One non-zero event in the window is enough to clear
    the signal: the machinery demonstrably works.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=FANOUT_SILENT_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = [
        e for e in collect.read(kind=collect.KIND_FANOUT_EVENT)
        if e.get("ts", "") >= cutoff
    ]
    if not recent:
        return None
    if any(e.get("candidates", 0) > 0 for e in recent):
        return None
    return {"kind": "fan-out-silent", "count": len(recent), "days": FANOUT_SILENT_DAYS}
```

Add to `watch`'s `checks` list, after `("no_llm_with_candidates", ...)`:

```python
        ("fanout_silent", lambda: _check_fanout_silent(state)),
```

and update `watch`'s docstring: "Run all six checks".

Import `timedelta` alongside the existing datetime imports, and `Final` if not
already imported.

- [ ] **Step 4: Update `skills/metric-watch/SKILL.md`**

Change "five signals" to "six signals" everywhere it appears, and add the
signal's row/bullet:

> - **fan-out silent** — every `fanout_event` in the last 7 days landed with
>   zero candidates. Items DO get related to other pages; a week of zeroes
>   means the candidate scorer or the link walk is broken, not that the
>   wiki has nothing in common with itself.

- [ ] **Step 5: Run the tests, verify they pass**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/metric_watch/ -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add skills/metric-watch/lib/__init__.py skills/metric-watch/SKILL.md tests/skills/metric_watch/test_fanout_silent.py
git commit -m "$(cat <<'EOF'
feat(metric-watch): fan-out silent signal — a week of zero-candidate events

Spec 2026-09-04 §5.5. Zero candidates for seven days is a broken scorer,
not an unrelated wiki.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

### Task 10: CHANGELOG, skill docs, and the decision pointer

**Files:**
- Modify: `CHANGELOG.md` (add a new top section)
- Modify: `skills/wrap/SKILL.md`, `skills/wiki-health/SKILL.md`, `skills/recall/SKILL.md`
- Create: `docs/decisions/2026-09-04-graph-is-the-hierarchy.md`
- Test: `tests/skills/wiki_health/test_graph_end_to_end.py` (create — the spec §10 end-to-end)

**Interfaces:**
- Consumes: everything from Tasks 1-9. Produces nothing new in code.

- [ ] **Step 1: Write the failing end-to-end test**

```python
# tests/skills/wiki_health/test_graph_end_to_end.py
"""Spec 2026-09-04 §10 — land a concept in a fixture project; assert the
item page, two related pages, and the event."""

from __future__ import annotations

import json

import pytest

from lib.instrument import collect
from lib.memory.fanout import LandedItem, fan_out
from lib.memory.links import parse_page_links


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    kn = root / "projects/demo/knowledge/architecture"
    kn.mkdir(parents=True)
    (kn / "architecture.md").write_text("---\ntype: hub\n---\n# Architecture\n", encoding="utf-8")
    for stem, body in (
        ("write-door", "The queue is the only write door for durable pages."),
        ("journal", "The journal records every applied write and its lineage."),
    ):
        (kn / f"{stem}.md").write_text(
            f"---\ntype: project-knowledge\n---\n# {stem}\n\n"
            f"Parent: [[architecture]]\n\n{body}\n\n## Related\n",
            encoding="utf-8",
        )
    (kn / "queue-holds.md").write_text(
        "---\ntype: project-knowledge\n---\n# Queue Holds\n\nParent: [[architecture]]\n\n"
        "A contradicts conflict holds the write door's proposal.\n\n## Related\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    return root


def test_landing_a_concept_relates_two_pages_and_records_the_event(wiki):
    def llm(prompt: str) -> str:
        return json.dumps({"verdicts": [
            {"page": "write-door", "edge": "relate", "reason": "holds happen at the door"},
            {"page": "journal", "edge": "relate", "reason": "an applied write follows a hold"},
        ]})

    item = LandedItem(
        page="projects/demo/knowledge/architecture/queue-holds.md",
        title="Queue Holds",
        text="A contradicts conflict holds the write door's proposal.",
        write_id="w-E2E01",
    )
    result = fan_out(item, "demo", "s-e2e", llm)

    assert result.unknown_reason is None
    assert result.verdicts["relate"] == 2

    kn = wiki / "projects/demo/knowledge/architecture"
    item_related = dict(parse_page_links((kn / "queue-holds.md").read_text(encoding="utf-8")).related)
    assert set(item_related) == {"write-door", "journal"}
    for stem in ("write-door", "journal"):
        back = dict(parse_page_links((kn / f"{stem}.md").read_text(encoding="utf-8")).related)
        assert "queue-holds" in back

    event = collect.read(kind=collect.KIND_FANOUT_EVENT)[-1]
    assert event["item"] == item.page
    assert event["applied"] == 3  # two candidates + the item's own page
```

- [ ] **Step 2: Run it, verify it passes**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests/skills/wiki_health/test_graph_end_to_end.py -q`
Expected: PASS (Tasks 1-3 already deliver the behaviour; this test is the
spec's §10 end-to-end acceptance and must not need new code. If it fails,
the failure is a real defect in Task 3 — fix it there, in this task's commit.)

- [ ] **Step 3: Write the CHANGELOG section**

At the top of `CHANGELOG.md`, above `## [0.8.6]`:

```markdown
## [0.8.7] - unreleased — "the graph is the hierarchy"

Depth 2 is a shelf; hierarchy is links. The cross-reference graph becomes a
first-class object: a body-text convention every producer emits, a write-time
fan-out that updates the pages a new item should touch, and lint and recall
that read the graph instead of throwing it away.

- **`lib/memory/links.py`** is the one link resolver: `parse_page_links`
  (tolerant — a page with no `Parent:` line is not an error), `render_related`
  (an EMPTY `## Related` is rendered, never omitted), the idempotent
  `upsert_parent`/`upsert_related`, and `build_link_index` → `LinkIndex`
  (outbound/inbound/parent/related, one regex walk, no LLM).
- **The link convention**: every `project-knowledge` and `lesson` page body
  carries `Parent: [[<stem>]]` after its H1 and a flat `## Related` list of
  `- [[<stem>]] — <why>`. No frontmatter fields — links live where Obsidian
  and `_orphan_pages` already see them.
- **`lib/memory/fanout.py`** runs after every durable landing under
  `projects/<slug>/knowledge/`: 12 candidates ranked by recall's own scorer,
  one classifier call, a `relate`/`fact`/`none` verdict each, every edit
  through `propose_and_apply`. `fact` lands only on concept-node content
  pages — on a `lessons/` page it downgrades to `relate`. A human-owned
  (`ren_trust: "user"`) candidate becomes a suggestion, never an edit. Any
  parse failure is `unknown`: zero edits, reported on the wrap close-out.
- **`skills/wiki-health`** gains `asymmetric_links` (A lists B, B does not
  list A — the reverse bullet is a safe auto-fix through the queue, never on
  a human-owned page) and `unpaged_concepts` (a hub-only taxonomy node, or a
  `[[stem]]` three pages link and nothing resolves — a suggestion, never an
  auto-create). `_orphan_pages` now reads the shared index, so a `Parent:` or
  `## Related` link saves a page from orphanhood.
- **`skills/recall`'s `rank`** multiplies by `1 + 0.1 * min(inbound, 5)`,
  hubs excluded (their inbound count is structural, not earned). The index is
  memoised on the wiki root's mtime; `rank`'s signature is unchanged.
- **`/ren:metric-watch`** watches a sixth signal, **fan-out silent**: a week
  of `fanout_event`s that all landed zero candidates means the scorer or the
  walk is broken, not that nothing was related.
- **No migration.** Existing pages gain links lazily when touched or when the
  asymmetry auto-fix runs. The first `/ren:wiki-health` after this update will
  report many asymmetric links — that is the backlog, not a regression.
```

- [ ] **Step 4: Add the convention to the three SKILL.md files**

`skills/wrap/SKILL.md`, in the concept-tree routing paragraph (step 3's
"Concept-tree routing" bullet), append:

> Every page wrap creates now carries the 2026-09-04 link convention:
> a `Parent: [[<stem>]]` line naming its folder-note hub (or the concept page
> that is its real conceptual parent) directly after the H1, and a `## Related`
> section — rendered even when empty, a visible "nothing linked yet". After the
> page actually LANDS (never for a held write), `lib.memory.fanout.fan_out`
> ranks up to 12 of the project's other knowledge pages against it and asks one
> classifier call which should now mention it; every resulting edit goes through
> the write door and is revertible. If that classifier's output does not parse,
> nothing is edited and the close-out says `⚠ fan-out unknown: …` — Unknown is
> an outcome, never a silent skip.

`skills/wiki-health/SKILL.md`, in the findings list, add:

> - **`asymmetric_links`** — page A lists B under `## Related` while B's
>   `## Related` does not list A. The `ren-wiki-lint` agent auto-applies the
>   reverse bullet (`(reverse of [[A]])`) through the queue as a mechanically
>   safe fix; a page whose `ren_trust` is `"user"` is reported and never edited.
> - **`unpaged_concepts`** — a taxonomy node from `schema.md` whose directory
>   holds only its folder-note hub, or a `[[stem]]` that at least three distinct
>   pages link and that resolves to nothing. Reported as a suggestion, never
>   auto-created: minting a page is model work.

`skills/recall/SKILL.md`, in the ranking description, add:

> Ranking also reads the graph (spec 2026-09-04 §8): a page's score is
> multiplied by `1 + 0.1 * min(inbound_links, 5)`, where inbound links are the
> `Parent:`/`## Related`/body wikilinks other pages point at it with. Folder-note
> hubs are excluded — their inbound count is structural, not earned. The index is
> built once per `rank` call and memoised on the wiki root's mtime.

- [ ] **Step 5: Write the decision pointer**

Create `docs/decisions/2026-09-04-graph-is-the-hierarchy.md`:

```markdown
# The graph is the hierarchy

- **Date:** 2026-09-04
- **Status:** accepted
- **Spec:** `docs/superpowers/specs/2026-09-04-graph-is-the-hierarchy-design.md`
- **Plan:** `docs/superpowers/plans/2026-09-04-graph-is-the-hierarchy.md`
- **Follows:** `docs/decisions/2026-09-04-taxonomy-depth-cap.md`

## Decision

The depth cap said directories are a shelf, not a hierarchy. This is the
mechanism that carries the hierarchy instead: links in the page body.

1. **Convention, not schema.** `Parent: [[stem]]` and a flat `## Related`
   list live in the body — never in frontmatter. Obsidian renders them and
   `_orphan_pages` already reads them; a frontmatter field would need a
   parser, a migration and a renderer to buy exactly nothing.
2. **Fan-out is bounded by its candidate count, not a second cap.** 12
   candidates, sitting inside Karpathy's observed 10-15 touches per source.
   A cap under the candidate count would only discard verdicts the
   classifier had already made.
3. **`fact` edges land only on concept-node content pages.** Lessons are
   episodic; accreting facts onto them makes them worse. A `fact` verdict on
   a `lessons/` page is downgraded to `relate`, never dropped.
4. **No migration.** Existing pages gain links lazily — when a producer
   touches them, or when the asymmetry auto-fix runs. The first sweep after
   the update reports a large backlog; that is the honest starting state.

## Consequences

- Every durable landing costs one extra classifier-class call and up to 12
  queued writes; distill's `WRITE_CAP` charges fan-out edits, so a capped
  run lands fewer items rather than more writes.
- Recall gets a graph signal for free, and wake-up inherits it (it calls
  `rank`). Any further wake-up ranking change is a separate decision.
- `_orphan_pages` and fan-out and recall share one resolver, so a future
  change to what "a link" means happens in exactly one file.
```

- [ ] **Step 6: Run the FULL suite**

Run: `UV_PROJECT_ENVIRONMENT="$HOME/.renos/.envs/dev-graph" uv run pytest tests -q`
Expected: PASS — every task's tests plus the pre-existing suites, including
`tests/audit/test_fail_open_declared.py` and `tests/test_repo_hygiene.py`.

- [ ] **Step 7: Commit**

```bash
git add CHANGELOG.md docs/decisions/2026-09-04-graph-is-the-hierarchy.md skills/wrap/SKILL.md skills/wiki-health/SKILL.md skills/recall/SKILL.md tests/skills/wiki_health/test_graph_end_to_end.py
git commit -m "$(cat <<'EOF'
docs(0.8.7): the graph is the hierarchy — changelog, skill docs, decision

Spec 2026-09-04 §10-§11. Includes the end-to-end acceptance test: land a
concept, two pages gain the reverse edge, one fanout_event is recorded.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01EEsGhGFjZaRKnn2HzYb7gk
EOF
)"
```

---

## Self-Review

**1. Spec coverage**

| Spec section | Task |
|---|---|
| §3 link convention (`Parent:`, `## Related`, wikilink form, tolerant parsing) | 1 (parse/render/upsert), 4/5/6 (producers emit it) |
| §4 `LinkIndex`, `build_link_index`, `project=` narrowing, `_orphan_pages` refactor + byte-identical regression | 1, 2 |
| §5 `fan_out`, `FANOUT_CANDIDATES=12`, candidate ranking via `_score_content`, exclusions, classifier + `parse_worker_json`, fail-closed unknown, relate-on-both, `fact` only on concept nodes, lesson downgrade, 40-bullet split, human-owned → suggestion, `propose_and_apply(writer="llm-auto", reason="fanout: <write_id>")`, `fanout_event` | 3 |
| §5 budget — distill's `WRITE_CAP` counts fan-out edits | 5 |
| §6 `asymmetric_links` (safe auto-fix, never on `ren_trust: user`), `unpaged_concepts` (suggestion only), `orphan_pages` keeps its contract | 2, 7 |
| §7 wrap `_durable_create_page` / `_apply_concept_create`; distill landing + `seed_tree`'s `See:` → `Parent:`; ingest drafting spec + `link_errors` without dropping the leaf | 4, 5, 6 |
| §8 recall boost `1 + 0.1*min(inbound,5)`, hubs excluded, memoised on mtime, signature unchanged, two fixture cases | 8 |
| §9 failure modes (unparseable → close-out line; zero candidates → metric-watch; human-owned → suggestion; reverse contradicts → held; I/O → Unknown) | 3, 4, 7, 9 |
| §10 testing (links, fanout, wiki-health, recall, producers, one end-to-end) | 1, 3, 4, 5, 6, 7, 8, 10 |
| §11 rollout — no migration | 10 (CHANGELOG states it) |
| §12 resolved questions (Q1 lesson downgrade, Q2 no second cap) | 3, and recorded in the decision page (10) |

**Gap found and closed inline:** the spec's §5 "40-bullet split suggestion
fires exactly as it does today" had no seam at first — the append helper
(`_append_facts_bullet`) and the split check lived in different places, the
check being inline in `wrap_session`'s concept-update branch rather than in
any reusable function. Task 3 now closes it inside the `fact` branch: after
`append_facts_bullet`, it re-counts with `count_facts_bullets` and applies
today's exact rule (a strict `>` against the threshold, evaluated AFTER the
append, so a node sitting at exactly 40 fires on this bullet), then calls
`_suggest_split`, which raises the suggestion on wrap's OWN
`wrap-split:{page}` fingerprint. Same finding, same fingerprint, so it dedups
against wrap's rather than becoming a second nag — that is what the
"second run does not duplicate it" test pins.

Closing it required a layering decision. `lib/` imports `skills/` nowhere
today (verified — only docstring references), so importing the threshold up
from wrap would have introduced the first real inversion. Instead
`_CONCEPT_SPLIT_BULLETS`, `_count_facts_bullets` and `_append_facts_bullet`
move DOWN into `lib/memory/links.py` as `CONCEPT_SPLIT_BULLETS`,
`count_facts_bullets` and `append_facts_bullet` (they are pure body-section
text edits, the same job `upsert_related` already does there), and wrap
re-exports them under their existing private names so no current call site or
test changes. The one deliberate remaining inversion is fan-out's
function-local `skills.recall.lib._score_content` import, which spec §5.1
mandates by name ("the recall scorer, not a new one") and which is
function-local precisely so module import order stays acyclic.

**Second gap:** `ingest()` currently does not receive the drafted leaf pages at
all (SKILL.md step 5 has the live session queue them directly), so there was
nothing for `parse_page_links` to validate. Task 6 adds the `leaf_pages`
parameter and moves the queuing into `ingest()` — without that, the spec's
`result["link_errors"]` requirement has no seam.

**2. Placeholder scan**

No "TBD", "implement later", "add error handling", or "similar to Task N".
Every code step carries runnable code. Two steps carry named judgment the
implementer must exercise rather than code: Task 8 step 4 (locating the frozen
eval wiki, which is discovered at runtime by reading `run_retrieval_eval`'s
default) and Task 1 step 3's explicit correction of the `upsert_parent` sketch —
both name exactly what to do and how to find it.

**3. Type consistency**

- `LinkIndex` fields (`outbound`, `inbound`, `parent`, `related`, `pages`) are
  named identically in Tasks 1, 2, 3, 7, 8.
- `PageLinks.related` is `tuple[tuple[str, str], ...]`; `LinkIndex.related` is
  `list[tuple[str, str]]` — deliberately different (frozen value object vs
  mutable index), and every consumer treats it as a sequence of pairs.
- `fan_out`'s return is `FanoutResult` everywhere; `LandedItem` is constructed
  with the same four keyword fields in Tasks 3, 4, 5, 10.
- `_orphan_pages(wiki_root, index=None)` — Task 2 defines the optional second
  parameter and Task 7 is its only caller that passes it.
- `_score_content(content, tokens)` matches the real signature at
  `skills/recall/lib/__init__.py:108`; `tokenize_query` produces the `tokens`.
- The Facts helpers keep one name each after Task 3's move: public
  `CONCEPT_SPLIT_BULLETS` / `count_facts_bullets` / `append_facts_bullet` in
  `lib/memory/links.py`, aliased back to `_CONCEPT_SPLIT_BULLETS` /
  `_count_facts_bullets` / `_append_facts_bullet` in wrap. Bodies are moved
  verbatim from `skills/wrap/lib/__init__.py:933` and ~1590, so behaviour is
  unchanged and the existing wrap tests are the regression gate.
- The split fingerprint string is `f"wrap-split:{page}"` in Task 3's
  `_suggest_split`, in its two tests, and in wrap's pre-existing
  concept-update branch — one literal, three call sites.
- `lib.suggestions.pending_suggestions()` (not `pending()`) is the read verb
  used in Task 3's split tests; `record()` returns `dict | None`, and
  `_suggest_split` branches on `None` rather than subscripting it.
- `parse_worker_json(raw)` matches `lib/adapter/worker.py:66` and raises
  `WorkerOutputError`, which Task 3 catches by name.
- The metric kind constant is `collect.KIND_FANOUT_EVENT` (value
  `"fanout_event"`) in Tasks 3 and 9; the finding kind string is
  `"fan-out-silent"` in Task 9 only.
- The lint fix class is `"asymmetric-link-reversed"` in Task 7's code, its
  test, and `agents/ren-wiki-lint.md`.
