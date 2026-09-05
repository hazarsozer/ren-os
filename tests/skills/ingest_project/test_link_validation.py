"""Spec 2026-09-04 §7 — ingest validates the link convention on drafted
leaves and reports errors WITHOUT dropping the leaf."""

from __future__ import annotations

import importlib

import pytest

ingest_lib = importlib.import_module("skills.ingest-project.lib")

SCHEMA = """---
type: project-schema
---
# Schema

```taxonomy
architecture/
```
"""
HUBS = {"architecture": "---\ntype: hub\nhub: true\n---\n# Architecture\n"}


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    root.mkdir()
    monkeypatch.setenv("REN_WIKI_ROOT", str(root))
    monkeypatch.setenv("REN_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(ingest_lib, "require_backup", lambda *a, **k: None)
    return root


GOOD_LEAF = {
    "name": "architecture/write-door.md",
    "body": "---\ntype: project-knowledge\n---\n# Write Door\n\n"
            "Parent: [[architecture]]\n\nThe queue.\n\n"
            "## Related\n- [[journal]] — lineage\n",
}
NO_PARENT_LEAF = {
    "name": "architecture/journal.md",
    "body": "---\ntype: project-knowledge\n---\n# Journal\n\nrecords writes.\n",
}


def test_clean_leaves_report_no_link_errors(wiki):
    result = ingest_lib.ingest(
        "demo", ["a fact"], [], "s1",
        schema_page=SCHEMA, hub_pages=HUBS, leaf_pages=[GOOD_LEAF],
    )
    assert result["link_errors"] == []


def test_leaf_without_parent_is_reported_but_still_written(wiki):
    result = ingest_lib.ingest(
        "demo", ["a fact"], [], "s1",
        schema_page=SCHEMA, hub_pages=HUBS, leaf_pages=[NO_PARENT_LEAF],
    )
    errors = {e["page"]: e["error"] for e in result["link_errors"]}
    assert "projects/demo/knowledge/architecture/journal.md" in errors
    assert "Parent:" in errors["projects/demo/knowledge/architecture/journal.md"]
    # Missing links are lint's job to find, never a reason to lose knowledge.
    assert (wiki / "projects/demo/knowledge/architecture/journal.md").is_file()


def test_leaf_without_related_is_reported_too(wiki):
    leaf = {
        "name": "architecture/x.md",
        "body": "# X\n\nParent: [[architecture]]\n\nbody.\n",
    }
    result = ingest_lib.ingest(
        "demo", ["f"], [], "s1", schema_page=SCHEMA, hub_pages=HUBS, leaf_pages=[leaf]
    )
    errors = {e["page"]: e["error"] for e in result["link_errors"]}
    assert "Related" in errors["projects/demo/knowledge/architecture/x.md"]


def test_link_errors_key_is_always_present_on_a_legacy_call(wiki):
    result = ingest_lib.ingest("demo", ["a fact"], [], "s1")
    assert result["link_errors"] == []


def test_existing_leaf_is_queued_as_an_update(wiki):
    """Controller ruling: the leaf write uses `_page_op`, like every other
    write site in `ingest()` — a re-ingest UPDATEs, never a second ADD."""
    leaf_abs = wiki / "projects/demo/knowledge/architecture/write-door.md"
    leaf_abs.parent.mkdir(parents=True)
    leaf_abs.write_text("# Write Door\n\nold body.\n", encoding="utf-8")

    seen: list[str] = []
    real = ingest_lib.propose_and_apply

    def _spy(proposal, *a, **k):
        seen.append(f"{proposal.op}:{proposal.page}")
        return real(proposal, *a, **k)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(ingest_lib, "propose_and_apply", _spy)
    try:
        ingest_lib.ingest(
            "demo", ["a fact"], [], "s1",
            schema_page=SCHEMA, hub_pages=HUBS, leaf_pages=[GOOD_LEAF],
        )
    finally:
        monkey.undo()

    assert "UPDATE:projects/demo/knowledge/architecture/write-door.md" in seen
