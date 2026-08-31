import pytest
from lib.memory.taxonomy import (
    Taxonomy, TaxonomyError, parse_taxonomy, classify_placement, render_block,
)

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
