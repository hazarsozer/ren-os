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

from lib.suggestions import SuggestionSpec, all_suggestions, pending_suggestions, record
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


def test_malformed_path_retracts_with_honest_reason(wiki):
    """A `PathTraversalError` on a finding's `page` is a wrongly-shaped path,
    not a missing page — `"page <p> no longer exists"` would be a false
    statement about it. It must still retract (a finding recorded against a
    path this shape can never be re-checked), but with an honest reason
    (doctrine review finding 5, 2026-08-21)."""
    entry = _file_finding("../../etc/passwd")

    lint._retract_resolved_findings(wiki)

    resolved = next(e for e in all_suggestions() if e["sid"] == entry["sid"])
    assert resolved["status"] == "resolved"
    assert "no longer exists" not in resolved["resolved_reason"]
    assert "not a valid wiki-relative path" in resolved["resolved_reason"]


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


def test_archived_duplicate_basename_does_not_falsely_retract_dangling_link(wiki):
    """Regression (fix round 1): the retraction walk's `all_pages` must
    mirror the production detection walk's `skip_archive=True`, or a page
    later moved into `archive/` with a matching basename counts as a valid
    unique resolution target during retraction even though production
    detection — which excludes `archive/` — would never accept it. That let
    a still-broken `dangling-link` finding vanish from the pending queue
    while the link on the unchanged page was still broken."""
    _write(wiki, "lessons/a.md", "# A\n\nsee [[foo]]\n")

    result = lint.run_incremental_lint(session="s-1", full=True)
    pend = pending_suggestions()
    assert any(
        s["payload"]["rule"] == "dangling-link" and s["payload"]["page"] == "lessons/a.md"
        for s in pend
    ), result
    entry = next(
        s for s in pend
        if s["payload"]["rule"] == "dangling-link" and s["payload"]["page"] == "lessons/a.md"
    )

    # A same-basename page later lands under archive/ — production detection
    # excludes archive/ from its match pool, so the link is STILL dangling.
    _write(wiki, "archive/foo.md", "# Foo (archived)\n")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] in {e["sid"] for e in pending_suggestions()}


def test_held_finding_stays_pending(wiki):
    """A `held:<cls>` finding names a fix the write queue held — it is not a
    rule `_lint_page()` can ever emit, so the pass must never treat its
    absence from a fresh `_lint_page()` call as "resolved" (finding 1,
    2026-08-21 whole-branch review)."""
    _write(wiki, "lessons/held.md", "---\ntype: lesson\n---\n# Held\n")
    entry = _file_finding("lessons/held.md", rule="held:hub-missing-entry")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] in {e["sid"] for e in pending_suggestions()}


def test_blocked_finding_stays_pending(wiki):
    """A `blocked:<cls>` finding names a fix class on a page the lint may not
    write — same non-re-checkable shape as `held:`."""
    _write(wiki, "lessons/blocked.md", "---\ntype: lesson\n---\n# Blocked\n")
    entry = _file_finding("lessons/blocked.md", rule="blocked:dangling-link-repointed")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] in {e["sid"] for e in pending_suggestions()}


def test_retired_rule_finding_stays_pending(wiki):
    """A finding for a rule `_lint_page()` no longer emits (e.g. a retired
    rule like `map-pointer-missing`) must stay pending — its absence from
    fresh judgments proves nothing about whether it still holds."""
    _write(wiki, "lessons/retired.md", "---\ntype: lesson\n---\n# Retired\n")
    entry = _file_finding("lessons/retired.md", rule="map-pointer-missing")

    lint._retract_resolved_findings(wiki)

    assert entry["sid"] in {e["sid"] for e in pending_suggestions()}
