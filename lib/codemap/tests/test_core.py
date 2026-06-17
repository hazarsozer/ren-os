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
