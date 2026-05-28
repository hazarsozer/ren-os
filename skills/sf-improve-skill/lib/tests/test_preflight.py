"""
Tests for skills.sf_improve_skill.lib.preflight.

Pure-logic coverage focuses on validate_autonomous_flags (no I/O) and the
JSON/path validators (use tmpdir fixtures). validate_working_tree_clean
needs a git repo and is exercised through tmpdir + `git init`.

Per dotfiles python/testing.md: pytest framework. Run with:
    python3 -m pytest skills/sf-improve-skill/lib/tests/ -v
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ..preflight import (
    pre_flight_check,
    validate_autonomous_flags,
    validate_working_tree_clean,
)
from ..types import ImproveSkillArgs, PreFlightError


# --- validate_autonomous_flags --------------------------------------------


class TestValidateAutonomousFlags:
    def test_interactive_default_no_flags_passes(self):
        args = ImproveSkillArgs(skill_name="x")
        validate_autonomous_flags(args)  # no raise

    def test_interactive_explicit_no_flags_passes(self):
        args = ImproveSkillArgs(skill_name="x", interactive=True, autonomous=False)
        validate_autonomous_flags(args)

    def test_autonomous_with_both_flags_passes(self):
        args = ImproveSkillArgs(
            skill_name="x",
            autonomous=True,
            max_iterations=10,
            max_budget_usd=5.00,
        )
        validate_autonomous_flags(args)

    def test_autonomous_missing_max_iterations_refused(self):
        args = ImproveSkillArgs(
            skill_name="x",
            autonomous=True,
            max_budget_usd=5.00,
        )
        with pytest.raises(PreFlightError, match="--max-iterations"):
            validate_autonomous_flags(args)

    def test_autonomous_missing_max_budget_refused(self):
        args = ImproveSkillArgs(
            skill_name="x",
            autonomous=True,
            max_iterations=10,
        )
        with pytest.raises(PreFlightError, match="--max-budget-usd"):
            validate_autonomous_flags(args)

    def test_autonomous_missing_both_lists_both(self):
        args = ImproveSkillArgs(skill_name="x", autonomous=True)
        with pytest.raises(PreFlightError) as exc_info:
            validate_autonomous_flags(args)
        msg = str(exc_info.value)
        assert "--max-iterations" in msg
        assert "--max-budget-usd" in msg

    def test_autonomous_with_zero_iterations_refused(self):
        args = ImproveSkillArgs(
            skill_name="x",
            autonomous=True,
            max_iterations=0,
            max_budget_usd=5.00,
        )
        with pytest.raises(PreFlightError, match="--max-iterations"):
            validate_autonomous_flags(args)

    def test_autonomous_with_negative_budget_refused(self):
        args = ImproveSkillArgs(
            skill_name="x",
            autonomous=True,
            max_iterations=10,
            max_budget_usd=-1.00,
        )
        with pytest.raises(PreFlightError, match="--max-budget-usd"):
            validate_autonomous_flags(args)

    def test_max_turns_NOT_required(self):
        """Per ADR-012 amendment 2026-05-28: --max-turns dropped from required set.

        This test pins option (a) — DO NOT add --max-turns to required without
        also confirming the flag actually exists in claude --help. See
        references/cc-flag-watch.md for the watch.
        """
        args = ImproveSkillArgs(
            skill_name="x",
            autonomous=True,
            max_iterations=10,
            max_budget_usd=5.00,
            # max_turns_shadow intentionally NOT set
        )
        validate_autonomous_flags(args)  # MUST PASS


# --- _validate_eval_file via pre_flight_check tmpdir fixtures -------------


REPO_ROOT = Path(__file__).resolve().parents[4]  # /home/hsozer/Dev/startup-framework

# Real framework-shipped eval.json files — used as CANONICAL pinning fixtures.
# If preflight rejects ANY of these, the validator has drifted from ADR-011.
CANONICAL_EVAL_FIXTURES = [
    REPO_ROOT / "skills" / "sf-install" / "eval" / "eval.json",
    REPO_ROOT / "skills" / "sf-interview" / "eval" / "eval.json",
    REPO_ROOT / "skills" / "sf-bootstrap-project" / "eval" / "eval.json",
    REPO_ROOT / "skills" / "sf-wrap" / "eval" / "eval.json",
]


@pytest.fixture
def args_interactive() -> ImproveSkillArgs:
    return ImproveSkillArgs(skill_name="sample-skill", autonomous=False)


class TestEvalFileValidation:
    """Negative tests + ADR-011 conformance tests for _validate_eval_file."""

    def test_missing_skill_dir_refused(self, tmp_path: Path, args_interactive):
        empty_root = tmp_path / "skills"
        empty_root.mkdir()
        with pytest.raises(PreFlightError, match="not found"):
            from ..preflight import _validate_skill_exists
            _validate_skill_exists(empty_root / "missing-skill")

    def test_missing_skill_md_refused(self, tmp_path: Path):
        from ..preflight import _validate_skill_exists
        skill_dir = tmp_path / "skills" / "bare-skill"
        skill_dir.mkdir(parents=True)
        with pytest.raises(PreFlightError, match="SKILL.md"):
            _validate_skill_exists(skill_dir)

    def test_missing_eval_file_refused(self, tmp_path: Path):
        from ..preflight import _validate_eval_file
        skill_dir = tmp_path / "skills" / "no-eval"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# x\n", encoding="utf-8")
        with pytest.raises(PreFlightError, match="eval"):
            _validate_eval_file(skill_dir)

    def test_malformed_json_refused(self, tmp_path: Path):
        from ..preflight import _validate_eval_file
        skill_dir = tmp_path / "skills" / "bad-json"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text("{not valid json", encoding="utf-8")
        with pytest.raises(PreFlightError, match="valid JSON"):
            _validate_eval_file(skill_dir)

    def test_missing_tests_key_refused(self, tmp_path: Path):
        """ADR-011: top-level key is 'tests', not 'test_cases' (regression test)."""
        from ..preflight import _validate_eval_file
        skill_dir = tmp_path / "skills" / "wrong-toplevel"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        # The PRE-FIX wrong shape — must be rejected because there's no 'tests' field
        (eval_dir / "eval.json").write_text(
            json.dumps({"test_cases": [{"id": "t1", "assertions": []}]}),
            encoding="utf-8",
        )
        with pytest.raises(PreFlightError, match="'tests' array"):
            _validate_eval_file(skill_dir)

    def test_empty_tests_array_refused(self, tmp_path: Path):
        from ..preflight import _validate_eval_file
        skill_dir = tmp_path / "skills" / "empty"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps({"tests": []}), encoding="utf-8"
        )
        with pytest.raises(PreFlightError, match="non-empty"):
            _validate_eval_file(skill_dir)

    def test_non_string_assertion_refused(self, tmp_path: Path):
        """ADR-011: binary_assertions items are STRINGS, not objects."""
        from ..preflight import _validate_eval_file
        skill_dir = tmp_path / "skills" / "object-assertions"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        # The PRE-FIX wrong shape — object with binary field
        (eval_dir / "eval.json").write_text(
            json.dumps(
                {
                    "tests": [
                        {
                            "id": "t1",
                            "binary_assertions": [
                                {"desc": "looks good", "binary": True}
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(PreFlightError, match="strings per ADR-011"):
            _validate_eval_file(skill_dir)

    def test_zero_assertions_total_refused(self, tmp_path: Path):
        from ..preflight import _validate_eval_file
        skill_dir = tmp_path / "skills" / "empty-assertions"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps(
                {"tests": [{"id": "t1", "binary_assertions": []}]}
            ),
            encoding="utf-8",
        )
        with pytest.raises(PreFlightError, match="zero binary assertions"):
            _validate_eval_file(skill_dir)

    def test_non_object_test_refused(self, tmp_path: Path):
        from ..preflight import _validate_eval_file
        skill_dir = tmp_path / "skills" / "bad-test-shape"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps({"tests": ["just-a-string-not-an-object"]}),
            encoding="utf-8",
        )
        with pytest.raises(PreFlightError, match="must be an object"):
            _validate_eval_file(skill_dir)

    def test_minimal_valid_eval_accepted(self, tmp_path: Path):
        """Smallest valid ADR-011 shape passes."""
        from ..preflight import _validate_eval_file
        skill_dir = tmp_path / "skills" / "minimal"
        eval_dir = skill_dir / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "eval.json").write_text(
            json.dumps(
                {
                    "name": "minimal",
                    "tests": [
                        {
                            "id": "t1",
                            "binary_assertions": ["The skill produces output."],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        # No raise → pass
        _validate_eval_file(skill_dir)


class TestCanonicalEvalFixtureConformance:
    """
    LOAD-BEARING PINNING TESTS — validate against REAL contract instances.

    These tests catch validator drift by loading every framework-shipped
    eval.json and asserting preflight accepts them. They exist because the
    previous validator (used wrong keys: 'test_cases' / 'assertions' /
    objects-with-binary-field) would have rejected EVERY framework skill's
    real eval.json — making /sf:improve-skill unusable on shipped skills.

    Lesson: always validate against a real instance of the contract, not
    against an in-memory model of what the contract should be. See
    skills/sf-improve-skill/learnings.md "validate against real contract
    instances" entry.

    If a new framework skill ships a real eval.json, ADD IT to
    CANONICAL_EVAL_FIXTURES at the top of this test module.
    """

    @pytest.mark.parametrize(
        "fixture_path",
        CANONICAL_EVAL_FIXTURES,
        ids=lambda p: p.parent.parent.name,  # display as e.g. "sf-install"
    )
    def test_canonical_eval_passes_preflight(self, fixture_path: Path):
        """Every framework-shipped eval.json must conform to ADR-011 per preflight."""
        from ..preflight import _validate_eval_file

        if not fixture_path.is_file():
            pytest.skip(f"fixture missing (not yet shipped?): {fixture_path}")

        # _validate_eval_file expects skill_dir; eval.json lives at skill_dir/eval/eval.json
        skill_dir = fixture_path.parent.parent
        # No raise → ADR-011 conformance confirmed
        _validate_eval_file(skill_dir)

    def test_at_least_two_real_fixtures_exist(self):
        """Sanity: we must have multiple real ADR-011 instances to pin against."""
        existing = [p for p in CANONICAL_EVAL_FIXTURES if p.is_file()]
        assert len(existing) >= 2, (
            f"Need at least 2 shipped eval.json fixtures to pin against ADR-011 drift. "
            f"Found: {[str(p) for p in existing]}"
        )


# --- validate_working_tree_clean (uses tmpdir + real git) -----------------


class TestWorkingTreeClean:
    def _init_repo(self, path: Path) -> None:
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=path, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)

    def test_clean_tree_passes(self, tmp_path: Path):
        self._init_repo(tmp_path)
        # Empty repo with no untracked → clean
        validate_working_tree_clean(cwd=tmp_path)  # no raise

    def test_clean_tree_with_committed_files_passes(self, tmp_path: Path):
        self._init_repo(tmp_path)
        (tmp_path / "a.txt").write_text("hi\n")
        subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True
        )
        validate_working_tree_clean(cwd=tmp_path)

    def test_untracked_file_refused(self, tmp_path: Path):
        self._init_repo(tmp_path)
        (tmp_path / "dirty.txt").write_text("uncommitted\n")
        with pytest.raises(PreFlightError, match="uncommitted"):
            validate_working_tree_clean(cwd=tmp_path)

    def test_modified_file_refused(self, tmp_path: Path):
        self._init_repo(tmp_path)
        (tmp_path / "a.txt").write_text("hi\n")
        subprocess.run(["git", "add", "a.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True
        )
        # Modify the file
        (tmp_path / "a.txt").write_text("modified\n")
        with pytest.raises(PreFlightError, match="uncommitted"):
            validate_working_tree_clean(cwd=tmp_path)

    def test_non_git_dir_refused(self, tmp_path: Path):
        with pytest.raises(PreFlightError, match="git"):
            validate_working_tree_clean(cwd=tmp_path)


# --- ImproveSkillArgs sanity ------------------------------------------------


class TestImproveSkillArgs:
    def test_default_args_interactive(self):
        args = ImproveSkillArgs(skill_name="x")
        assert args.interactive is True
        assert args.autonomous is False
        assert args.bare is True
        assert args.dry_run is False
        assert args.keep_branch is False

    def test_frozen(self):
        args = ImproveSkillArgs(skill_name="x")
        with pytest.raises(Exception):  # FrozenInstanceError
            args.autonomous = True  # type: ignore[misc]
