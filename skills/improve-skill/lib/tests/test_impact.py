"""
Tests for skills.improve-skill.lib.impact.

Exercises dependency_footprint: union of outgoing (imports) and incoming
(imported-by) edges for a set of target files, with the target set excluded
from both result tuples. Operates on a plain dependency dict
({src_rel: tuple[dst_rel, ...]} — exactly what CodeMap.dependencies holds), so
no CodeMap import is needed.

Per dotfiles python/testing.md: pytest framework. Run with:
    python3 -m pytest skills/improve-skill/lib/tests/ -q
"""

from __future__ import annotations

from ..impact import ImpactReport, dependency_footprint


def test_footprint_reports_deps_and_dependents():
    dependencies = {
        "skills/x/lib/a.py": ("lib/codemap/model.py",),  # target depends on model
        "skills/y/lib/b.py": ("skills/x/lib/a.py",),     # y depends on target
    }
    rep = dependency_footprint({"skills/x/lib/a.py"}, dependencies)
    assert isinstance(rep, ImpactReport)
    assert rep.dependencies == ("lib/codemap/model.py",)
    assert rep.dependents == ("skills/y/lib/b.py",)


def test_footprint_excludes_target_files_on_both_sides():
    # a <-> b mutual import; both in the target set, so each cancels out of both
    # result tuples. This genuinely exercises the `-= set(target_files)` lines —
    # deleting them would make this test fail.
    deps = {"a.py": ("b.py",), "b.py": ("a.py",)}
    rep = dependency_footprint({"a.py", "b.py"}, deps)
    assert rep.dependencies == ()   # b.py is a dep of a.py but b.py is in the target set -> excluded
    assert rep.dependents == ()     # a.py imports b.py but a.py is in the target set -> excluded


def test_footprint_empty_graph_is_safe():
    rep = dependency_footprint({"skills/x/lib/a.py"}, {})
    assert rep.dependencies == () and rep.dependents == ()
