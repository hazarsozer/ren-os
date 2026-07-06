"""
Tests for skills.code-map.lib — the Graphify-backed code-map wrapper
(Task 5.2).

The `skills/code-map/` directory name has a hyphen, which isn't a valid
Python package-path segment (`import skills.code-map.lib` is a syntax
error) — so this test loads the module directly from its file path via
`importlib.util`, bypassing dotted-import entirely. Every fake `graphify`
executable used below is written to a tmp bin dir and prepended onto PATH —
nothing here installs graphify or touches the network.

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos.

Run with: uv run pytest tests/skills/code_map/test_wrapper.py -v
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

from lib.ren_paths import state_dir, wiki_root

_MODULE_PATH = Path(__file__).resolve().parents[3] / "skills" / "code-map" / "lib" / "__init__.py"
_spec = importlib.util.spec_from_file_location("_code_map_lib_under_test", _MODULE_PATH)
code_map_lib = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = code_map_lib  # dataclass() needs the module registered before exec
_spec.loader.exec_module(code_map_lib)

CodeMapUnavailable = code_map_lib.CodeMapUnavailable
GRAPHIFY_PIN = code_map_lib.GRAPHIFY_PIN


_SHIM_SCRIPT = '''\
#!/usr/bin/env python3
import os
import sys


def main():
    args = sys.argv[1:]
    if args and args[0] == "--version":
        print(os.environ.get("GRAPHIFY_FAKE_VERSION", "0.9.8"))
        return 0

    if "--output" in args:
        idx = args.index("--output")
        output_dir = args[idx + 1]
        os.makedirs(output_dir, exist_ok=True)
        exit_code = int(os.environ.get("GRAPHIFY_FAKE_EXIT_CODE", "0"))
        if exit_code == 0:
            content = os.environ.get("GRAPHIFY_FAKE_GRAPH_CONTENT", '{"nodes": [], "edges": []}')
            with open(os.path.join(output_dir, "graph.json"), "w", encoding="utf-8") as f:
                f.write(content)
        else:
            sys.stderr.write("simulated graphify failure\\n")
        return exit_code

    sys.stderr.write("unrecognized invocation\\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path, monkeypatch):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / "framework"))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "identity.md").write_text("---\ntype: identity\n---\nHazar\n", encoding="utf-8")
    return root


@pytest.fixture
def no_graphify_on_path(monkeypatch):
    """Guarantee `shutil.which("graphify")` fails, regardless of the host's
    real PATH (in case a dev machine happens to have graphify installed)."""
    monkeypatch.setenv("PATH", "")


@pytest.fixture
def fake_graphify(tmp_path, monkeypatch):
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    shim = bin_dir / "graphify"
    shim.write_text(_SHIM_SCRIPT, encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return shim


@pytest.fixture
def repo_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    # A few "source" files with real, non-trivial content — big enough that a
    # tiny stub graph.json is reliably smaller (baseline >= loaded).
    (root / "a.py").write_text("def alpha():\n    return 1\n" * 40, encoding="utf-8")
    (root / "b.py").write_text("def beta():\n    return 2\n" * 40, encoding="utf-8")
    sub = root / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("def gamma():\n    return 3\n" * 40, encoding="utf-8")
    return root


def _wiki_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and ".ren" not in p.relative_to(root).parts
    }


# --- status: absent ----------------------------------------------------------


def test_status_when_absent_is_fully_degraded_without_raising(wiki, repo_root, no_graphify_on_path):
    result = code_map_lib.status(repo_root)
    assert result.installed is False
    assert result.version is None
    assert result.pinned_ok is False
    assert result.graph_path is None
    assert result.stale is True


# --- status: version / pin -----------------------------------------------


def test_status_pinned_version_is_ok(wiki, repo_root, fake_graphify, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_FAKE_VERSION", "0.9.8")
    result = code_map_lib.status(repo_root)
    assert result.installed is True
    assert result.version == "0.9.8"
    assert result.pinned_ok is True


def test_status_unpinned_version_is_not_ok(wiki, repo_root, fake_graphify, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_FAKE_VERSION", "1.2.0")
    result = code_map_lib.status(repo_root)
    assert result.installed is True
    assert result.version == "1.2.0"
    assert result.pinned_ok is False


# --- build: happy path ---------------------------------------------------


def test_build_runs_shim_and_records_real_byte_size_metric(wiki, repo_root, fake_graphify):
    from lib.instrument import collect

    graph_path = code_map_lib.build(repo_root, session="sess-1")

    assert graph_path.is_file()
    assert graph_path.parent == state_dir() / code_map_lib.DERIVED_DIR

    events = [e for e in collect.read(kind=collect.KIND_CODEMAP_TOKENS) if e.get("event") == "build"]
    assert len(events) == 1
    assert events[0]["graph_bytes"] == graph_path.stat().st_size
    assert events[0]["graph_bytes"] > 0
    assert events[0]["session"] == "sess-1"


# --- build: failure modes --------------------------------------------------


def test_build_missing_binary_raises_with_install_pointer(wiki, repo_root, no_graphify_on_path):
    with pytest.raises(CodeMapUnavailable) as exc_info:
        code_map_lib.build(repo_root, session="sess-1")
    assert "uv tool install" in str(exc_info.value)
    assert "graphify" in str(exc_info.value)


def test_build_nonzero_exit_raises_codemap_unavailable(wiki, repo_root, fake_graphify, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_FAKE_EXIT_CODE", "2")
    with pytest.raises(CodeMapUnavailable):
        code_map_lib.build(repo_root, session="sess-1")


# --- staleness ---------------------------------------------------------------


def test_staleness_detected_and_cleared_by_rebuild(wiki, repo_root, fake_graphify):
    code_map_lib.build(repo_root, session="sess-1")
    status_after_build = code_map_lib.status(repo_root)
    assert status_after_build.stale is False

    # Touch a source file so its mtime is unambiguously newer than graph.json.
    time.sleep(0.05)
    stale_file = repo_root / "a.py"
    stale_file.write_text(stale_file.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    os.utime(stale_file, None)  # bump mtime to "now"

    status_after_edit = code_map_lib.status(repo_root)
    assert status_after_edit.stale is True

    code_map_lib.build(repo_root, session="sess-2")
    status_after_rebuild = code_map_lib.status(repo_root)
    assert status_after_rebuild.stale is False


# --- consume -------------------------------------------------------------


def test_consume_records_tokens_loaded_and_baseline(wiki, repo_root, fake_graphify):
    from lib.instrument import collect

    code_map_lib.build(repo_root, session="sess-1")
    result = code_map_lib.consume(repo_root, session="sess-1")

    assert result["tokens_loaded"] > 0
    assert result["tokens_baseline"] > 0
    assert result["tokens_baseline"] >= result["tokens_loaded"]

    events = [e for e in collect.read(kind=collect.KIND_CODEMAP_TOKENS) if e.get("event") == "consume"]
    assert len(events) == 1
    assert events[0]["tokens_loaded"] == result["tokens_loaded"]
    assert events[0]["tokens_baseline"] == result["tokens_baseline"]
    assert events[0]["session"] == "sess-1"


def test_consume_on_absent_graph_raises_codemap_unavailable(wiki, repo_root):
    with pytest.raises(CodeMapUnavailable):
        code_map_lib.consume(repo_root, session="sess-1")


def test_consume_on_stale_graph_raises_codemap_unavailable(wiki, repo_root, fake_graphify):
    code_map_lib.build(repo_root, session="sess-1")

    time.sleep(0.05)
    stale_file = repo_root / "b.py"
    stale_file.write_text(stale_file.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    os.utime(stale_file, None)

    with pytest.raises(CodeMapUnavailable):
        code_map_lib.consume(repo_root, session="sess-1")


# --- nothing written under the wiki page tree -------------------------------


def test_build_and_consume_never_write_under_wiki_page_tree(wiki, repo_root, fake_graphify):
    before = _wiki_snapshot(wiki)

    code_map_lib.build(repo_root, session="sess-1")
    code_map_lib.consume(repo_root, session="sess-1")

    after = _wiki_snapshot(wiki)
    assert after == before
