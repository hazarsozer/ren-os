"""
Tests for skills.suggestions.lib's `promote_to_project` structured-action
branch (#63) — an accepted /ren:suggestions promotion completes the
instruction-plane hold immediately, same reasoning as pin's
`_complete_if_held`: acceptance IS the human approval.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/suggestions/test_promote_to_project_action.py -v
"""

from __future__ import annotations

import pytest

from lib.ren_paths import wiki_root
from lib.suggestions import SuggestionSpec, record
from skills.suggestions.lib import accept


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


def test_accept_promote_to_project_writes_rule_and_applies(wiki):
    entry = record(
        SuggestionSpec(
            producer="retrospective",
            title="Promote rule to projects/flux/instructions.md",
            rationale="repeated correction across sessions",
            evidence={"count": 3},
            kind="structured_action",
            payload={"action": "promote_to_project", "text": "Never touch the vendored parser.", "slug": "flux"},
            fingerprint="promotion:project:flux:1",
        )
    )

    result = accept(entry["sid"], "s-test")

    assert result["applied"] is True
    page = wiki / "projects/flux/instructions.md"
    assert page.exists()
    assert "- Never touch the vendored parser." in page.read_text(encoding="utf-8")
    assert result["decision_recorded"] is True


def test_accept_promote_to_project_held_on_contradicts_not_applied(wiki, monkeypatch):
    import lib.memory.promotion as promotion_module

    class _FakeEntry:
        def __init__(self):
            self.qid = "q-fake"
            self.status = "pending"
            self.conflicts = [{"kind": "contradicts", "page": "projects/flux/instructions.md"}]

    def _fake_promote_to_project(text, slug, session):
        return _FakeEntry()

    monkeypatch.setattr(promotion_module, "promote_to_project", _fake_promote_to_project)

    entry = record(
        SuggestionSpec(
            producer="retrospective",
            title="Promote rule to projects/flux/instructions.md",
            rationale="repeated correction across sessions",
            evidence={},
            kind="structured_action",
            payload={"action": "promote_to_project", "text": "Some rule.", "slug": "flux"},
            fingerprint="promotion:project:flux:2",
        )
    )

    result = accept(entry["sid"], "s-test")

    assert result["applied"] is False
    assert result["detail"]["status"] == "pending"
    assert result["detail"]["held_on"][0]["kind"] == "contradicts"
