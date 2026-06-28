"""
Tests for build_globalize_diffs — the project→global instinct promotion axis (C3).

Pure diff construction (provenance-preserving bullets + ONE coalesced marking),
verified end-to-end against real `git apply` via the tmp_wiki_repo fixture.

Run with:
    python3 -m pytest skills/consolidate/lib/tests/test_globalize.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..__init__ import (
    apply_diff_entries,
    build_globalize_diffs,
    parse_instincts,
    unpromoted,
)

_PROJ_REL = "wiki/projects/dry/instincts.md"
_GLOBAL_REL = "wiki/instincts.md"
_FV = "0.1.0"

_TWO = (
    "- **[worked]** 2026-06-20 — sort the glob for determinism\n"
    "- **[avoid]** 2026-06-21 — never git clean the whole wiki on rollback\n"
)


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _set_project_instincts(repo: Path, body: str) -> str:
    text = "---\ntype: instincts\nschema_version: 1\nscope: project\n---\n\n# Instincts — dry\n\n" + body
    (repo / _PROJ_REL).write_text(text, encoding="utf-8")
    _git(["add", _PROJ_REL], repo)
    _git(["commit", "-m", "set project instincts"], repo)
    return text


def _commit_global(repo: Path, body: str) -> str:
    text = (
        '---\ntype: instincts\nschema_version: 1\nframework_version: "0.1.0"\n'
        "scope: global\nupdated: 2026-06-01\n---\n\n# Instincts — Global\n\nAppend-only.\n\n" + body
    )
    (repo / _GLOBAL_REL).write_text(text, encoding="utf-8")
    _git(["add", _GLOBAL_REL], repo)
    _git(["commit", "-m", "global pool"], repo)
    return text


def _build(proj_cur: str, global_cur: str | None):
    entries = unpromoted(parse_instincts(proj_cur))
    return entries, build_globalize_diffs(
        entries,
        project_instincts_relpath=_PROJ_REL, project_instincts_current=proj_cur,
        global_relpath=_GLOBAL_REL, global_current=global_cur,
        framework_version=_FV, promoted_on="2026-06-28",
    )


def test_creates_global_pool_when_absent(tmp_wiki_repo: Path):
    proj_cur = _set_project_instincts(tmp_wiki_repo, _TWO)
    entries, (page, marking) = _build(proj_cur, None)
    assert len(entries) == 2
    res = apply_diff_entries((page, marking), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    assert res.success and res.diffs_applied == 2
    gtext = (tmp_wiki_repo / _GLOBAL_REL).read_text(encoding="utf-8")
    assert "type: instincts" in gtext and "scope: global" in gtext       # created with frontmatter
    assert "- **[worked]** 2026-06-20 — sort the glob for determinism" in gtext  # provenance preserved
    ptext = (tmp_wiki_repo / _PROJ_REL).read_text(encoding="utf-8")
    assert ptext.count("_(promoted 2026-06-28 → wiki/instincts.md)_") == 2


def test_appends_to_existing_global_pool(tmp_wiki_repo: Path):
    proj_cur = _set_project_instincts(tmp_wiki_repo, _TWO)
    gcur = _commit_global(tmp_wiki_repo, "- **[worked]** 2026-05-01 — pre-existing global\n")
    _, (page, marking) = _build(proj_cur, gcur)
    res = apply_diff_entries((page, marking), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    assert res.success
    gtext = (tmp_wiki_repo / _GLOBAL_REL).read_text(encoding="utf-8")
    assert "pre-existing global" in gtext                  # kept
    assert "sort the glob for determinism" in gtext        # appended
    assert gtext.count("type: instincts") == 1             # frontmatter not duplicated


def test_marking_is_one_coalesced_diff(tmp_wiki_repo: Path):
    proj_cur = _set_project_instincts(tmp_wiki_repo, _TWO)
    _, (page, marking) = _build(proj_cur, None)
    assert page.kind == "page-edit" and page.target_file == _GLOBAL_REL
    assert marking.kind == "marking" and marking.target_file == _PROJ_REL
    assert marking.unified_diff.count("_(promoted") == 2   # ONE diff covers BOTH source lines


def test_idempotent_after_apply(tmp_wiki_repo: Path):
    proj_cur = _set_project_instincts(tmp_wiki_repo, _TWO)
    _, (page, marking) = _build(proj_cur, None)
    apply_diff_entries((page, marking), wiki_root=tmp_wiki_repo / "wiki", cwd=tmp_wiki_repo)
    after = (tmp_wiki_repo / _PROJ_REL).read_text(encoding="utf-8")
    assert unpromoted(parse_instincts(after)) == ()        # all promoted → re-run proposes nothing
