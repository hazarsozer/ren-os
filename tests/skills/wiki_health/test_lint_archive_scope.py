"""#52 side observation: the wrap close-out lint sweep flags archive/l1/*
copies for missing-frontmatter-type. archive/ is a graveyard of point-in-time
copies, not live claims — excluded from lint scope like raw/ (same noise
class as #31)."""

import importlib

lint = importlib.import_module("skills.wiki-health.lib.lint")


def _mk(root, rel, text="body, no frontmatter\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_walk_skips_archive_when_asked(tmp_path):
    _mk(tmp_path, "archive/l1/old-session.md")
    _mk(tmp_path, "projects/flux/archive/notes.md")
    _mk(tmp_path, "projects/flux/knowledge/live.md")
    pages = lint.walk_wiki_pages(tmp_path, skip_archive=True)
    assert pages == ["projects/flux/knowledge/live.md"]


def test_walk_keeps_archive_by_default(tmp_path):
    _mk(tmp_path, "archive/l1/old-session.md")
    pages = lint.walk_wiki_pages(tmp_path)
    assert "archive/l1/old-session.md" in pages


def test_knowledge_archive_is_not_exempt(tmp_path):
    # only root archive/ and projects/<slug>/archive/ — never arbitrary depth
    _mk(tmp_path, "projects/flux/knowledge/archive/deep.md")
    pages = lint.walk_wiki_pages(tmp_path, skip_archive=True)
    assert "projects/flux/knowledge/archive/deep.md" in pages
