"""
Tests for Task 3 (#51): audit trail on every quarantine release path.

Every completed release — human-direct (`release_page`), machine
(`release_page_auto`), and suggestion-accepted (routed through
`skills.suggestions.lib`) — must record a `KIND_QUARANTINE_RELEASE`
metric carrying `via` and `evidence`.

Fixture convention copied from tests/skills/wiki_health/test_quarantine_screen.py
(itself copied from tests/skills/wiki_health/test_release.py) — no shared
isolated_wiki fixture exists in this codebase.

Run with: uv run pytest tests/skills/wiki_health/test_release_audit.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.instrument import collect
from lib.memory import quarantine
from lib.ren_paths import wiki_root

wiki_health = importlib.import_module("skills.wiki-health.lib")


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
