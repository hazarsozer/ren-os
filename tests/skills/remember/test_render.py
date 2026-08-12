"""
Tests for skills.remember.lib.remember — G14 "what do you remember" (Task 8.2).

Fixture maps are created by driving the REAL ingest-project / bootstrap-project
producers (not hand-written page content), so the rendering is tested against
the actual frozen L2 schema those skills emit.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/remember/test_render.py -v
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone

import pytest

from lib.memory import queue
from lib.memory.queue import Proposal
from lib.ren_paths import wiki_root
from skills.install.lib import stamp_wiki
from skills.remember.lib import remember

_ingest_lib = importlib.import_module("skills.ingest-project.lib")


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


def _ingest_and_apply(project_slug, knowledge, pointers, session="sess-1"):
    # v2.2: ingest is a data-plane write — it auto-applies through
    # propose_and_apply, no separate approve()/apply() step needed.
    return _ingest_lib.ingest(project_slug, knowledge, pointers, session)


# --- real fixture map: all sections + write_id stripped + quarantine warning ---


def test_remember_renders_ingested_map_with_all_sections(wiki):
    _ingest_and_apply(
        "demo-project",
        knowledge=["Uses FastAPI", "Deployed on Fly.io"],
        pointers=[
            {"topic": "database choice", "path": "projects/demo-project/decisions/db.md",
             "anchor": "decision", "write_id": "w-VERYSECRETID123"},
        ],
    )

    output = remember("demo-project")

    assert "Here's what I remember about demo-project:" in output
    assert "Uses FastAPI" in output
    assert "Deployed on Fly.io" in output
    assert "database choice — see projects/demo-project/decisions/db.md#decision" in output
    assert "w-VERYSECRETID123" not in output  # write_id parenthetical must be stripped
    assert "2 facts" in output
    assert "1 decision pointers" in output


def test_remember_shows_quarantine_warning_for_ingested_map(wiki):
    _ingest_and_apply("quarantined-proj", knowledge=["fact one"], pointers=[])

    output = remember("quarantined-proj")

    assert "⚠" in output
    assert "hasn't been reviewed" in output
    assert "quarantined: yes" in output


def test_remember_no_warning_for_human_reviewed_map(wiki):
    """A human-provenance UPDATE (as if a friend reviewed + re-approved the
    content) over the same page must NOT be quarantined."""
    _ingest_and_apply("reviewed-proj", knowledge=["fact one"], pointers=[])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = _ingest_lib.assemble_l2(
        "reviewed-proj", ["fact one"], [], f"{today}: reviewed by a human"
    )
    entry = queue.propose(
        Proposal(
            op="UPDATE",
            page="projects/reviewed-proj/map.md",
            content=content,
            reason="human review",
            producer="promotion",
            writer="human",
            session="sess-2",
        )
    )
    queue.approve(entry.qid, approved_by="hazar")
    queue.apply(entry.qid)

    output = remember("reviewed-proj")

    assert "⚠" not in output
    assert "quarantined: no" in output


# --- unknown slug: friendly guidance, no exception --------------------------


def test_remember_unknown_slug_gives_friendly_guidance(wiki):
    output = remember("totally-unknown-project")

    assert "don't have memory for totally-unknown-project" in output
    assert "ingest-project" in output
    assert "bootstrap-project" in output


# --- no slug ------------------------------------------------------------


def test_remember_no_slug_no_maps_at_all_shows_fallback(wiki):
    output = remember(None)

    assert "don't have any project memory yet" in output
    assert "identity profile" in output
    assert "global doctrine" in output


def test_remember_no_slug_with_index_present_renders_master_map(wiki):
    stamp_wiki()  # creates index.md (type: l2-map) via the skeleton

    output = remember(None)

    assert "Here's what I remember about this wiki:" in output
    assert "0 facts" in output


# --- _humanize_pointer tests (Task 3: rewire to use lib.pointer.parse_pointer_line)


def test_humanize_link_form():
    lib = importlib.import_module("skills.remember.lib")
    out = lib._humanize_pointer("[Stack decisions](projects/flux/knowledge/stack.md) (w-01ABC)")
    assert out == "Stack decisions — see projects/flux/knowledge/stack.md"


def test_humanize_link_form_with_anchor():
    lib = importlib.import_module("skills.remember.lib")
    out = lib._humanize_pointer("[Schema](projects/x/schema.md#conventions) (unstamped)")
    assert out == "Schema — see projects/x/schema.md#conventions"


def test_humanize_arrow_form_still_works():
    lib = importlib.import_module("skills.remember.lib")
    out = lib._humanize_pointer("[Architecture] → projects/ren-os/knowledge/architecture/index.md (w-01Y)")
    assert out == "Architecture — see projects/ren-os/knowledge/architecture/index.md"


def test_humanize_repo_ref():
    lib = importlib.import_module("skills.remember.lib")
    out = lib._humanize_pointer("[Specs] → repo:idea-generator:analyses (w-01Z)")
    assert out == "Specs — see repo:idea-generator:analyses"


def test_humanize_unparseable_falls_back_to_raw():
    lib = importlib.import_module("skills.remember.lib")
    assert lib._humanize_pointer("just some text (note)") == "just some text"


# --- Sessions section rendering (Task 3) ------------------------------------


def test_remember_renders_sessions_line(wiki):
    """When a map has ## Sessions section with entries, render a summary line."""
    _ingest_and_apply(
        "demo",
        knowledge=["Fact one"],
        pointers=[],
    )

    # Manually add Sessions section to the map
    map_path = wiki / "projects" / "demo" / "map.md"
    text = map_path.read_text(encoding="utf-8")
    # Insert Sessions section before Log if it exists
    lines = text.split("\n")
    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "## Log":
            insert_idx = i
            break
    if insert_idx is None:
        # No Log section, append before any other headers or at end
        insert_idx = len(lines)

    sessions_lines = [
        "## Sessions",
        "- [session-2024-01-02](projects/demo/l1/session-2024-01-02.md)",
        "- [session-abc](projects/demo/l1/session-abc.md)",
    ]
    for sess_line in reversed(sessions_lines):
        lines.insert(insert_idx, sess_line)
    map_path.write_text("\n".join(lines), encoding="utf-8")

    output = remember("demo")

    assert "2 recent session" in output
    assert "session-abc" in output


def test_remember_without_sessions_section_unchanged(wiki):
    """When a map has no ## Sessions section, output is unchanged."""
    _ingest_and_apply(
        "demo",
        knowledge=["Fact one"],
        pointers=[],
    )

    output = remember("demo")

    # Should still have the normal output
    assert "Here's what I remember about demo:" in output
    assert "Fact one" in output
    # Should NOT have sessions line
    assert "recent session" not in output
