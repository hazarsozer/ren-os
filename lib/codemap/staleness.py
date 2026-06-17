"""Detect drift between a CodeMap and the current project files."""
from __future__ import annotations

import hashlib
from pathlib import Path

from lib.codemap.model import CodeMap, StaleReport
from lib.codemap.sources import enumerate_source_files


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
    project_root = Path(project_root)
    mapped = set(code_map.file_hashes)
    current_files = set(enumerate_source_files(project_root))
    present = mapped & current_files
    current_hashes = hash_files(project_root, present)
    changed = tuple(sorted(f for f in present
                           if current_hashes.get(f) != code_map.file_hashes[f]))
    deleted = tuple(sorted(mapped - current_files))
    added = tuple(sorted(current_files - mapped))
    stale = bool(changed or deleted or added)
    return StaleReport(stale=stale, changed=changed, added=added, deleted=deleted)
