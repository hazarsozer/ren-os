"""
feed/ — Activity Feed module for the startup framework.

The framework's only cross-friend layer. Per ADR-018, ADR-021, ADR-020, ADR-017, ADR-019.

This package's public API is locked (team-lead approved 2026-05-28, refactored to the
split-writer shape 2026-05-28 evening). Signatures may not change without arbitration.
Implementations may change freely.

The locked contract is re-exported here so callers (lifecycle's wake-up hook +
/sf:wrap, onboarding's Stage 3, the /sf:catch-up / /sf:disable-feed skills) import
from one place:

    from feed import (
        feed_write_session_start,
        feed_write_session_end,
        feed_write_release,
        feed_read_friends_tails,
        feed_read_tail,
        is_skip_active,
        ...
    )
"""

from feed.skip import is_skip_active
from feed.format import (
    FeedEntry,
    FeedEntryKind,
    build_start_entry,
    build_end_entry,
    build_release_entry,
    validate_end_entry,
    validate_start_entry,
    FormatViolation,
)
from feed.writer import (
    # Public split writers (team-lead arbitration 2026-05-28)
    feed_write_session_start,
    feed_write_session_end,
    feed_write_release,
    # Deterministic fakes (matching split shape)
    feed_write_session_start_fake,
    feed_write_session_end_fake,
    feed_write_release_fake,
    # Utilities
    compute_entry_id,
    rename_handle,
    FeedWriteResult,
)
from feed.reader import (
    feed_read_friends_tails,
    feed_read_friends_tails_fake,
    feed_read_tail,
    read_all_entries,
    FriendsTail,
    format_relative_time,
    format_entry_one_line,
)
from feed.bootstrap import (
    feed_detect_repo_state,
    feed_bootstrap_first_friend,
    feed_clone_existing,
    RepoState,
    RepoMode,
)
from feed.identity_sync import feed_upsert_identity
from feed.io_github import (
    pull,
    push,
    check_auth,
    PullResult,
    PushResult,
    AuthStatus,
)
from feed import config

__all__ = [
    # skip-chain
    "is_skip_active",
    # format
    "FeedEntry",
    "FeedEntryKind",
    "build_start_entry",
    "build_end_entry",
    "build_release_entry",
    "validate_end_entry",
    "validate_start_entry",
    "FormatViolation",
    # writers (split per team-lead arbitration)
    "feed_write_session_start",
    "feed_write_session_end",
    "feed_write_release",
    "feed_write_session_start_fake",
    "feed_write_session_end_fake",
    "feed_write_release_fake",
    "compute_entry_id",
    "rename_handle",
    "FeedWriteResult",
    # readers
    "feed_read_friends_tails",
    "feed_read_friends_tails_fake",
    "feed_read_tail",
    "read_all_entries",
    "FriendsTail",
    "format_relative_time",
    "format_entry_one_line",
    # bootstrap
    "feed_detect_repo_state",
    "feed_bootstrap_first_friend",
    "feed_clone_existing",
    "RepoState",
    "RepoMode",
    # identity
    "feed_upsert_identity",
    # github I/O
    "pull",
    "push",
    "check_auth",
    "PullResult",
    "PushResult",
    "AuthStatus",
    # config
    "config",
]
