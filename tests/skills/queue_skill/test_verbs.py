"""
Tests for skills.queue.lib — thin presentation verbs over lib.memory.queue
and lib.memory.revert (Task 8.3b).

Run with: uv run pytest tests/skills/queue_skill/test_verbs.py -v
"""

from __future__ import annotations

import importlib

import pytest

from lib.memory.queue import Proposal, propose
from lib.ren_paths import wiki_root

queue_skill = importlib.import_module("skills.queue.lib")


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT", "CLAUDE_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proposal(**overrides):
    defaults = dict(
        op="ADD", page="projects/x/notes.md", content="hello", reason="test",
        producer="pin", writer="human", session="s",
    )
    defaults.update(overrides)
    return Proposal(**defaults)


# --------------------------------------------------------------------- review


def test_review_empty_queue():
    result = queue_skill.review()
    assert "No pending" in result


def test_review_renders_pending_entries(wiki):
    entry = propose(_proposal(page="projects/x/a.md"))
    result = queue_skill.review()
    assert entry.qid in result
    assert "ADD" in result
    assert "projects/x/a.md" in result


def test_review_renders_salience_flag(wiki):
    entry = propose(_proposal(page="projects/x/pinned.md", salience=True))
    result = queue_skill.review()
    assert "[salient]" in result


def test_review_renders_conflicts(wiki, monkeypatch):
    from dataclasses import dataclass

    from lib.memory import queue as queue_module

    @dataclass(frozen=True)
    class _FakeConflict:
        kind: str
        page: str
        write_id: str
        evidence: str

    class _FakeSemantics:
        @staticmethod
        def detect(op, page, content, wiki_root):
            return [_FakeConflict(kind="contradicts", page="projects/x/other.md", write_id="w-1", evidence="stub evidence")]

    monkeypatch.setattr(queue_module, "_semantics", _FakeSemantics)
    propose(_proposal(page="projects/x/conflicted.md"))

    result = queue_skill.review()
    assert "contradicts" in result
    assert "stub evidence" in result


# ---------------------------------------------------------------- approve_and_apply


def test_approve_and_apply_round_trip(wiki):
    entry = propose(_proposal(page="projects/x/approve-me.md", content="content to land"))
    result = queue_skill.approve_and_apply(entry.qid, who="hazar", session="sess-1")

    assert "Applied" in result
    assert entry.qid in result
    page_abs = wiki / "projects" / "x" / "approve-me.md"
    assert page_abs.exists()
    assert "content to land" in page_abs.read_text(encoding="utf-8")


def test_approve_and_apply_unknown_qid_returns_friendly_error(wiki):
    result = queue_skill.approve_and_apply("q-does-not-exist", who="hazar", session="s")
    assert "No such queue entry" in result
    assert "Traceback" not in result


def test_approve_and_apply_twice_returns_friendly_error(wiki):
    entry = propose(_proposal(page="projects/x/double.md"))
    queue_skill.approve_and_apply(entry.qid, who="hazar", session="s")
    result = queue_skill.approve_and_apply(entry.qid, who="hazar", session="s")
    assert "Could not approve/apply" in result


# ------------------------------------------------------------- reject_with_reason


def test_reject_with_reason(wiki):
    entry = propose(_proposal(page="projects/x/reject-me.md"))
    result = queue_skill.reject_with_reason(entry.qid, "not needed")
    assert "Rejected" in result
    assert "not needed" in result


def test_reject_unknown_qid_returns_friendly_error(wiki):
    result = queue_skill.reject_with_reason("q-nope", "why")
    assert "No such queue entry" in result


# ------------------------------------------------------------------ revert_write


def test_revert_write_returns_confirmation_no_citers(wiki):
    entry = propose(_proposal(page="projects/x/revert-me.md", content="content"))
    queue_skill.approve_and_apply(entry.qid, who="hazar", session="s")

    from lib.memory import queue as queue_module
    reloaded = queue_module.get(entry.qid)

    result = queue_skill.revert_write(reloaded.write_id)
    assert "Reverted" in result
    assert "No other pages cite" in result

    page_abs = wiki / "projects" / "x" / "revert-me.md"
    assert not page_abs.exists()


def test_revert_write_reports_citers(wiki):
    entry = propose(_proposal(page="projects/x/cited.md", content="original"))
    queue_skill.approve_and_apply(entry.qid, who="hazar", session="s")

    from lib.memory import queue as queue_module
    reloaded = queue_module.get(entry.qid)

    citer_page = wiki / "projects" / "x" / "citer.md"
    citer_page.parent.mkdir(parents=True, exist_ok=True)
    citer_page.write_text(f"references write {reloaded.write_id} directly", encoding="utf-8")

    result = queue_skill.revert_write(reloaded.write_id)
    assert "cite this write" in result
    assert "citer.md" in result


def test_revert_write_unknown_write_id_returns_friendly_error(wiki):
    result = queue_skill.revert_write("w-does-not-exist")
    assert "No such write_id" in result
    assert "Traceback" not in result
