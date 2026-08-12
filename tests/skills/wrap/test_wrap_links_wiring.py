"""
Tests for #54 Task 2 — wiring `skills.wrap.lib.links`' pure transforms into
the real `wrap_session` write path (D1 touched-pages, D2 log.md entry, D3 map
Sessions section, D4 auto-pointers + index spine) and their surfacing on the
wrap screen.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos. Fixtures mirror
`test_wrap_flow.py`'s `wiki`/`project` fixtures exactly, plus stamp the
handful of founding pages (log.md, project map.md) the link duties read/write.

Run with: uv run pytest tests/skills/wrap/test_wrap_links_wiring.py -v
"""

from __future__ import annotations

import pytest

from lib.memory import queue as _queue
from lib.ren_paths import wiki_root
from skills.wrap.lib import _run_link_duties, render_wrap_screen, wrap_session
import skills.wrap.lib as _wraplib

_MAP_SKELETON = "# demo — knowledge map\n\n## Knowledge\n- nothing yet\n"
_LOG_SKELETON = "# Wiki Log\n\n## [2026-08-01] init | x\n"


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
def wiki_env(clean_path_env, tmp_path):
    """Wiki root with a founding log.md and one project ("demo") whose
    map.md already exists — the shape the link duties expect to find on a
    real, already-bootstrapped wiki."""
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "log.md").write_text(_LOG_SKELETON, encoding="utf-8")
    project_dir = root / "projects" / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "map.md").write_text(_MAP_SKELETON, encoding="utf-8")
    return root


def _run_minimal_wrap(wiki_env, *, project=None, session="s-links"):
    return wrap_session(
        "---\n---\n\n# S\n\nDid some work today.\n",
        [],
        session=session,
        project=project,
    )


# --- result-key contract -----------------------------------------------------


def test_wrap_session_result_has_links_key(wiki_env):
    result = _run_minimal_wrap(wiki_env)
    links = result["links"]
    assert set(links) == {
        "l1_touched", "log_entry", "sessions_entry", "auto_pointers", "warnings",
    }


def test_wrap_session_result_has_links_key_even_without_project(wiki_env):
    """`links` must be present on every return path — not just the
    project-scoped one."""
    result = _run_minimal_wrap(wiki_env, project=None)
    assert "links" in result
    assert set(result["links"]) == {
        "l1_touched", "log_entry", "sessions_entry", "auto_pointers", "warnings",
    }


# --- D2 (log.md) + D3 (map Sessions) -----------------------------------------


def test_wrap_links_l1_into_log_and_map(wiki_env):
    session = "s-links-1"
    result = _run_minimal_wrap(wiki_env, project="demo", session=session)

    log_text = (wiki_env / "log.md").read_text(encoding="utf-8")
    assert f"[session-{session}](projects/demo/l1/session-" in log_text

    map_text = (wiki_env / "projects/demo/map.md").read_text(encoding="utf-8")
    assert "## Sessions" in map_text
    assert f"session-{session}" in map_text

    assert result["links"]["log_entry"] is True
    assert result["links"]["sessions_entry"] is True
    assert result["links"]["warnings"] == []


def test_wrap_held_log_entry_does_not_report_success(wiki_env, monkeypatch):
    """A held write (instruction-plane target, or a `contradicts` conflict —
    `propose_and_apply` returns `(entry, None)` in either case) must NOT be
    reported as a success: the flag stays False, a warning names it, and the
    page on disk is left untouched. Simulated here by making the log.md
    UPDATE hold: `queue.propose` alone (never `apply_auto`) leaves the entry
    pending and the page unwritten, exactly what a real hold looks like."""
    real_propose_and_apply = _wraplib.propose_and_apply

    def _fake(proposal):
        if proposal.page == "log.md":
            entry = _queue.propose(proposal)
            return entry, None
        return real_propose_and_apply(proposal)

    monkeypatch.setattr(_wraplib, "propose_and_apply", _fake)

    result = _run_minimal_wrap(wiki_env, project="demo")

    assert result["links"]["log_entry"] is False
    assert any(
        "log.md" in w and "held" in w for w in result["links"]["warnings"]
    ), result["links"]["warnings"]
    assert (wiki_env / "log.md").read_text(encoding="utf-8") == _LOG_SKELETON
    assert result["l1_qid"]  # wrap still completed normally


def test_wrap_missing_log_md_warns_not_raises(wiki_env):
    (wiki_env / "log.md").unlink()
    result = _run_minimal_wrap(wiki_env, project="demo")
    assert result["links"]["log_entry"] is False
    assert any("log.md" in w for w in result["links"]["warnings"])


def test_wrap_missing_project_map_warns_not_raises(wiki_env):
    (wiki_env / "projects/demo/map.md").unlink()
    result = _run_minimal_wrap(wiki_env, project="demo")
    assert result["links"]["sessions_entry"] is False
    assert any("map.md" in w for w in result["links"]["warnings"])


def test_wrap_no_project_in_scope_skips_map_duties_with_warning(wiki_env):
    result = _run_minimal_wrap(wiki_env, project=None)
    assert result["links"]["sessions_entry"] is False
    assert result["links"]["auto_pointers"] == []
    assert any("no project" in w for w in result["links"]["warnings"])
    # D2 (log.md) is NOT project-scoped, so it still runs:
    assert result["links"]["log_entry"] is True


