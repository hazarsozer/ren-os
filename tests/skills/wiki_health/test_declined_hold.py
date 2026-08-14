"""
#52: a human decline holds the machine quarantine exit until the page's
content actually changes. Incident: judge nondeterminism re-sampled a
declined, unchanged page during the wrap sweep and released it around the
decline (2026-08-04). `declined_release_holds` is the fail-closed gate that
stops that from happening again.

Fixture convention copied from tests/skills/wiki_health/test_quarantine_screen.py
— no shared isolated_wiki fixture exists in this codebase.

Run with: uv run pytest tests/skills/wiki_health/test_declined_hold.py -v
"""

from __future__ import annotations

import hashlib
import importlib

import pytest

from lib.memory import quarantine
from lib.ren_paths import wiki_root
from lib.suggestions import SuggestionSpec, decide, record

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


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _decline_release(rel, content_sha256=None):
    payload = {"action": "quarantine_release", "page": rel}
    if content_sha256 is not None:
        payload["content_sha256"] = content_sha256
    entry = record(
        SuggestionSpec(
            producer="wiki-health",
            title=f"Release {rel} from quarantine?",
            rationale="test decline",
            evidence={},
            kind="structured_action",
            payload=payload,
            fingerprint=f"quarantine:release:{rel}",
        )
    )
    decide(entry["sid"], "declined")


def _good_verdict(conf=0.95):
    return {"data_only": True, "confidence": conf, "reason": "facts only"}


class TestDeclinedReleaseHolds:
    def test_declined_page_never_machine_releases_while_unchanged(self, wiki):
        body = "## Notes\n- postgres is the store\n"
        rel = _write_page(wiki, "projects/app/knowledge/stack.md", body=body)
        text = (wiki / rel).read_text(encoding="utf-8")
        _decline_release(rel, content_sha256=_sha(text))

        result = wiki_health.run_quarantine_screen("sess-1")
        assert rel in result["held_declined"]
        assert rel not in [c["page"] for c in result["candidates"]]

        result2 = wiki_health.apply_quarantine_verdicts("sess-1", {rel: _good_verdict()})
        assert rel in result2["held_declined"]
        assert result2["released"] == []
        assert quarantine.is_quarantined((wiki / rel).read_text(encoding="utf-8"))

    def test_content_change_lifts_the_hold(self, wiki):
        body = "## Notes\n- postgres is the store\n"
        rel = _write_page(wiki, "projects/app/knowledge/stack.md", body=body)
        text = (wiki / rel).read_text(encoding="utf-8")
        _decline_release(rel, content_sha256=_sha(text))

        # content changes after the decline
        new_body = "## Notes\n- postgres is the store, and redis too\n"
        _write_page(wiki, rel, body=new_body)

        result = wiki_health.run_quarantine_screen("sess-1")
        assert rel not in result["held_declined"]
        assert rel in [c["page"] for c in result["candidates"]]

    def test_decline_after_content_changed_while_pending_still_holds(self, wiki):
        """Final-review finding 2 (2026-08-14) end-to-end: the release
        suggestion is filed (hashing content A), the page changes to content
        B while the suggestion sits pending, and only THEN does the human
        decline. Before the fix, the ledger line carried the stale
        record-time hash of A, `declined_release_holds` found no match for
        B, and the machine exit re-opened for the exact content the human
        just declined. The screen must HOLD."""
        body_a = "## Notes\n- postgres is the store\n"
        rel = _write_page(wiki, "projects/app/knowledge/stack.md", body=body_a)
        text_a = (wiki / rel).read_text(encoding="utf-8")

        # File the suggestion (as `_record_release_suggestion` would) while
        # content A is on disk.
        from lib.suggestions import SuggestionSpec, decide as _decide, record as _record

        entry = _record(
            SuggestionSpec(
                producer="wiki-health",
                title=f"Release {rel} from quarantine?",
                rationale="test decline",
                evidence={},
                kind="structured_action",
                payload={
                    "action": "quarantine_release",
                    "page": rel,
                    "content_sha256": _sha(text_a),
                },
                fingerprint=f"quarantine:release:{rel}",
            )
        )

        # content changes while the suggestion sits pending
        body_b = "## Notes\n- postgres is the store, and redis too\n"
        _write_page(wiki, rel, body=body_b)
        text_b = (wiki / rel).read_text(encoding="utf-8")

        # only now does the human decline
        _decide(entry["sid"], "declined")

        result = wiki_health.run_quarantine_screen("sess-1")
        assert rel in result["held_declined"]
        assert rel not in [c["page"] for c in result["candidates"]]
        assert wiki_health.declined_release_holds(rel, text_b)

    def test_legacy_decline_without_hash_holds_unconditionally(self, wiki):
        body = "## Notes\n- postgres is the store\n"
        rel = _write_page(wiki, "projects/app/knowledge/stack.md", body=body)
        _decline_release(rel)  # no content_sha256 — the pre-train incident shape

        result = wiki_health.run_quarantine_screen("sess-1")
        assert rel in result["held_declined"]
        assert rel not in [c["page"] for c in result["candidates"]]

        # even after content edits, the legacy decline still holds
        new_body = "## Notes\n- postgres is the store, and redis too\n"
        _write_page(wiki, rel, body=new_body)

        result2 = wiki_health.run_quarantine_screen("sess-1")
        assert rel in result2["held_declined"]
        assert rel not in [c["page"] for c in result2["candidates"]]
