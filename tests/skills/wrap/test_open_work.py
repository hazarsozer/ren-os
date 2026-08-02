"""
Tests for skills.wrap.lib.reconcile_open_work — the open-work ledger
(0.6.5 Task 6, M3 pointer/cursor shape).

Core invariant under test: the reconciler NEVER deletes a line. Closed lines
older than the archive window MOVE to `## Archive` intact; a line the regex
can't parse is carried through verbatim rather than dropped.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/wrap/test_open_work.py -v
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import yaml

from lib.ren_paths import wiki_root
from skills.wrap.lib import reconcile_open_work, wrap_session

PROJECT = "demo-project"


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in (
        "REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT",
        "CLAUDE_PLUGIN_OPTION_DEVROOT",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _page(wiki, project: str = PROJECT):
    return wiki / "projects" / project / "open-work.md"


def _write_ledger(wiki, body: str, project: str = PROJECT) -> None:
    path = _page(wiki, project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        'title: "Open work"\n'
        "type: open-work\n"
        "schema_version: 1\n"
        f"project: {project}\n"
        'framework_version: "0.6.5"\n'
        "created: 2026-01-01\n"
        "updated: 2026-01-01\n"
        "---\n\n" + body,
        encoding="utf-8",
    )


def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    end = text.find("\n---", 3)
    assert end != -1
    return yaml.safe_load(text[3:end])


# --- (a) creation ------------------------------------------------------------


def test_reconcile_creates_page_with_correct_frontmatter(wiki):
    page = _page(wiki)
    assert not page.exists()

    result = reconcile_open_work(
        "sess-1", PROJECT, open_threads=[{"desc": "wire the loader", "ptr": "issue:#42"}]
    )

    assert page.is_file(), "reconcile must create the ledger page via the queue"
    text = page.read_text(encoding="utf-8")
    fm = _frontmatter(text)
    assert fm["type"] == "open-work"
    assert fm["schema_version"] == 1
    assert fm["project"] == PROJECT
    # Written through the queue → provenance stamped by write_apply.
    assert "ren_write_id" in fm
    assert "## Open" in text and "## Archive" in text
    assert result["opened"] == ["issue:#42"]


# --- (b) closure from session queue entries -----------------------------------


def test_open_line_closes_when_session_wrote_its_ptr_target(wiki):
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] finish the map — ptr:spec:projects/{PROJECT}/map.md§2 (opened {_days_ago(3)})\n"
        f"- [ ] untouched thing — ptr:issue:#7 (opened {_days_ago(3)})\n\n"
        "## Archive\n",
    )

    # A real wrap: the durable item lands on the page the first ptr targets.
    wrap_session(
        "narrative",
        [],
        "sess-close",
        project=PROJECT,
    )
    # The queue write the ptr points at (L1 page of this session is not it) —
    # so drive closure through the explicit completed_ptrs channel too.
    result = reconcile_open_work(
        "sess-close",
        PROJECT,
        completed_ptrs=[f"spec:projects/{PROJECT}/map.md§2"],
    )

    text = _page(wiki).read_text(encoding="utf-8")
    assert f"- [x] finish the map — ptr:spec:projects/{PROJECT}/map.md§2 (opened {_days_ago(3)}, closed {_today()})" in text
    assert f"- [ ] untouched thing — ptr:issue:#7 (opened {_days_ago(3)})" in text
    assert result["closed"] == [f"spec:projects/{PROJECT}/map.md§2"]
    assert result["carried"] == 1


def test_open_line_closes_from_session_queue_page_write(wiki):
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] draft the knowledge page — ptr:spec:projects/{PROJECT}/knowledge/x.md (opened {_days_ago(2)})\n\n"
        "## Archive\n",
    )

    from lib.memory.queue import Proposal, propose_and_apply

    propose_and_apply(
        Proposal(
            op="ADD",
            page=f"projects/{PROJECT}/knowledge/x.md",
            content="---\ntitle: x\n---\n\nsome knowledge\n",
            reason="test write",
            producer="wrap",
            writer="llm-auto",
            session="sess-q",
        )
    )

    result = reconcile_open_work("sess-q", PROJECT)

    assert result["closed"] == [f"spec:projects/{PROJECT}/knowledge/x.md"]
    text = _page(wiki).read_text(encoding="utf-8")
    assert "- [x] draft the knowledge page" in text
    assert f"closed {_today()}" in text


# --- (c) new threads appended -------------------------------------------------


def test_new_open_threads_are_appended_as_open_lines(wiki):
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] existing — ptr:issue:#1 (opened {_days_ago(1)})\n\n"
        "## Archive\n",
    )

    result = reconcile_open_work(
        "sess-2",
        PROJECT,
        open_threads=[
            {"desc": "new thread", "ptr": "plan:docs/plans/p.md#task-3"},
            {"desc": "duplicate of existing", "ptr": "issue:#1"},
        ],
    )

    text = _page(wiki).read_text(encoding="utf-8")
    assert f"- [ ] new thread — ptr:plan:docs/plans/p.md#task-3 (opened {_today()})" in text
    # An already-open ptr is not duplicated.
    assert text.count("ptr:issue:#1") == 1
    assert result["opened"] == ["plan:docs/plans/p.md#task-3"]


# --- (d) carried verbatim ------------------------------------------------------


def test_untouched_and_unparseable_lines_are_carried_verbatim(wiki):
    weird = "- [ ] a line the regex cannot parse (no pointer at all)"
    note = "Some freeform note a human typed here."
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"{note}\n"
        f"{weird}\n"
        f"- [ ] real item — ptr:issue:#9 (opened {_days_ago(1)})\n\n"
        "## Archive\n",
    )

    reconcile_open_work("sess-3", PROJECT)

    text = _page(wiki).read_text(encoding="utf-8")
    assert weird in text, "an unparseable line must be carried through, never dropped"
    assert note in text
    assert f"- [ ] real item — ptr:issue:#9 (opened {_days_ago(1)})" in text


# --- (e) NO line is ever deleted ------------------------------------------------


def test_old_closed_line_moves_to_archive_intact_and_is_never_deleted(wiki):
    old_closed = (
        f"- [x] ancient work — ptr:issue:#2 (opened {_days_ago(40)}, closed {_days_ago(20)})"
    )
    recent_closed = (
        f"- [x] recent work — ptr:issue:#3 (opened {_days_ago(5)}, closed {_days_ago(2)})"
    )
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"{old_closed}\n"
        f"{recent_closed}\n"
        f"- [ ] still open — ptr:issue:#4 (opened {_days_ago(1)})\n\n"
        "## Archive\n",
    )

    reconcile_open_work("sess-4", PROJECT)

    text = _page(wiki).read_text(encoding="utf-8")
    assert old_closed in text, "an archived line must survive verbatim"
    assert recent_closed in text
    open_block = text.split("## Archive")[0]
    archive_block = text.split("## Archive")[1]
    assert old_closed in archive_block, "closed >14d ago belongs under ## Archive"
    assert old_closed not in open_block
    assert recent_closed in open_block, "closed inside the window stays under ## Open"
    assert "- [ ] still open — ptr:issue:#4" in open_block


# --- (f) failure never breaks wrap ---------------------------------------------


def test_reconcile_failure_never_breaks_wrap_session(wiki, monkeypatch):
    import skills.wrap.lib as wrap_lib

    def boom(*args, **kwargs):
        raise RuntimeError("ledger exploded")

    monkeypatch.setattr(wrap_lib, "reconcile_open_work", boom)

    result = wrap_session("narrative", [], "sess-5", project=PROJECT)

    assert result["l1_qid"]
    assert result["open_work"] == {"closed": [], "opened": [], "carried": 0}


def test_wrap_session_threads_open_work_through(wiki):
    result = wrap_session(
        "narrative",
        [],
        "sess-6",
        project=PROJECT,
        open_threads=[{"desc": "follow up on the drill", "ptr": "issue:#11"}],
    )

    assert result["open_work"]["opened"] == ["issue:#11"]
    assert "- [ ] follow up on the drill — ptr:issue:#11" in _page(wiki).read_text(encoding="utf-8")


def test_wrap_session_signature_is_backward_compatible(wiki):
    """Existing callers pass no open_threads/completed_ptrs at all."""
    result = wrap_session("narrative", [], "sess-7", project=PROJECT)
    assert result["open_work"] == {"closed": [], "opened": [], "carried": 0}
