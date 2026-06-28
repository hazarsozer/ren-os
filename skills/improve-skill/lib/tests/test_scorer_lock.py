"""
Tests for skills.improve-skill.lib.scorer_lock (A1 — anti-Goodhart edit-lock).

The improver may optimize a skill's ASSET (SKILL.md, references/) but must NEVER
modify the artifact that GRADES it (the skill's eval/ rubric) or escape the skill
directory. `diff_targets_locked_path` is the pure guard; `apply_proposed_change`
enforces it at the single choke point.

Run with:
    python3 -m pytest skills/improve-skill/lib/tests/test_scorer_lock.py -v
"""

from __future__ import annotations

import pytest

from ..scorer_lock import ScorerTamperError, diff_targets_locked_path


def _diff(path_a: str, path_b: str | None = None) -> str:
    """Build a minimal unified diff touching the given path(s)."""
    path_b = path_b or path_a
    return (
        f"diff --git a/{path_a} b/{path_b}\n"
        f"--- a/{path_a}\n"
        f"+++ b/{path_b}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )


SKILL = "sample-skill"


# --- LOCKED: editing the rubric -------------------------------------------------


def test_diff_editing_eval_json_repo_relative_is_locked():
    d = _diff(f"skills/{SKILL}/eval/eval.json")
    assert diff_targets_locked_path(d, "eval/eval.json", SKILL) is not None


def test_diff_editing_eval_json_skill_relative_is_locked():
    d = _diff("eval/eval.json")
    assert diff_targets_locked_path(d, "eval/eval.json", SKILL) is not None


def test_diff_editing_nested_eval_file_is_locked():
    d = _diff(f"skills/{SKILL}/eval/fixtures/case.json")
    assert diff_targets_locked_path(d, "eval/fixtures/case.json", SKILL) is not None


def test_target_file_claims_eval_even_if_diff_body_benign_is_locked():
    # target_file is advisory; a mismatch that claims eval/ is itself suspect.
    benign = _diff(f"skills/{SKILL}/SKILL.md")
    assert diff_targets_locked_path(benign, "eval/eval.json", SKILL) is not None


# --- LOCKED: escaping the skill directory --------------------------------------


def test_diff_traversal_escape_is_locked():
    d = _diff(f"skills/{SKILL}/../other-skill/SKILL.md")
    assert diff_targets_locked_path(d, "../other-skill/SKILL.md", SKILL) is not None


def test_diff_absolute_path_is_locked():
    d = _diff("/etc/passwd")
    assert diff_targets_locked_path(d, "/etc/passwd", SKILL) is not None


def test_diff_targeting_a_different_skill_is_locked():
    d = _diff("skills/other-skill/SKILL.md")
    assert diff_targets_locked_path(d, "SKILL.md", SKILL) is not None


# --- ALLOWED: the legitimate optimization surface ------------------------------


def test_diff_editing_skill_md_is_allowed():
    d = _diff(f"skills/{SKILL}/SKILL.md")
    assert diff_targets_locked_path(d, "SKILL.md", SKILL) is None


def test_diff_editing_references_file_is_allowed():
    d = _diff(f"skills/{SKILL}/references/orchestration.md")
    assert diff_targets_locked_path(d, "references/orchestration.md", SKILL) is None


def test_skill_relative_skill_md_is_allowed():
    d = _diff("SKILL.md")
    assert diff_targets_locked_path(d, "SKILL.md", SKILL) is None


def test_added_file_under_references_is_allowed():
    # `git diff` for a new file uses /dev/null on the old side.
    d = (
        f"diff --git a/skills/{SKILL}/references/new.md b/skills/{SKILL}/references/new.md\n"
        "--- /dev/null\n"
        f"+++ b/skills/{SKILL}/references/new.md\n"
        "@@ -0,0 +1 @@\n"
        "+hello\n"
    )
    assert diff_targets_locked_path(d, "references/new.md", SKILL) is None


# --- error type ----------------------------------------------------------------


def test_scorer_tamper_error_carries_path():
    err = ScorerTamperError("eval/eval.json")
    assert err.path == "eval/eval.json"
    assert "eval/eval.json" in str(err)


# --- enforcement wiring: apply_proposed_change rejects BEFORE git apply ---------


def test_apply_proposed_change_rejects_eval_diff(tmp_path):
    """The guard runs before `git apply`, so a tampering diff is refused without
    touching git (no repo needed)."""
    from ..__init__ import apply_proposed_change
    from ..types import ProposedChange

    change = ProposedChange(
        target_file="eval/eval.json",
        unified_diff=_diff(f"skills/{SKILL}/eval/eval.json"),
        summary="sneaky",
        rationale="game the score",
    )
    with pytest.raises(ScorerTamperError):
        apply_proposed_change(
            change, skill_name=SKILL, skills_root=tmp_path / "skills", cwd=tmp_path
        )
