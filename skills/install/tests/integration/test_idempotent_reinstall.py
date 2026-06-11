"""Idempotent re-install — second /sf:install no-ops cleanly on a completed install."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integration.simulator import InstallSimulator


def test_reinstall_after_completion_is_safe(
    tmp_wiki: Path,
    tmp_checkpoint: Path,
    skeleton_root: Path,
    distribution_fake,
    lifecycle_fake,
) -> None:
    """Run a fresh install, then re-run and assert nothing breaks."""
    first = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
    first.run()
    assert first.state["completed_stages"] == [1, 2, 3, 4, 5, 6, 7]

    # Reset call recorders; fresh fakes for the second run with same checkpoint.
    second_distribution = type(distribution_fake)()
    second_lifecycle = type(lifecycle_fake)()

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=second_distribution,
        lifecycle=second_lifecycle,
    )
    second.run()

    assert second.aborted_at is None
    assert second.state["completed_stages"] == [1, 2, 3, 4, 5, 6, 7]

    # Stage 2 plugin install list unchanged across re-run.
    assert (
        second.state["stage_artifacts"]["2"]["plugins_installed"]
        == first.state["stage_artifacts"]["2"]["plugins_installed"]
    )


def test_reinstall_skips_completed_stage_3(
    tmp_wiki: Path,
    tmp_checkpoint: Path,
    skeleton_root: Path,
    distribution_fake,
    lifecycle_fake,
) -> None:
    """Stage 3 (conditional plugins) is idempotent — a re-run marks it skipped,
    not re-executed."""
    first = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
    first.run()
    assert 3 in first.state["completed_stages"]

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=type(distribution_fake)(),
        lifecycle=type(lifecycle_fake)(),
    )
    second.run()
    # Stage 3 re-run is a skip (already complete), not a re-execute.
    assert any(n == 3 and status == "skip" for (n, status, _detail) in second.stage_log)


def test_reinstall_preserves_checkpoint_completion_set(
    tmp_wiki: Path,
    tmp_checkpoint: Path,
    skeleton_root: Path,
    distribution_fake,
    lifecycle_fake,
) -> None:
    first = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
    first.run()

    pre_completed = list(json.loads(tmp_checkpoint.read_text())["completed_stages"])

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        distribution=type(distribution_fake)(),
        lifecycle=type(lifecycle_fake)(),
    )
    second.run()
    post_completed = json.loads(tmp_checkpoint.read_text())["completed_stages"]

    # Same set; not duplicated; sorted.
    assert post_completed == pre_completed
    assert post_completed == sorted(set(post_completed))
