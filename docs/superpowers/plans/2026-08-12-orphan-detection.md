# Wiki-Wide Orphan Detection (#55) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The wiki-health sweep flags every durable page nothing links to — wiki-wide, path-resolved, with `raw/`/`archive/`/entry-point exemptions — and routes orphans to the suggestions store.

**Architecture:** One new walk `_orphan_pages(wiki_root)` in `skills/wiki-health/lib/__init__.py` (same shape as the sibling walks), a `record_orphan_suggestions` helper over `lib.suggestions.record`, wiring into `sweep()`/`render_report`, and a SKILL.md routing note.

**Tech Stack:** Python 3.13 via uv, pytest. Link parsing: markdown links via regex + `lib.pointer.parse_pointer_line` for legacy arrows.

**Spec:** `docs/superpowers/specs/2026-08-12-orphan-detection-design.md` — read it first; its Candidates/Corpus rules are the contract, copied below.

## Global Constraints

- Candidates: all `*.md` under wiki_root EXCEPT dot-dirs (any path component starting with `.`), `raw/` or `archive/` path components, and the root files `index.md`, `log.md`, `identity.md`, `LICENSES.md`.
- Linked = (a) markdown link target resolving to the page — try BOTH relative-to-linking-file and wiki-root-relative, strip `#fragments`; OR (b) arrow pointer via `parse_pointer_line` (form "arrow", root-relative path); OR (c) word-bounded filename mention using EXACTLY the existing `name_re` pattern from `_knowledge_tree_findings` (line ~376) — except pages named `index.md` are never mention-saved.
- Self-links never count. Exempt pages still contribute links to the corpus.
- `sweep()` result and its degraded (no-wiki) path both carry `orphan_pages`; `render_report` section title exactly `## Orphan pages (no incoming links)`.
- `record_orphan_suggestions(orphans, session) -> int` uses `lib.suggestions.record` with fingerprint `orphan:<page>`; sweep() itself stays read-only.
- Match house style (the sibling walks in the same file are the template).

---

### Task 1: `_orphan_pages` walk + sweep/report wiring + suggestions helper

**Files:**
- Modify: `skills/wiki-health/lib/__init__.py` (new `_orphan_pages`, `record_orphan_suggestions`; wire into `sweep()` ~line 536 and both its degraded paths; extend `render_report`)
- Modify: `skills/wiki-health/SKILL.md` (finding list + routing: "Orphan page: judgment-shaped — `record_orphan_suggestions` after showing the report; never auto-link")
- Test: `tests/skills/wiki_health/test_orphan_pages.py` (new file)

