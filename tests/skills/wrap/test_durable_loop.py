"""
Tests for the durable-items loop inside skills.wrap.lib.wrap_session (Task
4): classifier-driven placement (project-scoped vs. global CREATE),
classifier-driven UPDATE via lib.merge, the user-trust hold (a durable
UPDATE targeting a human-authored page becomes a suggestion instead of a
write), the merge-error fail-closed path, and the durable_outcome metric.

Reuses test_wrap_flow.py's isolation pattern (REN_FRAMEWORK_ROOT-pointed
`wiki` fixture) and scripted-llm_call convention: dispatch on a distinctive
prompt substring — "Candidate item:" is the classifier's prompt, "The
current page:" is the merge prompt; anything else (overview maintenance,
the semantic judge) gets a harmless stub answer so wrap_session's other
sub-steps never crash the test.

Run with: uv run pytest tests/skills/wrap/test_durable_loop.py -v
"""

from __future__ import annotations

import json

import pytest

from lib.instrument import collect
from lib.ren_paths import wiki_root
from lib.suggestions import pending_suggestions
from skills.wrap.lib import wrap_session


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


def _llm(classify_by_item: dict[str, dict], merge_text: str | None = None):
    """A stub `llm_call` that answers every prompt shape `wrap_session`'s
    durable loop can send:

      - the classifier's gate prompt ("Candidate item:") -> the decision
        JSON keyed by a substring of the item text in `classify_by_item`
        (defaults to a "session-only" verdict for anything unmatched)
      - the merge prompt ("The current page:") -> `merge_text` verbatim
      - anything else (overview maintenance, the semantic judge) -> a
        harmless stub so those unrelated sub-steps of wrap_session never
        raise or apply a write.
    """
    def llm_call(prompt: str) -> str:
        if "Candidate item:" in prompt:
            for item_text, decision in classify_by_item.items():
                if item_text in prompt:
                    return json.dumps({
                        "verdict": decision.get("verdict", "durable"),
                        "reason": decision.get("reason", "stub"),
                        "scope": decision.get("scope", "global"),
                        "action": decision.get("action", "create"),
                        "target_page": decision.get("target_page"),
                    })
            return json.dumps({"verdict": "session-only", "reason": "stub: unmatched"})
        if "The current page:" in prompt:
            if merge_text is None:
                raise AssertionError("merge prompt invoked but no merge_text configured")
            return merge_text
        # Overview maintenance's prompt (and the semantic judge's, if ever
        # reached) — a harmless no-op answer.
        return json.dumps({"material_change": False, "overview": ""})
    return llm_call


def test_create_project_scoped(wiki):
    item = "We decided to always index user_id first in the orders table."
    llm_call = _llm({item: {"verdict": "durable", "scope": "project", "action": "create"}})

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[item],
        session="s-create-proj",
        project="p",
        llm_call=llm_call,
    )

    assert len(result["applied"]) == 1
    page = result["applied"][0]["page"]
    assert page.startswith("projects/p/knowledge/lessons/")
    assert page.endswith(".md")
    assert (wiki / page).exists()


def test_create_global_fallback(wiki):
    item = "We decided to standardize on Postgres for order-history joins."
    llm_call = _llm({item: {"verdict": "durable", "scope": "global", "action": "create"}})

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[item],
        session="s-create-global",
        llm_call=llm_call,
    )

    assert len(result["applied"]) == 1
    page = result["applied"][0]["page"]
    assert page.startswith("lessons/")
    assert (wiki / page).exists()


_SEED_PAGE_TEXT = (
    "---\ntype: knowledge\nren_trust: model\n---\n\nLine one.\nLine two.\n"
)
_MERGED_PAGE_TEXT = (
    "---\ntype: knowledge\nren_trust: model\n---\n\nLine one.\nLine two changed.\n"
)
_USER_TRUST_SEED_PAGE_TEXT = (
    "---\ntype: knowledge\nren_trust: user\n---\n\nLine one.\nLine two.\n"
)
_USER_TRUST_MERGED_PAGE_TEXT = (
    "---\ntype: knowledge\nren_trust: user\n---\n\nLine one.\nLine two changed.\n"
)


