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


def test_footprint_excludes_target_set_and_is_empty_safe():
    rep = dependency_footprint({"skills/x/lib/a.py"}, {})
    assert rep.dependencies == () and rep.dependents == ()
