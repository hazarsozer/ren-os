"""
Tests for concept-tree routing in `wrap_session`'s durable loop (Task 3,
2026-08-31 spec §3): placement-aware concept creates (new-leaf vs. existing
node), the `ConceptPlacementError` lesson-fallback, taxonomy blindness,
trust-user `schema.md` suggestions, the split-bullet suggestion, and the
`KIND_DURABLE_OUTCOME` counter partition.

Reuses test_durable_loop.py's isolation pattern (REN_FRAMEWORK_ROOT-pointed
`wiki` fixture) and drives `wrap_session` via the `verdicts=` precomputed
transport (no live `llm_call`), same convention as test_wrap_verdicts.py.

Run with: uv run pytest tests/skills/wrap/test_wrap_session.py -v
"""

from __future__ import annotations

import pytest

from lib.instrument import collect
from lib.memory.taxonomy import parse_taxonomy
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


def _schema_md(nodes_block: str, *, trust_user: bool = False) -> str:
    trust_line = 'ren_trust: "user"\n' if trust_user else ""
    return (
        "---\ntype: project-schema\n" + trust_line + "---\n\n"
        "# Schema\n\n"
        "```taxonomy\n" + nodes_block + "```\n"
    )


def _seed_schema(wiki, project: str, nodes_block: str, *, trust_user: bool = False) -> None:
    path = wiki / "projects" / project / "schema.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_schema_md(nodes_block, trust_user=trust_user), encoding="utf-8")


def _concept_verdict(**overrides) -> dict:
    base = {
        "verdict": "durable", "reason": "r", "scope": "project",
        "action": "create", "target_page": None,
        "kind": "concept", "placement": None, "title": None,
    }
    base.update(overrides)
    return base


def _lesson_verdict(**overrides) -> dict:
    base = {
        "verdict": "durable", "reason": "r", "scope": "global",
        "action": "create", "target_page": None, "kind": "lesson",
    }
    base.update(overrides)
    return base


def test_concept_create_new_leaf(wiki):
    """(a) concept create to a new leaf: concept page + leaf hub + parent
    hub link + schema.md fence gains the node."""
    _seed_schema(wiki, "p", "billing/\n")
    item = "The topic subsystem owns routing for cross-cutting concerns."
    verdict = _concept_verdict(placement="topic", title="New Topic")

    result = wrap_session(
        "# n", [item], "s-new-leaf", project="p", verdicts=[verdict],
    )

    assert len(result["applied"]) == 1
    page = result["applied"][0]["page"]
    assert page == "projects/p/knowledge/topic/new-topic.md"
    assert (wiki / page).is_file()
    content = (wiki / page).read_text(encoding="utf-8")
    assert "type: project-knowledge" in content
    assert "## Facts" in content
    assert item in content

    leaf_hub = wiki / "projects/p/knowledge/topic/topic.md"
    assert leaf_hub.is_file()
    assert "hub: true" in leaf_hub.read_text(encoding="utf-8")

    parent_hub = wiki / "projects/p/knowledge/knowledge.md"
    assert parent_hub.is_file()
    assert "- [topic](topic/topic.md)" in parent_hub.read_text(encoding="utf-8")

    schema_text = (wiki / "projects/p/schema.md").read_text(encoding="utf-8")
    tax = parse_taxonomy(schema_text)
    assert "topic" in tax.nodes
    assert "billing" in tax.nodes


