"""
Tests for skills.wiki-health.lib.release_page — the quarantine release flow
(Task 3, RenOS 0.3.1). This is the ONLY product exit from quarantine: the
live session calls it after the friend explicitly blesses a page (see
SKILL.md — never auto-release from a sweep).

Fixture convention mirrors tests/skills/wiki_health/test_sweep.py and
tests/lib/memory/test_queue.py: redirect ren_paths' framework root to
tmp_path via REN_FRAMEWORK_ROOT so queue/journal/snapshot state stays in the
sandbox. There is no shared `isolated_wiki` fixture in this codebase — each
test module defines its own local `clean_path_env` + `wiki` fixtures.

Note on the journal assertion: `lib.memory.journal.entries()` lines are
`asdict(Provenance)` merged with an optional `extra` dict (see journal.py) —
there is no `reason` field on `Provenance` itself, and `propose_and_apply`'s
`apply_auto` path only merges `{"auto": True}` as journal extra. So "this
release was journaled" is verified by matching the journal line's write_id
to the `Provenance` `release_page` returns; "the reason recorded is
quarantine-release" is verified on the `QueueEntry.proposal.reason` the same
call returns (the reason that field name actually lives on).

Run with: uv run pytest tests/skills/wiki_health/test_release.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.memory import journal, quarantine
from lib.ren_paths import wiki_root

wiki_health = importlib.import_module("skills.wiki-health.lib")  # hyphen-safe import, same as test_sweep.py


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
    return root


def _make_quarantined_page(wiki_root, rel="projects/app/map.md"):
    page = wiki_root / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    body = "## Knowledge\n- uses postgres for storage\n"
    page.write_text(quarantine.mark(body), encoding="utf-8")
    return rel


class TestReleasePage:
    def test_release_strips_banner_through_substrate(self, wiki):
        rel = _make_quarantined_page(wiki)
        entry, prov = wiki_health.release_page(rel, session="test-session")
        assert prov is not None  # data-plane write auto-applied
        text = (wiki / rel).read_text(encoding="utf-8")
        assert not quarantine.is_quarantined(text)
        assert "uses postgres" in text  # body survives
        assert entry.proposal.reason == "quarantine-release"

    def test_release_is_journaled(self, wiki):
        rel = _make_quarantined_page(wiki)
        entry, prov = wiki_health.release_page(rel, session="test-session")
        page_entries = journal.entries(page=rel)
        assert any(e.get("write_id") == prov.write_id for e in page_entries)

    def test_release_rejects_unquarantined_page(self, wiki):
        rel = "projects/app/clean.md"
        page = wiki / rel
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("## Knowledge\n- fine\n", encoding="utf-8")
        with pytest.raises(ValueError):
            wiki_health.release_page(rel, session="test-session")

    def test_release_rejects_missing_page(self, wiki):
        with pytest.raises(FileNotFoundError):
            wiki_health.release_page("projects/app/nope.md", session="test-session")
