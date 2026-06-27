"""
Anti-Goodhart edit-lock for the improve-skill loop (A1).

The Karpathy loop lets a proposer subagent emit a unified diff that
`apply_proposed_change()` applies and commits. Nothing in the prompt is binding,
so a diff could edit the skill's OWN rubric (`eval/eval.json`) — delete a failing
assertion, `total` drops, score "rises", change kept: optimize-the-score-not-the-goal.

This module is the pure guard. The invariant: the improver may modify a skill's
ASSET (SKILL.md, references/, scripts/ …) but NEVER its SCORER (`eval/`), and never
a path outside the skill's own directory. `apply_proposed_change()` calls
`diff_targets_locked_path` before any `git apply`; a hit raises `ScorerTamperError`
and the orchestrator skips the iteration (counted toward the consecutive-skip cap).

Per ADR-036 (2026-06-27 second amendment) and dotfiles python/coding-style.md.
"""

from __future__ import annotations

from pathlib import PurePosixPath

# The locked sub-tree within a skill directory: the rubric the loop must not touch.
LOCKED_SUBDIR = "eval"


class ScorerTamperError(Exception):
    """
    Raised when a proposed change targets the locked scorer (`eval/`) or escapes
    the skill directory.

    The orchestrator treats it like `ProposerError`: skip the iteration, no apply,
    no commit, and count it toward the 3-consecutive-skip cap so a proposer that
    keeps clawing at `eval/` exits cleanly instead of looping or tampering.
    """

    def __init__(self, path: str):
        self.path = path
        super().__init__(
            f"proposed change targets the locked scorer or escapes the skill dir: {path!r}"
        )


def _iter_diff_paths(unified_diff: str):
    """Yield the raw path tokens from a unified diff's `---`/`+++`/`diff --git` headers."""
    for line in unified_diff.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            yield line[4:].strip()
        elif line.startswith("diff --git "):
            # `diff --git a/<x> b/<y>` — yield both sides.
            parts = line[len("diff --git ") :].split()
            for tok in parts:
                yield tok.strip()


def _is_locked(raw_path: str, skill_name: str) -> bool:
    """
    True if `raw_path` (a diff token or a declared target_file) names the skill's
    locked scorer or a path outside the skill directory.
    """
    p = (raw_path or "").strip()
    if not p or p == "/dev/null":
        return False

    # Absolute paths are always an escape from the skill directory.
    if p.startswith("/"):
        return True

    # Strip the diff-prefix (`a/`, `b/`) if present.
    if p.startswith(("a/", "b/")):
        p = p[2:]

    parts = PurePosixPath(p).parts

    # Any traversal component escapes the skill directory.
    if ".." in parts:
        return True

    # Repo-root-relative (`skills/<name>/...`) → must be THIS skill; reduce to skill-relative.
    if parts and parts[0] == "skills":
        if len(parts) < 2 or parts[1] != skill_name:
            return True  # a different skill, or malformed
        rel_parts = parts[2:]
    else:
        rel_parts = parts

    # Skill-relative: locked iff it lives under the rubric subdir.
    return bool(rel_parts) and rel_parts[0] == LOCKED_SUBDIR


def diff_targets_locked_path(
    unified_diff: str,
    target_file: str | None,
    skill_name: str,
) -> str | None:
    """
    Return the first path that would write the locked scorer or escape the skill
    directory, or `None` if the change is confined to the legitimate asset surface.

    Checks BOTH the declared `target_file` (advisory) and every path in the diff
    headers (what `git apply` will actually write) — either one indicating a locked
    path is a rejection.

    Args:
        unified_diff: The proposed change's unified diff.
        target_file: The proposer's declared target (relative to the skill dir).
        skill_name: The skill being improved (its directory under `skills/`).

    Returns:
        The offending raw path string, or `None` when the change is allowed.
    """
    candidates = list(_iter_diff_paths(unified_diff))
    if target_file:
        candidates.append(target_file)
    for raw in candidates:
        if _is_locked(raw, skill_name):
            return raw
    return None
