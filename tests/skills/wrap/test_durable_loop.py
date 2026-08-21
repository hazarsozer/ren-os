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

import skills.wrap.lib as _wraplib
from lib.instrument import collect
from lib.memory import quarantine
from lib.memory import queue as _queue
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


def test_merge_error_routes_to_suggestions_not_gated_out(wiki):
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
    # Spec 2026-08-21 §5.2: a durable item whose merge fails validation is
    # NOT gated_out (that's the die-silently bug #75 fixed) — it routes to
    # the suggestions store for a human to place instead.
    assert result["gated_out"] == []
    assert len(result["unplaced"]) == 1
    assert result["unplaced"][0]["item"] == item
    assert "merge" in result["unplaced"][0]["reason"]

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


def test_unchanged_durable_update_is_not_reported_as_held(wiki):
    """#78: a second run proposing content already on disk dedups to a
    synthetic noop-duplicate entry whose qid is absent from the queue dir by
    design. Reporting it as `held` cites a qid the friend cannot look up.

    The first run applies normally (same shape as
    `test_update_applies_merged_body`). For the second run, `validate_merged`
    (skills/wrap/lib/merge.py) requires the "merged" text's frontmatter block
    to be byte-identical to what's now on disk — which already carries the
    `ren_*` provenance stamps and the quarantine banner `apply` added during
    run one. A canned merge string can't satisfy that, so the second run's
    merge text is built from the actual on-disk page with
    `quarantine.release` stripping the banner back off: same frontmatter,
    banner-free body. `propose`'s own door re-adds the banner
    (`_quarantined_content`) before comparing, reproducing the on-disk page
    exactly and reproducing the real #78 scenario — a friend resubmitting a
    correction that's already landed."""
    page = "projects/p/knowledge/existing-note.md"
    page_path = wiki / page
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(_SEED_PAGE_TEXT, encoding="utf-8")

    item = "Correction: line two should say something different."

    def _run(session, merge_text):
        collect.record(collect.KIND_WAKEUP_SURFACE,
                       {"session": session, "pages": [page]})
        verdict = {item: {"verdict": "durable", "scope": "project",
                          "action": "update", "target_page": page}}
        return wrap_session(
            narrative_md="# Summary\n",
            durable_items=[item],
            session=session,
            project="p",
            llm_call=_llm(verdict, merge_text=merge_text),
        )

    first = _run("s-noop-1", _MERGED_PAGE_TEXT)
    assert len(first["updated"]) == 1, "precondition: the first run applies"

    second_merge_text = quarantine.release(page_path.read_text(encoding="utf-8"))
    second = _run("s-noop-2", second_merge_text)

    assert [h["page"] for h in second["held"]] == [], \
        f"noop-duplicate leaked into held: {second['held']}"
    assert [u["page"] for u in second["unchanged"]] == [page], \
        "an unchanged re-run must report the page as unchanged"


def test_user_trust_hold_still_reported(wiki, monkeypatch):
    """The discrimination must not swallow genuine holds.

    A `ren_trust: "user"` target (the scenario in
    `test_update_to_user_trust_page_held_as_suggestion`, line 165) never
    reaches `propose_and_apply` at all — `wrap_session` diverts it to
    `suggested` first, so it can't exercise the `held`-vs-`unchanged`
    discrimination. A real `contradicts`-conflict hold is likewise awkward to
    force deterministically through `lib.memory.semantics`. So — the same
    technique `test_touched_pages_excludes_a_held_durable_item`
    (test_wrap_links_wiring.py) already uses — `propose_and_apply` is
    monkeypatched to route this one page's UPDATE through the real
    `queue.propose` (a genuinely PENDING, persisted entry) while returning
    `(entry, None)`, the exact shape a real hold takes. Assert only that
    whatever lands in `held` still carries a real qid, so a hold is never
    silently reclassified as `unchanged`."""
    page = "projects/p/knowledge/human-note.md"
    page_path = wiki / page
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(_SEED_PAGE_TEXT, encoding="utf-8")
    collect.record(collect.KIND_WAKEUP_SURFACE, {"session": "s-hold-1", "pages": [page]})

    item = "Correction: line two should say something different."

    real_propose_and_apply = _wraplib.propose_and_apply

    def _fake(proposal):
        if proposal.op == "UPDATE" and proposal.page == page:
            entry = _queue.propose(proposal)
            return entry, None  # genuine pending hold, never applied
        return real_propose_and_apply(proposal)

    monkeypatch.setattr(_wraplib, "propose_and_apply", _fake)

    result = wrap_session(
        narrative_md="# Summary\n",
        durable_items=[item],
        session="s-hold-1",
        project="p",
        llm_call=_llm(
            {item: {"verdict": "durable", "scope": "project",
                    "action": "update", "target_page": page}},
            merge_text=_MERGED_PAGE_TEXT,
        ),
    )

    assert result["held"], "the durable item must actually be held for this test to mean anything"
    assert all(h["qid"] for h in result["held"]), \
        "a real hold must keep a qid that exists on disk"
    assert _queue.get(result["held"][0]["qid"]) is not None, \
        "a real hold's qid must resolve to an actual persisted queue entry"
    assert result["unchanged"] == [], "a hold is not an unchanged page"
