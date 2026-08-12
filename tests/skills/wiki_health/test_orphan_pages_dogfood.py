"""#55 — dogfood-shape verification: orphan detection against pre/post-#54 shapes.

This test reproduces the real wiki structures that motivated #55:
  - A project with standalone map pages (no incoming links)
  - Pre-#54 log.md mentioning sessions in prose WITHOUT the .md extension
  - L1 pages (global + project) unlinked and orphaned
  - archive/ pages (exempt from orphan detection)

The pre/post-#54 split tests that log.md sessions in prose-only form
('wrapped session-x today') don't save pages named 'session-x.md'
(mention fallback requires the full filename word-bounded), while
actual link targets do.
"""
from __future__ import annotations

import importlib

import pytest

wiki_health = importlib.import_module("skills.wiki-health.lib")


def _w(root, rel, text):
    """Write a file to the fixture wiki, creating parent dirs as needed."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def dogfood_pre_54(clean_path_env, tmp_path):
    """Pre-#54 dogfood shape: log.md mentions sessions in prose without .md extension.

    Expected orphans:
      - l1/session-x.md (prose mention 'session-x' won't match filename 'session-x.md')
      - l1/session-y.md (same reason)
      - projects/study/l1/session-z.md (not linked anywhere)
      - projects/study/study-format.md (standalone page, no incoming link)
      - projects/study/team-assignment.md (standalone page, no incoming link)
    Total: 5 orphans

    Exempt (NOT orphans):
      - index.md, log.md, identity.md (root exempts)
      - archive/l1/old-session.md (archive/ path component)
    """
    # Master index with spine pointer to study map
    _w(tmp_path, "index.md",
       "---\ntype: l2-map\n---\n# Master\n## Decision map\n"
       "- [Study](projects/study/map.md) (w-01A)\n")

    # Pre-#54 log.md: sessions mentioned in prose WITHOUT .md extension
    _w(tmp_path, "log.md",
       "---\ntype: log-entry\n---\n# Wiki Log\n"
       "## [2026-08-01] session | study kickoff\n"
       "Started with session-x today, gathered initial thoughts.\n"
       "## [2026-08-05] session | follow-up\n"
       "Wrapped session-x, moved to session-y for deeper work.\n"
       "## [2026-08-10] session | consolidation\n"
       "Wrapped session-y, planning next steps.\n")

    # Identity page (exempt)
    _w(tmp_path, "identity.md", "---\ntype: identity\n---\n# Me\n")

    # Global l1 pages (unlinked, orphaned)
    _w(tmp_path, "l1/session-x.md", "---\ntype: l1\n---\n# Session X notes\n")
    _w(tmp_path, "l1/session-y.md", "---\ntype: l1\n---\n# Session Y notes\n")

    # Study project map with Decision map pointers
    # The map HAS link-form pointers, but NOT to study-format/team-assignment
    _w(tmp_path, "projects/study/map.md",
       "---\ntype: l2-map\nproject: study\n---\n# study — knowledge map\n"
       "## Decision map\n"
       "- [Formatting guide](projects/study/guides/format-guide.md) (w-01A)\n"
       "- [Assignment template] → projects/study/guides/assignment-template.md (w-01B)\n")

    # Pages that map links to (these are NOT orphans)
    _w(tmp_path, "projects/study/guides/format-guide.md",
       "---\ntype: project-knowledge\n---\n# Format guide\n")
    _w(tmp_path, "projects/study/guides/assignment-template.md",
       "---\ntype: project-knowledge\n---\n# Assignment template\n")

    # Standalone study pages: NOT linked from map, not linked from anywhere
    # These are the orphans that motivated #55
    _w(tmp_path, "projects/study/study-format.md",
       "---\ntype: project-knowledge\n---\n# Study Format\nStandalone page with context.\n")
    _w(tmp_path, "projects/study/team-assignment.md",
       "---\ntype: project-knowledge\n---\n# Team Assignment\nStandalone reference.\n")

    # Project l1 page (unlinked, orphaned)
    _w(tmp_path, "projects/study/l1/session-z.md", "---\ntype: l1\n---\n# Session Z notes\n")

    # Archive l1 page (exempt from orphan detection)
    _w(tmp_path, "archive/l1/old-session.md", "---\ntype: l1\n---\n# Old session\n")

    clean_path_env.setenv("REN_WIKI_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def dogfood_post_54(dogfood_pre_54):
    """Post-#54 dogfood shape: log.md updated with Sessions section containing links.

    The Sessions section now has actual markdown links to l1 pages:
      - [session-x](l1/session-x.md)
      - [session-y](l1/session-y.md)
      - [session-z](projects/study/l1/session-z.md)

    Expected orphans (reduced):
      - projects/study/study-format.md (still standalone, no incoming link)
      - projects/study/team-assignment.md (still standalone, no incoming link)

    Total: 2 orphans (down from 5 — the 3 l1 pages are now linked by Sessions)
    """
    # Update log.md to include Sessions section with actual links
    _w(dogfood_pre_54, "log.md",
       "---\ntype: log-entry\n---\n# Wiki Log\n"
       "## [2026-08-01] session | study kickoff\n"
       "Started with session-x today, gathered initial thoughts.\n"
       "## [2026-08-05] session | follow-up\n"
       "Wrapped session-x, moved to session-y for deeper work.\n"
       "## [2026-08-10] session | consolidation\n"
       "Wrapped session-y, planning next steps.\n"
       "\n## Sessions\n"
       "- [session-x](l1/session-x.md)\n"
       "- [session-y](l1/session-y.md)\n"
       "- [session-z](projects/study/l1/session-z.md)\n")

    return dogfood_pre_54


def test_pre_54_orphan_counts_exact(dogfood_pre_54):
    """Pre-#54: exact counts to catch filter regressions.

    5 orphans expected:
      - 2 global l1 pages (prose-only mention doesn't save them)
      - 2 study standalone pages (no incoming links at all)
      - 1 project l1 page (not linked)
    """
    orphans = wiki_health._orphan_pages(dogfood_pre_54)

    # Exact count check so filter regressions can't pass silently
    assert len(orphans) == 5, f"Expected 5 orphans, got {len(orphans)}: {orphans}"

    # Global l1 pages: prose mention 'session-x' doesn't match filename 'session-x.md'
    assert "l1/session-x.md" in orphans
    assert "l1/session-y.md" in orphans

    # Study project standalone pages: no incoming links
    assert "projects/study/study-format.md" in orphans
    assert "projects/study/team-assignment.md" in orphans

    # Project l1 page: not linked from anywhere
    assert "projects/study/l1/session-z.md" in orphans


def test_pre_54_archive_exempt(dogfood_pre_54):
    """Pre-#54: archive/l1/ pages are exempt from orphan detection."""
    orphans = wiki_health._orphan_pages(dogfood_pre_54)

    # archive/ pages never flagged as orphans
    assert "archive/l1/old-session.md" not in orphans


def test_pre_54_root_exempts(dogfood_pre_54):
    """Pre-#54: root-level exempts (index.md, log.md, identity.md) are never orphans."""
    orphans = wiki_health._orphan_pages(dogfood_pre_54)

    # Root exempts never appear in orphan list
    for exempt in ("index.md", "log.md", "identity.md"):
        assert exempt not in orphans


def test_pre_54_linked_pages_not_orphaned(dogfood_pre_54):
    """Pre-#54: pages linked from map.md (guides/ pages) are not orphaned."""
    orphans = wiki_health._orphan_pages(dogfood_pre_54)

    # Guide pages linked from map are not orphans
    assert "projects/study/guides/format-guide.md" not in orphans
    assert "projects/study/guides/assignment-template.md" not in orphans


def test_post_54_l1_pages_linked_by_sessions(dogfood_post_54):
    """Post-#54: log.md Sessions section links now save l1 pages from orphan status.

    Expected: 2 orphans (the standalone study pages).
    The l1 pages are no longer orphaned due to Sessions section links.
    The guide pages remain not orphaned (already linked from map).
    """
    orphans = wiki_health._orphan_pages(dogfood_post_54)

    # Exact count: only the 2 standalone study pages remain orphaned
    assert len(orphans) == 2, f"Expected 2 orphans post-#54, got {len(orphans)}: {orphans}"

    # The l1 pages are now linked by Sessions section and are NOT orphans
    assert "l1/session-x.md" not in orphans
    assert "l1/session-y.md" not in orphans
    assert "projects/study/l1/session-z.md" not in orphans

    # Standalone pages still orphaned (no links to them anywhere)
    assert "projects/study/study-format.md" in orphans
    assert "projects/study/team-assignment.md" in orphans


def test_sweep_includes_dogfood_orphans(dogfood_pre_54):
    """Dogfood sweep includes orphan_pages and renders correctly."""
    findings = wiki_health.sweep(dogfood_pre_54)

    assert "orphan_pages" in findings
    assert len(findings["orphan_pages"]) == 5

    report = wiki_health.render_report(findings)
    assert "## Orphan pages (no incoming links)" in report
    assert "session-x.md" in report
    assert "study-format.md" in report
