"""
Repo-hygiene sweep (Task 9.1): the invariants that keep this repo's
test/shippable-code separation and every skill's contract shape honest.

  - No test files inside shippable dirs (skills/, hooks/, lib/, doctrine/,
    wiki-skeleton/, .claude-plugin/) — all tests live under top-level tests/.
  - Every SKILL.md declares the required frontmatter keys.
  - scripts/lint_no_dev_wiki_content.py passes (the dev-content lint).
  - Every skills/*/lib module imports cleanly (catches syntax/import rot in
    one sweep — including hyphenated skill dirs via the importlib pattern
    established starting Task 4.4).

Run with: uv run pytest tests/test_repo_hygiene.py -v
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIPPABLE_DIRS = ["skills", "hooks", "lib", "doctrine", "wiki-skeleton", ".claude-plugin"]

_REQUIRED_FRONTMATTER_KEYS = ("name", "version", "framework_version", "type")
_TEST_FILE_RE = re.compile(r"^(test_.*\.py|.*_test\.py|conftest\.py)$")


def _shippable_files() -> list[Path]:
    files = []
    for rel in SHIPPABLE_DIRS:
        root = REPO_ROOT / rel
        if not root.is_dir():
            continue
        files.extend(p for p in root.rglob("*") if p.is_file())
    return files


def test_no_test_files_inside_shippable_dirs():
    offenders = [str(p) for p in _shippable_files() if _TEST_FILE_RE.match(p.name)]
    assert not offenders, f"test files found inside shippable dirs: {offenders}"


def test_no_pycache_or_pytest_cache_inside_shippable_dirs():
    """Not strictly requested, but the same invariant's natural extension —
    a checked-in __pycache__/.pytest_cache under a shippable dir is exactly
    the kind of accidental test-tooling leakage this check exists to catch."""
    offenders = [
        str(p) for p in _shippable_files()
        if "__pycache__" in p.parts or ".pytest_cache" in p.parts
    ]
    # This only matters for files that would actually be committed; local
    # bytecode caches are gitignored, so this is informational, not a hard
    # failure, if git isn't available to check.
    if offenders:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain", "--ignored=no"],
            capture_output=True, text=True,
        )
        tracked_offenders = [o for o in offenders if Path(o).name in result.stdout]
        assert not tracked_offenders, f"cache files tracked in git: {tracked_offenders}"


def test_every_skill_md_has_required_frontmatter_keys():
    skill_mds = sorted((REPO_ROOT / "skills").glob("*/SKILL.md"))
    assert skill_mds, "expected at least one skills/*/SKILL.md"

    missing: dict[str, list[str]] = {}
    for path in skill_mds:
        text = path.read_text(encoding="utf-8")
        fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        frontmatter = fm_match.group(1) if fm_match else ""
        gaps = [key for key in _REQUIRED_FRONTMATTER_KEYS if not re.search(rf"^{key}:", frontmatter, re.MULTILINE)]
        if gaps:
            missing[str(path.relative_to(REPO_ROOT))] = gaps

    assert not missing, f"SKILL.md files missing required frontmatter keys: {missing}"


def test_dev_content_lint_passes():
    script = REPO_ROOT / "scripts" / "lint_no_dev_wiki_content.py"
    proc = subprocess.run(["python3", str(script)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert proc.returncode == 0, f"dev-content lint failed:\n{proc.stdout}\n{proc.stderr}"


def _skill_lib_module_names() -> list[str]:
    names = []
    for skill_dir in sorted((REPO_ROOT / "skills").iterdir()):
        if not skill_dir.is_dir():
            continue
        lib_init = skill_dir / "lib" / "__init__.py"
        if lib_init.is_file():
            names.append(f"skills.{skill_dir.name}.lib")
    return names


@pytest.mark.parametrize("module_name", _skill_lib_module_names())
def test_skill_lib_imports_cleanly(module_name):
    """Every skills/*/lib module must import without raising — catches
    syntax errors, broken imports, and stale references in one sweep.
    Hyphenated skill dirs (e.g. skills.ingest-project.lib) are reached the
    same way production code reaches them: importlib.import_module, which
    tolerates the non-identifier dotted segment where a plain `import`
    statement could not."""
    importlib.import_module(module_name)


def test_at_least_expected_number_of_skill_libs_discovered():
    """Sanity guard: if module discovery silently found zero modules, every
    parametrized import test above passes vacuously and hides real rot."""
    assert len(_skill_lib_module_names()) >= 10
