"""
End-to-end test for the frontmatter-type-1 migration (spec 2026-08-21 §2.5).

Backfills the derived `type:` onto pages created before the write door
derived one. Like trust-backfill-1, it walks the wiki tree directly rather
than following the per-page-type migrate.sh chain — see the README.

Run with: uv run pytest tests/migrations/test_frontmatter_type_1.py -v
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from lib.ren_paths import wiki_root

_MIGRATE_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "frontmatter-type-1" / "migrate.py"
)


def _load_migrate():
    spec = importlib.util.spec_from_file_location("frontmatter_type_1_migrate", _MIGRATE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_stamps_every_path_shape(wiki):
    cases = {
        "projects/h/schema.md": "project-schema",
        "projects/h/knowledge/codebase/codebase.md": "hub",
        "lessons/a.md": "lesson",
        "projects/f/knowledge/lessons/b.md": "lesson",
        "projects/r/l1/session-x.md": "l1",
        "projects/h/knowledge/operations.md": "project-knowledge",
        "identity.md": "identity",
    }
    for rel in cases:
        _write(wiki, rel, "# Body\n")

    migrate = _load_migrate()
    assert migrate.main([]) == 0

    for rel, expected in cases.items():
        text = (wiki / rel).read_text(encoding="utf-8")
        assert f"type: {expected}" in text, rel


def test_i1_already_typed_page_is_untouched(wiki):
    text = "---\ntype: project-knowledge\n---\n# Body\n"
    path = _write(wiki, "projects/h/knowledge/lessons/lessons.md", text)

    migrate = _load_migrate()
    assert migrate.main([]) == 0

    assert path.read_text(encoding="utf-8") == text


def test_i2_unmapped_page_is_untouched(wiki):
    text = "# Body\n"
    path = _write(wiki, "some/novel/shape.md", text)

    migrate = _load_migrate()
    assert migrate.main([]) == 0

    assert path.read_text(encoding="utf-8") == text


def test_check_only_reports_without_writing(wiki):
    path = _write(wiki, "lessons/a.md", "# Body\n")

    migrate = _load_migrate()
    assert migrate.main(["--check"]) == 0

    assert path.read_text(encoding="utf-8") == "# Body\n"


def test_is_idempotent(wiki):
    _write(wiki, "lessons/a.md", "# Body\n")

    migrate = _load_migrate()
    migrate.main([])
    first = (wiki / "lessons" / "a.md").read_text(encoding="utf-8")
    migrate.main([])
    second = (wiki / "lessons" / "a.md").read_text(encoding="utf-8")

    assert first == second
    assert first.count("type: lesson") == 1
