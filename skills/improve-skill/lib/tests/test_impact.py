"""
Tests for skills.improve-skill.lib.impact.

Exercises dependency_footprint: union of outgoing (depends_on) and incoming
(dependents_of) edges for a set of target files, with the target set excluded
from both result tuples.

Per dotfiles python/testing.md: pytest framework. Run with:
    python3 -m pytest skills/improve-skill/lib/tests/ -q
"""

from __future__ import annotations

# Import impact first — it inserts the repo root on sys.path as a side effect,
# which makes the subsequent lib.codemap import resolve correctly.
from ..impact import ImpactReport, dependency_footprint  # noqa: E402
from lib.codemap.model import CodeMap  # noqa: E402


def test_footprint_reports_deps_and_dependents():
    cm = CodeMap(
        project_path="/p",
        generated_at="t",
        git_commit="",
        file_hashes={},
        symbols=(),
        dependencies={
            "skills/x/lib/a.py": ("lib/codemap/model.py",),  # target depends on model
            "skills/y/lib/b.py": ("skills/x/lib/a.py",),     # y depends on target
        },
    )
    rep = dependency_footprint({"skills/x/lib/a.py"}, cm)
    assert rep.dependencies == ("lib/codemap/model.py",)
    assert rep.dependents == ("skills/y/lib/b.py",)


def test_footprint_excludes_target_set_and_is_empty_safe():
    cm = CodeMap(
        project_path="/p",
        generated_at="t",
        git_commit="",
        file_hashes={},
        symbols=(),
        dependencies={},
    )
    rep = dependency_footprint({"skills/x/lib/a.py"}, cm)
    assert rep.dependencies == () and rep.dependents == ()
