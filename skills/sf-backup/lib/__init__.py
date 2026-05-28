"""
sf-backup library — internal implementation for /sf:backup.

Per ADR-026: wiki-only backup; git push primary, tarball fallback. Plugin-
internal state (claude-mem/Context Mode SQLites) explicitly out of scope.

Pure-logic helpers fully unit-tested. Subprocess wrappers (git, tar) take
cwd args for tmpdir-driven testing.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


TARBALL_RETENTION_KEEP: Final[int] = 20  # per ADR-026 §"Open questions" — defaulting to 20
TARBALL_FILENAME_TEMPLATE: Final[str] = "wiki-{timestamp}.tar.gz"
TARBALL_TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%d-%H%M%S"

# Permissive git URL shape check — defer full validation to `git remote add`
# Matches: https://..., http://..., git@host:..., ssh://...
_GIT_URL_RE: Final[re.Pattern[str]] = re.compile(
    r"^("
    r"https?://[^\s]+\.git$|"
    r"https?://[^\s/]+/[^\s]+/[^\s]+(\.git)?$|"
    r"git@[^\s:]+:[^\s]+(\.git)?$|"
    r"ssh://[^\s]+(\.git)?$"
    r")"
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackupResult:
    """Outcome of a backup invocation."""

    success: bool
    method: str             # "git-push" | "tarball" | "tarball-fallback" | "skipped"
    path_or_remote: str     # tarball path or remote URL (whichever applies)
    message: str            # user-facing line
    error: str | None = None
    pruned_tarballs: int = 0


@dataclass(frozen=True)
class StatusResult:
    """Outcome of a status query."""

    wiki_path: str
    is_git_repo: bool
    remote_url: str | None              # None if not configured
    last_commit_sha: str | None
    last_commit_date: str | None         # ISO-format
    tarball_count: int
    oldest_tarball_date: str | None
    newest_tarball_date: str | None


# ---------------------------------------------------------------------------
# Pure-logic helpers (unit-testable without subprocess)
# ---------------------------------------------------------------------------


def looks_like_git_url(url: str) -> bool:
    """
    Permissive shape-check that a string looks like a git remote URL.

    Accepts:
      - https://host/user/repo.git  or  https://host/user/repo
      - http://...   (uncommon but valid)
      - git@host:user/repo.git
      - ssh://user@host/path

    Rejects empty strings, obviously-not-git inputs (e.g., 'foo bar', '/tmp/x.txt').
    Defers full validation to `git remote add` itself.

    Args:
        url: candidate URL.

    Returns:
        True if shape looks plausible.
    """
    if not isinstance(url, str) or not url.strip():
        return False
    return bool(_GIT_URL_RE.match(url.strip()))


def tarball_filename_for(now: datetime | None = None) -> str:
    """
    Compose the canonical tarball filename for the given timestamp.

    Args:
        now: Override the timestamp (for tests). Default: now() in UTC.

    Returns:
        Filename like `wiki-2026-05-28-203012.tar.gz`.
    """
    ts = (now or datetime.now(timezone.utc)).strftime(TARBALL_TIMESTAMP_FORMAT)
    return TARBALL_FILENAME_TEMPLATE.format(timestamp=ts)


def list_existing_tarballs(backup_dir: Path) -> list[Path]:
    """
    List existing wiki tarballs under backup_dir, sorted newest-first by mtime.

    Args:
        backup_dir: directory to scan.

    Returns:
        List of paths (may be empty if dir missing or no tarballs).
    """
    if not backup_dir.is_dir():
        return []
    # Pattern guard: only files matching our convention
    candidates = [
        p for p in backup_dir.glob("wiki-*.tar.gz")
        if p.is_file() and re.match(r"wiki-\d{4}-\d{2}-\d{2}-\d{6}\.tar\.gz$", p.name)
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates


def prune_old_tarballs(
    backup_dir: Path,
    *,
    keep: int = TARBALL_RETENTION_KEEP,
) -> int:
    """
    Delete tarballs beyond the `keep` most-recent.

    Args:
        backup_dir: directory containing tarballs.
        keep: how many to retain (default 20).

    Returns:
        Number of tarballs deleted (0 if at or under cap).
    """
    if keep < 0:
        raise ValueError(f"keep must be >= 0, got {keep}")

    tarballs = list_existing_tarballs(backup_dir)
    if len(tarballs) <= keep:
        return 0

    to_delete = tarballs[keep:]
    deleted = 0
    for path in to_delete:
        try:
            path.unlink()
            deleted += 1
            logger.info("Pruned old tarball: %s", path.name)
        except OSError as exc:
            logger.warning("Could not prune %s: %s", path, exc)
    return deleted


# ---------------------------------------------------------------------------
# Subprocess wrappers
# ---------------------------------------------------------------------------


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in cwd; return CompletedProcess (no check)."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def is_git_repo(wiki_root: Path) -> bool:
    """True if wiki_root/.git exists (or wiki_root IS a git repo via rev-parse)."""
    if not wiki_root.is_dir():
        return False
    result = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=wiki_root)
    return result.returncode == 0 and result.stdout.strip() == "true"


def get_remote_url(wiki_root: Path, *, remote_name: str = "origin") -> str | None:
    """Return the configured remote URL, or None if not configured."""
    result = _run_git(["remote", "get-url", remote_name], cwd=wiki_root)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_head_info(wiki_root: Path) -> tuple[str | None, str | None]:
    """Return (sha, ISO-date) of HEAD commit, or (None, None) if no commits."""
    result = _run_git(["log", "-1", "--format=%H%n%cI"], cwd=wiki_root)
    if result.returncode != 0:
        return None, None
    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        return None, None
    return lines[0], lines[1]


# ---------------------------------------------------------------------------
# Top-level entry points
# ---------------------------------------------------------------------------


def setup_remote(
    remote_url: str,
    wiki_root: Path,
    *,
    remote_name: str = "origin",
) -> BackupResult:
    """
    Configure a git remote on the wiki repo.

    Args:
        remote_url: the URL to set.
        wiki_root: wiki directory.
        remote_name: defaults to "origin".

    Returns:
        BackupResult with method="setup".
    """
    if not looks_like_git_url(remote_url):
        return BackupResult(
            success=False,
            method="setup",
            path_or_remote=remote_url,
            message=f"URL doesn't look like a git remote: {remote_url!r}",
            error="invalid-url-shape",
        )

    if not is_git_repo(wiki_root):
        return BackupResult(
            success=False,
            method="setup",
            path_or_remote=str(wiki_root),
            message=f"Wiki at {wiki_root} is not a git repo. Run /sf:install to bootstrap.",
            error="not-a-git-repo",
        )

    # Add or update the remote
    existing = get_remote_url(wiki_root, remote_name=remote_name)
    if existing is None:
        result = _run_git(["remote", "add", remote_name, remote_url], cwd=wiki_root)
    else:
        result = _run_git(["remote", "set-url", remote_name, remote_url], cwd=wiki_root)

    if result.returncode != 0:
        return BackupResult(
            success=False,
            method="setup",
            path_or_remote=remote_url,
            message=f"git remote {remote_name} configuration failed",
            error=result.stderr.strip() or "git-error",
        )

    # Confirm
    confirmed = get_remote_url(wiki_root, remote_name=remote_name)
    if confirmed != remote_url:
        return BackupResult(
            success=False,
            method="setup",
            path_or_remote=remote_url,
            message=f"remote URL after set was {confirmed!r}, expected {remote_url!r}",
            error="set-url-readback-mismatch",
        )

    verb = "added" if existing is None else "updated"
    return BackupResult(
        success=True,
        method="setup",
        path_or_remote=remote_url,
        message=f"Remote {remote_name!r} {verb} to {remote_url}. Run /sf:backup to push.",
    )


def status(wiki_root: Path, backup_dir: Path) -> StatusResult:
    """Compute the status report. Read-only."""
    repo = is_git_repo(wiki_root)
    if not repo:
        return StatusResult(
            wiki_path=str(wiki_root),
            is_git_repo=False,
            remote_url=None,
            last_commit_sha=None,
            last_commit_date=None,
            tarball_count=0,
            oldest_tarball_date=None,
            newest_tarball_date=None,
        )

    remote = get_remote_url(wiki_root)
    sha, date = get_head_info(wiki_root)

    tarballs = list_existing_tarballs(backup_dir)
    oldest = newest = None
    if tarballs:
        # newest-first sort means first is newest, last is oldest
        newest_mtime = tarballs[0].stat().st_mtime
        oldest_mtime = tarballs[-1].stat().st_mtime
        newest = datetime.fromtimestamp(newest_mtime, tz=timezone.utc).isoformat()
        oldest = datetime.fromtimestamp(oldest_mtime, tz=timezone.utc).isoformat()

    return StatusResult(
        wiki_path=str(wiki_root),
        is_git_repo=True,
        remote_url=remote,
        last_commit_sha=sha,
        last_commit_date=date,
        tarball_count=len(tarballs),
        oldest_tarball_date=oldest,
        newest_tarball_date=newest,
    )


def has_uncommitted_changes(wiki_root: Path) -> bool:
    """True if `git status --porcelain` shows any non-empty output."""
    result = _run_git(["status", "--porcelain"], cwd=wiki_root)
    return result.returncode == 0 and bool(result.stdout.strip())


def commit_pending_changes(wiki_root: Path, *, now: datetime | None = None) -> bool:
    """
    Commit any uncommitted changes with a canonical sf:backup message.

    Returns:
        True if a commit was created OR there was nothing to commit (idempotent
        success); False if the commit attempt failed.
    """
    if not has_uncommitted_changes(wiki_root):
        return True

    add = _run_git(["add", "-A"], cwd=wiki_root)
    if add.returncode != 0:
        return False

    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = f"sf:backup at {ts}"
    commit = _run_git(["commit", "-m", msg], cwd=wiki_root)
    return commit.returncode == 0


# Classify push failure from stderr text
_NON_FAST_FORWARD_PATTERNS: Final[tuple[str, ...]] = (
    "[rejected]",
    "non-fast-forward",
    "non-fast forward",
    "Updates were rejected",
    "fetch first",
)


def _classify_push_failure(stderr: str) -> str:
    """Map git push stderr to one of our internal failure categories."""
    lower = stderr.lower()
    for needle in _NON_FAST_FORWARD_PATTERNS:
        if needle.lower() in lower:
            return "non-fast-forward"
    return "transport-failure"  # auth, network, DNS, etc.


def push_to_remote(
    wiki_root: Path,
    *,
    remote_name: str = "origin",
) -> tuple[bool, str, str]:
    """
    Attempt to push the wiki repo to its configured remote.

    Returns:
        (success, failure_category, stderr).
        - success=True → ('', stderr) — pushed cleanly (stderr may be info messages)
        - success=False → category in {"non-fast-forward", "transport-failure", "no-remote", "no-commits"}

    Does NOT raise on push failure; the caller decides whether to fall back.
    """
    if get_remote_url(wiki_root, remote_name=remote_name) is None:
        return False, "no-remote", ""

    # Detect "no commits to push" before invoking git push (cleaner error)
    head_sha, _ = get_head_info(wiki_root)
    if head_sha is None:
        return False, "no-commits", "wiki has no commits"

    result = _run_git(["push", remote_name, "HEAD"], cwd=wiki_root)
    if result.returncode == 0:
        return True, "", result.stderr.strip()
    return False, _classify_push_failure(result.stderr), result.stderr.strip()


def create_tarball(
    wiki_root: Path,
    backup_dir: Path,
    *,
    now: datetime | None = None,
) -> tuple[bool, Path | None, str]:
    """
    Create a tar.gz of the wiki directory at backup_dir/wiki-<ts>.tar.gz.

    Uses Python's tarfile module (not subprocess `tar`) for portability.
    Includes `.git/` so the tarball is a complete restore artifact.

    Returns:
        (success, path_or_None, error_message).
    """
    import tarfile  # local import keeps the module lighter

    if not wiki_root.is_dir():
        return False, None, f"Wiki root not found: {wiki_root}"

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, None, f"Could not create backup dir {backup_dir}: {exc}"

    filename = tarball_filename_for(now)
    target = backup_dir / filename

    try:
        with tarfile.open(target, "w:gz") as tar:
            # arcname so contents are under wiki/, not the full absolute path
            tar.add(wiki_root, arcname=wiki_root.name)
    except (OSError, tarfile.TarError) as exc:
        # Clean up a partial tarball
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass
        return False, None, f"Tarball creation failed: {exc}"

    return True, target, ""


def backup(
    wiki_root: Path,
    backup_dir: Path,
    *,
    force_tarball: bool = False,
    keep: int = TARBALL_RETENTION_KEEP,
    now: datetime | None = None,
) -> BackupResult:
    """
    Top-level orchestrator. Per ADR-026 + SKILL.md §Behavior.

    Flow:
      1. Validate wiki is a git repo (refuse otherwise).
      2. Commit any uncommitted changes.
      3. If --force-tarball OR no remote configured → tarball path.
      4. Else → git push:
         - Success → emit success result; skip tarball.
         - Non-fast-forward → refuse; point at RECOVERY.md; NO tarball auto-fallback
           (this is a user-decision moment).
         - Transport failure (auth/network) → tarball fallback automatic; warn.
      5. After tarball: prune oldest beyond `keep`.

    Args:
        wiki_root: wiki directory.
        backup_dir: tarball directory.
        force_tarball: skip push entirely; always tarball.
        keep: tarball retention count.
        now: override timestamp (for tests).

    Returns:
        BackupResult.
    """
    if not is_git_repo(wiki_root):
        return BackupResult(
            success=False,
            method="skipped",
            path_or_remote=str(wiki_root),
            message=f"Wiki at {wiki_root} is not a git repo. Run /sf:install to bootstrap.",
            error="not-a-git-repo",
        )

    # Commit any pending changes — idempotent if working tree is clean
    if not commit_pending_changes(wiki_root, now=now):
        return BackupResult(
            success=False,
            method="skipped",
            path_or_remote=str(wiki_root),
            message="Could not commit pending changes. Run `git status` in the wiki to inspect.",
            error="commit-failed",
        )

    # Force-tarball path: skip push entirely
    if force_tarball:
        return _do_tarball(
            wiki_root, backup_dir, now=now, keep=keep,
            method="tarball", success_message_prefix="Tarball created",
        )

    # Attempt push
    pushed, category, stderr = push_to_remote(wiki_root)
    if pushed:
        remote = get_remote_url(wiki_root) or "<unknown remote>"
        return BackupResult(
            success=True,
            method="git-push",
            path_or_remote=remote,
            message=f"✓ Wiki backed up to {remote}",
        )

    # Push failed — classify
    if category == "non-fast-forward":
        # Refuse force-push; do NOT auto-tarball; this is a user decision
        return BackupResult(
            success=False,
            method="git-push",
            path_or_remote=get_remote_url(wiki_root) or "",
            message=(
                "Push rejected: remote diverged from local. "
                "See RECOVERY.md §'remote-history-rewrite' before proceeding. "
                "Force-push is NOT performed automatically."
            ),
            error="non-fast-forward",
        )

    # no-remote → tarball + nag
    # transport-failure → tarball + warn
    # no-commits → tarball anyway (snapshot the wiki state)
    if category == "no-remote":
        prefix = "No remote configured. Tarball created"
    elif category == "transport-failure":
        prefix = f"Push failed ({stderr.splitlines()[0] if stderr else 'transport error'}); tarball fallback created"
    else:
        prefix = "Tarball created"

    return _do_tarball(
        wiki_root, backup_dir, now=now, keep=keep,
        method="tarball-fallback" if category == "transport-failure" else "tarball",
        success_message_prefix=prefix,
    )


def _do_tarball(
    wiki_root: Path,
    backup_dir: Path,
    *,
    now: datetime | None,
    keep: int,
    method: str,
    success_message_prefix: str,
) -> BackupResult:
    """Shared tarball creation + pruning + result composition."""
    success, target, error = create_tarball(wiki_root, backup_dir, now=now)
    if not success:
        return BackupResult(
            success=False,
            method=method,
            path_or_remote=str(backup_dir),
            message="Tarball creation failed",
            error=error,
        )

    pruned = prune_old_tarballs(backup_dir, keep=keep)

    suffix = f" (pruned {pruned} old)" if pruned > 0 else ""
    return BackupResult(
        success=True,
        method=method,
        path_or_remote=str(target),
        message=f"{success_message_prefix} at {target}{suffix}",
        pruned_tarballs=pruned,
    )


__all__ = [
    "TARBALL_RETENTION_KEEP",
    "BackupResult",
    "StatusResult",
    "looks_like_git_url",
    "tarball_filename_for",
    "list_existing_tarballs",
    "prune_old_tarballs",
    "is_git_repo",
    "get_remote_url",
    "get_head_info",
    "has_uncommitted_changes",
    "commit_pending_changes",
    "push_to_remote",
    "create_tarball",
    "setup_remote",
    "status",
    "backup",
]