def test_update_applies_merged_body(wiki):
    session = "s-update-1"
    page = "projects/p/knowledge/existing-note.md"
    page_path = wiki / page
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(_SEED_PAGE_TEXT, encoding="utf-8")

    collect.record(collect.KIND_WAKEUP_SURFACE, {"session": session, "pages": [page]})

    item = "Correction: line two should say something different."
    llm_call = _llm(
        {item: {"verdict": "durable", "scope": "project", "action": "update", "target_page": page}},
        merge_text=_MERGED_PAGE_TEXT,
    )

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[item],
        session=session,
        project="p",
        llm_call=llm_call,
    )

    assert len(result["updated"]) == 1
    assert result["updated"][0]["page"] == page
    assert result["updated"][0]["op"] == "UPDATE"
    assert result["applied"] == []

    on_disk = page_path.read_text(encoding="utf-8")
    assert "Line two changed." in on_disk


def test_update_to_user_trust_page_held_as_suggestion(wiki):
    session = "s-update-2"
    page = "projects/p/knowledge/human-note.md"
    page_path = wiki / page
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(_USER_TRUST_SEED_PAGE_TEXT, encoding="utf-8")

    collect.record(collect.KIND_WAKEUP_SURFACE, {"session": session, "pages": [page]})

    item = "Correction: line two should say something different."
    llm_call = _llm(
        {item: {"verdict": "durable", "scope": "project", "action": "update", "target_page": page}},
        merge_text=_USER_TRUST_MERGED_PAGE_TEXT,
    )

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[item],
        session=session,
        project="p",
        llm_call=llm_call,
    )

    assert result["updated"] == []
    assert result["applied"] == []
    assert len(result["suggested"]) == 1
    assert result["suggested"][0]["page"] == page

    # The on-disk page must be untouched — no write happened.
    assert page_path.read_text(encoding="utf-8") == _USER_TRUST_SEED_PAGE_TEXT

    pending = pending_suggestions()
    matching = [s for s in pending if s["fingerprint"] == f"wrap-update:{session}:{page}"]
    assert len(matching) == 1
    assert matching[0]["kind"] == "page_write"
    assert matching[0]["producer"] == "wrap"


def test_merge_error_gates_item_out(wiki):
    session = "s-update-3"
    page = "projects/p/knowledge/existing-note-2.md"
    page_path = wiki / page
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(_SEED_PAGE_TEXT, encoding="utf-8")

    collect.record(collect.KIND_WAKEUP_SURFACE, {"session": session, "pages": [page]})

    item = "Correction: line two should say something different."
    tampered = "---\ntype: knowledge\nren_trust: model\nEXTRA: yes\n---\n\nLine one.\nLine two changed.\n"
    llm_call = _llm(
        {item: {"verdict": "durable", "scope": "project", "action": "update", "target_page": page}},
        merge_text=tampered,
    )

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[item],
        session=session,
        project="p",
        llm_call=llm_call,
    )

    assert result["updated"] == []
    assert result["applied"] == []
    assert result["suggested"] == []
    assert len(result["gated_out"]) == 1
    assert result["gated_out"][0]["item"] == item
    assert "merge" in result["gated_out"][0]["reason"]

    # No write landed — the page is untouched.
    assert page_path.read_text(encoding="utf-8") == _SEED_PAGE_TEXT


def test_durable_outcome_metric_recorded(wiki):
    session = "s-outcome-1"
    item = "We decided to standardize on Postgres for order-history joins."
    llm_call = _llm({item: {"verdict": "durable", "scope": "global", "action": "create"}})

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[item],
        session=session,
        llm_call=llm_call,
    )

    entries = [
        e for e in collect.read(kind=collect.KIND_DURABLE_OUTCOME)
        if e.get("session") == session
    ]
    assert len(entries) == 1
    entry = entries[0]

    for key in ("seen", "created", "created_project", "created_global",
                "updated", "gated_out", "suggested", "held", "refused"):
        assert key in entry
        assert isinstance(entry[key], int)

    # #I5 (spec §4): `seen` and the project/global split of creates are what
    # make "creates still starve" distinguishable from "nothing was proposed".
    assert entry["seen"] == 1
    assert entry["created_project"] + entry["created_global"] == entry["created"]
    # This item was classified global-scope, so it lands in `lessons/`.
    assert entry["created_global"] == len(result["applied"])
    assert entry["created_project"] == 0

    assert entry["created"] == len(result["applied"])
    assert entry["updated"] == len(result["updated"])
    assert entry["gated_out"] == len(result["gated_out"])
    assert entry["suggested"] == len(result["suggested"])
    assert entry["held"] == len(result["held"])
    assert entry["refused"] == len(result["refused"])
