"""
Tests for lib.suggestions — the 0.4.2 durable suggestion store (Task 14).

Suggestions are RARE AND HIGH-STAKES by design (spec §1.2): record dedups on
fingerprint against BOTH pending and decided suggestions so a declined
suggestion never re-nags. decide() is a pure state transition — it does not
apply anything.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/lib/suggestions/test_store.py -v
"""

from __future__ import annotations

import json

import pytest

from lib.ren_paths import state_dir, wiki_root
from lib.suggestions import SuggestionSpec, decide, decided_fingerprints, pending_suggestions, record


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


def _spec(**overrides):
    defaults = dict(
        producer="retrospective",
        title="Consider promoting X",
        rationale="you did X in 4 of the last 5 sessions",
        evidence={"count": 4, "of": 5},
        kind="structured_action",
        payload={"action": "promote", "target": "X"},
        fingerprint="fp-1",
    )
    defaults.update(overrides)
    return SuggestionSpec(**defaults)


def test_record_then_pending_roundtrip(wiki):
    created = record(_spec())
    assert created is not None
    assert created["sid"].startswith("s-")
    assert created["status"] == "pending"

    pending = pending_suggestions()
    assert len(pending) == 1
    assert pending[0]["sid"] == created["sid"]
    assert pending[0]["fingerprint"] == "fp-1"


def test_duplicate_fingerprint_against_pending_returns_none(wiki):
    first = record(_spec(fingerprint="fp-dup"))
    assert first is not None
    second = record(_spec(fingerprint="fp-dup", title="different title"))
    assert second is None
    assert len(pending_suggestions()) == 1


def test_duplicate_fingerprint_against_declined_returns_none(wiki):
    created = record(_spec(fingerprint="fp-declined"))
    decide(created["sid"], "declined")
    assert len(pending_suggestions()) == 0

    again = record(_spec(fingerprint="fp-declined"))
    assert again is None


def test_decide_accepted_transitions_and_persists(wiki):
    created = record(_spec(fingerprint="fp-accept"))
    result = decide(created["sid"], "accepted")
    assert result["status"] == "accepted"
    assert len(pending_suggestions()) == 0

    path = state_dir() / "suggestions" / f"{created['sid']}.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["status"] == "accepted"
    assert "fp-accept" in decided_fingerprints()


def test_decide_unknown_sid_raises_keyerror(wiki):
    with pytest.raises(KeyError):
        decide("s-does-not-exist", "accepted")


def test_decide_invalid_decision_raises_valueerror(wiki):
    created = record(_spec(fingerprint="fp-invalid"))
    with pytest.raises(ValueError):
        decide(created["sid"], "maybe")


def test_pending_suggestions_skips_corrupt_file(wiki, capsys):
    record(_spec(fingerprint="fp-good"))
    corrupt = state_dir() / "suggestions" / "s-corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")

    pending = pending_suggestions()
    assert len(pending) == 1
    assert pending[0]["fingerprint"] == "fp-good"
    assert "s-corrupt.json" in capsys.readouterr().err


def test_decide_appends_to_decision_ledger(wiki):
    entry = record(_spec(fingerprint="fp:ledger-1"))
    decide(entry["sid"], "declined")
    ledger = state_dir() / "suggestions" / "decisions.jsonl"
    lines = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert lines[-1]["fingerprint"] == "fp:ledger-1"
    assert lines[-1]["decision"] == "declined"


def test_ledger_backfills_from_existing_decided_entries(wiki):
    entry = record(_spec(fingerprint="fp:old-world"))
    decide(entry["sid"], "accepted")
    (state_dir() / "suggestions" / "decisions.jsonl").unlink()  # simulate pre-0.5.0 store

    from lib.suggestions import ledger_fingerprints
    assert "fp:old-world" in ledger_fingerprints()


def test_record_dedups_via_ledger_even_after_entry_file_removed(wiki):
    entry = record(_spec(fingerprint="fp:pruned"))
    decide(entry["sid"], "declined")
    (state_dir() / "suggestions" / f"{entry['sid']}.json").unlink()  # entry file gone, ledger remains
    assert record(_spec(fingerprint="fp:pruned")) is None
