"""
Tests for skills.consolidate.lib (C3b — governed promotion sweep).

Pure-logic: parse_instincts / unpromoted (no git). The diff-building + atomic
apply primitives are tested separately against a tmp git repo.

Run with:
    python3 -m pytest skills/consolidate/lib/tests/test_consolidate.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ..__init__ import build_promotion_diffs, parse_instincts, unpromoted
from ..types import InstinctEntry


_SAMPLE = """\
---
type: instincts
schema_version: 1
scope: project
---

# Instincts — dry

Append-only hot-tier memory. Kinds: worked | avoid | dont-repeat.

- **[worked]** 2026-06-28 — run each tests dir as its own pytest call
- **[avoid]** 2026-06-27 — don't mix commit with a double-dash flag in one command
- **[dont-repeat]** 2026-06-26 — Read a file before Edit  _(promoted 2026-06-28 → patterns/read-before-edit.md)_
"""


class TestParseInstincts:
    def test_parses_typed_bullets(self):
        entries = parse_instincts(_SAMPLE)
        assert len(entries) == 3
        assert entries[0] == InstinctEntry(
            kind="worked",
            date="2026-06-28",
            text="run each tests dir as its own pytest call",
            raw_line="- **[worked]** 2026-06-28 — run each tests dir as its own pytest call",
            promoted=False,
        )

    def test_detects_promoted_marker_and_strips_it(self):
        entries = parse_instincts(_SAMPLE)
        last = entries[2]
        assert last.kind == "dont-repeat"
        assert last.promoted is True
        assert last.text == "Read a file before Edit"  # marker stripped from text
        assert "_(promoted" in last.raw_line          # but preserved in raw_line

    def test_ignores_frontmatter_header_and_blank_lines(self):
        entries = parse_instincts(_SAMPLE)
        # Only the 3 bullets — nothing from frontmatter/header/prose.
        assert all(e.kind in ("worked", "avoid", "dont-repeat") for e in entries)

    def test_tolerates_malformed_lines(self):
        text = "- not an instinct\n- **[worked]** 2026-06-28 — good one\n- **[bad]** nodate — x\n"
        entries = parse_instincts(text)
        assert len(entries) == 1 and entries[0].text == "good one"

    def test_empty_text_returns_no_entries(self):
        assert parse_instincts("") == ()


class TestUnpromoted:
    def test_excludes_promoted_keeps_rest(self):
        entries = parse_instincts(_SAMPLE)
        fresh = unpromoted(entries)
        assert len(fresh) == 2
        assert all(not e.promoted for e in fresh)
        assert {e.kind for e in fresh} == {"worked", "avoid"}

    def test_all_promoted_returns_empty(self):
        entries = parse_instincts(
            "- **[worked]** 2026-06-28 — x  _(promoted 2026-06-28 → patterns/x.md)_\n"
        )
        assert unpromoted(entries) == ()


class TestBuildPromotionDiffs:
    """Diff construction — verified against real `git apply --check`."""

    def _check(self, diff: str, cwd: Path):
        return subprocess.run(["git", "apply", "--check", "-"], cwd=cwd,
                              input=diff, capture_output=True, text=True)

    def _setup(self, repo: Path):
        inst_rel = "wiki/projects/dry/instincts.md"
        inst_cur = (repo / inst_rel).read_text(encoding="utf-8")
        entry = parse_instincts(inst_cur)[0]
        return inst_rel, inst_cur, entry

    def test_append_page_edit_and_marking_apply(self, tmp_wiki_repo: Path):
        inst_rel, inst_cur, entry = self._setup(tmp_wiki_repo)
        tgt_rel = "wiki/patterns/index.md"
        tgt_cur = (tmp_wiki_repo / tgt_rel).read_text(encoding="utf-8")
        page, marking = build_promotion_diffs(
            entry, target_relpath=tgt_rel, target_current=tgt_cur,
            curated_addition="- learned: run each tests dir separately\n",
            instincts_relpath=inst_rel, instincts_current=inst_cur, promoted_on="2026-06-28")
        assert page.kind == "page-edit" and marking.kind == "marking"
        for d in (page, marking):
            r = self._check(d.unified_diff, tmp_wiki_repo)
            assert r.returncode == 0, r.stderr

    def test_create_new_page_applies(self, tmp_wiki_repo: Path):
        inst_rel, inst_cur, entry = self._setup(tmp_wiki_repo)
        page, _ = build_promotion_diffs(
            entry, target_relpath="wiki/patterns/new-thing.md", target_current=None,
            curated_addition="---\ntitle: New Thing\ntype: pattern\n---\n\n# New Thing\n\nbody line\n",
            instincts_relpath=inst_rel, instincts_current=inst_cur, promoted_on="2026-06-28")
        assert page.kind == "page-edit"
        r = self._check(page.unified_diff, tmp_wiki_repo)
        assert r.returncode == 0, r.stderr

    def test_marking_adds_marker_applies_and_is_idempotent(self, tmp_wiki_repo: Path):
        inst_rel, inst_cur, entry = self._setup(tmp_wiki_repo)
        tgt_rel = "wiki/patterns/index.md"
        _, marking = build_promotion_diffs(
            entry, target_relpath=tgt_rel,
            target_current=(tmp_wiki_repo / tgt_rel).read_text(encoding="utf-8"),
            curated_addition="- x\n",
            instincts_relpath=inst_rel, instincts_current=inst_cur, promoted_on="2026-06-28")
        assert "_(promoted 2026-06-28" in marking.unified_diff
        # apply for real → re-parse → entry now reads as promoted (idempotency proof)
        r = subprocess.run(["git", "apply", "-"], cwd=tmp_wiki_repo,
                           input=marking.unified_diff, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        after = parse_instincts((tmp_wiki_repo / inst_rel).read_text(encoding="utf-8"))
        assert after[0].promoted is True
        assert unpromoted(after) == ()
