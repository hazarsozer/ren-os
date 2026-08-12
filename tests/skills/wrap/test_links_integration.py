"""
Integration test for #54 (Task 4) — proves the D1-D4 link duties actually
weave together end-to-end through the real `wrap_session` write path, and
never duplicate on a second wrap of the same project.

Fixture skeleton is lifted from `test_wrap_links_wiring.py` (Task 2's
wiring suite): same `clean_path_env` / `wiki_env` shape, same
REN_FRAMEWORK_ROOT redirect, same fake `llm_call` that forces a "durable"
classifier verdict.

KNOWN CONSTRAINT (verified in Task 2's review, restated here because it
shapes this file's structure): `wrap_session`'s own durable-items loop
ALWAYS writes durable pages to the global `lessons/<slug>.md` tree (see
`_slugify` in `skills/wrap/lib/__init__.py`) — never `projects/<project>/...`.
So D4's auto-pointer branch (a project-scoped ADD in `applied`) can never
fire from a real `wrap_session()` call today; it is only reachable by
calling `_run_link_duties` directly with a hand-built `applied` entry, which
is exactly what `test_wrap_links_wiring.py` already does and what the
second test below does again (for the pointer non-duplication property).

The D4 *spine* write (index.md ← project map.md) is NOT gated on that
branch, though: `_run_link_duties` tries `ensure_index_spine` unconditionally
whenever `project` is set and `index.md` exists (see the `if project:` block
in `_run_link_duties`) — so spine weaving IS reachable end-to-end through
two real `wrap_session` calls, and is exercised that way below.

Run with: uv run pytest tests/skills/wrap/test_links_integration.py -v
"""
from __future__ import annotations

import re

import pytest

from lib.pointer import parse_pointer_line
from lib.ren_paths import wiki_root
from skills.wrap.lib import _run_link_duties, wrap_session

# A genuine D4 pointer line (`add_map_pointer`/`ensure_index_spine`, via
# `lib.pointer.render_pointer_line`) always ends in a trailing paren group
# that is either "(w-<write_id>)" or the literal "(unstamped)" — that's what
# distinguishes it from a plain D1/D3 narrative link (`- [topic](page)`,
# no trailing paren group). Filtering on "(w-" alone (as an earlier draft of
# this file did) silently missed every unstamped pointer, INCLUDING the
# spine line `_run_link_duties` renders via `ensure_index_spine(..., None)`
# — making 3 of the 4 round-trip loops in this file vacuous. Fixed here by
# matching either tail, and every caller below asserts a minimum match count
# so a future filter regression fails loud instead of silently no-op'ing.
_POINTER_LINE_RE = re.compile(r"^-\s*\[.*\]\(.+\)\s*\((?:w-[^)]*|unstamped)\)\s*$")


def _pointer_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if _POINTER_LINE_RE.match(line)]

_MAP_SKELETON = "# demo — knowledge map\n\n## Knowledge\n- nothing yet\n"
_LOG_SKELETON = "# Wiki Log\n\n## [2026-08-01] init | x\n"
_INDEX_SKELETON = "---\ntype: l2-map\n---\n# Master\n## Decision map\n"

_DURABLE_LLM_CALL = lambda prompt: '{"verdict": "durable", "reason": "stub"}'


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
    """A bootstrapped wiki: log.md, index.md (with a "## Decision map"
    section, the spine's home), and one project ("demo") with an existing
    map.md — the shape link duties expect on a real wiki."""
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "log.md").write_text(_LOG_SKELETON, encoding="utf-8")
    (root / "index.md").write_text(_INDEX_SKELETON, encoding="utf-8")
    project_dir = root / "projects" / "demo"
    project_dir.mkdir(parents=True)
    (project_dir / "map.md").write_text(_MAP_SKELETON, encoding="utf-8")
    return root


def read(wiki_env, rel_path):
    return (wiki_env / rel_path).read_text(encoding="utf-8")


def _wrap_with_durable_page(wiki_env, *, session, fact_word):
    """Run a real end-of-session wrap: one durable item (forced "durable"
    by the fake llm_call, same stub `test_wrap_links_wiring.py` uses),
    scoped to project "demo". The durable item lands under the global
    `lessons/` tree (see module docstring), so it also feeds D1's
    touched-pages section for this session's own L1.

    `fact_word` (rather than embedding `session`, e.g. "s1"/"s2", straight
    into the fact text) keeps the two calls' durable items from reading as a
    same-fact numeric divergence to `lib.memory.semantics.detect` — "s1" vs
    "s2" both mask to the same template with one digit changed, which is
    exactly the deterministic `contradicts` signal, and a held (not applied)
    second item would starve this test's D1 assertions of a page to link."""
    return wrap_session(
        f"---\n---\n\n# S\n\nSession {session} narrative.\n",
        [f"We decided {fact_word} is durable for the record."],
        session=session,
        project="demo",
        llm_call=_DURABLE_LLM_CALL,
    )


# --- end-to-end: two real wraps weave once, never duplicate -----------------


