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
