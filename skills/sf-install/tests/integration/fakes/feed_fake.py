"""Feed fake — sf-feed's contract surface as consumed by sf-install.

Mirrors the LOCKED API per team-lead 2026-05-28 + feed-2's bootstrap+identity
shipment in Task #21. Fakes return deterministic, scenario-configurable
results without touching git, gh, or the network.

Real symbols live in feed/__init__.py. test_contract_drift.py verifies
this fake's call signatures still match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


RepoMode = Literal["first-friend-bootstrap", "joiner-clone", "already-cloned"]


@dataclass(frozen=True)
class RepoState:
    """Matches feed.RepoState; see feed/bootstrap.py for canonical doc."""
    mode: RepoMode
    has_other_friends: bool
    existing_handles: tuple[str, ...]
    needs_init: bool
    local_path: Path
    auth_error: str | None = None
    detection_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedWriteResult:
    """Matches feed.FeedWriteResult; see feed/writer.py for canonical doc."""
    success: bool
    entry_id: str
    pushed: bool
    queued: bool = False
    error: str | None = None
    violation: str | None = None


@dataclass(frozen=True)
class CheckAuthResult:
    """Subset of feed.AuthStatus used by sf-install."""
    authed: bool
    reason: str = ""


class FeedFake:
    """Pluggable fake for the feed contract surface.

    Construct one per test. Configure via inject_* methods; assert against
    the .calls list (FIFO of invocations).

    Example:
        fake = FeedFake()
        fake.inject_detect_response(mode="first-friend-bootstrap")
        ... run simulator ...
        assert fake.calls[0] == ("detect_repo_state", "eval-friends/activity-feed", None)
    """

    def __init__(self, *, default_local_path: Path | None = None) -> None:
        self._default_local_path = default_local_path or Path("/tmp/sf-eval/activity-feed")
        self._detect_response: RepoState | None = None
        self._auth_response: CheckAuthResult = CheckAuthResult(authed=True)
        self._upsert_response: FeedWriteResult = FeedWriteResult(
            success=True, entry_id="identity-test-1234", pushed=True
        )
        self._rename_handle_response: bool = True
        self._bootstrap_should_raise: type[BaseException] | None = None
        self._clone_should_raise: type[BaseException] | None = None
        self.calls: list[tuple] = []

    # ----- contract surface (mirrors feed module's public API) -----

    def feed_detect_repo_state(
        self,
        repo_url: str,
        local_path: Path | None = None,
    ) -> RepoState:
        self.calls.append(("detect_repo_state", repo_url, local_path))
        if self._detect_response is None:
            # Sensible default: first-friend-bootstrap, no other friends.
            return RepoState(
                mode="first-friend-bootstrap",
                has_other_friends=False,
                existing_handles=(),
                needs_init=True,
                local_path=local_path or self._default_local_path,
            )
        return self._detect_response

    def feed_bootstrap_first_friend(
        self,
        local_path: Path,
        handle: str,
        repo_url: str,
    ) -> None:
        self.calls.append(("bootstrap_first_friend", local_path, handle, repo_url))
        if self._bootstrap_should_raise is not None:
            raise self._bootstrap_should_raise("simulated bootstrap failure")

    def feed_clone_existing(
        self,
        repo_url: str,
        local_path: Path,
        handle: str,
    ) -> None:
        self.calls.append(("clone_existing", repo_url, local_path, handle))
        if self._clone_should_raise is not None:
            raise self._clone_should_raise("simulated clone failure")

    def feed_upsert_identity(
        self,
        handle: str,
        public_identity_md: str,
    ) -> FeedWriteResult:
        self.calls.append(("upsert_identity", handle, public_identity_md))
        return self._upsert_response

    def rename_handle(self, old: str, new: str) -> bool:
        self.calls.append(("rename_handle", old, new))
        return self._rename_handle_response

    def check_auth(self) -> CheckAuthResult:
        self.calls.append(("check_auth",))
        return self._auth_response

    # ----- injection helpers -----

    def inject_detect_response(
        self,
        *,
        mode: RepoMode = "first-friend-bootstrap",
        existing_handles: tuple[str, ...] = (),
        has_other_friends: bool = False,
        local_path: Path | None = None,
        auth_error: str | None = None,
    ) -> None:
        self._detect_response = RepoState(
            mode=mode,
            has_other_friends=has_other_friends,
            existing_handles=existing_handles,
            needs_init=(mode != "joiner-clone"),
            local_path=local_path or self._default_local_path,
            auth_error=auth_error,
        )

    def inject_auth_failure(self, reason: str = "gh auth status: not logged in") -> None:
        self._auth_response = CheckAuthResult(authed=False, reason=reason)

    def inject_upsert_response(
        self,
        *,
        success: bool = True,
        entry_id: str = "identity-test-1234",
        pushed: bool = True,
        queued: bool = False,
        error: str | None = None,
        violation: str | None = None,
    ) -> None:
        self._upsert_response = FeedWriteResult(
            success=success,
            entry_id=entry_id,
            pushed=pushed,
            queued=queued,
            error=error,
            violation=violation,
        )

    def inject_bootstrap_failure(self, exc_type: type[BaseException] = RuntimeError) -> None:
        self._bootstrap_should_raise = exc_type

    def inject_clone_failure(self, exc_type: type[BaseException] = FileExistsError) -> None:
        self._clone_should_raise = exc_type

    def inject_rename_handle_response(self, value: bool) -> None:
        self._rename_handle_response = value

    # ----- assertion sugar -----

    def call_names(self) -> list[str]:
        """Return just the method names from .calls — handy for sequence asserts."""
        return [c[0] for c in self.calls]
