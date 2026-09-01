"""Parse, validate, and manage taxonomy from schema.md (spec 2026-08-31 §3).

Provides facilities for parsing the ```taxonomy fenced block from schema.md,
validating structure against depth/naming constraints, classifying concept
placements, and rendering blocks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from lib import ren_paths

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
    """Parse taxonomy from schema.md fence block (spec 2026-08-31 §3).

    Raises TaxonomyError on:
    - no ```taxonomy fence
    - bad indentation (not multiple of 2)
    - invalid segment (must match [a-z0-9][a-z0-9-]*)
    - depth > 2
    - duplicate path

    An empty fence is NOT an error (I4, spec §6 ruled authoritative): it
    parses to `Taxonomy(nodes=())` — defined-but-empty, the state the
    bootstrap skeleton's stub stamps and every project starts in before
    its first branch is added. Concept routing for such a project is NOT
    blind (`lib/reporting.py` Unknown conventions) — only a missing/
    unparseable fence is. A `#`-prefixed line is NOT a comment — it is an
    invalid segment like any other (the shipped skeleton stub's own fence
    is genuinely empty; its `<!-- # add branches... -->` note lives
    OUTSIDE the fence, in the surrounding markdown, so no shipped artifact
    depends on in-fence comment syntax — residual-review ruling).
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

    return Taxonomy(nodes=tuple(sorted(nodes)))


def load_taxonomy(project: str) -> Taxonomy:
    """Load taxonomy from projects/<project>/schema.md (spec 2026-08-31 §3).

    Raises TaxonomyError on any OSError, PathTraversalError, or parsing error.
    """
    try:
        path = ren_paths.safe_join(ren_paths.wiki_root(), f"projects/{project}/schema.md")
        with open(path, encoding="utf-8") as f:
            return parse_taxonomy(f.read())
    except (OSError, ren_paths.PathTraversalError) as exc:
        raise TaxonomyError(f"cannot load {project}/schema.md: {exc}") from exc


def classify_placement(tax: Taxonomy, placement: str) -> str:
    """Classify a placement as 'existing' or 'new-leaf' (spec 2026-08-31 §3,
    §4 "additive rule").

    Returns:
    - 'existing' if the placement is already a node
    - 'new-leaf' if the parent (or root for single segment) exists and depth <= 2

    Raises TaxonomyError if any segment is malformed, parent does not exist,
    or depth > 2.

    C1: EVERY segment of `placement` is validated against `_SEGMENT_RE`
    before anything else — a classifier-supplied placement is untrusted
    input that gets spliced verbatim into `schema.md`'s fence and a
    filesystem path (`_apply_concept_create`); an unvalidated segment
    (`"Bad_Seg"`, `".."`, empty) would either corrupt the fence so
    `load_taxonomy` can never parse it again, or reach `Proposal`'s own
    path-traversal guard as an uncaught `ValueError`. Raising here instead
    routes through `ConceptPlacementError` → the lesson-fallback path, same
    as any other placement rejection.
    """
    parts = placement.split("/")
    for seg in parts:
        if not _SEGMENT_RE.match(seg):
            raise TaxonomyError(f"invalid segment {seg!r} in placement {placement!r}")

    if tax.has(placement):
        return "existing"

    # Check depth constraint
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
    """Render taxonomy nodes as fenced block content with 2-space indentation
    (spec 2026-08-31 §3/§4 — used to splice a new leaf into `schema.md` and
    to render the classifier prompt's taxonomy block).

    Returns the content between ```taxonomy fences (without fence markers).
    Uses tree-based depth-first walk to ensure round-trip stability across
    lexicographic sort variations.
    """
    if not tax.nodes:
        return ""

    # Build a tree: map from parent path to sorted list of child segments
    children: dict[str, list[str]] = {}
    roots: list[str] = []

    for node in tax.nodes:
        parts = node.split("/")
        if len(parts) == 1:
            roots.append(node)
        else:
            parent = "/".join(parts[:-1])
            segment = parts[-1]
            if parent not in children:
                children[parent] = []
            children[parent].append(segment)

    # Sort each level for deterministic output
    roots.sort()
    for segs in children.values():
        segs.sort()

    # Render depth-first
    lines: list[str] = []

    def render_subtree(parent_path: str, depth: int) -> None:
        """Recursively render a node and its children."""
        indent = "  " * depth
        segment = parent_path.split("/")[-1]
        lines.append(f"{indent}{segment}/")

        # Render children if any
        if parent_path in children:
            for child_seg in children[parent_path]:
                render_subtree(f"{parent_path}/{child_seg}", depth + 1)

    for root in roots:
        render_subtree(root, 0)

    return "\n".join(lines) + "\n"
