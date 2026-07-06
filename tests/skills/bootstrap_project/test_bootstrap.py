"""
Tests for skills.bootstrap-project.lib — the empty-map, fresh-project verb
(Task 4.4).

`bootstrap` stamps the shared skeleton (additive) then queues an empty L2
map with writer="human" (never quarantined on apply, unlike ingest-project's
scan-derived writer="llm-auto" maps).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/bootstrap_project/test_bootstrap.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.memory import journal, quarantine, queue
from lib.ren_paths import wiki_root

bootstrap_lib = importlib.import_module("skills.bootstrap-project.lib")
bootstrap = bootstrap_lib.bootstrap


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


def test_bootstrap_creates_pending_add_with_empty_map(wiki):
    entry = bootstrap("new-idea", session="sess-1")

    assert entry.status == "pending"
    assert entry.proposal.op == "ADD"
    assert entry.proposal.page == "projects/new-idea/map.md"
    assert entry.proposal.producer == "promotion"
    assert entry.proposal.writer == "human"
    assert "## Knowledge" in entry.proposal.content
    assert "## Decision map" in entry.proposal.content
    assert "## Log" in entry.proposal.content
    assert "type: l2-map" in entry.proposal.content


def test_bootstrap_on_existing_map_proposes_update(wiki):
    first = bootstrap("existing-idea", session="sess-1")
    queue.approve(first.qid, approved_by="hazar")
    queue.apply(first.qid)

    second = bootstrap("existing-idea", session="sess-2")
    assert second.proposal.op == "UPDATE"


def test_bootstrap_applies_clean_human_provenance_not_quarantined(wiki):
    entry = bootstrap("clean-idea", session="sess-1")
    queue.approve(entry.qid, approved_by="hazar")
    prov = queue.apply(entry.qid)

    assert prov.writer == "human"

    page_text = (wiki / "projects" / "clean-idea" / "map.md").read_text(encoding="utf-8")
    assert not quarantine.is_quarantined(page_text)

    entries = journal.entries(page="projects/clean-idea/map.md")
    assert len(entries) == 1
    assert entries[0]["writer"] == "human"


def test_bootstrap_stamps_skeleton_additively_existing_user_file_untouched(wiki):
    sentinel_index = wiki / "index.md"
    sentinel_index.write_text("MY OWN CUSTOM INDEX — DO NOT TOUCH", encoding="utf-8")

    bootstrap("some-project", session="sess-1")

    assert sentinel_index.read_text(encoding="utf-8") == "MY OWN CUSTOM INDEX — DO NOT TOUCH"


def test_bootstrap_stamps_missing_skeleton_dirs(wiki):
    assert not (wiki / "research").exists()

    bootstrap("some-other-project", session="sess-1")

    assert (wiki / "research").is_dir()
    assert (wiki / "decisions").is_dir()
