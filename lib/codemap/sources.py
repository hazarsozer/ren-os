"""Shared source-file enumeration for the code-map (engine-agnostic)."""
from __future__ import annotations

import os
from pathlib import Path

SOURCE_GLOBS = ("*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.go", "*.rs", "*.java")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", "target", "vendor", ".next", ".mypy_cache", ".pytest_cache"}


def enumerate_source_files(project_root: Path) -> list[str]:
    """Sorted project-relative paths of source files (skip-dirs pruned)."""
    project_root = Path(project_root).resolve()
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if any(p.match(g) for g in SOURCE_GLOBS):
                out.append(str(p.relative_to(project_root)))
    return sorted(out)
