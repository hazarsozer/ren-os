"""
Tests for lib.adapter.claude_md — the hierarchical CLAUDE.md pointer layer
(finalize-v0.2 agenda items 1+2: doctrine delivery via the native CLAUDE.md
hierarchy + the recall doctrine as always-on content).

Run with: uv run pytest tests/lib/adapter/test_claude_md.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.adapter.claude_md import (
    MARKER_BEGIN,
    MARKER_END,
    apply_block,
    render_global_block,
    render_project_block,
    write_global_claude_md,
    write_project_claude_md,
)


def _make_doctrine(root: Path) -> Path:
    doctrine = root / "doctrine"
    doctrine.mkdir(parents=True, exist_ok=True)
    (doctrine / "conventions.md").write_text(
        "---\ntype: doctrine\nactivation: always-on\nscope_glob: null\n---\n\n"
        "# Cadence conventions\n\nBody.\n",
        encoding="utf-8",
    )
    (doctrine / "cadence-matrix.md").write_text(
        "---\ntype: doctrine\nactivation: agent-pulled\nscope_glob: null\n---\n\n"
        "# Cadence decision matrix\n\nBody.\n",
        encoding="utf-8",
    )
    (doctrine / "py-rules.md").write_text(
        "---\ntype: doctrine\nactivation: glob-scoped\nscope_glob: '*.py'\n---\n\n"
        "# Python rules\n\nBody.\n",
        encoding="utf-8",
    )
    return doctrine


# --- apply_block ---------------------------------------------------------


def test_apply_block_creates_missing_file(tmp_path):
    path = tmp_path / "nested" / "CLAUDE.md"

    result = apply_block(path, "hello block")

    assert result == "added"
    text = path.read_text(encoding="utf-8")
    assert MARKER_BEGIN in text and MARKER_END in text
    assert "hello block" in text


def test_apply_block_appends_to_existing_file_preserving_content(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("# My own rules\n\nDo not touch.\n", encoding="utf-8")

    result = apply_block(path, "ren content")

    assert result == "added"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# My own rules")
    assert "Do not touch." in text
    assert text.index("Do not touch.") < text.index(MARKER_BEGIN)


def test_apply_block_updates_only_between_markers(tmp_path):
    path = tmp_path / "CLAUDE.md"
    apply_block(path, "old content")
    path.write_text(
        "before text\n" + path.read_text(encoding="utf-8") + "after text\n",
        encoding="utf-8",
    )

    result = apply_block(path, "new content")

    assert result == "updated"
    text = path.read_text(encoding="utf-8")
    assert "new content" in text
    assert "old content" not in text
    assert "before text" in text and "after text" in text
    assert text.count(MARKER_BEGIN) == 1 and text.count(MARKER_END) == 1


def test_apply_block_is_idempotent(tmp_path):
    path = tmp_path / "CLAUDE.md"
    apply_block(path, "same content")
    before = path.read_text(encoding="utf-8")

    result = apply_block(path, "same content")

    assert result == "unchanged"
    assert path.read_text(encoding="utf-8") == before


def test_apply_block_torn_markers_touch_nothing(tmp_path):
    """Begin marker without end marker: never guess — leave the file alone."""
    path = tmp_path / "CLAUDE.md"
    original = f"stuff\n{MARKER_BEGIN}\nno end marker here\n"
    path.write_text(original, encoding="utf-8")

    result = apply_block(path, "new content")

    assert result == "conflict"
    assert path.read_text(encoding="utf-8") == original


# --- render_global_block --------------------------------------------------


def test_global_block_contains_behavioral_core_and_recall_doctrine(tmp_path):
    doctrine = _make_doctrine(tmp_path)

    block = render_global_block(doctrine_root=doctrine, wiki_root=tmp_path / "wiki")

    # Tailored Karpathy spine
    assert "Think Before Coding" in block
    assert "Simplicity First" in block
    assert "Surgical Changes" in block
    assert "Goal-Driven Execution" in block
    assert "Karpathy" in block  # attribution
    # Agenda item 2: the recall doctrine is always-on content
    assert "/ren:recall" in block
    assert "never" in block.lower() and "raw-read" in block.lower().replace("raw read", "raw-read")
    # Wiki navigation names the real root
    assert str((tmp_path / "wiki").resolve()) in block


def test_global_block_doctrine_index_consumes_loader(tmp_path):
    """THE consumer test for lib.doctrine.loader — closes the §3.3 delivery
    gap: every valid doctrine file appears in the generated index with its
    activation semantics."""
    doctrine = _make_doctrine(tmp_path)

    block = render_global_block(doctrine_root=doctrine, wiki_root=tmp_path / "wiki")

    assert "Cadence conventions" in block
    assert "Cadence decision matrix" in block
    assert "Python rules" in block
    assert "*.py" in block  # glob-scoped files show their trigger glob
    assert str((doctrine / "conventions.md").resolve()) in block


def test_global_block_skips_behavioral_core_when_already_present(tmp_path):
    """Dedup-awareness: a user whose CLAUDE.md already carries Karpathy's
    guidelines (outside our markers) must not get them twice."""
    doctrine = _make_doctrine(tmp_path)
    existing = (
        "# CLAUDE.md\n\nBehavioral guidelines to reduce common LLM coding "
        "mistakes.\n\n## 1. Think Before Coding\n...\n"
    )

    block = render_global_block(
        existing_text=existing, doctrine_root=doctrine, wiki_root=tmp_path / "wiki"
    )

    assert "## Think Before Coding" not in block
    assert "already present" in block.lower()
    # RenOS-specific globals still render
    assert "/ren:recall" in block


def test_global_block_dedup_ignores_our_own_managed_block(tmp_path):
    """Sentinels inside a previous ren-managed block must NOT count as
    'user already has the guidelines' — else the second run of install
    would drop the core we ourselves wrote."""
    doctrine = _make_doctrine(tmp_path)
    first = render_global_block(doctrine_root=doctrine, wiki_root=tmp_path / "wiki")
    path = tmp_path / "CLAUDE.md"
    apply_block(path, first)

    second = render_global_block(
        existing_text=path.read_text(encoding="utf-8"),
        doctrine_root=doctrine,
        wiki_root=tmp_path / "wiki",
    )

    assert "Think Before Coding" in second


# --- render_project_block ---------------------------------------------------


def test_project_block_points_at_map_and_defers_to_global(tmp_path):
    wiki_root = tmp_path / "wiki"

    block = render_project_block("demo-project", wiki_root=wiki_root)

    assert str((wiki_root / "projects" / "demo-project" / "map.md").resolve()) in block
    assert "/ren:recall" in block
    # Pointer layer never duplicates the global tier's content
    assert "Think Before Coding" not in block


# --- write surfaces ----------------------------------------------------------


def test_write_global_claude_md_honors_ren_claude_dir(tmp_path, monkeypatch):
    doctrine = _make_doctrine(tmp_path)
    claude_dir = tmp_path / "claude-home"
    monkeypatch.setenv("REN_CLAUDE_DIR", str(claude_dir))

    path, result = write_global_claude_md(
        doctrine_root=doctrine, wiki_root=tmp_path / "wiki"
    )

    assert path == claude_dir / "CLAUDE.md"
    assert result == "added"
    assert "/ren:recall" in path.read_text(encoding="utf-8")

    # Second run: nothing changed → unchanged
    _, second = write_global_claude_md(
        doctrine_root=doctrine, wiki_root=tmp_path / "wiki"
    )
    assert second == "unchanged"


def test_write_global_claude_md_dedups_against_existing_file(tmp_path, monkeypatch):
    doctrine = _make_doctrine(tmp_path)
    claude_dir = tmp_path / "claude-home"
    claude_dir.mkdir()
    (claude_dir / "CLAUDE.md").write_text(
        "Behavioral guidelines to reduce common LLM coding mistakes.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REN_CLAUDE_DIR", str(claude_dir))

    path, result = write_global_claude_md(
        doctrine_root=doctrine, wiki_root=tmp_path / "wiki"
    )

    assert result == "added"
    text = path.read_text(encoding="utf-8")
    assert text.count("reduce common LLM coding mistakes") == 1
    assert "## Think Before Coding" not in text


def test_write_project_claude_md(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    path, result = write_project_claude_md(
        repo_root, "demo-project", wiki_root=tmp_path / "wiki"
    )

    assert path == repo_root / "CLAUDE.md"
    assert result == "added"
    assert "demo-project" in path.read_text(encoding="utf-8")
