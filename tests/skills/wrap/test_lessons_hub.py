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

import importlib
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
    assert "type: hub" in text
    assert "project: p" in text
    assert "hub: true" in text


def test_project_hub_type_agrees_with_derive_type(wiki):
    """Final-review finding 2 (2026-08-21): the hard-coded `type:` this
    helper stamps on a NEW project lessons hub must equal
    `lib.memory.page_types.derive_type()`'s answer for that exact path —
    invariant I1 means whichever value lands here wins permanently at the
    write door, so a disagreement would leave the wiki accumulating project
    lessons hubs of both types depending on which code path created the
    page."""
    from lib.memory.page_types import derive_type

    lessons_dir = wiki / "projects" / "p" / "knowledge" / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "insight-one.md").write_text("Insight.\n", encoding="utf-8")

    _ensure_lessons_hub("projects/p/knowledge/lessons", "s1", "p")

    hub_path = lessons_dir / "lessons.md"
    text = hub_path.read_text(encoding="utf-8")
    stamped = next(
        line.split(":", 1)[1].strip()
        for line in text.splitlines()
        if line.startswith("type:")
    )
    assert stamped == derive_type("projects/p/knowledge/lessons/lessons.md")


def test_existing_hub_keeps_human_prose_and_gains_only_the_new_link(wiki):
    """#I2: an existing hub is APPENDED to, never re-rendered — a human's
    prose (and hand-written ordering) survives; only the missing link lands."""
    lessons_dir = wiki / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "old-one.md").write_text("Old lesson one.\n", encoding="utf-8")

    hub_path = lessons_dir / "lessons.md"
    hub_path.write_text(
        "---\ntype: hub\nhub: true\ntitle: \"Lessons\"\n---\n\n"
        "# Lessons\n\n"
        "These are the ones I actually reread — the rest is noise.\n\n"
        "- [old-one](old-one.md)\n",
        encoding="utf-8",
    )

    (lessons_dir / "new-one.md").write_text("New lesson.\n", encoding="utf-8")
    assert _ensure_lessons_hub("lessons", "s1", None) is True

    text = hub_path.read_text(encoding="utf-8")
    assert "These are the ones I actually reread — the rest is noise." in text
    assert "- [old-one](old-one.md)" in text
    assert "- [new-one](new-one.md)" in text
    assert _links(text) == ["- [old-one](old-one.md)", "- [new-one](new-one.md)"]


def test_trust_user_hub_is_never_touched(wiki):
    """#I2: a hub the friend owns (`ren_trust: user`) is skipped entirely —
    same hold rule the durable-update path applies to trust-user targets."""
    lessons_dir = wiki / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "new-one.md").write_text("New lesson.\n", encoding="utf-8")

    hub_path = lessons_dir / "lessons.md"
    before = (
        "---\ntype: hub\nhub: true\nren_trust: \"user\"\ntitle: \"Lessons\"\n---\n\n"
        "# Lessons\n\nMy hand-curated list.\n"
    )
    hub_path.write_text(before, encoding="utf-8")

    assert _ensure_lessons_hub("lessons", "s1", None) is False
    assert hub_path.read_text(encoding="utf-8") == before


def test_new_global_hub_has_frontmatter_type(wiki):
    """#I6: wiki-lint files a `missing-frontmatter-type` judgment on any page
    without a frontmatter `type:` — wrap's own hub must not trip its own lint."""
    lessons_dir = wiki / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "old-one.md").write_text("Old lesson one.\n", encoding="utf-8")

    assert _ensure_lessons_hub("lessons", "s1", None) is True

    text = (lessons_dir / "lessons.md").read_text(encoding="utf-8")
    assert "type: hub" in text

    lint = importlib.import_module("skills.wiki-health.lib.lint")
    assert lint._frontmatter_type(text) == "hub"


def test_hub_failure_never_raises(wiki, monkeypatch):
    lessons_dir = wiki / "lessons"
    lessons_dir.mkdir(parents=True, exist_ok=True)
    (lessons_dir / "old-one.md").write_text("Old lesson one.\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("queue explosion")

    monkeypatch.setattr("skills.wrap.lib.propose_and_apply", boom)

    result = _ensure_lessons_hub("lessons", "s1", None)

    assert result is False
