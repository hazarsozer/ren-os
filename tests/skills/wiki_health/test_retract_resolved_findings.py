"""
Tests for the wiki-health lint's retraction pass (spec 2026-08-21 §3.4).

A lint finding is VERIFIABLE — unlike a judgment call, you can re-check
whether it still holds. This pass does that, so a finding fixed by any other
means self-closes instead of sitting pending for the 30-day expiry.

Run with: uv run pytest tests/skills/wiki_health/test_retract_resolved_findings.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.suggestions import SuggestionSpec, pending_suggestions, record
from lib.ren_paths import wiki_root

lint = importlib.import_module("skills.wiki-health.lib.lint")


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _file_finding(page: str, rule: str = "missing-frontmatter-type"):
    return record(SuggestionSpec(
        producer="wiki-health",
        title=f"Wiki lint: {rule} in {page}",
        rationale="page has no frontmatter `type:`",
        evidence={"page": page, "rule": rule, "detail": "d"},
        kind="structured_action",
        payload={"action": "review_lint_finding", "page": page, "rule": rule, "detail": "d"},
        fingerprint=f"wiki-lint:{page}:{rule}",
    ))


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_fixed_page_retracts_its_finding(wiki):
    _write(wiki, "lessons/a.md", "---\ntype: lesson\n---\n# A\n")
    entry = _file_finding("lessons/a.md")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] not in {e["sid"] for e in pending_suggestions()}


def test_unfixed_page_keeps_its_finding_pending(wiki):
    _write(wiki, "lessons/b.md", "# B\n")
    entry = _file_finding("lessons/b.md")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] in {e["sid"] for e in pending_suggestions()}


def test_deleted_page_retracts_its_finding(wiki):
    entry = _file_finding("lessons/gone.md")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] not in {e["sid"] for e in pending_suggestions()}


def test_non_lint_suggestions_are_left_alone(wiki):
    entry = record(SuggestionSpec(
        producer="wrap",
        title="Place durable item",
        rationale="unplaceable",
        evidence={},
        kind="structured_action",
        payload={"action": "place_durable_item", "item": "x", "session": "s"},
        fingerprint="wrap-unplaced:s:0",
    ))

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] in {e["sid"] for e in pending_suggestions()}
