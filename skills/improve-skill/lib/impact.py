"""Dependency footprint of an improve-skill target, over the code-map dependency graph.
Read-only impact awareness for the Karpathy loop (Pillar 5 dependency-map consumer).

Operates on a plain dependency map ({src_rel: tuple[dst_rel, ...]} — exactly what
CodeMap.dependencies holds). Pure and stdlib-only: NO lib.codemap import, so there
is no "lib" package-name collision with the repo-root lib/ package. The caller
passes code_map.dependencies."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImpactReport:
    dependencies: tuple[str, ...]   # what the target imports (outgoing), minus the target set
    dependents: tuple[str, ...]     # what imports the target (incoming), minus the target set


def dependency_footprint(target_files: set, dependencies: dict) -> ImpactReport:
    """Union of outgoing (imports) and incoming (imported-by) edges for target_files.

    Args:
        target_files: project-relative paths under inspection.
        dependencies: {src_rel: tuple[dst_rel, ...]} — pass CodeMap.dependencies.

    Returns:
        ImpactReport with sorted tuples, both excluding the target set itself.
    """
    deps: set = set()
    dependents: set = set()
    for f in target_files:
        deps.update(dependencies.get(f, ()))
        dependents.update(src for src, dsts in dependencies.items() if f in dsts)
    deps -= set(target_files)
    dependents -= set(target_files)
    return ImpactReport(dependencies=tuple(sorted(deps)), dependents=tuple(sorted(dependents)))
