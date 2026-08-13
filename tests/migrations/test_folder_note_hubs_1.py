"""Tests for migrations/folder-note-hubs-1. Run with: uv run pytest tests/migrations/test_folder_note_hubs_1.py -v"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "migrations" / "folder-note-hubs-1" / "migrate.py"


def _load():
    spec = importlib.util.spec_from_file_location("folder_note_hubs_1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HUB = """---
type: project-knowledge
schema_version: 1
project: demo
title: "Research"
hub: true
---

# Research

- [Body Doubling](body-doubling.md)
"""

HUB_NO_FLAG = HUB.replace("hub: true\n", "")


def _mk_wiki(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_rename_map_finds_knowledge_hubs(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(HUB, encoding="utf-8")
    nested = root / "projects/demo/knowledge/research/interventions/index.md"
    nested.parent.mkdir(parents=True)
    nested.write_text(HUB, encoding="utf-8")
    mod = _load()
    renames = mod.build_rename_map(root)
    assert renames[hub.resolve()] == hub.parent.resolve() / "research.md"
    assert renames[nested.resolve()] == nested.parent.resolve() / "interventions.md"


def test_rename_map_skips_root_index_raw_and_hidden(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    (root / "index.md").write_text("# Root\n", encoding="utf-8")
    raw = root / "projects/demo/raw/knowledge/x/index.md"
    raw.parent.mkdir(parents=True)
    raw.write_text("raw copy", encoding="utf-8")
    snap = root / ".ren/snapshots/w-1/projects/demo/knowledge/research/index.md"
    snap.parent.mkdir(parents=True)
    snap.write_text(HUB, encoding="utf-8")
    mod = _load()
    assert mod.build_rename_map(root) == {}


def test_rename_map_collision_left_alone(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(HUB, encoding="utf-8")
    (hub.parent / "research.md").write_text("occupied", encoding="utf-8")
    mod = _load()
    assert mod.build_rename_map(root) == {}


def test_stamp_hub_true_inserts_when_missing():
    mod = _load()
    stamped = mod.stamp_hub_true(HUB_NO_FLAG)
    assert "hub: true" in stamped.split("---\n")[1]
    assert mod.stamp_hub_true(HUB) == HUB  # idempotent when present


def test_main_renames_and_stamps(tmp_path, monkeypatch, capsys):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(HUB_NO_FLAG, encoding="utf-8")
    mod = _load()
    assert mod.main() == 0
    assert capsys.readouterr().out.strip().endswith("OK")
    new = hub.parent / "research.md"
    assert not hub.exists() and new.exists()
    assert "hub: true" in new.read_text(encoding="utf-8")


def test_main_skips_when_already_migrated(tmp_path, monkeypatch, capsys):
    root = _mk_wiki(tmp_path, monkeypatch)
    done = root / "projects/demo/knowledge/research/research.md"
    done.parent.mkdir(parents=True)
    done.write_text(HUB, encoding="utf-8")
    mod = _load()
    assert mod.main() == 0
    assert capsys.readouterr().out.startswith("SKIP:")


MAP = """---
type: l2-map
schema_version: 2
project: demo
---
# demo — map

## Decision map
- [Research](projects/demo/knowledge/research/index.md) (w-01ABC)
- [External](repo:demo:src/main.py) (w-01DEF)

## Sessions
- [session-1](projects/demo/l1/session-1.md)
"""

LEAF = """---
type: project-knowledge
schema_version: 1
project: demo
---
# Body Doubling

Back to the [hub](index.md), or [up](../research/index.md#anchor).
See also [interventions](interventions/index.md).
"""


def _full_wiki(tmp_path, monkeypatch):
    root = _mk_wiki(tmp_path, monkeypatch)
    hub = root / "projects/demo/knowledge/research/index.md"
    hub.parent.mkdir(parents=True)
    hub.write_text(HUB, encoding="utf-8")
    nested = root / "projects/demo/knowledge/research/interventions/index.md"
    nested.parent.mkdir(parents=True)
    nested.write_text(HUB, encoding="utf-8")
    (root / "projects/demo/knowledge/research/body-doubling.md").write_text(LEAF, encoding="utf-8")
    (root / "projects/demo/map.md").write_text(MAP, encoding="utf-8")
    return root


def test_rewrite_root_relative_pointer(tmp_path, monkeypatch):
    root = _full_wiki(tmp_path, monkeypatch)
    mod = _load()
    renames = mod.build_rename_map(root)
    text, n = mod.rewrite_links(MAP, root / "projects/demo/map.md", root, renames)
    assert "- [Research](projects/demo/knowledge/research/research.md) (w-01ABC)" in text
    assert "repo:demo:src/main.py" in text          # repo pointer untouched
    assert "l1/session-1.md" in text                # non-hub link untouched
    assert n == 1


def test_rewrite_file_relative_variants_preserve_style_and_anchor(tmp_path, monkeypatch):
    root = _full_wiki(tmp_path, monkeypatch)
    mod = _load()
    renames = mod.build_rename_map(root)
    leaf = root / "projects/demo/knowledge/research/body-doubling.md"
    text, n = mod.rewrite_links(LEAF, leaf, root, renames)
    assert "[hub](research.md)" in text
    assert "[up](../research/research.md#anchor)" in text
    assert "[interventions](interventions/interventions.md)" in text
    assert n == 3


def test_main_full_run_rewrites_then_renames(tmp_path, monkeypatch, capsys):
    root = _full_wiki(tmp_path, monkeypatch)
    mod = _load()
    assert mod.main() == 0
    map_text = (root / "projects/demo/map.md").read_text(encoding="utf-8")
    assert "research/research.md" in map_text and "research/index.md" not in map_text
    assert (root / "projects/demo/knowledge/research/research.md").exists()
    assert (root / "projects/demo/knowledge/research/interventions/interventions.md").exists()


def test_schema_md_convention_line_rewritten(tmp_path, monkeypatch):
    root = _full_wiki(tmp_path, monkeypatch)
    schema = root / "projects/demo/schema.md"
    schema.write_text(
        "---\ntype: project-schema\nschema_version: 1\n---\n"
        "# Schema\n\n- Hub files are always named `index.md`.\n",
        encoding="utf-8",
    )
    mod = _load()
    assert mod.main() == 0
    text = schema.read_text(encoding="utf-8")
    assert "always named `index.md`" not in text
    assert "folder notes" in text


def test_second_run_is_noop_skip(tmp_path, monkeypatch, capsys):
    root = _full_wiki(tmp_path, monkeypatch)
    mod = _load()
    assert mod.main() == 0
    before = {p: p.read_text(encoding="utf-8") for p in root.rglob("*.md")}
    assert mod.main() == 0
    assert capsys.readouterr().out.strip().endswith("SKIP: no knowledge hubs named index.md")
    assert {p: p.read_text(encoding="utf-8") for p in root.rglob("*.md")} == before
