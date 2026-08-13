"""Run with: uv run pytest tests/skills/install/test_graph_config.py -v"""
import importlib
import json

install_lib = importlib.import_module("skills.install.lib")


def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    import lib.ren_paths as rp
    root = rp.wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_writes_when_absent(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    assert install_lib.write_default_graph_config() is True
    cfg = json.loads((root / ".obsidian" / "graph.json").read_text())
    assert cfg["search"] == "-path:raw -path:archive"
    assert [g["query"] for g in cfg["colorGroups"]][0] == '"ren-quarantine"'


def test_never_clobbers_existing(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch)
    dest = root / ".obsidian" / "graph.json"
    dest.parent.mkdir(parents=True)
    dest.write_text('{"search": "user-tuned"}', encoding="utf-8")
    assert install_lib.write_default_graph_config() is False
    assert json.loads(dest.read_text())["search"] == "user-tuned"


def test_okabe_ito_only(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch)
    okabe_ito = {0x0072B2, 0x009E73, 0x56B4E9, 0xE69F00, 0xD55E00, 0xCC79A7}
    for group in install_lib.DEFAULT_GRAPH_CONFIG["colorGroups"]:
        assert group["color"]["rgb"] in okabe_ito


def test_skeleton_still_has_no_obsidian_dir():
    # regression guard alongside tests/test_obsidian_invariant.py
    from pathlib import Path
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    WIKI_SKELETON = REPO_ROOT / "wiki-skeleton"
    assert not list(WIKI_SKELETON.rglob(".obsidian"))
