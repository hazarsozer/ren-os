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


@pytest.mark.parametrize("decision", ["accepted", "declined"])
def test_retract_refuses_an_already_decided_entry(store, decision):
    """#78: only resolved->resolved was covered. A decided entry is immutable
    and retract must refuse it, or a ledgered decision could be reopened."""
    entry = record(_spec())
    suggestions.decide(entry["sid"], decision)

    with pytest.raises(ValueError):
        retract(entry["sid"], "no longer holds")


def test_retract_refuses_an_expired_entry(store):
    """Expiry is terminal too — the third status decide()'s docstring named
    and retract() has always rejected."""
    entry = record(_spec())

    # Backdate past PENDING_MAX_AGE_DAYS, same idiom as
    # test_prune_decided_sweeps_resolved_files. expire_stale_pending() ages
    # against the entry's `ts` field (set by record()), not `created_at` —
    # there is no `created_at` field on a suggestion entry.
    stored = suggestions._load(entry["sid"])
    stored["ts"] = "2020-01-01T00:00:00Z"
    suggestions._persist(stored)
    suggestions.expire_stale_pending()

    with pytest.raises(ValueError):
        retract(entry["sid"], "no longer holds")


def test_resolved_is_public():
    """The private spelling was exported in __all__ while its siblings were
    not. Renamed rather than exported."""
    assert suggestions.RESOLVED == "resolved"
    assert "RESOLVED" in suggestions.__all__
    assert "_RESOLVED" not in suggestions.__all__