# --- D1 (touched pages appended to L1) ---------------------------------------


def test_wrap_l1_gains_touched_pages_section_for_applied_durable_items(wiki_env):
    session = "s-links-touched"
    result = wrap_session(
        "---\n---\n\n# S\n\nDid some work.\n",
        ["We decided to standardize on Postgres for order-history joins."],
        session=session,
        project="demo",
        llm_call=lambda prompt: '{"verdict": "durable", "reason": "stub"}',
    )
    assert len(result["applied"]) == 1
    l1_text = (wiki_env / "projects/demo/l1" / f"session-{session}.md").read_text(encoding="utf-8")
    assert "## Touched pages" in l1_text
    page = result["applied"][0]["page"]
    assert page in l1_text
    assert result["links"]["l1_touched"] >= 1


def test_wrap_l1_no_touched_section_when_nothing_else_written(wiki_env):
    # No project in scope means no open-work reconcile write either, so this
    # session's queue holds nothing besides the L1 write itself.
    result = _run_minimal_wrap(wiki_env, project=None)
    assert result["links"]["l1_touched"] == 0


# --- isolation: a link-duty explosion must never fail wrap ------------------


def test_wrap_link_duties_failure_is_isolated(wiki_env, monkeypatch):
    import skills.wrap.lib as wraplib

    def _boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(wraplib, "_run_link_duties", _boom)

    result = _run_minimal_wrap(wiki_env, project="demo")
    assert result["l1_qid"]  # wrap still completed
    assert any("link duties failed" in w for w in result["links"]["warnings"])


# --- D4 (auto-pointers + index spine) ----------------------------------------
#
# None of `wrap_session`'s OWN durable-items loop ever produces a
# `projects/<project>/...` page (durable items always land under the global
# `lessons/` tree, per `_slugify` in this same module) — so `auto_pointers`
# is empty through every `wrap_session`-level test above. `_run_link_duties`
# is exercised directly here to prove the D4 branch itself (a
# project-scoped ADD in `applied`) works, independent of what currently
# feeds it.


def test_run_link_duties_adds_map_pointer_and_index_spine_for_project_page(wiki_env):
    (wiki_env / "index.md").write_text(
        "---\ntype: l2-map\n---\n# Master\n## Decision map\n", encoding="utf-8"
    )
    (wiki_env / "projects/demo/knowledge").mkdir(parents=True)
    (wiki_env / "projects/demo/knowledge/new-fact.md").write_text(
        "# New Fact\nbody\n", encoding="utf-8"
    )

    out = _run_link_duties(
        session="s-d4",
        project="demo",
        l1_page="projects/demo/l1/session-s-d4.md",
        l1_path=wiki_env / "projects/demo/l1/session-s-d4.md",
        applied=[
            {
                "qid": "q1",
                "write_id": "w-01D4",
                "page": "projects/demo/knowledge/new-fact.md",
                "op": "ADD",
            }
        ],
        wiki_root=wiki_env,
    )

    assert out["auto_pointers"] == ["projects/demo/knowledge/new-fact.md"]
    map_text = (wiki_env / "projects/demo/map.md").read_text(encoding="utf-8")
    assert "new-fact.md" in map_text
    index_text = (wiki_env / "index.md").read_text(encoding="utf-8")
    assert "projects/demo/map.md" in index_text


def test_run_link_duties_excludes_non_add_ops_and_reserved_names(wiki_env):
    out = _run_link_duties(
        session="s-d4-excl",
        project="demo",
        l1_page="projects/demo/l1/session-s-d4-excl.md",
        l1_path=wiki_env / "projects/demo/l1/session-s-d4-excl.md",
        applied=[
            {"qid": "q1", "write_id": "w-1", "page": "projects/demo/overview.md", "op": "ADD"},
            {"qid": "q2", "write_id": "w-2", "page": "projects/demo/knowledge/x.md", "op": "UPDATE"},
            {"qid": "q3", "write_id": "w-3", "page": "lessons/not-scoped.md", "op": "ADD"},
        ],
        wiki_root=wiki_env,
    )
    assert out["auto_pointers"] == []


# --- applied entries gain "op" ------------------------------------------------


def test_applied_entries_carry_op(wiki_env):
    result = wrap_session(
        "---\n---\n\n# S\n\nDid some work.\n",
        ["We decided to standardize on Postgres for order-history joins."],
        session="s-op",
        project="demo",
        llm_call=lambda prompt: '{"verdict": "durable", "reason": "stub"}',
    )
    assert len(result["applied"]) == 1
    assert result["applied"][0]["op"] == "ADD"


# --- wrap screen rendering ----------------------------------------------------


def test_wrap_screen_renders_links_summary_line(wiki_env):
    session = "s-links-screen"
    result = _run_minimal_wrap(wiki_env, project="demo", session=session)
    screen = render_wrap_screen(result, session=session)
    assert "log ✓" in screen
    assert "sessions ✓" in screen


def test_wrap_screen_renders_link_warnings(wiki_env):
    (wiki_env / "log.md").unlink()
    session = "s-links-screen-warn"
    result = _run_minimal_wrap(wiki_env, project="demo", session=session)
    screen = render_wrap_screen(result, session=session)
    assert "⚠" in screen
    assert "log.md" in screen
