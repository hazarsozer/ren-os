"""
Tests for skills.wiki-health.lib.watermark — Task 2, RenOS 0.6.5 (incremental
wiki-lint selection). `unlinted()` returns how many journal lines have
accumulated since the last stamped watermark and which distinct pages they
touched (from both per-write `page` entries and `_wrap-session` summaries'
`pages_touched`), so a lint pass can work incrementally instead of re-walking
the whole wiki every time.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — matching the convention in
tests/skills/wiki_health/test_sweep.py.

Run with: uv run pytest tests/skills/wiki_health/test_watermark.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.memory import journal
from lib.memory.provenance import Provenance
from lib.ren_paths import wiki_root

watermark = importlib.import_module("skills.wiki-health.lib.watermark")


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


def _prov(page: str) -> Provenance:
    return Provenance(
        write_id="w-test", ts="2026-08-02T00:00:00Z", writer="human",
        session="s", op="UPDATE", page=page, supersedes=None,
    )


def _append_page(page: str):
    journal.append(_prov(page))


def _append_wrap(pages_touched):
    journal.append(
        _prov("_wrap-session"),
        extra={"wrap_summary": {
            "session": "s", "project": None, "pages_touched": pages_touched,
            "counts": {"applied": len(pages_touched), "held": 0, "refused": 0},
        }},
    )


def test_unlinted_empty_journal(wiki):
    assert watermark.unlinted() == (0, [])


def test_unlinted_counts_and_dedupes_pages_excluding_pseudo_pages(wiki):
    _append_page("index")
    _append_page("log")
    _append_page("index")
    _append_wrap(["projects/foo/map", "log", "_wrap-session"])

    count, pages = watermark.unlinted()

    assert count == 4
    assert pages == ["index", "log", "projects/foo/map"]


def test_advance_watermark_clears_unlinted(wiki):
    _append_page("index")
    _append_page("log")

    watermark.advance_watermark(2, clean=True)

    assert watermark.unlinted() == (0, [])


def test_advance_watermark_leaves_only_new_lines(wiki):
    _append_page("index")
    watermark.advance_watermark(1, clean=True)
    _append_page("log")

    count, pages = watermark.unlinted()

    assert count == 1
    assert pages == ["log"]


def test_corrupt_watermark_file_treated_as_missing(wiki):
    _append_page("index")
    _append_page("log")
    path = wiki_root() / ".ren" / "wiki_lint_watermark.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    assert watermark.read_watermark() == {}
    assert watermark.unlinted() == (2, ["index", "log"])


def test_watermark_round_trip_survives(wiki):
    watermark.advance_watermark(5, clean=False)

    stamped = watermark.read_watermark()

    assert stamped["journal_lines_seen"] == 5
    assert stamped["clean"] is False
    assert "stamped_at" in stamped
