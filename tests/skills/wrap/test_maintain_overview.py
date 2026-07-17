"""
Tests for skills.wrap.lib.maintain_overview — the overview.md producer
(0.5.5 Task 3).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/wrap/test_maintain_overview.py -v
"""

from __future__ import annotations

import json

import pytest

from lib import ren_paths
from lib.memory.provenance import read_frontmatter_provenance
from lib.memory.revert import revert
from lib.ren_paths import wiki_root
from skills.wrap.lib import maintain_overview, wrap_session


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


def _overview_path(wiki, project="demo-project"):
    return wiki / "projects" / project / "overview.md"


def _skeleton_text() -> str:
    return (
        '---\ntitle: "Project Overview"\ntype: overview\nschema_version: 1\n'
        'framework_version: "0.5.5"\ncreated: 2026-07-17\nupdated: 2026-07-17\n---\n\n'
        "# Project overview\n\n"
        "<!-- What this project is, its current stage/thesis, and 3–5 "
        "load-bearing facts. -->\n"
    )


def _llm_json(**kwargs):
    def llm_call(prompt: str) -> str:
        return json.dumps(kwargs)
    return llm_call


def _llm_raises(exc: Exception = ValueError("boom")):
    def llm_call(prompt: str) -> str:
        raise exc
    return llm_call


def test_overview_created_on_first_wrap(wiki):
    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    page.write_text(_skeleton_text(), encoding="utf-8")

    llm_yes = _llm_json(material_change=True, overview="We built X. Stage: MVP.")

    res = maintain_overview("demo-project", "sess-1", "we built X", llm_yes)

    assert res is not None
    text = page.read_text(encoding="utf-8")
    assert "we built X" in text or "We built X" in text
    prov = read_frontmatter_provenance(text)
    assert prov is not None
    assert prov["trust"] == "model"


def test_overview_created_when_page_absent(wiki):
    """Older projects with no skeleton stamp at all: page is entirely
    absent, still CREATE via a queue ADD."""
    llm_yes = _llm_json(material_change=True, overview="We built Y. Stage: alpha.")

    res = maintain_overview("demo-project", "sess-1", "we built Y", llm_yes)

    assert res is not None
    page = _overview_path(wiki)
    assert page.is_file()
    text = page.read_text(encoding="utf-8")
    assert "We built Y" in text


def test_overview_untouched_when_no_material_change(wiki):
    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    real_overview = (
        '---\ntitle: "Project Overview"\ntype: overview\nschema_version: 1\n'
        '---\n\n# Project overview\n\nAlready has real content.\n'
    )
    page.write_text(real_overview, encoding="utf-8")
    mtime_before = page.stat().st_mtime_ns

    llm_no = _llm_json(material_change=False, overview="irrelevant")

    res = maintain_overview("demo-project", "sess-1", "minor chatter", llm_no)

    assert res is None
    assert page.stat().st_mtime_ns == mtime_before


def test_overview_llm_failure_fail_closed(wiki):
    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    page.write_text(_skeleton_text(), encoding="utf-8")

    res = maintain_overview("demo-project", "sess-1", "we built X", _llm_raises())

    assert res is None
    # fail-closed: nothing written
    assert page.read_text(encoding="utf-8") == _skeleton_text()


def test_overview_llm_bad_json_fail_closed(wiki):
    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    page.write_text(_skeleton_text(), encoding="utf-8")

    def llm_bad(prompt: str) -> str:
        return "not json at all"

    res = maintain_overview("demo-project", "sess-1", "we built X", llm_bad)

    assert res is None
    assert page.read_text(encoding="utf-8") == _skeleton_text()


def test_overview_prompt_strips_quarantine_banner_from_current_body(wiki):
    # Task 3b (spec §4.5): the existing overview may be quarantine-bannered
    # (routine for an llm-auto write) — the prompt embedding the "current
    # overview" must not include the banner text itself.
    from lib.memory import quarantine

    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    bannered = (
        '---\ntitle: "Project Overview"\ntype: overview\nschema_version: 1\n'
        '---\n' + quarantine.QUARANTINE_BANNER + '\n# Project overview\n\nAlready has real content.\n'
    )
    page.write_text(bannered, encoding="utf-8")

    captured_prompts: list[str] = []

    def llm_capture(prompt: str) -> str:
        captured_prompts.append(prompt)
        return json.dumps({"material_change": False, "overview": "irrelevant"})

    maintain_overview("demo-project", "sess-1", "minor chatter", llm_capture)

    assert len(captured_prompts) == 1
    assert quarantine.QUARANTINE_BANNER.strip() not in captured_prompts[0]
    assert "Already has real content." in captured_prompts[0]


def test_overview_title_with_quote_round_trips_valid_frontmatter(wiki):
    # MINOR fix (Task 6c, same holistic review): _build_overview_content
    # interpolated `title` into the frontmatter fence via an unescaped
    # f-string — a hand-edited title carrying a `"` would malform the
    # fence. `title` is carried forward from the EXISTING page's frontmatter
    # on every UPDATE, so a friend who once hand-edited a quoted title would
    # keep re-breaking their own overview on every subsequent wrap.
    import re

    import yaml

    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    existing = (
        "---\n"
        "title: 'My \"Cool\" Project'\n"
        "type: overview\nschema_version: 1\n"
        "---\n\n# Project overview\n\nAlready has real content.\n"
    )
    page.write_text(existing, encoding="utf-8")

    llm_yes = _llm_json(material_change=True, overview="New replacement body.")
    res = maintain_overview("demo-project", "sess-1", "session narrative", llm_yes)

    assert res is not None
    text = page.read_text(encoding="utf-8")
    fm_match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    assert fm_match is not None
    frontmatter = yaml.safe_load(fm_match.group(1))
    assert frontmatter["title"] == 'My "Cool" Project'


def test_overview_update_is_revertible(wiki):
    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    original = (
        '---\ntitle: "Project Overview"\ntype: overview\nschema_version: 1\n'
        '---\n\n# Project overview\n\nOriginal body.\n'
    )
    page.write_text(original, encoding="utf-8")

    llm_yes = _llm_json(material_change=True, overview="New replacement body.")
    res = maintain_overview("demo-project", "sess-1", "session narrative", llm_yes)

    assert res is not None
    write_id = res["write_id"]
    updated_text = page.read_text(encoding="utf-8")
    assert "New replacement body." in updated_text

    result = revert(write_id)
    assert result.restored
    reverted_text = page.read_text(encoding="utf-8")
    assert "Original body." in reverted_text


# --- wrap_session integration -----------------------------------------------


def test_wrap_session_reports_overview_created(wiki):
    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    page.write_text(_skeleton_text(), encoding="utf-8")

    llm_yes = _llm_json(material_change=True, overview="We built X.")

    result = wrap_session(
        narrative_md="# Session summary\n\nDid work.\n",
        durable_items=[],
        session="sess-1",
        llm_call=llm_yes,
        project="demo-project",
    )

    assert result["overview"] == "created"


def test_wrap_session_reports_overview_skipped_on_llm_failure(wiki):
    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    page.write_text(_skeleton_text(), encoding="utf-8")

    result = wrap_session(
        narrative_md="# Session summary\n\nDid work.\n",
        durable_items=[],
        session="sess-1",
        llm_call=_llm_raises(),
        project="demo-project",
    )

    assert result["overview"] == "skipped"


def test_wrap_session_reports_overview_unchanged(wiki):
    page = _overview_path(wiki)
    page.parent.mkdir(parents=True)
    real_overview = (
        '---\ntitle: "Project Overview"\ntype: overview\nschema_version: 1\n'
        '---\n\n# Project overview\n\nAlready has real content.\n'
    )
    page.write_text(real_overview, encoding="utf-8")

    llm_no = _llm_json(material_change=False, overview="irrelevant")

    result = wrap_session(
        narrative_md="# Session summary\n\nminor chatter\n",
        durable_items=[],
        session="sess-1",
        llm_call=llm_no,
        project="demo-project",
    )

    assert result["overview"] == "unchanged"


def test_wrap_session_reports_overview_skipped_when_no_project(wiki):
    result = wrap_session(
        narrative_md="# Session summary\n\nDid work.\n",
        durable_items=[],
        session="sess-1",
        llm_call=_llm_json(material_change=True, overview="x"),
        project=None,
    )

    assert result["overview"] == "skipped"
