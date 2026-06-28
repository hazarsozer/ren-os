"""
Tests for skills.consolidate.lib.links — C3c dead-link repair sweep.

Detection + deterministic repair proposal are pure (a {relpath: text} dict, no
disk). Per-file diff composition is verified against real `git apply` (the
`tmp_link_repo` fixture).

Run with:
    python3 -m pytest skills/consolidate/lib/tests/test_links.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..links import (
    build_basename_index,
    build_link_repair_diffs,
    build_slug_index,
    find_dead_links,
    propose_link_repair,
)
from ..types import DeadLink, LinkRepair, PromotionDiff


def _pages() -> dict[str, str]:
    """A small wiki keyed by repo-relative path (the shape the sweep passes in)."""
    return {
        "wiki/patterns/schema-versioning.md": "# Schema Versioning\n\nbody\n",
        "wiki/patterns/read-before-edit.md": (
            "# Read Before Edit\n\nsee [[schema-versioning]] and [[scheme-versioning]]\n"
        ),
        "wiki/decisions/037-foo.md": (
            "# 037\n\nlive: [[read-before-edit|the pattern]]\n"
            "dead md: [bar](../patterns/missing.md)\n"
        ),
        "wiki/index.md": (
            "# Index\n\nrelocated: [sv](wrong/schema-versioning.md)\n"
            "external: [x](https://example.com/y.md)\n"
        ),
    }


def _read_wiki(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): p.read_text(encoding="utf-8")
        for p in (root / "wiki").rglob("*.md")
    }


class TestFindDeadLinks:
    def test_detects_dead_wikilink(self):
        dead = find_dead_links(_pages())
        assert (
            "wiki/patterns/read-before-edit.md",
            "scheme-versioning",
        ) in {(d.source_relpath, d.raw_target) for d in dead if d.form == "wikilink"}

    def test_ignores_live_wikilink(self):
        dead = find_dead_links(_pages())
        assert all(
            not (d.form == "wikilink" and d.raw_target == "schema-versioning") for d in dead
        )

    def test_ignores_live_aliased_wikilink(self):
        # [[read-before-edit|the pattern]] resolves → must NOT be flagged
        dead = find_dead_links(_pages())
        assert all(d.raw_target != "read-before-edit" for d in dead)

    def test_captures_alias_and_literal(self):
        dead = find_dead_links({"wiki/a.md": "[[nope|shown text]]\n"})
        assert len(dead) == 1
        d = dead[0]
        assert d.raw_target == "nope"
        assert d.alias == "shown text"
        assert d.old_literal == "[[nope|shown text]]"

    def test_detects_dead_mdlink_relative_to_source(self):
        dead = find_dead_links(_pages())
        assert any(
            d.form == "mdlink" and d.raw_target == "../patterns/missing.md" for d in dead
        )

    def test_valid_relative_mdlink_is_not_dead(self):
        pages = {"wiki/decisions/037.md": "[ok](../patterns/p.md)\n", "wiki/patterns/p.md": "x\n"}
        assert find_dead_links(pages) == ()

    def test_ignores_http_mdlink(self):
        dead = find_dead_links(_pages())
        assert all("example.com" not in d.raw_target for d in dead)

    def test_records_line_no_and_raw_line(self):
        dead = find_dead_links({"wiki/a.md": "line zero\n[[dead]] here\n"})
        assert dead[0].line_no == 1
        assert dead[0].raw_line == "[[dead]] here"

    def test_multiple_dead_links_one_page(self):
        dead = find_dead_links({"wiki/a.md": "[[x]] and [[y]]\n"})
        assert {d.raw_target for d in dead} == {"x", "y"}

    def test_clean_wiki_returns_empty(self):
        assert find_dead_links({"wiki/a.md": "# A\n\nno links here\n"}) == ()


class TestProposeLinkRepair:
    def _setup(self, pages):
        return build_slug_index(pages), build_basename_index(pages)

    def test_confident_wikilink_fuzzy_match(self):
        pages = _pages()
        slug, base = self._setup(pages)
        dead = next(d for d in find_dead_links(pages) if d.raw_target == "scheme-versioning")
        rep = propose_link_repair(dead, slug, base)
        assert rep is not None
        assert rep.new_target == "schema-versioning"
        assert rep.new_literal == "[[schema-versioning]]"

    def test_far_miss_returns_none(self):
        pages = {"wiki/patterns/schema-versioning.md": "x\n", "wiki/a.md": "[[zzzzzzzzzz]]\n"}
        slug, base = self._setup(pages)
        dead = find_dead_links(pages)[0]
        assert propose_link_repair(dead, slug, base) is None

    def test_alias_preserved_in_rewrite(self):
        pages = {
            "wiki/patterns/schema-versioning.md": "x\n",
            "wiki/a.md": "[[scheme-versioning|the schema]]\n",
        }
        slug, base = self._setup(pages)
        dead = find_dead_links(pages)[0]
        rep = propose_link_repair(dead, slug, base)
        assert rep is not None
        assert rep.new_literal == "[[schema-versioning|the schema]]"

    def test_mdlink_basename_relocation(self):
        pages = {
            "wiki/patterns/schema-versioning.md": "x\n",
            "wiki/index.md": "[sv](wrong/schema-versioning.md)\n",
        }
        slug, base = self._setup(pages)
        dead = next(d for d in find_dead_links(pages) if d.form == "mdlink")
        rep = propose_link_repair(dead, slug, base)
        assert rep is not None
        assert rep.new_target == "patterns/schema-versioning.md"
        assert rep.new_literal == "](patterns/schema-versioning.md)"

    def test_mdlink_relocation_relative_to_nested_source(self):
        pages = {
            "wiki/patterns/schema-versioning.md": "x\n",
            "wiki/decisions/037.md": "[sv](schema-versioning.md)\n",
        }
        slug, base = self._setup(pages)
        dead = next(d for d in find_dead_links(pages) if d.form == "mdlink")
        rep = propose_link_repair(dead, slug, base)
        assert rep is not None
        assert rep.new_target == "../patterns/schema-versioning.md"

    def test_mdlink_ambiguous_basename_returns_none(self):
        pages = {
            "wiki/a/dup.md": "x\n",
            "wiki/b/dup.md": "y\n",
            "wiki/index.md": "[d](wrong/dup.md)\n",
        }
        slug, base = self._setup(pages)
        dead = next(d for d in find_dead_links(pages) if d.form == "mdlink")
        assert propose_link_repair(dead, slug, base) is None


class TestBuildLinkRepairDiffs:
    """Composition — verified against real `git apply`."""

    def _check(self, diff: str, cwd: Path):
        return subprocess.run(
            ["git", "apply", "--check", "-"], cwd=cwd, input=diff, capture_output=True, text=True
        )

    def _repairs_for(self, pages, page_rel):
        slug, base = build_slug_index(pages), build_basename_index(pages)
        dead = [d for d in find_dead_links(pages) if d.source_relpath == page_rel]
        return tuple(r for r in (propose_link_repair(d, slug, base) for d in dead) if r)

    def test_single_fix_applies(self, tmp_link_repo: Path):
        pages = _read_wiki(tmp_link_repo)
        page_rel = "wiki/patterns/read-before-edit.md"
        repairs = self._repairs_for(pages, page_rel)
        assert len(repairs) == 1
        diff = build_link_repair_diffs(page_rel, pages[page_rel], repairs)
        assert diff.kind == "link-fix"
        assert diff.target_file == page_rel
        r = self._check(diff.unified_diff, tmp_link_repo)
        assert r.returncode == 0, r.stderr

    def test_multiple_fixes_one_page_compose_one_diff(self, tmp_link_repo: Path):
        pages = _read_wiki(tmp_link_repo)
        page_rel = "wiki/decisions/037.md"
        repairs = self._repairs_for(pages, page_rel)
        assert len(repairs) == 2
        diff = build_link_repair_diffs(page_rel, pages[page_rel], repairs)
        # one PromotionDiff covering both fixes, and it applies cleanly
        assert self._check(diff.unified_diff, tmp_link_repo).returncode == 0
        subprocess.run(
            ["git", "apply", "-"], cwd=tmp_link_repo, input=diff.unified_diff,
            capture_output=True, text=True, check=True,
        )
        after = (tmp_link_repo / page_rel).read_text(encoding="utf-8")
        assert "[[schema-versioning]]" in after
        assert "[[read-before-edit]]" in after

    def test_idempotent_after_apply(self, tmp_link_repo: Path):
        pages = _read_wiki(tmp_link_repo)
        page_rel = "wiki/decisions/037.md"
        repairs = self._repairs_for(pages, page_rel)
        diff = build_link_repair_diffs(page_rel, pages[page_rel], repairs)
        subprocess.run(
            ["git", "apply", "-"], cwd=tmp_link_repo, input=diff.unified_diff,
            capture_output=True, text=True, check=True,
        )
        # re-scan the whole wiki (full slug index) → the repaired page is now clean
        remaining = [d for d in find_dead_links(_read_wiki(tmp_link_repo)) if d.source_relpath == page_rel]
        assert remaining == []
