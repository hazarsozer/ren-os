"""Code-map data contract. Engine-agnostic; nothing here imports lean-ctx."""
from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True)
class StaleReport:
    stale: bool
    changed: tuple
    added: tuple
    deleted: tuple

    def __bool__(self) -> bool:
        return self.stale
