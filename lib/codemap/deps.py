"""Module-level dependency graph from Python imports (stdlib ast). Engine-agnostic.
Resolves both absolute imports (via a dotted-name index) and relative imports
(directory-relative, so hyphenated skill dirs like skills/improve-skill/ work)."""
from __future__ import annotations

import ast
from pathlib import Path


def _module_index(py_rel_files: list[str]) -> dict:
    """dotted importable name -> rel file. 'a/b/c.py'->'a.b.c'; 'a/b/__init__.py'->'a.b'."""
    index: dict = {}
    for rel in py_rel_files:
        parts = rel[:-3].split("/")
        dotted = ".".join(parts[:-1]) if parts[-1] == "__init__" else ".".join(parts)
        if dotted:
            index.setdefault(dotted, rel)
    return index


def _resolve_absolute(dotted: str, index: dict) -> str | None:
    """Longest-prefix match: 'lib.codemap.model.X' -> file for 'lib.codemap.model'."""
    parts = dotted.split(".")
    while parts:
        cand = ".".join(parts)
        if cand in index:
            return index[cand]
        parts.pop()
    return None


def _relative_pkg(importer_rel: str, level: int) -> Path:
    """The package directory a relative import resolves against (level 1 = same dir)."""
    pkg = Path(importer_rel).parent
    for _ in range(level - 1):                 # each extra level goes up one dir
        pkg = pkg.parent
    return pkg


def _relative_candidate(pkg: Path, sub: Path, present: set) -> str | None:
    """Match `pkg/sub.py` or `pkg/sub/__init__.py` against in-project files."""
    for cand in (f"{(pkg / sub)}.py", f"{(pkg / sub / '__init__')}.py"):
        cand = cand.replace("\\", "/")
        if cand in present:
            return cand
    return None


def _resolve_relative(node: ast.ImportFrom, importer_rel: str, present: set) -> list:
    """Directory-relative resolution for `from . / .. import` (handles hyphenated dirs).

    Covers both `from .mod import X` (node.module set) and the bare-name form
    `from . import a, b` (node.module None → each alias is a sibling module).
    """
    pkg = _relative_pkg(importer_rel, node.level)
    if node.module:
        hit = _relative_candidate(pkg, Path(*node.module.split(".")), present)
        return [hit] if hit else []
    hits = [_relative_candidate(pkg, Path(a.name), present) for a in node.names]
    return [h for h in hits if h]


def extract_dependencies(project_root: Path, rel_files: list[str]) -> dict:
    """{src_rel: tuple[dst_rel,...]} import edges resolved to in-project files. Never raises."""
    project_root = Path(project_root).resolve()
    py = [r for r in rel_files if r.endswith(".py")]
    index, present = _module_index(py), set(py)
    deps: dict = {}
    for rel in py:
        try:
            tree = ast.parse((project_root / rel).read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError, ValueError):
            continue
        targets: set = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    hit = _resolve_absolute(a.name, index)
                    if hit:
                        targets.add(hit)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    targets.update(_resolve_relative(node, rel, present))
                else:
                    hit = _resolve_absolute(node.module or "", index)
                    if hit:
                        targets.add(hit)
        targets.discard(rel)
        if targets:
            deps[rel] = tuple(sorted(targets))
    return deps
