"""Tests for scripts/lint-shell-portability.py (bash-3.2 / BSD-sed guard)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT = REPO_ROOT / "scripts" / "lint-shell-portability.py"

spec = importlib.util.spec_from_file_location("lint_shell_portability", LINT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return p


def test_flags_mapfile(tmp_path):
    p = _write(tmp_path, "a.sh", 'mapfile -t ARR < <(find . -type d)\n')
    hits = mod.scan_file(p)
    assert len(hits) == 1 and "mapfile" in hits[0][1]


def test_flags_readarray(tmp_path):
    p = _write(tmp_path, "a.sh", 'readarray -t ARR < <(ls)\n')
    assert len(mod.scan_file(p)) == 1


def test_flags_bare_sed_i(tmp_path):
    p = _write(tmp_path, "a.sh", 'sed -i "s/^x$/y/" "$PAGE"\n')
    hits = mod.scan_file(p)
    assert len(hits) == 1 and "sed -i" in hits[0][1]


def test_allows_sed_i_with_suffix(tmp_path):
    p = _write(tmp_path, "a.sh", 'sed -i.bak "s/^x$/y/" "$PAGE"\n')
    assert mod.scan_file(p) == []


def test_flags_gnu_oneline_append(tmp_path):
    p = _write(tmp_path, "a.sh", 'sed -i.bak "/^schema_version: 2$/a allowlist:" "$PAGE"\n')
    hits = mod.scan_file(p)
    assert len(hits) == 1 and "append" in hits[0][1].lower()


def test_allows_portable_append(tmp_path):
    p = _write(tmp_path, "a.sh", 'sed -i.bak "/^schema_version: 2$/a\\\nallowlist:" "$PAGE"\n')
    assert mod.scan_file(p) == []


def test_ignores_comments_and_non_sh(tmp_path):
    _write(tmp_path, "a.sh", '# mapfile is banned; sed -i too\necho ok\n')
    _write(tmp_path, "b.py", 'x = "mapfile"\n')
    assert mod.scan_file(tmp_path / "a.sh") == []


def test_cli_exit_codes(tmp_path):
    (tmp_path / "skills").mkdir()
    _write(tmp_path / "skills", "bad.sh", "mapfile -t A < <(ls)\n")
    r = subprocess.run([sys.executable, str(LINT), str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 1 and "bad.sh" in r.stdout
    (tmp_path / "skills" / "bad.sh").write_text("echo ok\n")
    r2 = subprocess.run([sys.executable, str(LINT), str(tmp_path)], capture_output=True, text=True)
    assert r2.returncode == 0
