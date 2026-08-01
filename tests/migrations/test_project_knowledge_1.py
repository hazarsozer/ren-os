"""
End-to-end tests for the project-knowledge-1 migration (issue #20, 0.6.2).

Relocates flat `.md` files under `projects/<slug>/` (everything the pre-0.6.2
taxonomy had no home for) into the sanctioned `projects/<slug>/knowledge/`
subtree, normalizes their frontmatter to `type: project-knowledge`, and
rewrites L2 Decision-map pointers that referenced the old paths.

Like `trust-backfill-1` and `queue-governance-2-to-3`, this migration walks
state directly rather than following the per-page-type `migrate.sh` chain —
see its README for the shape decision.

Run with: uv run pytest tests/migrations/test_project_knowledge_1.py -v
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from lib.ren_paths import state_dir, wiki_root

_MIGRATE_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "project-knowledge-1" / "migrate.py"
)


def _load_migrate():
    spec = importlib.util.spec_from_file_location("_project_knowledge_1_migrate", _MIGRATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wiki(monkeypatch, tmp_path):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _map_text(slug: str, pointers: list[str]) -> str:
    lines = [
        "---",
        "type: l2-map",
        "schema_version: 1",
        f"project: {slug}",
        "---",
        f"# {slug} — knowledge map",
        "## Knowledge",
        "## Decision map",
        "_All pointer paths are relative to the wiki root, not this file._",
        *pointers,
        "## Log",
        "- 2026-01-01: ingested",
    ]
    return "\n".join(lines) + "\n"


def _flux(wiki: Path) -> Path:
    """The founder's Flux-shaped wiki: a map, an overview, an L1 session, and
    two flat pages that had nowhere sanctioned to live."""
    project = wiki / "projects" / "flux"
    _write(project / "map.md", _map_text("flux", ["- [stack] → projects/flux/stack.md (w-abc)"]))
    _write(project / "overview.md", "---\ntype: overview\n---\n# flux\nOrientation.\n")
    _write(project / "l1" / "session-2026-07-31.md", "---\ntype: l1\n---\nsession notes\n")
    _write(
        project / "stack.md",
        '---\nren_writer: "llm-auto"\nren_trust: "foreign"\n---\nRust + wgpu.\n',
    )
    _write(project / "conventions.md", "No frontmatter at all.\n")
    return project


# ----------------------------------------------------------------- dry run


def test_dry_run_is_the_default_and_writes_nothing(wiki, capsys):
    project = _flux(wiki)
    before = (project / "stack.md").read_text(encoding="utf-8")

    assert _load_migrate().main([]) == 0

    assert (project / "stack.md").read_text(encoding="utf-8") == before
    assert not (project / "knowledge").exists()
    out = capsys.readouterr().out
    assert "WOULD MOVE" in out and "DRY RUN" in out
    # pointer rewrite is reported but not performed
    assert "projects/flux/stack.md (w-abc)" in (project / "map.md").read_text(encoding="utf-8")


def test_no_projects_dir_is_a_clean_noop(wiki, capsys):
    assert _load_migrate().main([]) == 0
    assert "nothing to do" in capsys.readouterr().out


# ------------------------------------------------------------------- apply


def test_apply_moves_flat_pages_and_leaves_sanctioned_ones(wiki):
    project = _flux(wiki)

    assert _load_migrate().main(["--apply"]) == 0

    assert not (project / "stack.md").exists()
    assert not (project / "conventions.md").exists()
    assert (project / "knowledge" / "stack.md").is_file()
    assert (project / "knowledge" / "conventions.md").is_file()
    # sanctioned taxonomy untouched
    assert (project / "map.md").is_file()
    assert (project / "overview.md").is_file()
    assert (project / "l1" / "session-2026-07-31.md").is_file()


def test_apply_normalizes_frontmatter_and_preserves_body_and_provenance(wiki):
    project = _flux(wiki)

    _load_migrate().main(["--apply"])

    text = (project / "knowledge" / "stack.md").read_text(encoding="utf-8")
    assert "type: project-knowledge" in text
    assert "schema_version: 1" in text
    assert "project: flux" in text
    # provenance stamps survive verbatim
    assert 'ren_writer: "llm-auto"' in text
    assert 'ren_trust: "foreign"' in text
    # body byte-for-byte
    assert text.endswith("---\nRust + wgpu.\n")


def test_apply_adds_frontmatter_to_a_page_that_had_none(wiki):
    project = _flux(wiki)

    _load_migrate().main(["--apply"])

    text = (project / "knowledge" / "conventions.md").read_text(encoding="utf-8")
    assert text == "---\ntype: project-knowledge\nschema_version: 1\nproject: flux\n---\nNo frontmatter at all.\n"


def test_apply_rewrites_l2_pointers_to_the_new_path(wiki):
    project = _flux(wiki)

    _load_migrate().main(["--apply"])

    map_text = (project / "map.md").read_text(encoding="utf-8")
    assert "- [stack] → projects/flux/knowledge/stack.md (w-abc)" in map_text


def test_pointer_rewrite_leaves_repo_refs_and_unrelated_targets_alone(wiki):
    project = wiki / "projects" / "flux"
    _write(
        project / "map.md",
        _map_text(
            "flux",
            [
                "- [entrypoint] → repo:flux:src/main.rs (w-1)",
                "- [stack] → projects/flux/stack.md (w-2)",
                "- [general] → decisions/some-decision.md (w-3)",
            ],
        ),
    )
    _write(project / "stack.md", "Rust.\n")

    _load_migrate().main(["--apply"])

    map_text = (project / "map.md").read_text(encoding="utf-8")
    assert "- [entrypoint] → repo:flux:src/main.rs (w-1)" in map_text
    assert "- [stack] → projects/flux/knowledge/stack.md (w-2)" in map_text
    assert "- [general] → decisions/some-decision.md (w-3)" in map_text


def test_collision_leaves_the_flat_file_in_place(wiki, capsys):
    project = _flux(wiki)
    _write(project / "knowledge" / "stack.md", "Pre-existing knowledge page.\n")

    _load_migrate().main(["--apply"])

    assert (project / "stack.md").is_file()  # untouched
    assert (project / "knowledge" / "stack.md").read_text(encoding="utf-8") == "Pre-existing knowledge page.\n"
    assert "COLLISION" in capsys.readouterr().out
    # the map pointer is NOT rewritten for a page that didn't move
    assert "projects/flux/stack.md (w-abc)" in (project / "map.md").read_text(encoding="utf-8")


def test_second_run_is_a_noop(wiki, capsys):
    _flux(wiki)
    _load_migrate().main(["--apply"])
    capsys.readouterr()

    assert _load_migrate().main(["--apply"]) == 0
    out = capsys.readouterr().out
    assert "0 page(s) moved" in out
    assert "0 pointer(s) rewritten" in out


def test_moves_are_journaled(wiki):
    _flux(wiki)

    _load_migrate().main(["--apply"])

    journal = state_dir() / "migrations" / "project-knowledge-1.jsonl"
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    moved = {(r["from"], r["to"]) for r in records}
    assert ("projects/flux/stack.md", "projects/flux/knowledge/stack.md") in moved
    assert ("projects/flux/conventions.md", "projects/flux/knowledge/conventions.md") in moved
    assert all(r["slug"] == "flux" and r["ts"] for r in records)


def test_multiple_projects_are_each_scoped_to_their_own_slug(wiki):
    _write(wiki / "projects" / "a" / "notes.md", "a notes\n")
    _write(wiki / "projects" / "b" / "notes.md", "b notes\n")

    _load_migrate().main(["--apply"])

    assert "project: a" in (wiki / "projects" / "a" / "knowledge" / "notes.md").read_text(encoding="utf-8")
    assert "project: b" in (wiki / "projects" / "b" / "knowledge" / "notes.md").read_text(encoding="utf-8")


def test_registered_page_type_matches_the_schema_registry(wiki):
    import importlib

    registry = importlib.import_module("skills.wiki-migration.lib").load_registry()
    migrate = _load_migrate()
    entry = registry["page_types"][migrate.PAGE_TYPE]
    assert entry["current"] == migrate.SCHEMA_VERSION
    assert migrate.PAGE_TYPE == "project-knowledge"


def test_reports_missing_schema_md_without_fabricating_one(wiki, capsys):
    """Issue #20 amendment: the run reports a project missing its
    `schema.md` (the taxonomy is the model's/human's to write — a migration
    script cannot invent it) and never creates the file itself."""
    _flux(wiki)

    _load_migrate().main([])
    out = capsys.readouterr().out
    assert "projects/flux: no schema.md" in out
    assert not (wiki / "projects" / "flux" / "schema.md").exists()

    _load_migrate().main(["--apply"])
    out = capsys.readouterr().out
    assert "projects/flux: no schema.md" in out
    assert not (wiki / "projects" / "flux" / "schema.md").exists()


def test_project_with_schema_md_is_not_flagged(wiki, capsys):
    _flux(wiki)
    _write(
        wiki / "projects" / "flux" / "schema.md",
        "---\ntype: project-schema\nschema_version: 1\nproject: flux\n---\n# Schema\n",
    )

    _load_migrate().main([])
    out = capsys.readouterr().out
    assert "no schema.md" not in out
