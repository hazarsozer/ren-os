import textwrap
from pathlib import Path
from lib.codemap.deps import extract_dependencies

def _w(root, rel, src):
    p = root / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(textwrap.dedent(src)); return rel

def test_absolute_import_edge(tmp_path):
    _w(tmp_path, "lib/codemap/model.py", "X = 1\n")
    _w(tmp_path, "lib/codemap/core.py", "from lib.codemap.model import X\n")
    deps = extract_dependencies(tmp_path, ["lib/codemap/model.py", "lib/codemap/core.py"])
    assert deps["lib/codemap/core.py"] == ("lib/codemap/model.py",)
    assert "lib/codemap/model.py" not in deps  # no outgoing edges

def test_import_package_resolves_to_init(tmp_path):
    _w(tmp_path, "lib/codemap/__init__.py", "\n")
    _w(tmp_path, "app.py", "import lib.codemap\n")
    deps = extract_dependencies(tmp_path, ["lib/codemap/__init__.py", "app.py"])
    assert deps["app.py"] == ("lib/codemap/__init__.py",)

def test_relative_import_in_hyphenated_skill_dir(tmp_path):
    _w(tmp_path, "skills/improve-skill/lib/types.py", "class A: ...\n")
    _w(tmp_path, "skills/improve-skill/lib/preflight.py", "from .types import A\n")
    rels = ["skills/improve-skill/lib/types.py", "skills/improve-skill/lib/preflight.py"]
    deps = extract_dependencies(tmp_path, rels)
    assert deps["skills/improve-skill/lib/preflight.py"] == ("skills/improve-skill/lib/types.py",)

def test_bare_relative_from_import(tmp_path):
    _w(tmp_path, "skills/improve-skill/lib/types.py", "class A: ...\n")
    _w(tmp_path, "skills/improve-skill/lib/preflight.py", "from . import types\n")
    rels = ["skills/improve-skill/lib/types.py", "skills/improve-skill/lib/preflight.py"]
    deps = extract_dependencies(tmp_path, rels)
    assert deps["skills/improve-skill/lib/preflight.py"] == ("skills/improve-skill/lib/types.py",)

def test_unparseable_and_nonpy_and_external_yield_no_edges(tmp_path):
    _w(tmp_path, "broken.py", "def (:\n")          # SyntaxError
    _w(tmp_path, "data.json", "{}\n")               # non-py
    _w(tmp_path, "ext.py", "import os\nimport requests\n")  # external, not in project
    deps = extract_dependencies(tmp_path, ["broken.py", "data.json", "ext.py"])
    assert deps == {}  # no in-project edges, no crash

def test_non_utf8_is_tolerated(tmp_path):
    p = tmp_path / "weird.py"; p.write_bytes(b"\xff\xfe import os\n")
    assert extract_dependencies(tmp_path, ["weird.py"]) == {}  # no crash, no edge