def test_concept_create_existing_node_appends_facts_bullet(wiki):
    """(b) concept "create" whose placement resolves to an EXISTING node
    accretes onto the node's own page (no new page minted)."""
    _seed_schema(wiki, "p", "auth/\n")
    node_page = wiki / "projects/p/knowledge/auth/auth.md"
    node_page.parent.mkdir(parents=True, exist_ok=True)
    node_page.write_text(
        "---\ntype: hub\nhub: true\ntitle: \"Auth Hub\"\n---\n\n"
        "# Auth\n\n## Facts\n\n- Existing fact.\n",
        encoding="utf-8",
    )

    item = "Sessions expire after 30 minutes of inactivity."
    verdict = _concept_verdict(placement="auth", title=None)

    result = wrap_session(
        "# n", [item], "s-existing", project="p", verdicts=[verdict],
    )

    assert result["applied"] == []
    assert len(result["updated"]) == 1
    assert result["updated"][0]["page"] == "projects/p/knowledge/auth/auth.md"

    on_disk = node_page.read_text(encoding="utf-8")
    assert "- Existing fact." in on_disk
    assert f"- {item}" in on_disk

    md_files = list((wiki / "projects/p/knowledge/auth").glob("*.md"))
    assert [p.name for p in md_files] == ["auth.md"], "no new page must be minted"

    outcome = [
        e for e in collect.read(kind=collect.KIND_DURABLE_OUTCOME)
        if e.get("session") == "s-existing"
    ][-1]
    assert outcome["concept_updates"] == 1


def test_concept_placement_error_falls_back_to_lesson(wiki):
    """(c) a `ConceptPlacementError` (here: concept + scope="global", which
    the classifier disallows — no global taxonomy) is NEVER `unplaced`; it
    falls back to a lesson create and records a `placement_event`."""
    _seed_schema(wiki, "p", "billing/\n")
    item = "We should never let cross-project concepts share a taxonomy."
    verdict = _concept_verdict(scope="global", placement="foo", title="Foo Thing")

    result = wrap_session(
        "# n", [item], "s-rejected", project="p", verdicts=[verdict],
    )

    assert result["unplaced"] == []
    assert len(result["applied"]) == 1
    page = result["applied"][0]["page"]
    assert page.startswith("lessons/"), "scope=global fallback lands in global lessons/"

    events = [
        e for e in collect.read(kind=collect.KIND_PLACEMENT_EVENT)
        if e.get("session") == "s-rejected"
    ]
    assert len(events) == 1
    assert events[0]["event"] == "placement_rejected"

    outcome = [
        e for e in collect.read(kind=collect.KIND_DURABLE_OUTCOME)
        if e.get("session") == "s-rejected"
    ][-1]
    assert outcome["placement_rejected"] == 1
    assert outcome["created_lesson"] == 1
    assert outcome["created_concept"] == 0


def test_absent_schema_routes_everything_to_lessons_and_reports_blind(wiki):
    """(d) no schema.md at all: concept routing is blind — every durable
    item (even a concept-kind one) lands as a lesson, and the wrap result
    surfaces `concept_routing.blind` rather than guessing."""
    item = "Auth tokens rotate every hour."
    verdict = _concept_verdict(placement="auth", title="Auth Thing")

    result = wrap_session(
        "# n", [item], "s-blind", project="p", verdicts=[verdict],
    )

    assert result["unplaced"] == []
    assert len(result["applied"]) == 1
    assert result["applied"][0]["page"].startswith("projects/p/knowledge/lessons/")

    assert "concept_routing" in result
    assert result["concept_routing"]["blind"] is not None
    assert "p/schema.md" in result["concept_routing"]["blind"] or "schema.md" in result["concept_routing"]["blind"]


def test_taxonomy_loaded_fine_reports_not_blind(wiki):
    """The mirror of (d): a parseable schema.md reports `blind: None`."""
    _seed_schema(wiki, "p", "billing/\n")
    item = "A plain durable lesson, nothing concept-shaped."
    verdict = _lesson_verdict()

    result = wrap_session(
        "# n", [item], "s-not-blind", project="p", verdicts=[verdict],
    )

    assert result["concept_routing"] == {"blind": None}


