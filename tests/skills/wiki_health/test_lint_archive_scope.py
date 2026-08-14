"""#52 side observation: the wrap close-out lint sweep flags archive/l1/*
copies for missing-frontmatter-type. archive/ is a graveyard of point-in-time
copies, not live claims — excluded from lint scope like raw/ (same noise
class as #31).

Final-review finding 1 (2026-08-14): Task 2's `skip_archive=True` rider only
covered `walk_wiki_pages` (the full scope + link corpus) — the INCREMENTAL
path builds its scope from `_incremental_scope(wiki_root, touched)`, which
was unfiltered. Archiving a page journals an ADD of `archive/<rel>` (the
archive copy), so a freshly archived page lands in the very next incremental
sweep and gets flagged for missing-frontmatter-type — the actual incident
path. Reproduced below: seed watermark, journal an ADD under `archive/`,
run incremental → the archive page must NOT appear in `pages_checked`."""

import importlib

import pytest

from lib.memory import journal
from lib.memory.provenance import Provenance
from lib.ren_paths import wiki_root
from lib.suggestions import pending_suggestions

lint = importlib.import_module("skills.wiki-health.lib.lint")
watermark = importlib.import_module("skills.wiki-health.lib.watermark")


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


# ------------------------------------------------- incremental-path scope


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    watermark.advance_watermark(0, clean=True)
    return root


def _touch_journal(page, op="ADD"):
    journal.append(Provenance(
        write_id="w-test", ts="2026-08-14T00:00:00Z", writer="routine",
        session="s", op=op, page=page, supersedes=None,
    ))


def test_incremental_sweep_excludes_a_freshly_archived_page(wiki):
    """Repro of the actual incident path: archiving `l1/session-001.md`
    journals an ADD of `archive/l1/session-001.md`. That page must not be
    checked (or flagged) in the very next incremental sweep, while a normal
    touched page still is."""
    _mk(wiki, "archive/l1/session-001.md", "body, no frontmatter\n")
    _mk(wiki, "projects/flux/knowledge/live.md", "body, no frontmatter\n")
    _touch_journal("archive/l1/session-001.md", op="ADD")
    _touch_journal("projects/flux/knowledge/live.md", op="ADD")

    result = lint.run_incremental_lint(session="s-1")

    assert "archive/l1/session-001.md" not in result["pages_checked"]
    assert "projects/flux/knowledge/live.md" in result["pages_checked"]
    assert not any(
        s["evidence"].get("page") == "archive/l1/session-001.md" for s in pending_suggestions()
    )
