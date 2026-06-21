"""Dependency footprint of an improve-skill target, over the code-map dependency graph.
Read-only impact awareness for the Karpathy loop (Pillar 5 dependency-map consumer)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# ---- Import bootstrap -------------------------------------------------------
# skills/improve-skill/lib shares the package name "lib" with the repo-root
# lib/ package. When pytest loads these tests, "lib" is registered in
# sys.modules as skills/improve-skill/lib AND skills/improve-skill is first
# on sys.path. To import lib.codemap.model from the repo root we must:
#   1. Pop "lib" (and sub-entries) from sys.modules so re-import is attempted.
#   2. Ensure the repo root precedes skills/improve-skill in sys.path so the
#      correct "lib" is picked up.
#   3. Restore sys.modules to its original state so nothing else breaks.
_repo_root = str(Path(__file__).resolve().parents[3])
_skill_parent = str(Path(__file__).resolve().parents[1])  # skills/improve-skill

_saved = {
    k: v for k, v in sys.modules.items()
    if k == "lib" or k.startswith("lib.")
}
for k in list(_saved):
    sys.modules.pop(k, None)

# Remove skills/improve-skill from sys.path temporarily so lib resolves correctly.
_had_skill_parent = _skill_parent in sys.path
if _had_skill_parent:
    sys.path.remove(_skill_parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from lib.codemap.model import CodeMap as _CodeMap  # noqa: E402
from lib.codemap.model import depends_on as _depends_on  # noqa: E402
from lib.codemap.model import dependents_of as _dependents_of  # noqa: E402

# Restore sys.path and sys.modules
if _had_skill_parent:
    sys.path.insert(0, _skill_parent)
sys.modules.update(_saved)
# ---- End bootstrap ----------------------------------------------------------

CodeMap = _CodeMap
depends_on = _depends_on
dependents_of = _dependents_of


@dataclass(frozen=True)
class ImpactReport:
    dependencies: tuple   # what the target imports (outgoing), minus the target set
    dependents: tuple     # what imports the target (incoming), minus the target set


def dependency_footprint(target_files: set, cm: _CodeMap) -> ImpactReport:
    """Return the union of outgoing and incoming edges for target_files, excluding targets."""
    deps: set = set()
    dependents: set = set()
    for f in target_files:
        deps.update(_depends_on(cm, f))
        dependents.update(_dependents_of(cm, f))
    deps -= set(target_files)
    dependents -= set(target_files)
    return ImpactReport(dependencies=tuple(sorted(deps)), dependents=tuple(sorted(dependents)))
