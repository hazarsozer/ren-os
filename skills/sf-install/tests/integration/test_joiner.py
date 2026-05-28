"""Joiner install — Stage 3 detects existing feed and clones (no bootstrap)."""

from __future__ import annotations


def test_joiner_takes_clone_branch_not_bootstrap(simulator, feed_fake) -> None:
    feed_fake.inject_detect_response(
        mode="joiner-clone",
        existing_handles=("hazar", "second-friend"),
        has_other_friends=True,
    )
    simulator.run()

    assert simulator.aborted_at is None
    names = feed_fake.call_names()
    # Joiner path: detect → clone → upsert. NOT bootstrap_first_friend.
    assert "clone_existing" in names
    assert "bootstrap_first_friend" not in names
    assert "upsert_identity" in names


def test_joiner_records_clone_mode_in_state(simulator, feed_fake) -> None:
    feed_fake.inject_detect_response(
        mode="joiner-clone",
        existing_handles=("hazar",),
        has_other_friends=True,
    )
    simulator.run()

    assert simulator.state["stage_artifacts"]["3"]["feed_state"] == "joiner-clone"


def test_joiner_aborts_on_handle_collision(simulator, feed_fake) -> None:
    feed_fake.inject_detect_response(
        mode="joiner-clone",
        existing_handles=("eval-friend", "second-friend"),
        has_other_friends=True,
    )
    # The default answer's handle is "eval-friend" — collision.
    simulator.run()

    assert simulator.aborted_at == 3
    assert "handle collision" in simulator.abort_reason
    # Stage 3 didn't call clone_existing because the collision halts before dispatch.
    names = feed_fake.call_names()
    assert "clone_existing" not in names
    assert "bootstrap_first_friend" not in names


def test_joiner_does_not_inherit_group_history(simulator, tmp_wiki, feed_fake) -> None:
    """Per ADR-017: joiner's local wiki starts EMPTY of other friends' content."""
    feed_fake.inject_detect_response(
        mode="joiner-clone",
        existing_handles=("hazar",),
        has_other_friends=True,
    )
    simulator.run()

    # The new local wiki is created from skeleton; no other friend's content
    # appears anywhere under it.
    for path in tmp_wiki.rglob("*.md"):
        body = path.read_text(encoding="utf-8")
        assert "hazar" not in body.lower() or path.name == "identity.md", (
            f"file {path} contains 'hazar' — possible group-history leak"
        )