def test_trust_user_schema_suggests_taxonomy_edit_but_page_still_created(wiki):
    """(e) a human-owned (`ren_trust: user`) schema.md: the taxonomy edit is
    held as a suggestion, but the concept page + hub writes still land — the
    tree exists on disk, wiki-health reconciles the fence drift."""
    _seed_schema(wiki, "p", "billing/\n", trust_user=True)
    item = "The topic subsystem owns routing for cross-cutting concerns."
    verdict = _concept_verdict(placement="topic", title="New Topic")

    result = wrap_session(
        "# n", [item], "s-trust-user", project="p", verdicts=[verdict],
    )

    assert len(result["applied"]) == 1
    page = result["applied"][0]["page"]
    assert (wiki / page).is_file()
    assert (wiki / "projects/p/knowledge/topic/topic.md").is_file()

    schema_text = (wiki / "projects/p/schema.md").read_text(encoding="utf-8")
    assert "topic" not in parse_taxonomy(schema_text).nodes, \
        "a trust-user schema.md must not be auto-edited"

    assert len(result["suggested"]) == 1
    assert result["suggested"][0]["page"] == "projects/p/schema.md"

    pending = pending_suggestions()
    matching = [s for s in pending if s["fingerprint"] == "wrap-taxonomy:s-trust-user:topic"]
    assert len(matching) == 1
    assert matching[0]["kind"] == "page_write"
    assert matching[0]["producer"] == "wrap"


def test_split_suggestion_on_41st_bullet(wiki):
    """(f) the 41st `## Facts` bullet on a concept node triggers a (never
    auto-applied) split suggestion, deduped by page fingerprint."""
    _seed_schema(wiki, "p", "auth/\n")
    node_page = wiki / "projects/p/knowledge/auth/auth.md"
    node_page.parent.mkdir(parents=True, exist_ok=True)
    existing_bullets = "\n".join(f"- fact {i}" for i in range(40))
    node_page.write_text(
        "---\ntype: hub\nhub: true\ntitle: \"Auth Hub\"\n---\n\n"
        f"# Auth\n\n## Facts\n\n{existing_bullets}\n",
        encoding="utf-8",
    )

    item = "The 41st fact."
    verdict = _concept_verdict(placement="auth", title=None)

    result = wrap_session(
        "# n", [item], "s-split", project="p", verdicts=[verdict],
    )

    assert len(result["updated"]) == 1

    pending = pending_suggestions()
    matching = [
        s for s in pending
        if s["fingerprint"] == "wrap-split:projects/p/knowledge/auth/auth.md"
    ]
    assert len(matching) == 1
    assert matching[0]["kind"] == "structured_action"
    assert matching[0]["payload"]["action"] == "split_concept_node"


def test_counters_partition_correctly(wiki):
    """(g) `created_concept + created_lesson == created`; `concept_updates`
    is a subset of `updated`; `placement_rejected` counts independently."""
    _seed_schema(wiki, "p", "auth/\nbilling/\n")
    node_page = wiki / "projects/p/knowledge/auth/auth.md"
    node_page.parent.mkdir(parents=True, exist_ok=True)
    node_page.write_text(
        "---\ntype: hub\nhub: true\ntitle: \"Auth Hub\"\n---\n\n"
        "# Auth\n\n## Facts\n\n- Existing fact.\n",
        encoding="utf-8",
    )

    concept_new_leaf = "A brand-new topic worth its own node."
    plain_lesson = "A plain global lesson."
    concept_update = "Another fact about auth."

    verdicts = [
        _concept_verdict(placement="topic", title="New Topic"),
        _lesson_verdict(),
        _concept_verdict(placement="auth", title=None),
    ]

    result = wrap_session(
        "# n",
        [concept_new_leaf, plain_lesson, concept_update],
        "s-partition", project="p", verdicts=verdicts,
    )

    assert len(result["applied"]) == 2  # concept new-leaf + plain lesson
    assert len(result["updated"]) == 1  # concept existing-node accretion

    outcome = [
        e for e in collect.read(kind=collect.KIND_DURABLE_OUTCOME)
        if e.get("session") == "s-partition"
    ][-1]

    assert outcome["created_concept"] + outcome["created_lesson"] == outcome["created"]
    assert outcome["created_concept"] == 1
    assert outcome["created_lesson"] == 1
    assert outcome["created"] == 2
    assert outcome["concept_updates"] == 1
    assert outcome["concept_updates"] <= outcome["updated"]
    assert outcome["placement_rejected"] == 0
