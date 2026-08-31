import pytest
from lib.memory.taxonomy import (
    Taxonomy, TaxonomyError, parse_taxonomy, classify_placement, render_block,
    load_taxonomy,
)
from lib import ren_paths

FENCED = """---
type: project-schema
---
# Schema

```taxonomy
architecture/
  memory-plane/
  instrumentation/
governance/
```

prose after.
"""

def test_parse_extracts_nodes():
    tax = parse_taxonomy(FENCED)
    assert tax.nodes == (
        "architecture", "architecture/instrumentation",
        "architecture/memory-plane", "governance",
    )
    assert tax.has("architecture/memory-plane")
    assert not tax.has("nope")

def test_parse_no_fence_raises():
    with pytest.raises(TaxonomyError):
        parse_taxonomy("# Schema\n\nno block here\n")

def test_parse_bad_segment_raises():
    with pytest.raises(TaxonomyError):
        parse_taxonomy("```taxonomy\nBad_Name/\n```\n")

def test_parse_too_deep_raises():
    with pytest.raises(TaxonomyError):
        parse_taxonomy("```taxonomy\na/\n  b/\n    c/\n      d/\n```\n")

def test_classify_existing_and_new_leaf():
    tax = parse_taxonomy(FENCED)
    assert classify_placement(tax, "governance") == "existing"
    assert classify_placement(tax, "architecture/write-door") == "new-leaf"
    assert classify_placement(tax, "brand-new-root") == "new-leaf"

def test_classify_orphan_parent_raises():
    tax = parse_taxonomy(FENCED)
    with pytest.raises(TaxonomyError):
        classify_placement(tax, "missing-parent/child")

def test_render_block_round_trips():
    tax = parse_taxonomy(FENCED)
    text = "```taxonomy\n" + render_block(tax) + "```\n"
    assert parse_taxonomy(text).nodes == tax.nodes

def test_render_block_hyphenated_sibling_round_trip():
    """Regression: hyphenated siblings breaking contiguity in lexicographic sort.

    Before fix: render_block derived indentation from path depth and relied on
    lexicographic sort to keep parents before children. But '-' < '/' in ASCII,
    so 'governance-related' would sort before 'governance/sub', causing the
    subtree to reparent. This test ensures render_block now uses a tree-based
    depth-first walk, which is round-trip stable.
    """
    # Nodes with hyphenated sibling that sorts before parent's slash-child
    tax = Taxonomy(nodes=("governance", "governance-related", "governance/sub"))

    # Render and re-parse
    rendered = "```taxonomy\n" + render_block(tax) + "```\n"
    reparsed = parse_taxonomy(rendered)

    # Must preserve all nodes — governance/sub must not reparent to governance-related
    assert reparsed.nodes == tax.nodes

def test_load_taxonomy_path_traversal_raises():
    """Regression: load_taxonomy only caught OSError, not PathTraversalError.

    safe_join raises PathTraversalError (a ValueError subclass) on path
    traversal attempts, which escaped unwrapped — bypassing callers' blind-circuit
    fallback. This test ensures load_taxonomy catches and wraps it.
    """
    with pytest.raises(TaxonomyError) as exc_info:
        load_taxonomy("../../../../etc")

    # The error should be wrapped as TaxonomyError, not escape as PathTraversalError
    assert isinstance(exc_info.value, TaxonomyError)
    assert isinstance(exc_info.value.__cause__, ren_paths.PathTraversalError)
