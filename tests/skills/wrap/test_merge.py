import pytest

from skills.wrap.lib.merge import merge_update, MergeError

PAGE = """---
type: project-knowledge
ren_write_id: "w-01TEST"
ren_trust: "model"
---

# Damage Formula

Old fact: crit multiplier is 1.5.
"""


def test_merge_returns_llm_body_when_frontmatter_preserved():
    merged_ok = PAGE.replace("1.5", "2.0")
    out = merge_update(PAGE, "crit multiplier is actually 2.0", lambda p: merged_ok)
    assert "2.0" in out and out.startswith("---\ntype: project-knowledge")


def test_merge_rejects_frontmatter_tampering():
    tampered = PAGE.replace('ren_trust: "model"', 'ren_trust: "user"').replace("1.5", "2.0")
    with pytest.raises(MergeError):
        merge_update(PAGE, "item", lambda p: tampered)


def test_merge_rejects_empty_or_nonstring_output():
    with pytest.raises(MergeError):
        merge_update(PAGE, "item", lambda p: "   ")
    with pytest.raises(MergeError):
        merge_update(PAGE, "item", lambda p: None)  # type: ignore[arg-type]


def test_merge_rejects_unchanged_output():
    with pytest.raises(MergeError):
        merge_update(PAGE, "item", lambda p: PAGE)


def test_merge_wraps_llm_call_failure_as_merge_error():
    def crashing_llm(prompt):
        raise RuntimeError("llm backend down")

    with pytest.raises(MergeError):
        merge_update(PAGE, "item", crashing_llm)


def test_merge_prompt_contains_page_and_item():
    seen = {}
    def llm(prompt):
        seen["prompt"] = prompt
        return PAGE.replace("1.5", "2.0")
    merge_update(PAGE, "THE-ITEM-TEXT", llm)
    assert "THE-ITEM-TEXT" in seen["prompt"] and "Damage Formula" in seen["prompt"]
