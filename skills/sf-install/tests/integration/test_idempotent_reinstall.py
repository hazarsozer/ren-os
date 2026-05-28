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
    feed_fake,
    distribution_fake,
    lifecycle_fake,
) -> None:
    """Run a fresh install, then re-run and assert nothing breaks."""
    first = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        feed=feed_fake,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
    first.run()
    assert first.state["completed_stages"] == [1, 2, 3, 4, 5, 6, 7]

    # Reset call recorders; fresh fakes for the second run with same checkpoint.
    second_feed = type(feed_fake)()
    second_distribution = type(distribution_fake)()
    second_lifecycle = type(lifecycle_fake)()

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        feed=second_feed,
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


def test_reinstall_does_not_call_feed_bootstrap_again(
    tmp_wiki: Path,
    tmp_checkpoint: Path,
    skeleton_root: Path,
    distribution_fake,
    lifecycle_fake,
) -> None:
    from integration.fakes.feed_fake import FeedFake

    first_feed = FeedFake()
    first = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        feed=first_feed,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
    first.run()
    assert "bootstrap_first_friend" in first_feed.call_names()

    second_feed = FeedFake()
    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        feed=second_feed,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
    second.run()
    # Stage 3 should skip — bootstrap_first_friend MUST NOT be called again.
    assert "bootstrap_first_friend" not in second_feed.call_names()


def test_reinstall_preserves_checkpoint_completion_set(
    tmp_wiki: Path,
    tmp_checkpoint: Path,
    skeleton_root: Path,
    feed_fake,
    distribution_fake,
    lifecycle_fake,
) -> None:
    first = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        feed=feed_fake,
        distribution=distribution_fake,
        lifecycle=lifecycle_fake,
    )
    first.run()

    pre_completed = list(json.loads(tmp_checkpoint.read_text())["completed_stages"])

    second = InstallSimulator(
        wiki_root=tmp_wiki,
        checkpoint_path=tmp_checkpoint,
        skeleton_root=skeleton_root,
        feed=type(feed_fake)(),
        distribution=type(distribution_fake)(),
        lifecycle=type(lifecycle_fake)(),
    )
    second.run()
    post_completed = json.loads(tmp_checkpoint.read_text())["completed_stages"]

    # Same set; not duplicated; sorted.
    assert post_completed == pre_completed
    assert post_completed == sorted(set(post_completed))