def test_two_wraps_weave_and_never_duplicate(wiki_env):
    """Spec §Testing: full wrap on a temp wiki -> L1 linked from log + map,
    index spine present; second wrap adds a second session line but
    duplicates neither the map's Sessions entries nor the index spine."""
    r1 = _wrap_with_durable_page(wiki_env, session="s1", fact_word="alpha")
    r2 = _wrap_with_durable_page(wiki_env, session="s2", fact_word="beta")

    assert r1["links"]["warnings"] == []
    assert r2["links"]["warnings"] == []

    map_text = read(wiki_env, "projects/demo/map.md")
    index_text = read(wiki_env, "index.md")
    log_text = read(wiki_env, "log.md")
    l1_s1_text = read(wiki_env, "projects/demo/l1/session-s1.md")
    l1_s2_text = read(wiki_env, "projects/demo/l1/session-s2.md")

    assert "## Touched pages" in l1_s1_text
    assert "## Touched pages" in l1_s2_text
    assert log_text.count("] session | demo") == 2
    assert map_text.count("- [session-") == 2

    # session-distinctness: both sessions' own lines are present (a plain
    # count()==2 would also pass if s1 were written twice and s2 dropped) —
    # assert each FULL link target, not just the topic text, so a swapped or
    # truncated l1_page would also be caught.
    assert "[session-s1](projects/demo/l1/session-s1.md)" in log_text
    assert "[session-s2](projects/demo/l1/session-s2.md)" in log_text
    assert "- [session-s1](projects/demo/l1/session-s1.md)" in map_text
    assert "- [session-s2](projects/demo/l1/session-s2.md)" in map_text

    # spine: index.md points at the project's map.md exactly once across
    # both wraps — `ensure_index_spine` is a no-op once the target line is
    # already present (see `_append_pointer`'s `if path in page_text` guard).
    assert index_text.count("projects/demo/map.md") == 1

    # every generated pointer line parses through the shared grammar. The
    # spine line in index.md is the one genuine pointer line reachable
    # end-to-end through `wrap_session` (see module docstring) — assert the
    # loop actually found it, not just that whatever it found parses.
    index_pointer_lines = _pointer_lines(index_text)
    assert len(index_pointer_lines) >= 1
    for line in index_pointer_lines:
        assert parse_pointer_line(line) is not None

    # map.md has NO genuine pointer line in this flow — D4's auto-pointer
    # branch never fires from `wrap_session`'s own durable-items loop (see
    # module docstring); asserted explicitly so this is a documented zero,
    # not a silently vacuous loop.
    assert _pointer_lines(map_text) == []


# --- D4 auto-pointer: only reachable by calling _run_link_duties directly ---
#
# See the module docstring: none of `wrap_session`'s OWN durable-items loop
# ever produces a `projects/<project>/...` page, so `applied` never contains
# a project-scoped ADD through the public API. This test seeds an
# `applied`-shaped entry by hand (mirrors
# `test_wrap_links_wiring.py::test_run_link_duties_adds_map_pointer_and_index_spine_for_project_page`)
# and calls `_run_link_duties` TWICE with the identical `applied` page, to
# prove D4's own pointer write is idempotent — the property the brief asks
# for that `wrap_session` alone cannot exercise today.


def test_run_link_duties_pointer_not_duplicated_across_repeat_calls(wiki_env):
    (wiki_env / "projects/demo/knowledge").mkdir(parents=True)
    (wiki_env / "projects/demo/knowledge/auto-page.md").write_text(
        "# Auto Page\nbody\n", encoding="utf-8"
    )
    applied = [
        {
            "qid": "q1",
            "write_id": "w-01D4",
            "page": "projects/demo/knowledge/auto-page.md",
            "op": "ADD",
        }
    ]

    out1 = _run_link_duties(
        session="s-d4-a",
        project="demo",
        l1_page="projects/demo/l1/session-s-d4-a.md",
        l1_path=wiki_env / "projects/demo/l1/session-s-d4-a.md",
        applied=applied,
        wiki_root=wiki_env,
    )
    out2 = _run_link_duties(
        session="s-d4-b",
        project="demo",
        l1_page="projects/demo/l1/session-s-d4-b.md",
        l1_path=wiki_env / "projects/demo/l1/session-s-d4-b.md",
        applied=applied,
        wiki_root=wiki_env,
    )

    assert out1["auto_pointers"] == ["projects/demo/knowledge/auto-page.md"]
    assert out2["auto_pointers"] == []  # already present — not re-added

    map_text = read(wiki_env, "projects/demo/map.md")
    index_text = read(wiki_env, "index.md")
    assert map_text.count("knowledge/auto-page.md") == 1
    assert index_text.count("projects/demo/map.md") == 1

    map_pointer_lines = _pointer_lines(map_text)
    assert len(map_pointer_lines) >= 1
    for line in map_pointer_lines:
        assert parse_pointer_line(line) is not None

    index_pointer_lines = _pointer_lines(index_text)
    assert len(index_pointer_lines) >= 1
    for line in index_pointer_lines:
        assert parse_pointer_line(line) is not None
