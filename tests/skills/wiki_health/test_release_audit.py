"""
Tests for Task 3 (#51): audit trail on every quarantine release path.

This file covers `skills.wiki-health.lib.release_page` and
`release_page_auto` DIRECTLY: default `via="human-direct"`, an explicit
`via`/`evidence` passed straight through `release_page`, the `"machine"`
literal `release_page_auto` always records, and that a held-on-contradicts
`release_page` call records no metric at all.

It does NOT exercise the suggestion-accepted wiring in
`skills/suggestions/lib/__init__.py` (the `quarantine_release` action
branch) — that goes through the real `accept()` path and lives in
`tests/skills/suggestions/test_suggestions_skill.py`
(`test_accept_quarantine_release_records_metric_via_suggestion_accepted`).

Fixture convention copied from tests/skills/wiki_health/test_quarantine_screen.py
(itself copied from tests/skills/wiki_health/test_release.py) — no shared
isolated_wiki fixture exists in this codebase.

Run with: uv run pytest tests/skills/wiki_health/test_release_audit.py -v
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

import pytest

from lib.instrument import collect
from lib.memory import quarantine
from lib.memory import queue as queue_mod
from lib.ren_paths import wiki_root

wiki_health = importlib.import_module("skills.wiki-health.lib")


@dataclass
class _FakeConflict:
    """Mirrors test_quarantine_screen.py's `_FakeConflict` — the
    monkeypatched-`_semantics.detect` recipe used there to fabricate a
    `contradicts` hold without needing a real second contradicting page."""

    kind: str
    page: str
    write_id: str | None
    evidence: str


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


def _write_page(root, rel, body="## Notes\n- postgres is the store\n",
                trust="model", banner=True):
    page = root / rel
    page.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        "---\n"
        'ren_write_id: "w-01TESTTESTTESTTESTTESTTEST"\n'
        'ren_ts: "2026-08-01T00:00:00Z"\n'
        'ren_writer: "llm-auto"\n'
        'ren_op: "ADD"\n'
        f'ren_trust: "{trust}"\n'
        "---\n"
    )
    text = fm + (quarantine.mark(body) if banner else body)
    page.write_text(text, encoding="utf-8")
    return rel


@pytest.fixture
def wiki_with_quarantined_page(wiki):
    return _write_page(wiki, "projects/app/knowledge/stack.md")


@pytest.fixture
def recorded_metrics(monkeypatch):
    """Captures every `collect.record(kind, data)` call as `{"kind": ..,
    "data": ..}` while still writing through to the real (tmp-rooted)
    metrics store, so both the capture list and `collect.read` agree."""
    events: list[dict] = []
    original_record = collect.record

    def _capture(kind, data):
        events.append({"kind": kind, "data": data})
        return original_record(kind, data)

    monkeypatch.setattr(collect, "record", _capture)
    return events


class TestReleasePageAuditTrail:
    def test_release_page_records_metric_with_via(
        self, wiki_with_quarantined_page, recorded_metrics
    ):
        rel = wiki_with_quarantined_page
        wiki_health.release_page(
            rel, "sess-t3", via="suggestion-accepted",
            evidence={"judge": {"confidence": 0.9}},
        )
        events = [e for e in recorded_metrics if e["kind"] == collect.KIND_QUARANTINE_RELEASE]
        assert len(events) == 1
        assert events[0]["data"]["via"] == "suggestion-accepted"
        assert events[0]["data"]["evidence"] == {"judge": {"confidence": 0.9}}

    def test_release_page_default_via_is_human_direct(
        self, wiki_with_quarantined_page, recorded_metrics
    ):
        rel = wiki_with_quarantined_page
        wiki_health.release_page(rel, "sess-t3")
        events = [e for e in recorded_metrics if e["kind"] == collect.KIND_QUARANTINE_RELEASE]
        assert len(events) == 1
        assert events[0]["data"]["via"] == "human-direct"
        assert events[0]["data"]["evidence"] == {}

    def test_release_page_auto_metric_carries_via_machine(
        self, wiki_with_quarantined_page, recorded_metrics
    ):
        rel = wiki_with_quarantined_page
        wiki_health.release_page_auto(rel, "sess-t3", {"judge": {"confidence": 0.9, "reason": "r"}})
        events = [e for e in recorded_metrics if e["kind"] == collect.KIND_QUARANTINE_RELEASE]
        assert len(events) == 1
        assert events[0]["data"]["via"] == "machine"

    def test_release_page_held_on_contradicts_records_no_metric(
        self, wiki_with_quarantined_page, recorded_metrics, monkeypatch
    ):
        rel = wiki_with_quarantined_page

        class _FakeSemantics:
            @staticmethod
            def detect(op, page, content, wiki_root, exempt_pages=None):
                return [_FakeConflict(kind="contradicts", page=page, write_id="w-old-1", evidence="stub")]

        monkeypatch.setattr(queue_mod, "_semantics", _FakeSemantics)

        entry, prov = wiki_health.release_page(rel, "sess-t3")
        assert prov is None
        events = [e for e in recorded_metrics if e["kind"] == collect.KIND_QUARANTINE_RELEASE]
        assert events == []
