"""
feed.io_github — GitHub I/O via gh CLI + raw git.

Strategy (lead-approved):
- `gh` CLI for auth + repo metadata (auth status, repo view, repo clone, contents API)
- Raw `git` for hot path (pull, commit, push) — auth is cached after gh, raw git is faster
- Auth check upfront via check_auth() during onboarding; on-demand only after push failure
- 10s timeout on pull/push; never block session start/end on network
- Offline-queue on push failure: feed/.queue.log + feed/.state.json inside local_path
  (per team-lead pushback — self-contained cleanup)
- Conflict resolution: pull --rebase --autostash → retry N=3 exp backoff → queue

Every function in this module is "soft-failing": it logs warnings and returns Result
dataclasses with `ok: bool`, but NEVER raises on network/auth issues. The session must
not be blocked by feed I/O problems (ADR-018 Consequences).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from feed import config


# --- result types -----------------------------------------------------------


@dataclass(frozen=True)
class PullResult:
    ok: bool
    queued: bool = False
    error: Optional[str] = None
    """Set when ok=False. Useful for /sf:doctor diagnostic output."""


@dataclass(frozen=True)
class PushResult:
    ok: bool
    queued: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class AuthStatus:
    authed: bool
    scopes: tuple[str, ...] = ()
    reason: Optional[str] = None
    """When authed=False, this carries the gh auth status error message."""


# --- constants --------------------------------------------------------------

PULL_TIMEOUT_S = 10
PUSH_TIMEOUT_S = 10
PUSH_RETRY_BACKOFFS_S = (1, 2, 4)
"""Exponential backoff sequence for push retries after rebase. N=3 retries per plan §3.3."""

CONSECUTIVE_FAILURE_THRESHOLD = 3
"""After this many consecutive whole-session push failures, /sf:doctor surfaces a warning."""


def _c_locale_env() -> dict[str, str]:
    """Environment for git subprocesses, forcing the C locale (REVIEW §H2).

    git localizes its messages via gettext, so on a non-English system (e.g. Hazar's
    Turkish-locale machine) the "[rejected]"/"non-fast-forward" substrings that
    `_looks_like_non_fast_forward` matches come back translated → conflict
    misdetection → pushes silently queue instead of rebase-retrying. Forcing
    LANG=C/LC_ALL=C makes git emit stable English regardless of the host locale.

    Merges (not replaces) os.environ so PATH, HOME, GIT_* config, credential helpers,
    and test overrides are preserved. Computed per-call so later env mutations are
    honored.
    """
    return {**os.environ, "LANG": "C", "LC_ALL": "C"}


# --- auth check -------------------------------------------------------------


def check_auth() -> AuthStatus:
    """Wrap `gh auth status` to check GitHub authentication.

    Called by:
    - Onboarding Stage 3 upfront (refuses to proceed without auth)
    - /sf:doctor on every run
    - feed.io_github.push on auth-shaped push failure (one-time)

    Returns AuthStatus(authed=True, ...) on success. Never raises.
    """
    try:
        # SECURITY: Do NOT pass --show-token. Per onboarding-2's review (F1):
        # `--show-token` prints the OAuth token to stderr, which would propagate
        # into AuthStatus.reason on failure paths and from there into install-state
        # JSON checkpoints. We only need scopes + authed/not-authed, both available
        # without --show-token.
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=PULL_TIMEOUT_S,
            env=_c_locale_env(),
        )
    except FileNotFoundError:
        return AuthStatus(
            authed=False,
            reason="gh CLI not installed — install per https://cli.github.com/",
        )
    except subprocess.TimeoutExpired:
        return AuthStatus(
            authed=False, reason=f"gh auth status timed out after {PULL_TIMEOUT_S}s"
        )

    if result.returncode != 0:
        return AuthStatus(
            authed=False,
            reason=(result.stderr.strip() or "gh auth status reported not authenticated"),
        )

    # gh auth status writes the "Logged in to..." line to stderr (success case),
    # and "Token scopes:" line lists the scopes. Parse what we can; not critical.
    scopes = _parse_gh_scopes(result.stderr + result.stdout)
    return AuthStatus(authed=True, scopes=scopes)


def _parse_gh_scopes(output: str) -> tuple[str, ...]:
    """Extract scope names from `gh auth status` output."""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("- Token scopes:") or line.startswith("Token scopes:"):
            # Format: "Token scopes: 'repo', 'workflow', ..."
            tail = line.split(":", 1)[1].strip()
            return tuple(s.strip().strip("'\"") for s in tail.split(",") if s.strip())
    return ()


# --- pull -------------------------------------------------------------------


def pull(*, timeout_s: int = PULL_TIMEOUT_S, local_path: Path | None = None) -> PullResult:
    """Best-effort `git pull --rebase --autostash` of the activity-feed clone.

    Never raises on network failure; returns PullResult with ok=False instead. Allows
    callers (wake-up hook, /sf:catch-up, /sf:doctor) to continue with stale local data.

    Records the timestamp in .state.json on success so readers can compute "synced
    <relative-time> ago".
    """
    repo = local_path or config.local_path()
    if not (repo / ".git").exists():
        return PullResult(ok=False, error=f"not a git repo: {repo}")

    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "pull", "--rebase", "--autostash"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=_c_locale_env(),
        )
    except FileNotFoundError:
        return PullResult(ok=False, error="git not installed")
    except subprocess.TimeoutExpired:
        return PullResult(ok=False, error=f"git pull timed out after {timeout_s}s")

    if result.returncode != 0:
        return PullResult(
            ok=False, error=result.stderr.strip() or "git pull failed (no stderr)"
        )

    _record_state(repo, last_pull_ok=True)
    return PullResult(ok=True)


# --- push -------------------------------------------------------------------


def push(commit_msg: str, *, timeout_s: int = PUSH_TIMEOUT_S, local_path: Path | None = None) -> PushResult:
    """Stage all changes, commit, and push with conflict resolution + offline-queue.

    Flow per plan §3.3:
    1. git add -A + git commit -m <msg> (if staged changes exist)
    2. git push
    3. On non-fast-forward reject: pull --rebase --autostash, push again
    4. Retry up to N=3 with exp backoff (1s, 2s, 4s)
    5. If still failing: queue locally (`.queue.log` + `.state.json`), return queued=True
    6. Next session-start pull+push cycle flushes the queue

    Never raises. Returns PushResult(ok=True, queued=False) on success,
    PushResult(ok=True, queued=True) when commit succeeded but push deferred,
    PushResult(ok=False, ...) only when even the local commit failed (catastrophic).
    """
    repo = local_path or config.local_path()
    if not (repo / ".git").exists():
        return PushResult(ok=False, error=f"not a git repo: {repo}")

    # Step 1: stage + commit (skip if no changes)
    commit_outcome = _stage_and_commit(repo, commit_msg)
    if commit_outcome is not None:
        # commit_outcome is the error string if commit failed
        return PushResult(ok=False, error=commit_outcome)

    # Step 2-4: push with rebase + retries
    push_err = _push_with_retries(repo, timeout_s=timeout_s)
    if push_err is None:
        _record_state(repo, last_push_ok=True, reset_failures=True)
        return PushResult(ok=True)

    # Step 5: queue locally
    _enqueue(repo, commit_msg, push_err)
    return PushResult(ok=True, queued=True, error=push_err)


def _stage_and_commit(repo: Path, message: str) -> Optional[str]:
    """Stage all changes + commit. Returns None on success, error string on failure.

    Returns None (success) also when there are no changes to commit — the writer may
    call us when only metadata changed and git has nothing to add.
    """
    try:
        # Stage everything not excluded by the clone's committed .gitignore (the
        # primary C3 mechanism, written at bootstrap and inherited by joiners).
        add_result = subprocess.run(
            ["git", "-C", str(repo), "add", "-A"],
            capture_output=True, text=True, timeout=5, env=_c_locale_env(),
        )
        if add_result.returncode != 0:
            return f"git add failed: {add_result.stderr.strip()}"

        # Defense-in-depth backstop (C3): defensively unstage per-clone local-only state
        # so it can never reach the shared repo even if this clone's .gitignore is
        # missing or hand-deleted. `git reset -- <paths>` is a no-op (exit 0) when the
        # .gitignore already kept them unstaged — the normal case — and works even on a
        # fresh repo with no HEAD (bootstrap's first push). We can't fold this into the
        # `git add` pathspec: naming a gitignored file in a :(exclude) pathspec makes
        # `git add` error out ("paths are ignored ... use -f"), which is the common path.
        reset_result = subprocess.run(
            ["git", "-C", str(repo), "reset", "-q", "--", *config.FEED_LOCAL_ONLY_FILES],
            capture_output=True, text=True, timeout=5, env=_c_locale_env(),
        )
        if reset_result.returncode != 0:
            # Surface rather than risk committing state files in the missing-.gitignore case.
            return f"git reset (C3 state-file backstop) failed: {reset_result.stderr.strip()}"

        # Check if there's anything to commit
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, env=_c_locale_env(),
        )
        if not status.stdout.strip():
            return None  # nothing to commit, that's fine

        # Commit
        commit_result = subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", message],
            capture_output=True, text=True, timeout=5, env=_c_locale_env(),
        )
        if commit_result.returncode != 0:
            return f"git commit failed: {commit_result.stderr.strip()}"
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"git error during commit: {e}"

    return None


def _push_with_retries(repo: Path, *, timeout_s: int) -> Optional[str]:
    """Try push; on non-fast-forward, rebase + retry up to N=3. Returns None on success,
    error string on persistent failure."""
    last_err: Optional[str] = None

    # Initial attempt
    err = _try_push(repo, timeout_s=timeout_s)
    if err is None:
        return None
    last_err = err

    # Retry loop with rebase
    for backoff in PUSH_RETRY_BACKOFFS_S:
        if not _looks_like_non_fast_forward(last_err):
            # Not a conflict — no point rebasing. Bail to queue.
            break

        time.sleep(backoff)
        rebase_err = _try_rebase(repo, timeout_s=timeout_s)
        if rebase_err:
            last_err = rebase_err
            continue

        err = _try_push(repo, timeout_s=timeout_s)
        if err is None:
            return None
        last_err = err

    return last_err


def _try_push(repo: Path, *, timeout_s: int) -> Optional[str]:
    """Single git-push attempt. None on success, error string on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "push"],
            capture_output=True, text=True, timeout=timeout_s, env=_c_locale_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return f"git push error: {e}"

    if result.returncode == 0:
        return None
    return result.stderr.strip() or "git push failed (no stderr)"


