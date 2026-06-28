"""
sf-consolidate diff primitives — deterministic, git-apply-compatible unified diffs.

Shared by the promotion sweep (`build_promotion_diffs`, C3b) and the link-repair
sweep (`build_link_repair_diffs`, C3c). Extracted into their own module once a
second consumer appeared, so both import one source instead of duplicating the
difflib plumbing. Pure string logic; no git, no I/O.
"""

from __future__ import annotations

import difflib


def unified_diff(relpath: str, old_text: str, new_text: str) -> str:
    """Unified diff for an edit to an EXISTING file (git apply -p1 compatible)."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{relpath}", tofile=f"b/{relpath}")
    )


def create_file_diff(relpath: str, content: str) -> str:
    """Unified diff that CREATES a new file holding `content`."""
    lines = content.splitlines()
    body = "".join(f"+{ln}\n" for ln in lines)
    return (
        f"diff --git a/{relpath} b/{relpath}\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        f"+++ b/{relpath}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}"
    )


def mark_line(text: str, raw_line: str, marked_line: str) -> str:
    """Replace exactly the matching `raw_line` with `marked_line` (first match)."""
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if ln == raw_line:
            lines[i] = marked_line
            break
    return "\n".join(lines)


__all__ = ["unified_diff", "create_file_diff", "mark_line"]
