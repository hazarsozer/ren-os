import json
import subprocess
from pathlib import Path

import pytest

from lib.codemap import adapter_leanctx as adapter

FIXTURE = Path(__file__).parent / "fixtures" / "leanctx-sample-output.json"


def _raw_signatures() -> str:
    # The spike recorded lean-ctx's real `read -m signatures` text under this key.
    return json.loads(FIXTURE.read_text())["_raw_signatures_output"]


def test_parse_signatures_to_symbols():
    syms = adapter._symbols_from_signatures(_raw_signatures(), "lib/sf_paths.py")
    assert syms, "fixture should yield symbols"
    fv = next(s for s in syms if s.name == "framework_version")
    assert fv.file == "lib/sf_paths.py"
    assert fv.start_line == 49 and fv.end_line == 82
    assert fv.kind == "function"
    assert "framework_version(" in fv.signature


def test_class_without_parens_signature_has_no_parentheses():
    text = "class pub Foo @L1-40"
    syms = adapter._symbols_from_signatures(text, "lib/foo.py")
    assert len(syms) == 1
    assert syms[0].signature == "Foo"


def test_run_parses_stubbed_output(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    return 1\n")
    raw = _raw_signatures()

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 0
            stdout = raw.encode()
            stderr = b""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    syms = adapter.run_leanctx(tmp_path)
    assert any(s.name == "framework_version" for s in syms)


def test_missing_binary_raises_engine_unavailable(monkeypatch, tmp_path):
    (tmp_path / "a.py").write_text("def f(): return 1\n")

    def boom(cmd, **kwargs):
        raise FileNotFoundError("lean-ctx")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(adapter.EngineUnavailable):
        adapter.run_leanctx(tmp_path)
