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
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
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


def test_sweep_carries_key_and_report_renders(wiki, clean_path_env):
    clean_path_env.setenv("REN_WIKI_ROOT", str(wiki))
    findings = wiki_health.sweep(wiki)
    assert "orphan_pages" in findings
    report = wiki_health.render_report(findings)
    assert "## Orphan pages (no incoming links)" in report
    assert "session-orphan.md" in report


def test_sweep_degraded_path_has_key(clean_path_env, tmp_path):
    # M9: a clean env so the degraded (no-wiki-root) path's other sweep
    # calls (e.g. `_mass_deletions`' journal read) hit tmp_path, never the
    # real ~/.renos state.
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    findings = wiki_health.sweep(tmp_path / "nope")
    assert findings["orphan_pages"] == []


def test_quarantined_page_not_orphan_candidate_until_released(wiki):
    from lib.memory import quarantine

    rel = "projects/demo/knowledge/quarantined.md"
    _w(wiki, rel, quarantine.mark("---\ntype: project-knowledge\n---\n# Q\nunreviewed\n"))

    orphans = wiki_health._orphan_pages(wiki)
    assert rel not in orphans  # still quarantined — not a placement candidate

    _w(wiki, rel, quarantine.release((wiki / rel).read_text(encoding="utf-8")))
    orphans = wiki_health._orphan_pages(wiki)
    assert rel in orphans  # banner removed — flags like any other orphan


def test_archive_exemption_is_depth_exact(wiki):
    # root-level archive/: exempt at any depth.
    _w(wiki, "archive/deep/sub/old.md", "# Old\n")
    # projects/<slug>/archive/: exempt.
    _w(wiki, "projects/demo/archive/old-note.md", "# Old note\n")
    # archive as a dir under knowledge/ (not root, not projects/<slug>/archive/
    # directly) must NOT be exempt — the spec's exact-depth rule, not a bare
    # "archive" in parts check.
    _w(wiki, "projects/demo/knowledge/archive/deep-archive.md", "# Deep archive\n")

    orphans = wiki_health._orphan_pages(wiki)
    assert "archive/deep/sub/old.md" not in orphans
    assert "projects/demo/archive/old-note.md" not in orphans
    assert "projects/demo/knowledge/archive/deep-archive.md" in orphans


def test_raw_exemption_is_depth_exact(wiki):
    # projects/<slug>/raw/ (canonical `in_project_raw` shape): exempt.
    _w(wiki, "projects/demo/raw/deep/dump2.md", "# Raw2\n")
    # a `raw/` dir nested deeper (not directly under projects/<slug>/) must
    # NOT be exempt — the old `"raw" in parts` check silently exempted this.
    _w(wiki, "projects/demo/knowledge/raw/notes.md", "# Notes\n")

    orphans = wiki_health._orphan_pages(wiki)
    assert "projects/demo/raw/deep/dump2.md" not in orphans
    assert "projects/demo/knowledge/raw/notes.md" in orphans


def test_link_forms_titled_and_angle_bracketed(wiki):
    # M4: `](path.md "Title")` and `](<path.md>)` must resolve as links too,
    # not just the plain `](path.md)` form.
    _w(wiki, "projects/demo/knowledge/titled-target.md", "# Titled target\n")
    _w(wiki, "projects/demo/knowledge/angle-target.md", "# Angle target\n")
    _w(
        wiki,
        "projects/demo/link-forms.md",
        "# Link forms\n"
        "- [titled](projects/demo/knowledge/titled-target.md \"Titled target\")\n"
        "- [angled](<projects/demo/knowledge/angle-target.md>)\n"
        "[self](projects/demo/link-forms.md)\n",
    )
    _w(wiki, "index.md", (wiki / "index.md").read_text(encoding="utf-8")
       .replace("(unstamped)", "(unstamped)\n- [link-forms](projects/demo/link-forms.md) (w-lf)"))

    orphans = wiki_health._orphan_pages(wiki)
    assert "projects/demo/knowledge/titled-target.md" not in orphans
    assert "projects/demo/knowledge/angle-target.md" not in orphans


