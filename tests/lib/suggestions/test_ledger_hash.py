"""#52: the durable-decline ledger must carry the declined page's content
hash so the machine exit can distinguish 'same page the human declined'
from 'page changed since the decline'. Passthrough is generic: decide()
copies payload['content_sha256'] to the ledger line when present.

Fixture convention copied from tests/lib/suggestions/test_store.py — every
test redirects ren_paths' framework root to tmp_path via REN_FRAMEWORK_ROOT,
never the real ~/.renos.

Run with: uv run pytest tests/lib/suggestions/test_ledger_hash.py -v
"""

from __future__ import annotations

import pytest

from lib.ren_paths import wiki_root
from lib.suggestions import SuggestionSpec, decide, ledger_entries, record


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def suggestions_store(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _spec(fp, payload):
    return SuggestionSpec(
        producer="wiki-health", title="t", rationale="r", evidence={},
        kind="structured_action", payload=payload, fingerprint=fp,
    )


def test_decline_ledgers_content_hash(suggestions_store):
    entry = record(_spec("quarantine:release:p.md",
                         {"action": "quarantine_release", "page": "p.md",
                          "content_sha256": "abc123"}))
    decide(entry["sid"], "declined")
    lines = [e for e in ledger_entries() if e["fingerprint"] == "quarantine:release:p.md"]
    assert lines[0]["content_sha256"] == "abc123"


def test_decline_without_hash_omits_key(suggestions_store):
    entry = record(_spec("other:fp", {"action": "x"}))
    decide(entry["sid"], "declined")
    lines = [e for e in ledger_entries() if e["fingerprint"] == "other:fp"]
    assert "content_sha256" not in lines[0]
