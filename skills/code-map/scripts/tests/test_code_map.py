import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location(
    "code_map_cli", ROOT / "skills/code-map/scripts/code_map.py")
cli = importlib.util.module_from_spec(spec)
sys.modules["code_map_cli"] = cli
spec.loader.exec_module(cli)


def test_graceful_when_engine_unavailable(monkeypatch, capsys, tmp_path):
    from lib.codemap.adapter_leanctx import EngineUnavailable
    monkeypatch.setattr(cli.sf_paths, "code_map_path", lambda n: tmp_path / "nope.md")  # no cache -> generate path
    monkeypatch.setattr(cli, "generate", lambda *a, **k: (_ for _ in ()).throw(EngineUnavailable("no bin")))
    rc = cli.main([str(tmp_path), "--name", "demo"])
    assert rc == 0                                   # graceful, not a crash
    assert "lean-ctx" in capsys.readouterr().out.lower()


def test_generate_prints_cache_path(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli.sf_paths, "code_map_path", lambda n: tmp_path / "demo.md")  # no cache yet
    monkeypatch.setattr(cli, "generate",
                        lambda root, project_name: __import__("types").SimpleNamespace(symbols=(1, 2)))
    rc = cli.main([str(tmp_path), "--name", "demo"])
    assert rc == 0
    assert "demo.md" in capsys.readouterr().out


def test_reports_stale_when_cache_exists(monkeypatch, capsys, tmp_path):
    from lib.codemap.model import StaleReport
    cache = tmp_path / "demo.md"
    cache.write_text("# Code-map: x\n")                      # cache exists -> staleness path
    monkeypatch.setattr(cli.sf_paths, "code_map_path", lambda n: cache)
    monkeypatch.setattr(cli, "check_staleness",
                        lambda name, root: StaleReport(stale=True, changed=("a.py",), added=(), deleted=()))
    rc = cli.main([str(tmp_path), "--name", "demo"])         # no --refresh
    assert rc == 0
    assert "STALE" in capsys.readouterr().out
