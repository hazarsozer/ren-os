import importlib
from pathlib import Path

import lib.sf_paths as sf_paths


def test_code_map_cache_dir_honors_env(monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/tmp/plugdata")
    importlib.reload(sf_paths)
    assert sf_paths.code_map_cache_dir() == Path("/tmp/plugdata/code-maps")


def test_code_map_cache_dir_default(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    importlib.reload(sf_paths)
    expected = Path.home() / ".claude/plugins/data/ren-ren-os/code-maps"
    assert sf_paths.code_map_cache_dir() == expected


def test_code_map_path_uses_project_name(monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/tmp/plugdata")
    importlib.reload(sf_paths)
    assert sf_paths.code_map_path("demo-api") == Path("/tmp/plugdata/code-maps/demo-api.md")