def test_link_label_does_not_mention_save_unrelated_page(wiki):
    # M5: a link's LABEL text must not double as a prose mention of an
    # unrelated page sharing that filename — only the strip covers labels too.
    _w(wiki, "foo.md", "---\ntype: project-knowledge\n---\n# unrelated foo\n")
    _w(
        wiki,
        "projects/demo/label-link.md",
        "# Label link\nSee [foo.md](projects/demo/knowledge/stack.md) for details.\n",
    )
    _w(wiki, "index.md", (wiki / "index.md").read_text(encoding="utf-8")
       .replace("(unstamped)", "(unstamped)\n- [label-link](projects/demo/label-link.md) (w-ll)"))

    orphans = wiki_health._orphan_pages(wiki)
    assert "foo.md" in orphans  # label "foo.md" must not mention-save the real foo.md


def _empty_findings(**overrides):
    base = {
        "dangling_pointers": [], "contradiction_pairs": [], "duplicate_pairs": [],
        "numeric_drift_pairs": [], "contradiction_scan_note": None, "mass_deletions": [],
        "quarantined_pages": {"count": 0, "pages": []}, "single_project_global_pages": [],
        "hubless_knowledge_dirs": [], "unlinked_knowledge_pages": [], "orphan_pages": [],
        "judge_dismissed": [], "judge_supersedes": [], "retrieval_eval": {"hit_rate": None},
        "machine_released_total": 0, "generated_at": "2026-08-12T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_render_report_cross_references_unlinked_when_both_nonempty():
    # M7: the cross-reference note only appears when BOTH sections are non-empty.
    findings = _empty_findings(
        orphan_pages=["projects/demo/orphan.md"],
        unlinked_knowledge_pages=["projects/demo/knowledge/sub/leaf.md"],
    )
    report = wiki_health.render_report(findings)
    assert "(pages above may also appear under Unlinked knowledge pages)" in report


def test_render_report_no_cross_reference_when_unlinked_empty():
    findings = _empty_findings(orphan_pages=["projects/demo/orphan.md"])
    report = wiki_health.render_report(findings)
    assert "(pages above may also appear under Unlinked knowledge pages)" not in report


def test_record_orphan_suggestions_dedups(wiki, clean_path_env, tmp_path):
    # point the suggestions store at a temp dir per the store's own test pattern
    # (READ tests for lib.suggestions and reuse its fixture/monkeypatch approach)
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))

    n1 = wiki_health.record_orphan_suggestions(["projects/demo/l1/session-orphan.md"], session="s1")
    n2 = wiki_health.record_orphan_suggestions(["projects/demo/l1/session-orphan.md"], session="s2")
    assert n1 == 1 and n2 == 0


def test_arrow_pointer_label_does_not_mention_save_unrelated_page(wiki):
    # #55: an arrow pointer's LABEL (e.g. [victim.md]) must not double as a
    # prose mention of an unrelated page sharing that filename. The entire
    # arrow line must be stripped from the mention corpus, not just the path.
    _w(wiki, "victim.md", "---\ntype: project-knowledge\n---\n# unrelated victim\n")
    _w(
        wiki,
        "projects/demo/arrow-label.md",
        "# Arrow with label\n- [victim.md] → projects/demo/knowledge/stack.md\n",
    )
    _w(wiki, "index.md", (wiki / "index.md").read_text(encoding="utf-8")
       .replace("(unstamped)", "(unstamped)\n- [arrow-label](projects/demo/arrow-label.md) (w-al)"))

    orphans = wiki_health._orphan_pages(wiki)
    # arrow's actual target must not be flagged
    assert "projects/demo/knowledge/stack.md" not in orphans
    # arrow's label as a file must not save unrelated victim.md
    assert "victim.md" in orphans
