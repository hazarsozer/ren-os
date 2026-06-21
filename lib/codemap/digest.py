"""Render a CodeMap as a compact markdown digest."""
from __future__ import annotations

from itertools import groupby

from lib.codemap.model import CodeMap

_HEADER = (
    "# Code-map: {path}\n\n"
    "> Generated {ts} at commit `{commit}`. **Regenerable** — `/ren:code-map --refresh`.\n"
    "> **Trust but verify:** line ranges are hints; confirm a symbol is at the cited range "
    "before relying on it. A stale map is worse than none.\n\n"
)


def render_digest(code_map: CodeMap) -> str:
    parts = [_HEADER.format(path=code_map.project_path,
                            ts=code_map.generated_at,
                            commit=code_map.git_commit or "n/a")]
    for fname, group in groupby(sorted(code_map.symbols, key=lambda s: (s.file, s.start_line)),
                                key=lambda s: s.file):
        parts.append(f"## {fname}\n")
        for s in group:
            parts.append(f"- `{s.name}` ({s.kind}) L{s.start_line}-{s.end_line} — {s.signature}\n")
        parts.append("\n")
    if code_map.dependencies:
        parts.append("## Dependencies\n\n")
        for src in sorted(code_map.dependencies):
            deps = ", ".join(sorted(code_map.dependencies[src]))
            parts.append(f"- {src} → {deps}\n")
        parts.append("\n")
    return "".join(parts)
