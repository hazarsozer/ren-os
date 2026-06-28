from pathlib import Path

from lib.codemap import core
from lib.codemap.model import Symbol


def test_generate_builds_map_and_writes_cache(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    monkeypatch.setattr(core, "run_leanctx",
                        lambda root: [Symbol("f", "function", "a.py", 1, 2, "def f()")])
    cache = tmp_path / "out.md"
    monkeypatch.setattr(core.sf_paths, "code_map_path", lambda name: cache)
    cm = core.generate(tmp_path, project_name="demo")
    assert cm.symbols[0].name == "f"
    assert "a.py" in cm.file_hashes                 # hashed real file
    assert cache.exists() and "# Code-map:" in cache.read_text()


def test_load_cached_roundtrips_text(monkeypatch, tmp_path):
    cache = tmp_path / "out.md"
    cache.write_text("# Code-map: x\n")
    monkeypatch.setattr(core.sf_paths, "code_map_path", lambda name: cache)
    assert core.load_cached("demo").startswith("# Code-map: x")


def test_generate_writes_sidecar_and_check_staleness(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    monkeypatch.setattr(core, "run_leanctx",
                        lambda root: [Symbol("f", "function", "a.py", 1, 2, "def f()")])
    monkeypatch.setattr(core.sf_paths, "code_map_path", lambda name: tmp_path / "demo.md")
    core.generate(tmp_path, project_name="demo")
    assert (tmp_path / "demo.json").exists()                  # sidecar carries the hashes
    assert core.check_staleness("demo", tmp_path).stale is False
    (tmp_path / "a.py").write_text("def f():\n    return 2\n")
    assert core.check_staleness("demo", tmp_path).changed == ("a.py",)


def test_generate_then_fresh_with_symbolless_file(monkeypatch, tmp_path):
    # A source file with no symbols (e.g. __init__.py) must NOT make a fresh map stale.
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    (tmp_path / "__init__.py").write_text("")               # source file, no symbols
    monkeypatch.setattr(core, "run_leanctx",
                        lambda root: [Symbol("f", "function", "a.py", 1, 2, "def f()")])
    monkeypatch.setattr(core.sf_paths, "code_map_path", lambda name: tmp_path / "demo.md")
    core.generate(tmp_path, project_name="demo")
    assert core.check_staleness("demo", tmp_path).stale is False   # was True before the fix


def test_dependencies_round_trip(tmp_path, monkeypatch):
    from lib.codemap import core
    from lib.codemap.model import CodeMap
    cm = CodeMap(project_path="/p", generated_at="t", git_commit="abc",
                 file_hashes={"a.py": "h"}, symbols=(), dependencies={"a.py": ("b.py",)})
    text = core._serialize(cm)
    assert core._deserialize(text).dependencies == {"a.py": ("b.py",)}


def test_deserialize_legacy_without_dependencies():
    from lib.codemap import core
    legacy = '{"project_path":"/p","generated_at":"t","git_commit":"","file_hashes":{},"symbols":[]}'
    assert core._deserialize(legacy).dependencies == {}


def test_load_fresh_regenerates_when_stale(tmp_path, monkeypatch):
    from lib.codemap import core
    calls = {"n": 0}
    fake = object()
    monkeypatch.setattr(core, "load_cached_map", lambda name: _StubMap())
    monkeypatch.setattr(core, "is_stale", lambda cm, root: _StaleTrue())
    monkeypatch.setattr(core, "generate", lambda root, *, project_name: calls.__setitem__("n", calls["n"]+1) or fake)
    out = core.load_fresh("proj", tmp_path)
    assert out is fake and calls["n"] == 1   # regenerated because stale


def test_load_fresh_uses_cache_when_fresh(tmp_path, monkeypatch):
    from lib.codemap import core
    cached = _StubMap()
    monkeypatch.setattr(core, "load_cached_map", lambda name: cached)
    monkeypatch.setattr(core, "is_stale", lambda cm, root: _StaleFalse())
    monkeypatch.setattr(core, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not regenerate")))
    assert core.load_fresh("proj", tmp_path) is cached


class _StubMap: pass
class _StaleTrue:
    def __bool__(self): return True
class _StaleFalse:
    def __bool__(self): return False
