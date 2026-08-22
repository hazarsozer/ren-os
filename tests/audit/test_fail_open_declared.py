"""Fail-open must declare itself (spec 2026-08-22).

Companion to `test_destructive_write_paths.py`: that audit pins the class
"a generated write meets an existing file"; this one pins the class "a broad
exception handler conceals whether it failed".

The convention enforced here already exists — 66 handlers carried
`# noqa: BLE001 - <reason>` before this test was written. Ruff is not
configured in this repo and never runs, so the comment functions as
documentation, not suppression. This test is what makes it binding.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Copied verbatim from tests/test_repo_hygiene.py:28 — the shippable surface.
SHIPPABLE_DIRS = ["skills", "hooks", "lib", "doctrine", "wiki-skeleton", ".claude-plugin", "agents"]

_MARKER_RE = re.compile(r"noqa:\s*BLE001\b")
# Separators a reason may follow the code with: "BLE001 - why", "BLE001: why".
_REASON_SEPARATORS = " -–—:"


def _comments_by_line(src: str) -> dict[int, str]:
    """Map line number -> comment text. Comments are absent from the AST, so
    they must come from tokenize. The first comment on a line wins."""
    out: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                out.setdefault(tok.start[0], tok.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # A file that does not tokenize also does not parse; ast.parse in the
        # caller raises and pytest reports it. Returning {} keeps this helper
        # total rather than hiding a parse failure here.
        pass
    return out


def _is_broad(handler: ast.ExceptHandler) -> bool:
    """True for `except:`, `except Exception:`, `except BaseException:` —
    including the `as exc` forms. A tuple or a named exception is not broad."""
    caught = handler.type
    if caught is None:
        return True
    return isinstance(caught, ast.Name) and caught.id in ("Exception", "BaseException")


def undeclared_broad_handlers(src: str, label: str) -> list[str]:
    """Return "<label>:<lineno>" for every broad handler in `src` that lacks a
    `# noqa: BLE001` marker with a non-empty reason on its `except` line."""
    tree = ast.parse(src)
    comments = _comments_by_line(src)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not _is_broad(node):
            continue
        comment = comments.get(node.lineno, "")
        match = _MARKER_RE.search(comment)
        if match is None:
            offenders.append(f"{label}:{node.lineno}")
            continue
        reason = comment[match.end():].lstrip(_REASON_SEPARATORS).strip()
        if not reason:
            offenders.append(f"{label}:{node.lineno}")
    return offenders


def test_unmarked_broad_handler_is_flagged():
    src = "try:\n    f()\nexcept Exception:\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_bare_except_is_flagged():
    src = "try:\n    f()\nexcept:\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_marker_without_a_reason_is_flagged():
    src = "try:\n    f()\nexcept Exception:  # noqa: BLE001\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_marker_with_a_reason_passes():
    src = "try:\n    f()\nexcept Exception:  # noqa: BLE001 - callers handle None\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == []


def test_marker_with_colon_separator_passes():
    src = "try:\n    f()\nexcept Exception:  # noqa: BLE001: callers handle None\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == []


def test_as_exc_form_is_still_broad():
    src = "try:\n    f()\nexcept Exception as exc:\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_named_exception_is_out_of_scope():
    src = "try:\n    f()\nexcept OSError:\n    return None\n"
    assert undeclared_broad_handlers(src, "x.py") == []


def test_tuple_of_named_exceptions_is_out_of_scope():
    src = "try:\n    f()\nexcept (OSError, ValueError):\n    return None\n"
    assert undeclared_broad_handlers(src, "x.py") == []


def test_return_shape_is_irrelevant():
    """The rule is about handler breadth, not what the handler returns —
    spec §2.1. A handler returning a plausible-but-wrong literal is exactly
    the case a return-shape rule would miss."""
    src = 'try:\n    f()\nexcept Exception:\n    return "0.8.3"\n'
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]


def test_decoy_substring_is_not_a_marker():
    """A comment merely containing the characters BLE001 is not a marker —
    the convention is `noqa: BLE001`, and a substring match let
    `# see NOBLE0011 ticket` pass as validly marked."""
    src = "try:\n    f()\nexcept Exception:  # see NOBLE0011 ticket\n    pass\n"
    assert undeclared_broad_handlers(src, "x.py") == ["x.py:3"]
