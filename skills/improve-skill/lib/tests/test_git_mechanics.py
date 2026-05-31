"""
Tests for skills.sf_improve_skill.lib.git_mechanics.

Real subprocess git operations against per-test tmpdir repos. Each operation
exercised in isolation; the conftest's `tmp_git_repo` fixture provides a clean
repo with one initial commit on `main`.

Per common/testing.md: real git execution, not mocked. Subprocess wrappers are
thin enough that mocking the underlying calls would be testing the mock, not
the behavior.

Run with:
    python3 -m pytest skills/sf-improve-skill/lib/tests/test_git_mechanics.py -v
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ..git_mechanics import (
    TIMESTAMP_FORMAT,
    amend_iteration_metadata,
    cleanup_on_cancel,
    commit_iteration,
    create_improve_branch,
    get_current_branch,
    get_head_sha,
    parse_iteration_metadata,
    revert_last_iteration,
    squash_merge_on_success,
)


# ---------------------------------------------------------------------------
# Helpers used across tests
# ---------------------------------------------------------------------------


def _list_branches(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "branch", "--list"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().lstrip("* ").strip() for line in result.stdout.splitlines() if line.strip()]


def _modify_and_stage(repo: Path, content: str = "modified\n") -> None:
    """Edit the sample skill so a commit has something to record."""
    (repo / "skills" / "sample-skill" / "SKILL.md").write_text(content, encoding="utf-8")


def _commit_body(repo: Path) -> str:
    """Return the full body (subject + body) of HEAD."""
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------
# create_improve_branch
# ---------------------------------------------------------------------------


class TestCreateImproveBranch:
    def test_creates_branch_with_canonical_format(self, tmp_git_repo: Path):
        branch = create_improve_branch("sf-wrap", cwd=tmp_git_repo)
        # Format: improve/<skill>/<YYYY-MM-DD-HHMMSS>
        assert re.match(r"^improve/sf-wrap/\d{4}-\d{2}-\d{2}-\d{6}$", branch), branch
        assert branch in _list_branches(tmp_git_repo)

    def test_switches_to_new_branch(self, tmp_git_repo: Path):
        branch = create_improve_branch("sf-wrap", cwd=tmp_git_repo)
        assert get_current_branch(cwd=tmp_git_repo) == branch

    def test_uses_provided_prefix(self, tmp_git_repo: Path):
        branch = create_improve_branch("sf-wrap", prefix="experiment", cwd=tmp_git_repo)
        assert branch.startswith("experiment/sf-wrap/"), branch

    def test_uses_provided_timestamp(self, tmp_git_repo: Path):
        fixed_now = datetime(2026, 1, 15, 12, 34, 56, tzinfo=timezone.utc)
        branch = create_improve_branch("sf-wrap", cwd=tmp_git_repo, now=fixed_now)
        assert branch == "improve/sf-wrap/2026-01-15-123456"

    def test_two_calls_get_distinct_branches(self, tmp_git_repo: Path):
        # Mock distinct timestamps to avoid same-second collision
        now1 = datetime(2026, 1, 15, 12, 34, 56, tzinfo=timezone.utc)
        now2 = datetime(2026, 1, 15, 12, 34, 57, tzinfo=timezone.utc)
        b1 = create_improve_branch("s", cwd=tmp_git_repo, now=now1)
        subprocess.run(["git", "switch", "main"], cwd=tmp_git_repo, check=True, capture_output=True)
        b2 = create_improve_branch("s", cwd=tmp_git_repo, now=now2)
        assert b1 != b2

    def test_unknown_base_ref_raises(self, tmp_git_repo: Path):
        with pytest.raises(subprocess.CalledProcessError):
            create_improve_branch("s", base_ref="totally-nonexistent-ref", cwd=tmp_git_repo)


# ---------------------------------------------------------------------------
# commit_iteration + get_head_sha
# ---------------------------------------------------------------------------


class TestCommitIteration:
    def test_basic_commit(self, tmp_git_repo: Path):
        create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo)
        sha = commit_iteration(1, "tightened the language", cwd=tmp_git_repo)

        # SHA is 40 hex chars
        assert re.match(r"^[0-9a-f]{40}$", sha)
        # HEAD now is the new commit
        assert get_head_sha(cwd=tmp_git_repo) == sha

    def test_commit_subject_format(self, tmp_git_repo: Path):
        create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo)
        commit_iteration(3, "added clarifying example", cwd=tmp_git_repo)
        body = _commit_body(tmp_git_repo)
        # First line is the subject
        assert body.splitlines()[0] == "iter 3: added clarifying example"

    def test_commit_body_has_metadata_block(self, tmp_git_repo: Path):
        create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo)
        commit_iteration(
            2,
            "test summary",
            cwd=tmp_git_repo,
            metadata={"score_before": "0.5", "score_after": "0.7"},
        )
        body = _commit_body(tmp_git_repo)
        assert "improve-skill metadata:" in body
        assert "iteration: 2" in body
        assert "status: pending" in body
        assert "score_before: 0.5" in body
        assert "score_after: 0.7" in body

    def test_nothing_staged_raises(self, tmp_git_repo: Path):
        create_improve_branch("s", cwd=tmp_git_repo)
        # No working-tree changes
        with pytest.raises(subprocess.CalledProcessError):
            commit_iteration(1, "nothing to commit", cwd=tmp_git_repo)


# ---------------------------------------------------------------------------
# amend_iteration_metadata
# ---------------------------------------------------------------------------


class TestAmendIterationMetadata:
    def _setup_commit(self, repo: Path) -> str:
        create_improve_branch("s", cwd=repo)
        _modify_and_stage(repo)
        return commit_iteration(1, "test", cwd=repo, metadata={"score_before": "0.5"})

    def test_updates_existing_key(self, tmp_git_repo: Path):
        original_sha = self._setup_commit(tmp_git_repo)
        new_sha = amend_iteration_metadata(cwd=tmp_git_repo, status="improved")
        assert new_sha != original_sha  # amend changes the SHA
        body = _commit_body(tmp_git_repo)
        assert "status: improved" in body
        assert "status: pending" not in body

    def test_appends_missing_key(self, tmp_git_repo: Path):
        self._setup_commit(tmp_git_repo)
        amend_iteration_metadata(cwd=tmp_git_repo, score_after="0.75")
        body = _commit_body(tmp_git_repo)
        assert "score_after: 0.75" in body
        assert "score_before: 0.5" in body  # untouched

    def test_multiple_fields_at_once(self, tmp_git_repo: Path):
        self._setup_commit(tmp_git_repo)
        amend_iteration_metadata(
            cwd=tmp_git_repo,
            status="improved",
            score_after="0.7",
            usd_spent="0.18",
        )
        body = _commit_body(tmp_git_repo)
        assert "status: improved" in body
        assert "score_after: 0.7" in body
        assert "usd_spent: 0.18" in body


# ---------------------------------------------------------------------------
# revert_last_iteration
# ---------------------------------------------------------------------------


class TestRevertLastIteration:
    def test_discards_commit_and_working_tree(self, tmp_git_repo: Path):
        create_improve_branch("s", cwd=tmp_git_repo)
        base_sha = get_head_sha(cwd=tmp_git_repo)

        _modify_and_stage(tmp_git_repo)
        commit_iteration(1, "to be reverted", cwd=tmp_git_repo)
        assert get_head_sha(cwd=tmp_git_repo) != base_sha

        revert_last_iteration("score dropped", cwd=tmp_git_repo)
        assert get_head_sha(cwd=tmp_git_repo) == base_sha

        # Working tree clean
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout == ""

    def test_reflog_still_records_reverted_sha(self, tmp_git_repo: Path):
        create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo)
        sha_to_revert = commit_iteration(1, "test", cwd=tmp_git_repo)
        revert_last_iteration("test revert", cwd=tmp_git_repo)

        # The reflog should still have the reverted SHA recoverable.
        # `git reflog` abbreviates SHAs to 7 chars by default (older versions);
        # newer versions may show more. We assert on the 7-char prefix to be
        # version-robust. The full SHA is recoverable via `git reflog --no-abbrev`.
        result = subprocess.run(
            ["git", "reflog"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert sha_to_revert[:7] in result.stdout, (
            f"Expected reflog to contain {sha_to_revert[:7]!r}, got:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# cleanup_on_cancel
# ---------------------------------------------------------------------------


class TestCleanupOnCancel:
    def test_clears_dirty_working_tree(self, tmp_git_repo: Path):
        create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo, "dirty changes\n")

        cleanup_on_cancel(cwd=tmp_git_repo)

        # Working tree is now clean
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout == ""

    def test_preserves_last_completed_commit(self, tmp_git_repo: Path):
        create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo, "first iteration\n")
        sha_completed = commit_iteration(1, "completed", cwd=tmp_git_repo)

        # Now start a "second iteration" by editing again, then cancel
        _modify_and_stage(tmp_git_repo, "mid-iteration changes\n")
        cleanup_on_cancel(cwd=tmp_git_repo)

        # The completed commit is still HEAD
        assert get_head_sha(cwd=tmp_git_repo) == sha_completed


# ---------------------------------------------------------------------------
# squash_merge_on_success
# ---------------------------------------------------------------------------


class TestSquashMergeOnSuccess:
    def test_merges_and_deletes_branch(self, tmp_git_repo: Path):
        branch = create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo, "iter 1 content\n")
        commit_iteration(1, "improved", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo, "iter 2 content\n")
        commit_iteration(2, "improved more", cwd=tmp_git_repo)

        sha = squash_merge_on_success(
            branch,
            base_ref="main",
            commit_message="improve(s): 2 iterations; 0% → 100%",
            cwd=tmp_git_repo,
        )

        assert sha is not None
        # Now on main, with the squash commit
        assert get_current_branch(cwd=tmp_git_repo) == "main"
        body = _commit_body(tmp_git_repo)
        assert "improve(s): 2 iterations" in body
        # Branch is deleted
        assert branch not in _list_branches(tmp_git_repo)

    def test_keep_branch_true_is_noop(self, tmp_git_repo: Path):
        branch = create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo)
        commit_iteration(1, "kept", cwd=tmp_git_repo)
        original_branch_count = len(_list_branches(tmp_git_repo))

        result = squash_merge_on_success(
            branch,
            base_ref="main",
            commit_message="not used",
            keep_branch=True,
            cwd=tmp_git_repo,
        )

        assert result is None
        # Branch still exists; no merge happened
        assert branch in _list_branches(tmp_git_repo)
        assert len(_list_branches(tmp_git_repo)) == original_branch_count

    def test_single_squash_commit_collapses_multiple_iterations(self, tmp_git_repo: Path):
        branch = create_improve_branch("s", cwd=tmp_git_repo)

        for i in range(1, 4):
            _modify_and_stage(tmp_git_repo, f"iter {i}\n")
            commit_iteration(i, f"iter {i}", cwd=tmp_git_repo)

        squash_merge_on_success(
            branch,
            base_ref="main",
            commit_message="squashed",
            cwd=tmp_git_repo,
        )

        # On main, between the initial commit and the squash commit there should be NO intermediate commits
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=tmp_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        # main has exactly: initial + 1 squash = 2 commits
        assert len(result.stdout.strip().splitlines()) == 2


# ---------------------------------------------------------------------------
# parse_iteration_metadata
# ---------------------------------------------------------------------------


class TestParseIterationMetadata:
    def test_parses_metadata_block(self):
        body = (
            "iter 1: tightened the language\n"
            "\n"
            "improve-skill metadata:\n"
            "  iteration: 1\n"
            "  status: improved\n"
            "  score_before: 0.5\n"
            "  score_after: 0.7\n"
        )
        meta = parse_iteration_metadata(body)
        assert meta == {
            "iteration": "1",
            "status": "improved",
            "score_before": "0.5",
            "score_after": "0.7",
        }

    def test_empty_dict_when_no_block(self):
        body = "just a regular commit message\n"
        assert parse_iteration_metadata(body) == {}

    def test_stops_at_block_end(self):
        body = (
            "subject\n"
            "\n"
            "improve-skill metadata:\n"
            "  iteration: 1\n"
            "\n"
            "Unrelated trailing content: stuff\n"
        )
        meta = parse_iteration_metadata(body)
        assert meta == {"iteration": "1"}
        assert "Unrelated trailing content" not in meta

    def test_round_trips_with_commit_and_amend(self, tmp_git_repo: Path):
        """Integration: commit metadata, parse it back."""
        create_improve_branch("s", cwd=tmp_git_repo)
        _modify_and_stage(tmp_git_repo)
        commit_iteration(
            5,
            "round-trip test",
            cwd=tmp_git_repo,
            metadata={"score_before": "0.4", "score_after": "0.6"},
        )
        meta = parse_iteration_metadata(_commit_body(tmp_git_repo))
        assert meta["iteration"] == "5"
        assert meta["score_before"] == "0.4"
        assert meta["score_after"] == "0.6"
        assert meta["status"] == "pending"


# ---------------------------------------------------------------------------
# Module-level smoke
# ---------------------------------------------------------------------------


class TestModuleSmoke:
    def test_timestamp_format_constant(self):
        # Verify the format string produces the expected layout when given a real datetime
        sample = datetime(2026, 5, 28, 20, 30, 12, tzinfo=timezone.utc).strftime(TIMESTAMP_FORMAT)
        assert sample == "2026-05-28-203012"
        assert re.match(r"^\d{4}-\d{2}-\d{2}-\d{6}$", sample)