def _rebase_in_progress(repo: Path) -> bool:
    """True if a git rebase is mid-flight, i.e. the clone is stuck in REBASE state (M5).

    Detected by git's rebase state directory (merge backend `.git/rebase-merge` or the
    older am backend `.git/rebase-apply`). Filesystem-based, so it is locale-independent
    — unlike message parsing it does not depend on H2's forced C locale.
    """
    git_dir = repo / ".git"
    return (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists()


def _abort_rebase(repo: Path, *, timeout_s: int) -> None:
    """Best-effort `git rebase --abort` to clear a stuck rebase. Never raises."""
    try:
        subprocess.run(
            ["git", "-C", str(repo), "rebase", "--abort"],
            capture_output=True, text=True, timeout=timeout_s, env=_c_locale_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def _try_rebase(repo: Path, *, timeout_s: int) -> Optional[str]:
    """git pull --rebase --autostash, with stalled-rebase recovery (M5).

    None on success, error string on failure. Guarantees the clone is never left stuck in
    REBASE state: a pre-existing stalled rebase is aborted before we start, and if the
    pull leaves a conflict mid-rebase we abort it too. The caller then queues the push
    (eventually-consistent) instead of locking up permanently and silently swallowing all
    future feed writes — which is the failure C3 prevents on fresh repos and M5 recovers
    on already-corrupted ones.
    """
    # Clear a rebase left mid-flight by a previous run (an already-corrupted clone, or a
    # session killed during a conflict) so this attempt can proceed.
    if _rebase_in_progress(repo):
        _abort_rebase(repo, timeout_s=timeout_s)

    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "pull", "--rebase", "--autostash"],
            capture_output=True, text=True, timeout=timeout_s, env=_c_locale_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        if _rebase_in_progress(repo):
            _abort_rebase(repo, timeout_s=timeout_s)
        return f"git rebase error: {e}"

    if result.returncode == 0:
        return None

    # Non-zero: a conflict may have left a rebase in progress → abort so the clone stays
    # usable (the push queues and flushes on a later, conflict-free session).
    if _rebase_in_progress(repo):
        _abort_rebase(repo, timeout_s=timeout_s)
    return result.stderr.strip() or "git pull --rebase failed"


def _looks_like_non_fast_forward(err: str) -> bool:
    """Heuristic for git's non-fast-forward rejection message.

    Git's exact wording varies across versions; we match common substrings.
    """
    lowered = err.lower()
    return any(
        token in lowered
        for token in (
            "non-fast-forward",
            "fetch first",
            "rejected",
            "updates were rejected",
        )
    )


# --- offline queue + state -------------------------------------------------


def _enqueue(repo: Path, commit_msg: str, error: str) -> None:
    """Append a line to .queue.log + bump pending_commit_count in .state.json.

    Per team-lead pushback (2026-05-28): queue files live INSIDE local_path so deleting
    the clone is self-contained cleanup.
    """
    queue_log = repo / ".queue.log"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with queue_log.open("a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {commit_msg!r} -- error: {error}\n")
    except OSError:
        # Queue is a best-effort artifact; failure to write is non-fatal
        pass

    state = _read_state(repo)
    state["pending_commit_count"] = state.get("pending_commit_count", 0) + 1
    state["consecutive_push_failures"] = state.get("consecutive_push_failures", 0) + 1
    state["last_push_error"] = error
    state["last_push_at"] = timestamp
    _write_state(repo, state)


def consecutive_push_failures(local_path: Path | None = None) -> int:
    """Return the current consecutive-push-failure count. Used by /sf:doctor."""
    repo = local_path or config.local_path()
    state = _read_state(repo)
    return state.get("consecutive_push_failures", 0)


def pending_commit_count(local_path: Path | None = None) -> int:
    """Return the count of commits sitting in the local queue. Used by /sf:doctor."""
    repo = local_path or config.local_path()
    state = _read_state(repo)
    return state.get("pending_commit_count", 0)


def last_pull_at(local_path: Path | None = None) -> Optional[datetime]:
    """Return the last successful pull timestamp, or None if never."""
    repo = local_path or config.local_path()
    state = _read_state(repo)
    ts = state.get("last_pull_at")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _record_state(
    repo: Path,
    *,
    last_pull_ok: bool = False,
    last_push_ok: bool = False,
    reset_failures: bool = False,
) -> None:
    """Update the .state.json with a successful pull/push."""
    state = _read_state(repo)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if last_pull_ok:
        state["last_pull_at"] = now
    if last_push_ok:
        state["last_push_at"] = now
        state["pending_commit_count"] = 0
        state["last_push_error"] = None
    if reset_failures:
        state["consecutive_push_failures"] = 0
    _write_state(repo, state)


def _read_state(repo: Path) -> dict:
    """Load .state.json or return empty dict. Never raises."""
    path = repo / ".state.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(repo: Path, state: dict) -> None:
    """Persist .state.json. Best-effort; failure is non-fatal."""
    path = repo / ".state.json"
    try:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass
