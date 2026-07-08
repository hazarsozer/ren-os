"""
Tests for skills.interview.lib — capped, skippable identity interview
(Task 8.1).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/interview/test_profile.py -v
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lib.memory import quarantine
from lib.memory.provenance import read_frontmatter_provenance
from lib.ren_paths import wiki_root
from skills.install.lib import QUESTION_BUDGET
from skills.interview.lib import QUESTIONS, render_identity, save_identity

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3] / "wiki-skeleton" / "templates" / "identity.md.tmpl"
)


def _template_frontmatter_fields() -> set[str]:
    """Top-level frontmatter field names from identity.md.tmpl.

    Not a full YAML parse: the template's unquoted `{{placeholder}}` values
    (e.g. `handle: {{handle}}`) aren't valid YAML on their own, so this reads
    top-level (non-indented) `key:` lines directly — sufficient for the
    golden cross-check this test needs (which fields exist), without
    needing the template to be render-clean YAML.
    """
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None, "identity.md.tmpl has no frontmatter block"
    fields = set()
    for line in match.group(1).splitlines():
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):", line)
        if m:
            fields.add(m.group(1))
    return fields


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


# --- QUESTIONS shape / golden cross-check -----------------------------------


def test_questions_length_within_budget():
    assert len(QUESTIONS) <= QUESTION_BUDGET


def test_every_question_key_maps_to_a_template_field():
    template_fields = _template_frontmatter_fields()
    for question in QUESTIONS:
        assert question["key"] in template_fields, (
            f"QUESTIONS key {question['key']!r} is not a field in identity.md.tmpl"
        )


def test_every_question_has_a_non_none_default():
    for question in QUESTIONS:
        assert question["default"] is not None


# --- render_identity: zero-doctrine + partial merge -------------------------


def test_render_identity_zero_answers_produces_valid_page_all_defaults():
    """THE zero-doctrine test: the system must work with ZERO user-authored
    doctrine — calling this with nothing answered must still produce a
    complete, valid page."""
    text = render_identity({})

    assert text.startswith("---\n")
    prov_like = read_frontmatter_provenance(text)  # no ren_* keys yet, but must not crash
    assert prov_like is None  # not yet stamped by write_apply — expected

    for question in QUESTIONS:
        key = question["key"]
        assert f"skipped_questions:" in text
        # every key should appear in the skipped_questions list rendering
    assert "name: \"Friend\"" in text
    assert "handle: friend" in text
    assert "working_style: balanced" in text


def test_render_identity_partial_answers_merge_correctly():
    text = render_identity({"name": "Hazar", "handle": "hazar", "working_style": "structured"})

    assert 'name: "Hazar"' in text
    assert "handle: hazar" in text
    assert "working_style: structured" in text
    # Answered keys must NOT be listed as skipped.
    skipped_line = next(line for line in text.splitlines() if line.startswith("skipped_questions:"))
    assert "name" not in skipped_line
    assert "handle" not in skipped_line
    assert "working_style" not in skipped_line
    # Unanswered keys must still be listed as skipped and keep defaults.
    assert "communication_style" in skipped_line
    assert "communication_style: balanced-with-emoji" in text


# --- save_identity: queues human-writer ADD/UPDATE, applies clean ----------


def test_save_identity_auto_applies_human_add_clean(wiki):
    # v2.2: identity.md is a non-global (data-plane) page — save_identity now
    # auto-applies through propose_and_apply instead of landing pending.
    entry = save_identity({"name": "Hazar", "handle": "hazar"}, session="sess-1")

    assert entry.status == "applied"
    assert entry.write_id is not None
    assert entry.proposal.page == "identity.md"
    assert entry.proposal.op == "ADD"
    assert entry.proposal.writer == "human"

    page_text = (wiki / "identity.md").read_text(encoding="utf-8")
    assert quarantine.is_quarantined(page_text) is False
    read_prov = read_frontmatter_provenance(page_text)
    assert read_prov["write_id"] == entry.write_id
    assert read_prov["writer"] == "human"


def test_save_identity_update_path_when_identity_already_exists(wiki):
    first = save_identity({"name": "Hazar"}, session="sess-1")
    assert first.status == "applied"  # v2.2: no separate approve()/apply() step

    second = save_identity({"name": "Hazar", "working_style": "structured"}, session="sess-2")
    assert second.proposal.op == "UPDATE"
    assert second.status == "applied"


def test_save_identity_auto_applies_after_stamp_wiki_fresh_install(wiki):
    # Regression for the false `contradicts` conflict found on every fresh
    # install: identity.md.tmpl and index.md.tmpl share stock boilerplate
    # ("...edit ... by hand") and index.md.tmpl's line contains "whenever",
    # which used to be misread as a negated "never" line (fixed in
    # lib.memory.semantics — word-boundary negation matching). With the fix,
    # the real fresh-install path (stamp_wiki() then the interview's first
    # save_identity()) must auto-apply deterministically, not land pending.
    from skills.install.lib import stamp_wiki

    stamp_wiki()
    entry = save_identity({"name": "Hazar", "handle": "hazar"}, session="sess-1")
    assert entry.status == "applied"

    # Re-running the interview (changed answers) must also auto-apply: the
    # only overlap with the existing identity.md is boilerplate, not a real
    # contradiction.
    second = save_identity(
        {"name": "Hazar", "handle": "hazar", "working_style": "structured"},
        session="sess-2",
    )
    assert second.status == "applied"
