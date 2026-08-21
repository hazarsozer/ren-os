"""
Tests for lib.suggestions.retract — closing a finding that no longer holds
(spec 2026-08-21 §3.3).

The load-bearing test here is `test_retract_does_not_ledger_the_fingerprint`.
Retraction models `expire_stale_pending`, NOT `decide`: decide() ledgers, and
record() refuses any ledgered fingerprint, so retracting via decide would
permanently deafen the producer for that fingerprint.

Run with: uv run pytest tests/lib/suggestions/test_retract.py -v
"""

from __future__ import annotations

import pytest

from lib import suggestions
from lib.suggestions import (
    SuggestionSpec,
    ledger_fingerprints,
    pending_suggestions,
    record,
    retract,
)
from lib.ren_paths import wiki_root


@pytest.fixture
def store(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    wiki_root().mkdir(parents=True, exist_ok=True)
    return tmp_path


def _spec(fingerprint="wiki-lint:lessons/a.md:missing-frontmatter-type"):
    return SuggestionSpec(
        producer="wiki-health",
        title="Wiki lint: missing-frontmatter-type in lessons/a.md",
        rationale="page has no frontmatter `type:`",
        evidence={"page": "lessons/a.md", "rule": "missing-frontmatter-type"},
        kind="structured_action",
        payload={"action": "review_lint_finding", "page": "lessons/a.md",
                 "rule": "missing-frontmatter-type"},
        fingerprint=fingerprint,
    )


def test_retract_sets_resolved_status(store):
    entry = record(_spec())
    result = retract(entry["sid"], "type: is now present")

    assert result["status"] == "resolved"
    assert result["resolved_reason"] == "type: is now present"
    assert result["resolved_at"] is not None


def test_retracted_entry_leaves_pending(store):
    entry = record(_spec())
    retract(entry["sid"], "fixed")

    assert entry["sid"] not in {e["sid"] for e in pending_suggestions()}


def test_retract_does_not_ledger_the_fingerprint(store):
    """The whole point. A retracted finding must be able to fire again."""
    entry = record(_spec())
    retract(entry["sid"], "fixed")

    assert _spec().fingerprint not in ledger_fingerprints()

    again = record(_spec())
    assert again is not None
    assert again["sid"] != entry["sid"]


def test_retract_refuses_a_non_pending_entry(store):
    entry = record(_spec())
    retract(entry["sid"], "fixed")

    with pytest.raises(ValueError):
        retract(entry["sid"], "again")


def test_retract_raises_keyerror_for_unknown_sid(store):
    with pytest.raises(KeyError):
        retract("s-nope", "fixed")


def test_prune_decided_sweeps_resolved_files(store):
    entry = record(_spec())
    retract(entry["sid"], "fixed")

    # Backdate so it falls outside the retention window.
    stored = suggestions._load(entry["sid"])
    stored["resolved_at"] = "2020-01-01T00:00:00Z"
    suggestions._persist(stored)

    assert suggestions.prune_decided() >= 1
    assert not suggestions._suggestion_path(entry["sid"]).exists()
