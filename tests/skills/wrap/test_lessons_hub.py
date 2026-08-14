"""
Tests for `_ensure_lessons_hub` (Task 5): the lessons/ folder-note hub —
`<dir>/<dirname>.md`, `hub: true` frontmatter — created/backfilled the first
time a durable lesson lands in a directory, and left alone (idempotent) on
every call after that.

Reuses test_durable_loop.py's isolation pattern (REN_FRAMEWORK_ROOT-pointed
`wiki` fixture).

CONTROLLER RULING: the write door stamps `ren_*` provenance frontmatter onto
every applied page, so the on-disk hub file never byte-equals the freshly
rendered body. Idempotence is therefore checked by comparing the LINK LIST
extracted from the on-disk hub body against the freshly rendered link list
(same helper `_ensure_lessons_hub` uses internally to decide whether to
write) — not by raw byte-equality of the whole file.

Run with: uv run pytest tests/skills/wrap/test_lessons_hub.py -v
"""

from __future__ import annotations

import re

import pytest

from lib.ren_paths import wiki_root
from skills.wrap.lib import _ensure_lessons_hub

_LINK_RE = re.compile(r"^- \[[^\]]+\]\([^)]+\)$", re.MULTILINE)


def _links(text: str) -> list[str]:
    return _LINK_RE.findall(text)


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in (
        "REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT",
        "CLAUDE_PLUGIN_OPTION_DEVROOT",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_global_hub_created_with_backfill(wiki):
    lessons_dir = wiki / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "old-one.md").write_text("Old lesson one.\n", encoding="utf-8")
    (lessons_dir / "old-two.md").write_text("Old lesson two.\n", encoding="utf-8")

    result = _ensure_lessons_hub("lessons", "s1", None)

    assert result is True
    hub_path = lessons_dir / "lessons.md"
    assert hub_path.is_file()
    text = hub_path.read_text(encoding="utf-8")
    assert "hub: true" in text
    assert "- [old-one](old-one.md)" in text
    assert "- [old-two](old-two.md)" in text


def test_hub_idempotent(wiki):
    lessons_dir = wiki / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "old-one.md").write_text("Old lesson one.\n", encoding="utf-8")

    first = _ensure_lessons_hub("lessons", "s1", None)
    assert first is True

    hub_path = lessons_dir / "lessons.md"
    before = hub_path.read_text(encoding="utf-8")
    before_links = _links(before)

    second = _ensure_lessons_hub("lessons", "s1", None)

    assert second is False
    after = hub_path.read_text(encoding="utf-8")
    after_links = _links(after)
    assert after_links == before_links
    assert after == before


def test_project_hub_frontmatter(wiki):
    lessons_dir = wiki / "projects" / "p" / "knowledge" / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "insight-one.md").write_text("Insight.\n", encoding="utf-8")

    result = _ensure_lessons_hub("projects/p/knowledge/lessons", "s1", "p")

    assert result is True
    hub_path = lessons_dir / "lessons.md"
    assert hub_path.is_file()
    text = hub_path.read_text(encoding="utf-8")
    assert "type: project-knowledge" in text
    assert "project: p" in text
    assert "hub: true" in text


def test_hub_failure_never_raises(wiki, monkeypatch):
    lessons_dir = wiki / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "old-one.md").write_text("Old lesson one.\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("queue explosion")

    monkeypatch.setattr("skills.wrap.lib.propose_and_apply", boom)

    result = _ensure_lessons_hub("lessons", "s1", None)

    assert result is False
