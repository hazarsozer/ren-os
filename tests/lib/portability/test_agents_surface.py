"""
Tests for lib.portability.agents_surface — G13 AGENTS.md canonical surface
(Task 7.2, spec §3.9 A-9, exit criterion 5).

Run with: uv run pytest tests/lib/portability/test_agents_surface.py -v
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from lib.portability.agents_surface import (
    CLAUDE_TOKENS,
    lint_generated_surfaces,
    lint_harness_neutral,
    render_agents_md,
    write_agents_md,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROOF_SCRIPT = REPO_ROOT / "scripts" / "codex_read_proof.sh"


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- render_agents_md ---------------------------------------------------


def test_render_agents_md_with_project_slug_links_project_map_and_global(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    content = render_agents_md(wiki_root, project_slug="demo-project")

    assert str((wiki_root / "projects" / "demo-project" / "map.md").resolve()) in content
    assert str((wiki_root / "global").resolve()) in content


def test_render_agents_md_passes_lint_harness_neutral_golden(tmp_path):
    """THE golden test for exit criterion 5's substrate: zero offenders."""
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    content = render_agents_md(wiki_root, project_slug="demo-project")
    assert lint_harness_neutral(content) == []


def test_render_agents_md_without_slug_links_master_index(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    content = render_agents_md(wiki_root, project_slug=None)

    assert str((wiki_root / "index.md").resolve()) in content
    assert "demo-project" not in content
    assert lint_harness_neutral(content) == []


# --- write_agents_md ------------------------------------------------------


def test_write_agents_md_lands_at_repo_root(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    path = write_agents_md(repo_root, wiki_root, project_slug="demo-project")

    assert path == repo_root / "AGENTS.md"
    assert path.is_file()
    assert "demo-project" in path.read_text(encoding="utf-8")


def test_write_agents_md_reruns_overwrite_idempotently(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()

    write_agents_md(repo_root, wiki_root, project_slug="first-project")
    first_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    assert "first-project" in first_text

    write_agents_md(repo_root, wiki_root, project_slug="second-project")
    second_text = (repo_root / "AGENTS.md").read_text(encoding="utf-8")

    assert "second-project" in second_text
    assert "first-project" not in second_text  # overwritten, not appended
    # Only one AGENTS.md, still exactly at repo_root.
    assert list(repo_root.glob("AGENTS.md")) == [repo_root / "AGENTS.md"]


# --- lint_harness_neutral --------------------------------------------------


@pytest.mark.parametrize("token", list(CLAUDE_TOKENS))
def test_lint_harness_neutral_catches_each_token_case_insensitively(token):
    text = f"some prose mentioning {token.upper()} right here"
    offenders = lint_harness_neutral(text)
    assert token in offenders


def test_lint_harness_neutral_clean_text_returns_empty_list():
    assert lint_harness_neutral("Just a normal orientation paragraph about this project.") == []


# --- lint_generated_surfaces -----------------------------------------------


def test_lint_generated_surfaces_flags_planted_l2_map_with_claude_mention(tmp_path):
    wiki_root = tmp_path / "wiki"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    _write(
        wiki_root, "projects/demo/map.md",
        "---\ntype: l2-map\nproject: demo\n---\n# demo map\n\nBuilt for use with Claude Code.\n",
    )

    report = lint_generated_surfaces(wiki_root, repo_root)
    assert str((wiki_root / "projects" / "demo" / "map.md")) in report
    assert "claude" in report[str(wiki_root / "projects" / "demo" / "map.md")]


def test_lint_generated_surfaces_does_not_flag_human_lessons_page(tmp_path):
    wiki_root = tmp_path / "wiki"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    _write(
        wiki_root, "lessons/my-lesson.md",
        "---\ntype: lesson\n---\n# A lesson\n\nI was using Claude Code and noticed...\n",
    )

    report = lint_generated_surfaces(wiki_root, repo_root)
    assert str(wiki_root / "lessons" / "my-lesson.md") not in report


def test_lint_generated_surfaces_missing_agents_md_not_in_report(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()  # no AGENTS.md written

    report = lint_generated_surfaces(wiki_root, repo_root)
    assert str(repo_root / "AGENTS.md") not in report


def test_lint_generated_surfaces_flags_agents_md_itself_if_dirty(tmp_path):
    wiki_root = tmp_path / "wiki"
    wiki_root.mkdir()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write(repo_root, "AGENTS.md", "# AGENTS.md\n\nMaintained by Claude Code.\n")

    report = lint_generated_surfaces(wiki_root, repo_root)
    assert str(repo_root / "AGENTS.md") in report


# --- codex_read_proof.sh: static assertions only, never invoke codex -------


def test_codex_read_proof_script_exists_and_is_executable():
    assert PROOF_SCRIPT.is_file()
    mode = PROOF_SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def test_codex_read_proof_script_contains_exit_3_pending_branch():
    text = PROOF_SCRIPT.read_text(encoding="utf-8")
    assert "PENDING-HUMAN" in text
    assert "exit 3" in text
