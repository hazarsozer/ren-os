from lib.codemap.model import CodeMap
from lib.codemap.staleness import hash_files, is_stale


def _write(p, text):
    p.write_text(text)
    return p


def test_hash_files_is_relative_and_stable(tmp_path):
    _write(tmp_path / "a.py", "print(1)\n")
    h1 = hash_files(tmp_path, ["a.py"])
    h2 = hash_files(tmp_path, ["a.py"])
    assert list(h1) == ["a.py"] and h1 == h2


def test_is_stale_detects_change_add_delete(tmp_path):
    _write(tmp_path / "a.py", "print(1)\n")
    base = hash_files(tmp_path, ["a.py"])
    cm = CodeMap(project_path=str(tmp_path), generated_at="t", git_commit="",
                 file_hashes=base, symbols=())
    assert not is_stale(cm, tmp_path)            # unchanged
    _write(tmp_path / "a.py", "print(2)\n")
    assert is_stale(cm, tmp_path).changed == ("a.py",)
    (tmp_path / "a.py").unlink()
    assert is_stale(cm, tmp_path).deleted == ("a.py",)
    _write(tmp_path / "a.py", "print(1)\n")
    _write(tmp_path / "b.py", "x=1\n")
    rep = is_stale(cm, tmp_path)
    assert "b.py" in rep.added
