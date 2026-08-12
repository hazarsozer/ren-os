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
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))
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
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))

    n1 = wiki_health.record_orphan_suggestions(["projects/demo/l1/session-orphan.md"], session="s1")
    n2 = wiki_health.record_orphan_suggestions(["projects/demo/l1/session-orphan.md"], session="s2")
    assert n1 == 1 and n2 == 0
