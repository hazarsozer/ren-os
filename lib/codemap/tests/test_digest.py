from lib.codemap.digest import render_digest
from lib.codemap.model import CodeMap, Symbol


def _map():
    syms = (
        Symbol("alpha", "function", "pkg/a.py", 10, 20, "def alpha(x)"),
        Symbol("Beta", "class", "pkg/b.py", 1, 40, "class Beta"),
    )
    return CodeMap(project_path="/p/demo", generated_at="2026-06-17T12:00:00Z",
                   git_commit="abc1234", file_hashes={"pkg/a.py": "h1", "pkg/b.py": "h2"}, symbols=syms)


def test_digest_has_header_and_verify_notice():
    out = render_digest(_map())
    assert "# Code-map: /p/demo" in out
    assert "abc1234" in out and "2026-06-17T12:00:00Z" in out
    assert "verify" in out.lower()  # trust-but-verify discipline stated


def test_digest_groups_by_file_with_line_ranges():
    out = render_digest(_map())
    assert "## pkg/a.py" in out and "## pkg/b.py" in out
    assert "alpha" in out and "L10-20" in out
    assert "Beta" in out and "L1-40" in out


def test_digest_dependencies_section_rendered():
    cm = CodeMap(project_path="/p/demo", generated_at="2026-06-17T12:00:00Z",
                 git_commit="abc1234", file_hashes={},
                 symbols=(),
                 dependencies={"a.py": ("b.py",)})
    out = render_digest(cm)
    assert "## Dependencies" in out
    assert "a.py → b.py" in out


def test_digest_no_dependencies_section_when_empty():
    out = render_digest(_map())  # _map() has no dependencies
    assert "## Dependencies" not in out
