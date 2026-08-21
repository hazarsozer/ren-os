"""
End-to-end test for the frontmatter-type-1 migration (spec 2026-08-21 §2.5).

Backfills the derived `type:` onto pages created before the write door
derived one. Like trust-backfill-1, it walks the wiki tree directly rather
than following the per-page-type migrate.sh chain — see the README.

Run with: uv run pytest tests/migrations/test_frontmatter_type_1.py -v
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from lib.ren_paths import state_dir, wiki_root

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


def _journal_path(wiki: Path) -> Path:
    return state_dir() / "migrations" / "frontmatter-type-1.jsonl"


def test_real_run_journals_one_line_per_stamped_page(wiki):
    _write(wiki, "lessons/a.md", "# Body\n")
    _write(wiki, "identity.md", "# Body\n")
    # Already typed — must NOT be journaled (I1, no write happens for it).
    _write(
        wiki,
        "projects/h/knowledge/lessons/lessons.md",
        "---\ntype: project-knowledge\n---\n# Body\n",
    )
    # Unmapped — must NOT be journaled (I2, no write happens for it).
    _write(wiki, "some/novel/shape.md", "# Body\n")

    migrate = _load_migrate()
    assert migrate.main([]) == 0

    journal = _journal_path(wiki)
    assert journal.is_file()

    lines = journal.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    records = [json.loads(line) for line in lines]
    pages = {r["page"] for r in records}
    assert pages == {"lessons/a.md", "identity.md"}
    for record in records:
        assert record["migration"] == "frontmatter-type-1"
        assert "ts" in record


def test_check_writes_no_journal_file(wiki):
    _write(wiki, "lessons/a.md", "# Body\n")

    migrate = _load_migrate()
    assert migrate.main(["--check"]) == 0

    assert not _journal_path(wiki).exists()


def test_second_run_appends_no_duplicate_journal_lines(wiki):
    _write(wiki, "lessons/a.md", "# Body\n")
    _write(wiki, "identity.md", "# Body\n")

    migrate = _load_migrate()
    migrate.main([])

    journal = _journal_path(wiki)
    first_lines = journal.read_text(encoding="utf-8").splitlines()
    assert len(first_lines) == 2

    migrate.main([])

    second_lines = journal.read_text(encoding="utf-8").splitlines()
    assert len(second_lines) == len(first_lines) == 2
    assert second_lines == first_lines
