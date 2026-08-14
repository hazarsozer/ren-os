"""skills.wrap.lib.merge — the ONE extra LLM call an update-action durable
item makes (spec §1). Input: the target page's full text + the item; output:
the full merged body. Strict like the classifier: anything suspect raises
`MergeError` and the caller gates the item out (fail-closed) — a bad merge
must never reach the write door.

Frontmatter is the door's property (provenance stamping), never the
merge's: the returned text's frontmatter block must be byte-identical to
the input's, or we refuse.
"""

from __future__ import annotations

import re
from typing import Callable, Final

_FRONTMATTER_RE: Final[re.Pattern[str]] = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

_MERGE_PROMPT_TEMPLATE: Final[str] = """\
You are updating ONE existing wiki page with ONE new durable learning.

Rules:
- Return the COMPLETE updated page as markdown, and NOTHING else (no code
  fence, no commentary).
- Change ONLY the section(s) the learning affects: correct, extend, or
  append. Preserve every other line exactly.
- Do NOT touch the YAML frontmatter block at the top — copy it verbatim.
- Keep the page's existing tone, heading structure, and link style.

The new durable learning:
---
{item_text}
---

The current page:
---
{page_text}
---
"""


class MergeError(Exception):
    """Merge output was malformed, unchanged, or tampered with frontmatter."""


def _frontmatter_block(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    return m.group(0) if m else ""


def merge_update(
    current_text: str, item_text: str, llm_call: Callable[[str], str]
) -> str:
    prompt = _MERGE_PROMPT_TEMPLATE.format(item_text=item_text, page_text=current_text)
    try:
        raw = llm_call(prompt)
    except Exception as exc:  # noqa: BLE001 - any llm_call failure gates the item out, never crashes wrap
        raise MergeError(f"merge llm call failed: {exc}") from exc
    if not isinstance(raw, str) or not raw.strip():
        raise MergeError("merge output empty or not a string")
    if _frontmatter_block(raw) != _frontmatter_block(current_text):
        raise MergeError("merge output altered the frontmatter block")
    if raw == current_text:
        raise MergeError("merge output is byte-identical to the current page")
    return raw


__all__ = ["merge_update", "MergeError"]