**Interfaces:**
- Consumes: `lib.pointer.parse_pointer_line`; `lib.suggestions.record` (READ `lib/suggestions/__init__.py` first for `record`'s exact signature and the SuggestionSpec/fingerprint shape — mirror how the quarantine screen records `quarantine:release:<page>` suggestions, grep `quarantine:release` in this same file for the working example).
- Produces: `_orphan_pages(wiki_root: Path) -> list[str]` (sorted wiki-relative posix paths); `record_orphan_suggestions(orphans: list[str], session: str) -> int` (count newly recorded); `sweep()["orphan_pages"]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/skills/wiki_health/test_orphan_pages.py
"""#55 — wiki-wide orphan detection: durable pages nothing links to."""
from __future__ import annotations

import importlib

import pytest

wiki_health = importlib.import_module("skills.wiki-health.lib")


def _w(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def wiki(tmp_path):
    _w(tmp_path, "index.md", "---\ntype: l2-map\n---\n# Master\n## Decision map\n- [demo](projects/demo/map.md) (unstamped)\n")
    _w(tmp_path, "log.md", "---\ntype: log-entry\n---\n# Wiki Log\n## [2026-08-12] session | demo — [session-linked](projects/demo/l1/session-linked.md)\n")
    _w(tmp_path, "identity.md", "---\ntype: identity\n---\n# Me\n")
    _w(tmp_path, "projects/demo/map.md",
       "---\ntype: l2-map\nproject: demo\n---\n# demo — knowledge map\n"
       "## Knowledge\n- see also prose-saved.md for background\n"
       "## Decision map\n- [Stack](projects/demo/knowledge/stack.md) (w-01A)\n"
       "- [Legacy] → projects/demo/knowledge/legacy.md (w-01B)\n"
       "## Sessions\n- [session-mapped](projects/demo/l1/session-mapped.md)\n")
    _w(tmp_path, "projects/demo/knowledge/stack.md", "---\ntype: project-knowledge\n---\n# Stack\nsee [rel](./rel-linked.md)\n")
    _w(tmp_path, "projects/demo/knowledge/rel-linked.md", "# Rel\n")
    _w(tmp_path, "projects/demo/knowledge/legacy.md", "# Legacy\n")
    _w(tmp_path, "projects/demo/knowledge/prose-saved.md", "# Prose\n")
    _w(tmp_path, "projects/demo/l1/session-linked.md", "---\ntype: l1\n---\nx\n")
    _w(tmp_path, "projects/demo/l1/session-mapped.md", "---\ntype: l1\n---\nx\n")
    _w(tmp_path, "projects/demo/l1/session-orphan.md", "---\ntype: l1\n---\nx\n")
    _w(tmp_path, "projects/demo/raw/dump.md", "# Raw\n")
    _w(tmp_path, "archive/old.md", "# Old\n")
    _w(tmp_path, "projects/demo/standalone.md", "# Standalone fact\n[self](projects/demo/standalone.md)\n")
    _w(tmp_path, "projects/demo/knowledge/research/index.md", "# Research hub\n")
    return tmp_path


def test_orphans_flagged_and_linked_pages_not(wiki):
    orphans = wiki_health._orphan_pages(wiki)
    assert "projects/demo/l1/session-orphan.md" in orphans          # true orphan L1
    assert "projects/demo/l1/session-linked.md" not in orphans      # linked from log.md
    assert "projects/demo/l1/session-mapped.md" not in orphans      # linked from map Sessions
    assert "projects/demo/knowledge/stack.md" not in orphans        # link-form pointer
    assert "projects/demo/knowledge/legacy.md" not in orphans       # arrow pointer resolves
    assert "projects/demo/knowledge/rel-linked.md" not in orphans   # relative link resolves
    assert "projects/demo/knowledge/prose-saved.md" not in orphans  # name-mention fallback


def test_exemptions_and_self_link(wiki):
    orphans = wiki_health._orphan_pages(wiki)
    for exempt in ("index.md", "log.md", "identity.md", "projects/demo/raw/dump.md", "archive/old.md"):
        assert exempt not in orphans
    assert "projects/demo/standalone.md" in orphans                 # self-link doesn't save


def test_index_md_never_mention_saved(wiki):
    # research/index.md: nothing path-links it; the word "index.md" appearing
    # in prose elsewhere must NOT save it.
    _w(wiki, "projects/demo/notes.md", "# Notes\ntalk about index.md generally\n[notes-back](projects/demo/notes.md)")
    orphans = wiki_health._orphan_pages(wiki)
    assert "projects/demo/knowledge/research/index.md" in orphans


def test_map_md_is_a_candidate(wiki):
    # demo map is linked from index.md's spine; a second project's map with no spine flags.
    _w(wiki, "projects/lone/map.md", "---\ntype: l2-map\nproject: lone\n---\n# lone\n")
    orphans = wiki_health._orphan_pages(wiki)
    assert "projects/demo/map.md" not in orphans
    assert "projects/lone/map.md" in orphans


def test_sweep_carries_key_and_report_renders(wiki, monkeypatch):
    findings = wiki_health.sweep(wiki)
    assert "orphan_pages" in findings
    report = wiki_health.render_report(findings)
    assert "## Orphan pages (no incoming links)" in report
    assert "session-orphan.md" in report


def test_sweep_degraded_path_has_key(tmp_path):
    findings = wiki_health.sweep(tmp_path / "nope")
    assert findings["orphan_pages"] == []


def test_record_orphan_suggestions_dedups(wiki, monkeypatch, tmp_path):
    # point the suggestions store at a temp dir per the store's own test pattern
    # (READ tests for lib.suggestions and reuse its fixture/monkeypatch approach)
    n1 = wiki_health.record_orphan_suggestions(["projects/demo/l1/session-orphan.md"], session="s1")
    n2 = wiki_health.record_orphan_suggestions(["projects/demo/l1/session-orphan.md"], session="s2")
    assert n1 == 1 and n2 == 0
```

- [ ] **Step 2: Verify RED** — `uv run pytest tests/skills/wiki_health/test_orphan_pages.py -v` → AttributeError `_orphan_pages`.

- [ ] **Step 3: Implement**

`_orphan_pages` skeleton (follow the sibling walks' style; the corpus rules in Global Constraints are the contract):

```python
_MD_LINK_RE = re.compile(r"\]\(([^)\s#]+\.md)(?:#[^)]*)?\)")

def _orphan_pages(wiki_root: Path) -> list[str]:
    """#55 — durable pages with no incoming links, wiki-wide. ..."""
    pages: dict[str, str] = {}   # rel posix path -> text, ALL pages incl. exempt
    for md in sorted(wiki_root.rglob("*.md")):
        rel = md.relative_to(wiki_root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        pages[rel.as_posix()] = md.read_text(encoding="utf-8", errors="replace")

    linked: set[str] = set()
    mention_corpus: list[str] = []
    for src, text in pages.items():
        mention_corpus.append(text)
        src_dir = Path(src).parent
        for target in _MD_LINK_RE.findall(text):
            for cand in (
                (src_dir / target),           # relative to linking file
                Path(target),                  # wiki-root-relative
            ):
                norm = Path(os.path.normpath(cand.as_posix())).as_posix()
                if norm in pages and norm != src:
                    linked.add(norm)
        for line in text.splitlines():
            ptr = parse_pointer_line(line)
            if ptr and ptr.form == "arrow" and ptr.path and ptr.path in pages and ptr.path != src:
                linked.add(ptr.path)
    joined = "\n".join(mention_corpus)

    _EXEMPT_ROOT = {"index.md", "log.md", "identity.md", "LICENSES.md"}
    orphans: list[str] = []
    for rel in pages:
        parts = Path(rel).parts
        if rel in _EXEMPT_ROOT or "raw" in parts or "archive" in parts:
            continue
        if rel in linked:
            continue
        name = Path(rel).name
        if name != "index.md":
            name_re = re.compile(rf"(?<![A-Za-z0-9._-]){re.escape(name)}(?![A-Za-z0-9_])")
            # a page's own text must not mention-save it: subtract its text
            others = joined.replace(pages[rel], "", 1)
            if name_re.search(others):
                continue
        orphans.append(rel)
    return sorted(orphans)
```

(NOTE for the implementer: the `others = joined.replace(...)` self-mention exclusion is O(corpus) per orphan candidate — fine at wiki scale (~100 pages); if you find a cleaner per-page corpus split, prefer it, but keep behavior: a page cannot mention-save itself. Also `import os` if not present.)

`record_orphan_suggestions`: mirror the `quarantine:release:<page>` recording call found in this same module — same `record(...)` shape, fingerprint `f"orphan:{page}"`, a one-line `why` ("no incoming links wiki-wide — needs a home in a hub, map, or log"), return the count actually recorded (record's return/dedup semantics tell you how — read it).

Wire into `sweep()`: compute alongside the other walks, add to the findings dict AND to the degraded/no-wiki dicts (`"orphan_pages": []`). `render_report`: new section after the unlinked-knowledge section, `- none` when empty. SKILL.md: add the finding row + routing note.

- [ ] **Step 4: GREEN** — the new file, then `uv run pytest tests/skills/wiki_health -v`, then full `uv run pytest -q`. Existing sweep tests asserting the exact findings-dict key set are old-contract flips — update them, list in report.

- [ ] **Step 5: Commit**

```bash
git add skills/wiki-health tests/skills/wiki_health/test_orphan_pages.py
git commit -m "feat(wiki-health): wiki-wide orphan_pages finding + suggestion routing (#55)"
```

---

### Task 2: Dogfood-shape verification test

**Files:**
- Create: `tests/skills/wiki_health/test_orphan_pages_dogfood.py`

**Interfaces:** consumes `_orphan_pages` + `sweep` public behavior only.

- [ ] **Step 1: Build the fixture** — a temp wiki reproducing the REAL dogfood shapes that motivated #55 (from the issue): a `projects/study/`-like project with a map whose pointers are link-form but whose standalone top-level pages (`study-format.md`, `team-assignment.md`) have no incoming links; a pre-#54 `l1/` set (global `l1/session-x.md` + project `l1/` pages) with a `log.md` that names sessions in prose WITHOUT links (the pre-#54 reality — prose mention of `session-x` is NOT the filename `session-x.md`, so it must NOT save them); an `archive/l1/` set (exempt).

- [ ] **Step 2: Assert** — the standalone pages and unlinked l1 pages flag; archive/ pages don't; the map (linked from index spine) doesn't; counts are exact (`len(orphans) == <expected>` so a filter regression can't silently pass); a follow-up fixture where #54-style links are added (log entry + Sessions section) drops the l1 pages from the orphan list.

- [ ] **Step 3: Run** — file green, then full `uv run pytest -q` green.

- [ ] **Step 4: Commit** — `git commit -m "test(wiki-health): orphan detection against pre/post-#54 dogfood shapes (#55)"`

---

## Self-Review (performed at plan time)

- **Spec coverage:** candidates/exemptions/corpus rules → Task 1 (tests mirror each rule); suggestions routing + fingerprint dedup → Task 1; degraded path → Task 1; dogfood discovery expectation → Task 2. No gaps.
- **Placeholder scan:** implementation skeleton is complete except deliberately-delegated store plumbing ("read lib.suggestions / mirror quarantine:release") — the working in-repo example is named, which satisfies the no-invention bar.
- **Type consistency:** `_orphan_pages -> list[str]` sorted posix rel paths used consistently in tests and report wiring.
