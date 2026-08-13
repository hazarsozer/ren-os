"""Run with: uv run pytest tests/migrations/test_folder_note_hubs_1_verify.py -v"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY = REPO_ROOT / "migrations" / "folder-note-hubs-1" / "verify.py"
MIGRATE = REPO_ROOT / "migrations" / "folder-note-hubs-1" / "migrate.py"


def _load(script):
    spec = importlib.util.spec_from_file_location(script.stem + "_fnh", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mk_wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


GOOD_HUB = ("---\ntype: project-knowledge\nschema_version: 1\nhub: true\n---\n# Research\n")
GOOD_MAP = ("---\ntype: l2-map\nschema_version: 2\n---\n## Decision map\n"
            "- [Research](projects/demo/knowledge/research/research.md) (w-01ABC)\n")


def _migrated_wiki(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/research.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(GOOD_HUB, encoding="utf-8")
    (root / "projects/demo/map.md").write_text(GOOD_MAP, encoding="utf-8")
    return root


def test_clean_migrated_wiki_passes(tmp_path, monkeypatch):
    _migrated_wiki(tmp_path, monkeypatch)
    assert _load(VERIFY).main() == 0


def test_leftover_index_md_fails(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    stray = root / "projects/demo/knowledge/design/index.md"
    stray.parent.mkdir(parents=True)
    stray.write_text(GOOD_HUB, encoding="utf-8")
    assert _load(VERIFY).main() == 1


def test_stale_hub_link_fails_but_unrelated_dangler_passes(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    page = root / "projects/demo/knowledge/research/note.md"
    page.write_text("---\ntype: project-knowledge\n---\n[x](missing-leaf.md)\n", encoding="utf-8")
    assert _load(VERIFY).main() == 0            # unrelated dangler: not this migration's problem
    page.write_text("---\ntype: project-knowledge\n---\n[x](../research/index.md)\n", encoding="utf-8")
    assert _load(VERIFY).main() == 1            # stale hub link: missed rewrite


def test_misnamed_hub_flag_fails(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    bad = root / "projects/demo/knowledge/design/wrong-name.md"
    bad.parent.mkdir(parents=True)
    bad.write_text(GOOD_HUB, encoding="utf-8")
    assert _load(VERIFY).main() == 1


def test_broken_pointer_line_fails(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    (root / "projects/demo/map.md").write_text(
        GOOD_MAP + "- [broken](projects/demo/knowledge/research/research.md (w-01\n",
        encoding="utf-8")
    assert _load(VERIFY).main() == 1


def test_end_to_end_migrate_then_verify(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(GOOD_HUB, encoding="utf-8")
    (root / "projects/demo/map.md").write_text(
        GOOD_MAP.replace("research/research.md", "research/index.md"), encoding="utf-8")
    assert _load(MIGRATE).main() == 0
    assert _load(VERIFY).main() == 0


def test_project_named_knowledge_not_false_positive(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    page = root / "projects/knowledge/notes/index.md"
    page.parent.mkdir(parents=True)
    page.write_text("---\ntype: project-knowledge\nhub: true\n---\n# Notes index\n", encoding="utf-8")
    other = root / "projects/knowledge/other.md"
    other.write_text("---\ntype: project-knowledge\n---\n[n](notes/index.md)\n", encoding="utf-8")
    assert _load(VERIFY).main() == 0


def test_leaf_named_like_index_suffix_not_false_positive(tmp_path, monkeypatch):
    root = _migrated_wiki(tmp_path, monkeypatch)
    leaf = root / "projects/demo/knowledge/research/specs-index.md"
    leaf.write_text("---\ntype: project-knowledge\n---\n# Specs\n", encoding="utf-8")
    (root / "projects/demo/map.md").write_text(
        GOOD_MAP + "- [Specs](projects/demo/knowledge/research/specs-index.md) (w-01XYZ)\n",
        encoding="utf-8")
    assert _load(VERIFY).main() == 0


def test_registry_lists_migration():
    import json
    registry = json.loads((REPO_ROOT / "skills/wiki-migration/schemas.json").read_text())
    assert "folder-note-hubs-1" in registry["global_migrations"]["migrations"]
