"""Detect drift between a CodeMap and the current project files."""
from __future__ import annotations

import hashlib
from pathlib import Path

from lib.codemap.model import CodeMap, StaleReport


def hash_files(project_root: Path, rel_paths) -> dict:
    """sha256 of each existing relative path. Missing files are omitted."""
    out: dict = {}
    for rel in sorted(rel_paths):
        fp = project_root / rel
        try:
            out[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
        except OSError:
            continue
    return out


def is_stale(code_map: CodeMap, project_root: Path) -> StaleReport:
    mapped = set(code_map.file_hashes)
    current = hash_files(project_root, mapped)
    changed = tuple(sorted(p for p in mapped & set(current)
                           if current[p] != code_map.file_hashes[p]))
    deleted = tuple(sorted(mapped - set(current)))
    mapped_files = {s.file for s in code_map.symbols}
    seen_now = {str(p.relative_to(project_root)) for p in project_root.rglob("*.py") if p.is_file()}
    added = tuple(sorted(seen_now - mapped_files - set(mapped)))
    stale = bool(changed or deleted or added)
    return StaleReport(stale=stale, changed=changed, added=added, deleted=deleted)
