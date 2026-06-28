"""Code-map data contract. Engine-agnostic; nothing here imports lean-ctx."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str          # function | class | method | ...
    file: str          # project-relative path
    start_line: int
    end_line: int
    signature: str


@dataclass(frozen=True)
class CodeMap:
    project_path: str
    generated_at: str          # ISO-8601 UTC
    git_commit: str            # short hash, or "" when not a repo
    file_hashes: dict          # {project-relative path: sha256-hex}
    symbols: tuple             # tuple[Symbol, ...]
    dependencies: dict = field(default_factory=dict)  # {src_rel: tuple[dst_rel,...]}


@dataclass(frozen=True)
class StaleReport:
    stale: bool
    changed: tuple
    added: tuple
    deleted: tuple

    def __bool__(self) -> bool:
        return self.stale


def depends_on(cm: "CodeMap", file: str) -> tuple:
    """Direct dependencies of `file` (its import targets)."""
    return tuple(cm.dependencies.get(file, ()))


def dependents_of(cm: "CodeMap", file: str) -> tuple:
    """Files that import `file` (reverse edges)."""
    return tuple(sorted(src for src, dsts in cm.dependencies.items() if file in dsts))
