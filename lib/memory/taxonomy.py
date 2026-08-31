"""Parse, validate, and manage taxonomy from schema.md.

Provides facilities for parsing the ```taxonomy fenced block from schema.md,
validating structure against depth/naming constraints, classifying concept
placements, and rendering blocks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

import lib.ren_paths as ren_paths

_SEGMENT_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_FENCE_RE: Final = re.compile(r"```taxonomy\n(.*?)```", re.DOTALL)
MAX_DEPTH: Final[int] = 2  # levels below knowledge/

__all__ = [
    "Taxonomy",
    "TaxonomyError",
    "parse_taxonomy",
    "load_taxonomy",
    "classify_placement",
    "render_block",
    "render_added_line",
]


class TaxonomyError(Exception):
    """Unparseable/invalid taxonomy — callers treat any raise as 'blind'."""


@dataclass(frozen=True)
class Taxonomy:
    """Immutable taxonomy with sorted node paths."""

    nodes: tuple[str, ...]

    def has(self, path: str) -> bool:
        """Check if a path is an existing node in the taxonomy."""
        return path in self.nodes


def parse_taxonomy(schema_md_text: str) -> Taxonomy:
    """Parse taxonomy from schema.md fence block.

    Raises TaxonomyError on:
    - no ```taxonomy fence
    - bad indentation (not multiple of 2)
    - invalid segment (must match [a-z0-9][a-z0-9-]*)
    - depth > 2
    - duplicate path
    - empty fence
    """
    m = _FENCE_RE.search(schema_md_text)
    if not m:
        raise TaxonomyError("no ```taxonomy fence in schema.md")

    nodes: list[str] = []
    stack: list[str] = []

    for raw in m.group(1).splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            raise TaxonomyError(f"odd indentation: {raw!r}")
        depth = indent // 2
        seg = raw.strip().rstrip("/")
        if not _SEGMENT_RE.match(seg):
            raise TaxonomyError(f"invalid segment {seg!r}")
        if depth > len(stack):
            raise TaxonomyError(f"indentation jump: {raw!r}")
        if depth >= MAX_DEPTH + 1:
            raise TaxonomyError(f"deeper than cap {MAX_DEPTH}: {raw!r}")
        stack = stack[:depth] + [seg]
        path = "/".join(stack)
        if path in nodes:
            raise TaxonomyError(f"duplicate node {path!r}")
        nodes.append(path)

    if not nodes:
        raise TaxonomyError("taxonomy fence is empty")

    return Taxonomy(nodes=tuple(sorted(nodes)))


def load_taxonomy(project: str) -> Taxonomy:
    """Load taxonomy from projects/<project>/schema.md.

    Raises TaxonomyError on any OSError or parsing error.
    """
    try:
        path = ren_paths.safe_join(ren_paths.wiki_root(), f"projects/{project}/schema.md")
        with open(path, encoding="utf-8") as f:
            return parse_taxonomy(f.read())
    except OSError as exc:
        raise TaxonomyError(f"cannot load {project}/schema.md: {exc}") from exc


def classify_placement(tax: Taxonomy, placement: str) -> str:
    """Classify a placement as 'existing' or 'new-leaf'.

    Returns:
    - 'existing' if the placement is already a node
    - 'new-leaf' if the parent (or root for single segment) exists and depth <= 2

    Raises TaxonomyError if parent does not exist or depth > 2.
    """
    if tax.has(placement):
        return "existing"

    # Check depth constraint
    parts = placement.split("/")
    if len(parts) > MAX_DEPTH + 1:
        raise TaxonomyError(f"placement {placement!r} exceeds depth {MAX_DEPTH}")

    # Check parent exists (or root for single segment)
    if len(parts) == 1:
        # Single segment is a new root
        return "new-leaf"

    parent = "/".join(parts[:-1])
    if not tax.has(parent):
        raise TaxonomyError(f"parent {parent!r} not found in taxonomy")

    return "new-leaf"


def render_block(tax: Taxonomy) -> str:
    """Render taxonomy nodes as fenced block content with 2-space indentation.

    Returns the content between ```taxonomy fences (without fence markers).
    """
    if not tax.nodes:
        return ""

    # Group nodes by parent to build hierarchical structure
    lines: list[str] = []

    for node in tax.nodes:
        parts = node.split("/")
        depth = len(parts) - 1
        indent = "  " * depth
        segment = parts[-1]
        lines.append(f"{indent}{segment}/")

    return "\n".join(lines) + "\n"


def render_added_line(placement: str) -> tuple[str, str]:
    """Return (parent_line_prefix, new_line) for appending a leaf.

    Helper used by Task 3 to append the leaf into the fenced block.
    Returns the indentation prefix for the parent and the new line with proper indentation.
    """
    parts = placement.split("/")
    depth = len(parts) - 1
    indent = "  " * depth
    segment = parts[-1]
    new_line = f"{indent}{segment}/"

    if len(parts) == 1:
        parent_prefix = ""
    else:
        parent_depth = depth - 1
        parent_prefix = "  " * parent_depth

    return (parent_prefix, new_line)
