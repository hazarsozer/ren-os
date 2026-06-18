import dataclasses

from lib.codemap.model import CodeMap, StaleReport, Symbol


def test_symbol_is_frozen():
    s = Symbol(name="f", kind="function", file="a.py", start_line=1, end_line=3, signature="def f()")
    assert s.start_line == 1
    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        s.name = "g"  # type: ignore[misc]


def test_codemap_holds_symbols_and_hashes():
    s = Symbol(name="f", kind="function", file="a.py", start_line=1, end_line=3, signature="def f()")
    cm = CodeMap(project_path="/p", generated_at="2026-06-17T00:00:00Z",
                 git_commit="abc1234", file_hashes={"a.py": "deadbeef"}, symbols=(s,))
    assert cm.symbols[0].file == "a.py"
    assert cm.file_hashes["a.py"] == "deadbeef"


def test_stale_report_truthiness():
    assert bool(StaleReport(stale=True, changed=("a.py",), added=(), deleted=())) is True
    assert bool(StaleReport(stale=False, changed=(), added=(), deleted=())) is False
