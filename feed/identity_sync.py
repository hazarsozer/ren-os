"""
feed.identity_sync — write identities/<handle>.md to the activity-feed repo.

Real implementation (task #21). Replaces scaffold stub from task #17.

Called by onboarding-2's Stage 4 (/sf:interview) after the friend's local
wiki/identity.md is written. Onboarding produces a PUBLIC-facing markdown summary
(subset of wiki/identity.md per ADR-018 §"Identity in the activity feed") and passes
it here. We upsert + commit + push.

Idempotent: only commits if content changed. Onboarding can call this on every
install run without polluting git history with no-op commits.
"""

from __future__ import annotations

from feed import config, io_github
from feed.writer import FeedWriteResult


def feed_upsert_identity(handle: str, public_identity_md: str) -> FeedWriteResult:
    """Upsert identities/<handle>.md in the activity-feed repo.

    Idempotent: only commits if content changed.

    Args:
        handle: the friend's handle (used as the filename: identities/<handle>.md)
        public_identity_md: pre-rendered markdown summary. Onboarding decides what's
            shareable; we just write the bytes.

    Returns FeedWriteResult — caller checks .success + .pushed + .error.
    """
    identities_dir = config.local_path() / "identities"
    identities_dir.mkdir(parents=True, exist_ok=True)
    target = identities_dir / f"{handle}.md"

    # Idempotency: skip if content is byte-identical
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
            if existing == public_identity_md:
                return FeedWriteResult(
                    success=True,
                    entry_id=f"identity-{handle}-unchanged",
                    pushed=False,
                    queued=False,
                    error=None,
                    violation=None,
                )
        except OSError:
            pass  # if we can't read, just overwrite

    try:
        target.write_text(public_identity_md, encoding="utf-8")
    except OSError as e:
        return FeedWriteResult(
            success=False,
            entry_id="",
            pushed=False,
            queued=False,
            error=f"failed to write {target}: {e}",
            violation=None,
        )

    push_result = io_github.push(commit_msg=f"{handle} identity update")
    return FeedWriteResult(
        success=True,
        entry_id=f"identity-{handle}",
        pushed=push_result.ok and not push_result.queued,
        queued=push_result.queued,
        error=push_result.error,
        violation=None,
    )
