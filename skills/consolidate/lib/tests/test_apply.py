"""
Tests for skills.consolidate.lib.apply — atomic promotion-diff application.

A faithful copy of wrap's atomic apply pattern (skill libs can't cross-import).
Exercised against a real tmp git repo (the `tmp_wiki_repo` fixture).

Run with:
    python3 -m pytest skills/consolidate/lib/tests/test_apply.py -v
"""

from __future__ import annotations

from pathlib import Path

from ..__init__ import build_promotion_diffs, parse_instincts
from ..apply import ApplyResult, apply_diff_entries
from ..links import (
    build_basename_index,
    build_link_repair_diffs,
    build_slug_index,
    find_dead_links,
    propose_link_repair,
)
from ..types import PromotionDiff

_INST_REL = "wiki/projects/dry/instincts.md"


def _entry(repo: Path):
    cur = (repo / _INST_REL).read_text(encoding="utf-8")
    return parse_instincts(cur)[0], cur


def test_applies_valid_pair_atomically(tmp_wiki_repo: Path):
    entry, inst_cur = _entry(tmp_wiki_repo)
    tgt_rel = "wiki/patterns/index.md"
    tgt_cur = (tmp_wiki_repo / tgt_rel).read_text(encoding="utf-8")
    page, marking = build_promotion_diffs(
        entry, target_relpath=tgt_rel, target_current=tgt_cur,
        curated_addition="- promoted thing\n",
        instincts_relpath=_INST_REL, instincts_current=inst_cur, promoted_on="2026-06-28")

    res = apply_diff_entries((page, marking), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    assert isinstance(res, ApplyResult)
    assert res.success and res.diffs_applied == 2
    assert "promoted thing" in (tmp_wiki_repo / tgt_rel).read_text(encoding="utf-8")
    assert "_(promoted" in (tmp_wiki_repo / _INST_REL).read_text(encoding="utf-8")


def test_empty_is_success_noop(tmp_wiki_repo: Path):
    res = apply_diff_entries((), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    assert res.success and res.diffs_applied == 0 and not res.rollback_performed


def test_invalid_diff_fails_validation_without_writes(tmp_wiki_repo: Path):
    tgt = tmp_wiki_repo / "wiki/patterns/index.md"
    before = tgt.read_text(encoding="utf-8")
    bad = PromotionDiff(target_file="wiki/patterns/index.md",
                        unified_diff="garbage not a diff\n", kind="page-edit", rationale="x")
    res = apply_diff_entries((bad,), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    assert not res.success
    assert not res.rollback_performed              # caught in pre-validation; nothing applied
    assert tgt.read_text(encoding="utf-8") == before


def test_conflicting_second_diff_triggers_rollback(tmp_wiki_repo: Path):
    # Two markings of the SAME instinct line: each passes `git apply --check` against
    # the original, but applying the first invalidates the second → rollback.
    entry, inst_cur = _entry(tmp_wiki_repo)
    _, m1 = build_promotion_diffs(
        entry, target_relpath="wiki/patterns/a.md", target_current=None, curated_addition="x\n",
        instincts_relpath=_INST_REL, instincts_current=inst_cur, promoted_on="2026-06-28")
    _, m2 = build_promotion_diffs(
        entry, target_relpath="wiki/patterns/b.md", target_current=None, curated_addition="y\n",
        instincts_relpath=_INST_REL, instincts_current=inst_cur, promoted_on="2026-06-28")
    before = (tmp_wiki_repo / _INST_REL).read_text(encoding="utf-8")

    res = apply_diff_entries((m1, m2), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    assert not res.success and res.rollback_performed
    assert (tmp_wiki_repo / _INST_REL).read_text(encoding="utf-8") == before  # fully rolled back


def test_rollback_is_scoped_to_changed_files(tmp_wiki_repo: Path):
    # A mid-batch rollback must touch ONLY the batch's files — not unrelated
    # uncommitted wiki work. The whole-wiki `git restore`+`git clean` nuked it
    # (C3c widened the exposure: --fix-links can target any/all pages).
    scratch = tmp_wiki_repo / "wiki" / "scratch-note.md"
    scratch.write_text("uncommitted brainstorm\n", encoding="utf-8")          # untracked
    idx = tmp_wiki_repo / "wiki" / "patterns" / "index.md"
    idx_dirty = idx.read_text(encoding="utf-8") + "- uncommitted edit\n"
    idx.write_text(idx_dirty, encoding="utf-8")                               # tracked, dirty

    entry, inst_cur = _entry(tmp_wiki_repo)
    _, m1 = build_promotion_diffs(
        entry, target_relpath="wiki/patterns/a.md", target_current=None, curated_addition="x\n",
        instincts_relpath=_INST_REL, instincts_current=inst_cur, promoted_on="2026-06-28")
    _, m2 = build_promotion_diffs(
        entry, target_relpath="wiki/patterns/b.md", target_current=None, curated_addition="y\n",
        instincts_relpath=_INST_REL, instincts_current=inst_cur, promoted_on="2026-06-28")

    res = apply_diff_entries((m1, m2), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    assert not res.success and res.rollback_performed
    assert (tmp_wiki_repo / _INST_REL).read_text(encoding="utf-8") == inst_cur   # batch file restored
    assert scratch.exists() and scratch.read_text(encoding="utf-8") == "uncommitted brainstorm\n"
    assert idx.read_text(encoding="utf-8") == idx_dirty                          # unrelated edit survives


def test_rollback_removes_batch_created_files(tmp_wiki_repo: Path):
    # A new file created EARLIER in the batch must be removed on rollback (the
    # `git clean` half), while unrelated untracked files are left alone.
    keep = tmp_wiki_repo / "wiki" / "keep.md"
    keep.write_text("unrelated untracked\n", encoding="utf-8")
    entry, inst_cur = _entry(tmp_wiki_repo)
    page_a, m1 = build_promotion_diffs(
        entry, target_relpath="wiki/patterns/a.md", target_current=None, curated_addition="x\n",
        instincts_relpath=_INST_REL, instincts_current=inst_cur, promoted_on="2026-06-28")
    _, m2 = build_promotion_diffs(
        entry, target_relpath="wiki/patterns/b.md", target_current=None, curated_addition="y\n",
        instincts_relpath=_INST_REL, instincts_current=inst_cur, promoted_on="2026-06-28")

    # page_a creates a.md (applies), m1 marks the line (applies), m2 marks the same line → fails.
    res = apply_diff_entries((page_a, m1, m2), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    assert not res.success and res.rollback_performed
    assert not (tmp_wiki_repo / "wiki/patterns/a.md").exists()    # batch-created file removed
    assert (tmp_wiki_repo / _INST_REL).read_text(encoding="utf-8") == inst_cur   # marking reverted
    assert keep.exists()                                          # unrelated untracked survives


def test_link_repair_diff_applies_through_apply(tmp_link_repo: Path):
    # spec §8: a build_link_repair_diffs output applies cleanly through the
    # shared apply_diff_entries primitive (previously only page-edit/marking
    # diffs were exercised end-to-end).
    pages = {
        str(p.relative_to(tmp_link_repo)): p.read_text(encoding="utf-8")
        for p in (tmp_link_repo / "wiki").rglob("*.md")
    }
    slug, base = build_slug_index(pages), build_basename_index(pages)
    page_rel = "wiki/patterns/read-before-edit.md"
    repairs = tuple(
        r for d in find_dead_links(pages) if d.source_relpath == page_rel
        for r in (propose_link_repair(d, slug, base),) if r
    )
    diff = build_link_repair_diffs(page_rel, pages[page_rel], repairs)
    res = apply_diff_entries((diff,), wiki_root=tmp_link_repo / "wiki", cwd=tmp_link_repo)
    assert res.success and res.diffs_applied == 1 and res.files_changed == (page_rel,)
    fixed = (tmp_link_repo / page_rel).read_text(encoding="utf-8")
    assert "[[schema-versioning]]" in fixed and "[[scheme-versioning]]" not in fixed
