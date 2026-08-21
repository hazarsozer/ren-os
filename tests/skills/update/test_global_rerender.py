"""
The update flow must re-render the GLOBAL CLAUDE.md block, not just project
blocks (spec 2026-08-21 (0.8.2) §5).

The global block's doctrine index holds absolute paths pinned to the running
plugin version. Nothing re-rendered it on a version bump, so after the 0.8.0 ->
0.8.1 update those five paths still named 0.8.0 -- live only because that cache
dir happened to survive.

Run with: uv run pytest tests/skills/update/test_global_rerender.py -v
"""

from __future__ import annotations

from pathlib import Path

from lib.adapter import claude_md


def _doctrine(tmp_path):
    doctrine = tmp_path / "doctrine"
    doctrine.mkdir()
    (doctrine / "model-classes.md").write_text(
        "---\nactivation: always-on\n---\n# Model classes\n",
        encoding="utf-8"
    )
    return doctrine


def test_rerender_writes_the_running_doctrine_paths(tmp_path):
    claude_dir = tmp_path / "claude"
    claude_dir.mkdir()
    doctrine = _doctrine(tmp_path)

    path, result = claude_md.write_global_claude_md(
        claude_dir=claude_dir, doctrine_root=doctrine
    )

    assert result in ("added", "updated")
    assert str(doctrine) in path.read_text(encoding="utf-8")


def test_rerender_preserves_content_outside_the_markers(tmp_path):
    claude_dir = tmp_path / "claude"
    claude_dir.mkdir()
    doctrine = _doctrine(tmp_path)

    target = claude_dir / "CLAUDE.md"
    preamble = "# My own notes\n\nDo not touch this.\n\n"
    target.write_text(preamble, encoding="utf-8")

    claude_md.write_global_claude_md(claude_dir=claude_dir, doctrine_root=doctrine)

    assert target.read_text(encoding="utf-8").startswith(preamble)


def test_skill_documents_the_global_rerender_step():
    """The closing steps are prose the model follows; the step must be there."""
    text = Path("skills/update/SKILL.md").read_text(encoding="utf-8")

    assert "write_global_claude_md" in text, \
        "update's closing steps must re-render the global tier, not only projects"
