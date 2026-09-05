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
