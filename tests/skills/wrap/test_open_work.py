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


def test_open_line_closes_from_explicit_completed_ptrs(wiki):
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


# --- closure-rule regressions (fix round 1) ----------------------------------


def test_issue_pointer_closes_only_its_own_line(wiki):
    """Regression: `_ptr_target("issue:#7")` is empty (the whole body is a
    fragment), so target-equality matching used to close EVERY issue-pointer
    line at once — the ledger reporting unfinished work as done."""
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] a — ptr:issue:#7 (opened {_days_ago(1)})\n"
        f"- [ ] b — ptr:issue:#42 (opened {_days_ago(1)})\n"
        f"- [ ] c — ptr:issue:#99 (opened {_days_ago(1)})\n\n"
        "## Archive\n",
    )

    result = reconcile_open_work("sess-issue", PROJECT, completed_ptrs=["issue:#7"])

    assert result["closed"] == ["issue:#7"]
    text = _page(wiki).read_text(encoding="utf-8")
    assert "- [x] a — ptr:issue:#7" in text
    assert f"- [ ] b — ptr:issue:#42 (opened {_days_ago(1)})" in text
    assert f"- [ ] c — ptr:issue:#99 (opened {_days_ago(1)})" in text


def test_completed_task_does_not_close_sibling_task_in_same_plan(wiki):
    """Regression: `plan:docs/p.md#task-3` and `#task-9` share a target file;
    the fragment is load-bearing and must not be dropped when matching."""
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] three — ptr:plan:docs/p.md#task-3 (opened {_days_ago(1)})\n"
        f"- [ ] nine — ptr:plan:docs/p.md#task-9 (opened {_days_ago(1)})\n"
        f"- [ ] sec two — ptr:spec:x.md§2 (opened {_days_ago(1)})\n"
        f"- [ ] sec five — ptr:spec:x.md§5 (opened {_days_ago(1)})\n\n"
        "## Archive\n",
    )

    result = reconcile_open_work(
        "sess-frag", PROJECT, completed_ptrs=["plan:docs/p.md#task-3", "spec:x.md§2"]
    )

    assert sorted(result["closed"]) == ["plan:docs/p.md#task-3", "spec:x.md§2"]
    text = _page(wiki).read_text(encoding="utf-8")
    assert f"- [ ] nine — ptr:plan:docs/p.md#task-9 (opened {_days_ago(1)})" in text
    assert f"- [ ] sec five — ptr:spec:x.md§5 (opened {_days_ago(1)})" in text


def test_page_write_never_closes_a_fragment_pointer(wiki):
    """A file write is not evidence that a specific task INSIDE that file is
    done — the `written_pages` channel only closes fragment-less pointers."""
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] whole page — ptr:spec:projects/{PROJECT}/knowledge/y.md (opened {_days_ago(1)})\n"
        f"- [ ] one section — ptr:spec:projects/{PROJECT}/knowledge/y.md§3 (opened {_days_ago(1)})\n\n"
        "## Archive\n",
    )

    from lib.memory.queue import Proposal, propose_and_apply

    propose_and_apply(
        Proposal(
            op="ADD",
            page=f"projects/{PROJECT}/knowledge/y.md",
            content="---\ntitle: y\n---\n\nsome knowledge\n",
            reason="test write",
            producer="wrap",
            writer="llm-auto",
            session="sess-frag2",
        )
    )

    result = reconcile_open_work("sess-frag2", PROJECT)

    assert result["closed"] == [f"spec:projects/{PROJECT}/knowledge/y.md"]
    text = _page(wiki).read_text(encoding="utf-8")
    assert f"- [ ] one section — ptr:spec:projects/{PROJECT}/knowledge/y.md§3" in text


def test_bare_target_in_completed_ptrs_still_closes_fragmentless_line(wiki):
    """Callers may pass a bare path instead of a schemed pointer; that still
    closes a fragment-less line."""
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] whole page — ptr:spec:docs/z.md (opened {_days_ago(1)})\n\n"
        "## Archive\n",
    )

    result = reconcile_open_work("sess-bare", PROJECT, completed_ptrs=["docs/z.md"])

    assert result["closed"] == ["spec:docs/z.md"]


# --- FINAL REVIEW 2: automated writers must not close open work -------------


def _write(session: str, page: str, producer: str, writer: str) -> None:
    from lib.memory.queue import Proposal, propose_and_apply

    propose_and_apply(
        Proposal(
            op="ADD",
            page=page,
            content="---\ntitle: x\n---\n\nbody\n",
            reason="test write",
            producer=producer,
            writer=writer,
            session=session,
        )
    )


def test_routine_lint_write_does_not_close_an_open_line(wiki):
    """`ren-wiki-lint` writes with producer="routine", writer="routine" on
    EVERY session (0.6.5 wrap step 7). A lint touching a page is not evidence
    that the human's work on that page is done."""
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] rewrite the psychology page — ptr:spec:projects/{PROJECT}/knowledge/psy.md "
        f"(opened {_days_ago(2)})\n\n"
        "## Archive\n",
    )
    _write("sess-routine", f"projects/{PROJECT}/knowledge/psy.md", "routine", "routine")

    result = reconcile_open_work("sess-routine", PROJECT)

    assert result["closed"] == []
    assert result["carried"] == 1
    text = _page(wiki).read_text(encoding="utf-8")
    assert "- [ ] rewrite the psychology page" in text


def test_wrap_overview_write_does_not_close_an_overview_pointer(wiki):
    """`maintain_overview` writes the overview unconditionally whenever it
    materially changed — which must not tick off "rewrite the overview"."""
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] rewrite the overview — ptr:spec:projects/{PROJECT}/overview.md "
        f"(opened {_days_ago(2)})\n\n"
        "## Archive\n",
    )
    _write("sess-ov", f"projects/{PROJECT}/overview.md", "wrap", "llm-auto")

    result = reconcile_open_work("sess-ov", PROJECT)

    assert result["closed"] == []
    text = _page(wiki).read_text(encoding="utf-8")
    assert "- [ ] rewrite the overview" in text


def test_wrap_l1_write_does_not_close_an_l1_pointer(wiki):
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] revisit the narrative — ptr:spec:projects/{PROJECT}/l1/session-sess-l1.md "
        f"(opened {_days_ago(2)})\n\n"
        "## Archive\n",
    )
    _write("sess-l1", f"projects/{PROJECT}/l1/session-sess-l1.md", "wrap", "llm-auto")

    result = reconcile_open_work("sess-l1", PROJECT)

    assert result["closed"] == []


def test_ledgers_own_write_does_not_close_a_ledger_pointer(wiki):
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] prune the ledger — ptr:spec:projects/{PROJECT}/open-work.md "
        f"(opened {_days_ago(2)})\n\n"
        "## Archive\n",
    )
    _write("sess-ow2", f"projects/{PROJECT}/open-work.md", "wrap", "llm-auto")

    result = reconcile_open_work("sess-ow2", PROJECT)

    assert result["closed"] == []


def test_genuine_session_write_still_closes(wiki):
    """The channel must stay useful: a real session write to the pointed-at
    knowledge page still closes the line."""
    _write_ledger(
        wiki,
        "## Open\n\n"
        f"- [ ] draft the knowledge page — ptr:spec:projects/{PROJECT}/knowledge/z.md "
        f"(opened {_days_ago(2)})\n\n"
        "## Archive\n",
    )
    _write("sess-real", f"projects/{PROJECT}/knowledge/z.md", "wrap", "llm-auto")

    result = reconcile_open_work("sess-real", PROJECT)

    assert result["closed"] == [f"spec:projects/{PROJECT}/knowledge/z.md"]
