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
from skills.update import lib as update_lib


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


def test_rerender_malformed_registry_is_unknown(tmp_path, monkeypatch):
    """{} used to mean both "no project has an instructions.md" (benign)
    and "the registry could not be parsed" (blind). This exercises the
    malformed-but-readable branch — syntactically invalid JSON in a file
    that reads fine. See test_rerender_unreadable_registry_is_unknown below
    for the separate OSError-on-read branch."""
    from lib.reporting import Unknown

    wiki = tmp_path / "wiki"
    (wiki / "projects").mkdir(parents=True)
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))

    registry = tmp_path / "projects.json"
    registry.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(
        "lib.ren_paths.projects_registry_path", lambda: registry
    )

    result = update_lib.rerender_all_project_claude_md()

    assert isinstance(result, Unknown)
    assert "malformed" in result.reason


def test_rerender_unreadable_registry_is_unknown(tmp_path, monkeypatch):
    """Genuinely exercises the `except OSError` branch: making the registry
    "path" a directory means Path.read_text() raises IsADirectoryError (an
    OSError subclass) on the read attempt — this works regardless of user
    privileges, unlike a chmod(0o000) approach which silently fails to deny
    root, and CI often runs as root."""
    from lib.reporting import Unknown

    wiki = tmp_path / "wiki"
    (wiki / "projects").mkdir(parents=True)
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))

    registry = tmp_path / "projects.json"
    registry.mkdir()
    monkeypatch.setattr(
        "lib.ren_paths.projects_registry_path", lambda: registry
    )

    result = update_lib.rerender_all_project_claude_md()

    assert isinstance(result, Unknown)
    assert "unreadable" in result.reason


def test_rerender_readable_but_empty_registry_is_not_unknown(tmp_path, monkeypatch):
    """A registry that reads fine and lists nothing is a real answer: no
    projects. It must NOT be reported as blindness."""
    import json

    from lib.reporting import Unknown

    wiki = tmp_path / "wiki"
    (wiki / "projects").mkdir(parents=True)
    monkeypatch.setenv("REN_WIKI_ROOT", str(wiki))

    registry = tmp_path / "projects.json"
    registry.write_text(json.dumps({"projects": {}}), encoding="utf-8")
    monkeypatch.setattr(
        "lib.ren_paths.projects_registry_path", lambda: registry
    )

    result = update_lib.rerender_all_project_claude_md()

    assert not isinstance(result, Unknown)
    assert result == {}
