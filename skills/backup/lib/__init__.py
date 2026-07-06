"""
ren-backup library — internal implementation for /ren:backup (Task 7.3,
RenOS 0.2 Phase 7 — carried from donor `skills/backup/lib/__init__.py`).

Wiki-only backup: git push primary, tarball fallback. Carried near-verbatim;
pure-logic helpers fully unit-tested, subprocess wrappers (git, tar) take cwd
args for tmpdir-driven testing — same structure as donor.

Deltas from donor:
  - Default git remote name is `"backup"`, not `"origin"` — this MUST match
    `skills.metric-watch.lib`'s `_check_backup` (Task 6.3, shipped first), which
    already checks for a remote literally named `"backup"`. Changing this
    skill's default instead of metric-watch's is the only way the two agree.
  - `default_backup_dir()` returns `ren_paths.plugin_data_dir() / "backups"` —
    again matching metric-watch's `_check_backup`, which already reads
    tarballs from that exact path. (The task brief also mentioned
    `~/.renos/backups`; `plugin_data_dir()/"backups"` is what the ALREADY-SHIPPED
    metric-watch check reads, so that's the contract this module aligns to —
    see the implementation report for this explicit call.)
  - New: `backup_configured(wiki_root=None) -> bool` — the single yes/no
    entry point metric-watch's check (and `/ren:doctor`'s backup-unconfigured
    check, Task 7.3's doctor half) both want, without duplicating the
    remote-or-recent-tarball logic a second time.
  - Commit message prefix renamed `sf:backup` → `ren:backup`.
  - The "remote-change confirmation" donor's SKILL.md would otherwise need to
    describe is now enforced by the Task 6.2 `write_gate` PreToolUse hook —
    documented in this skill's SKILL.md rather than re-implemented here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from lib import ren_paths

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARBALL_RETENTION_KEEP: Final[int] = 20
TARBALL_FILENAME_TEMPLATE: Final[str] = "wiki-{timestamp}.tar.gz"
TARBALL_TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%d-%H%M%S"

BACKUP_REMOTE_NAME: Final[str] = "backup"
"""Matches `skills.metric-watch.lib`'s `BACKUP_REMOTE_NAME` (Task 6.3) —
kept as a shared literal rather than a cross-skill import, same reasoning as
elsewhere in this codebase for hyphen-safe/skill-independent constants."""

BACKUP_TARBALL_MAX_AGE_DAYS: Final[float] = 7
"""Matches metric-watch's freshness window for "is a backup recent enough
to count as configured"."""

# Permissive git URL shape check — defer full validation to `git remote add`
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
    success: bool
    method: str             # "git-push" | "tarball" | "tarball-fallback" | "skipped" | "setup"
    path_or_remote: str
    message: str
    error: str | None = None
    pruned_tarballs: int = 0


@dataclass(frozen=True)
class StatusResult:
    wiki_path: str
    is_git_repo: bool
    remote_url: str | None
    last_commit_sha: str | None
    last_commit_date: str | None
    tarball_count: int
    oldest_tarball_date: str | None
    newest_tarball_date: str | None


# ---------------------------------------------------------------------------
# Pure-logic helpers
# ---------------------------------------------------------------------------


def looks_like_git_url(url: str) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    return bool(_GIT_URL_RE.match(url.strip()))


def tarball_filename_for(now: datetime | None = None) -> str:
    ts = (now or datetime.now(timezone.utc)).strftime(TARBALL_TIMESTAMP_FORMAT)
    return TARBALL_FILENAME_TEMPLATE.format(timestamp=ts)


def default_backup_dir() -> Path:
    """`plugin_data_dir()/"backups"` — the SAME path metric-watch's
    `_check_backup` already reads tarballs from (Task 6.3 shipped first)."""
    return ren_paths.plugin_data_dir() / "backups"


def list_existing_tarballs(backup_dir: Path) -> list[Path]:
    if not backup_dir.is_dir():
        return []
    candidates = [
        p for p in backup_dir.glob("wiki-*.tar.gz")
        if p.is_file() and re.match(r"wiki-\d{4}-\d{2}-\d{2}-\d{6}\.tar\.gz$", p.name)
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates


def prune_old_tarballs(backup_dir: Path, *, keep: int = TARBALL_RETENTION_KEEP) -> int:
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
        except OSError as exc:
            logger.warning("Could not prune %s: %s", path, exc)
    return deleted


def _has_recent_tarball(backup_dir: Path, max_age_days: float) -> bool:
    tarballs = list_existing_tarballs(backup_dir)
    if not tarballs:
        return False
    now = datetime.now(timezone.utc).timestamp()
    newest = tarballs[0]
    try:
        age_days = (now - newest.stat().st_mtime) / 86400.0
    except OSError:
        return False
    return age_days <= max_age_days


# ---------------------------------------------------------------------------
# Subprocess wrappers
# ---------------------------------------------------------------------------


def _run_git(args: list[str], *, cwd: Path):
    import subprocess
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=False)


def is_git_repo(wiki_root: Path) -> bool:
    if not wiki_root.is_dir():
        return False
    result = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=wiki_root)
    return result.returncode == 0 and result.stdout.strip() == "true"


def get_remote_url(wiki_root: Path, *, remote_name: str = BACKUP_REMOTE_NAME) -> str | None:
    result = _run_git(["remote", "get-url", remote_name], cwd=wiki_root)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_head_info(wiki_root: Path) -> tuple[str | None, str | None]:
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


def setup_remote(remote_url: str, wiki_root: Path, *, remote_name: str = BACKUP_REMOTE_NAME) -> BackupResult:
    if not looks_like_git_url(remote_url):
        return BackupResult(
            success=False, method="setup", path_or_remote=remote_url,
            message=f"URL doesn't look like a git remote: {remote_url!r}",
            error="invalid-url-shape",
        )
    if not is_git_repo(wiki_root):
        return BackupResult(
            success=False, method="setup", path_or_remote=str(wiki_root),
            message=f"Wiki at {wiki_root} is not a git repo. Run /ren:install to bootstrap.",
            error="not-a-git-repo",
        )

    existing = get_remote_url(wiki_root, remote_name=remote_name)
    if existing is None:
        result = _run_git(["remote", "add", remote_name, remote_url], cwd=wiki_root)
    else:
        result = _run_git(["remote", "set-url", remote_name, remote_url], cwd=wiki_root)

    if result.returncode != 0:
        return BackupResult(
            success=False, method="setup", path_or_remote=remote_url,
            message=f"git remote {remote_name} configuration failed",
            error=result.stderr.strip() or "git-error",
        )

    confirmed = get_remote_url(wiki_root, remote_name=remote_name)
    if confirmed != remote_url:
        return BackupResult(
            success=False, method="setup", path_or_remote=remote_url,
            message=f"remote URL after set was {confirmed!r}, expected {remote_url!r}",
            error="set-url-readback-mismatch",
        )

    verb = "added" if existing is None else "updated"
    return BackupResult(
        success=True, method="setup", path_or_remote=remote_url,
        message=f"Remote {remote_name!r} {verb} to {remote_url}. Run /ren:backup to push.",
    )


def status(wiki_root: Path, backup_dir: Path | None = None) -> StatusResult:
    backup_dir = backup_dir or default_backup_dir()
    repo = is_git_repo(wiki_root)
    if not repo:
        return StatusResult(
            wiki_path=str(wiki_root), is_git_repo=False, remote_url=None,
            last_commit_sha=None, last_commit_date=None,
            tarball_count=0, oldest_tarball_date=None, newest_tarball_date=None,
        )

    remote = get_remote_url(wiki_root)
    sha, date = get_head_info(wiki_root)
    tarballs = list_existing_tarballs(backup_dir)
    oldest = newest = None
    if tarballs:
        newest_mtime = tarballs[0].stat().st_mtime
        oldest_mtime = tarballs[-1].stat().st_mtime
        newest = datetime.fromtimestamp(newest_mtime, tz=timezone.utc).isoformat()
        oldest = datetime.fromtimestamp(oldest_mtime, tz=timezone.utc).isoformat()

    return StatusResult(
        wiki_path=str(wiki_root), is_git_repo=True, remote_url=remote,
        last_commit_sha=sha, last_commit_date=date,
        tarball_count=len(tarballs), oldest_tarball_date=oldest, newest_tarball_date=newest,
    )


def backup_configured(wiki_root: Path | None = None) -> bool:
    """True iff either a `"backup"` git remote is configured on the wiki repo
    OR a tarball newer than `BACKUP_TARBALL_MAX_AGE_DAYS` exists in
    `default_backup_dir()`. Matches `skills.metric-watch.lib`'s
    `_check_backup` exactly (same remote name, same dir, same freshness
    window) — this is the single function `/ren:doctor`'s backup-unconfigured
    check calls, so the two never drift apart."""
    wiki_root = wiki_root or ren_paths.wiki_root()
    if is_git_repo(wiki_root) and get_remote_url(wiki_root) is not None:
        return True
    return _has_recent_tarball(default_backup_dir(), BACKUP_TARBALL_MAX_AGE_DAYS)


def has_uncommitted_changes(wiki_root: Path) -> bool:
    result = _run_git(["status", "--porcelain"], cwd=wiki_root)
    return result.returncode == 0 and bool(result.stdout.strip())


def commit_pending_changes(wiki_root: Path, *, now: datetime | None = None) -> bool:
    if not has_uncommitted_changes(wiki_root):
        return True
    add = _run_git(["add", "-A"], cwd=wiki_root)
    if add.returncode != 0:
        return False
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg = f"ren:backup at {ts}"
    commit = _run_git(["commit", "-m", msg], cwd=wiki_root)
    return commit.returncode == 0


_NON_FAST_FORWARD_PATTERNS: Final[tuple[str, ...]] = (
    "[rejected]", "non-fast-forward", "non-fast forward", "Updates were rejected", "fetch first",
)


def _classify_push_failure(stderr: str) -> str:
    lower = stderr.lower()
    for needle in _NON_FAST_FORWARD_PATTERNS:
        if needle.lower() in lower:
            return "non-fast-forward"
    return "transport-failure"


def push_to_remote(wiki_root: Path, *, remote_name: str = BACKUP_REMOTE_NAME) -> tuple[bool, str, str]:
    if get_remote_url(wiki_root, remote_name=remote_name) is None:
        return False, "no-remote", ""
    head_sha, _ = get_head_info(wiki_root)
    if head_sha is None:
        return False, "no-commits", "wiki has no commits"
    result = _run_git(["push", remote_name, "HEAD"], cwd=wiki_root)
    if result.returncode == 0:
        return True, "", result.stderr.strip()
    return False, _classify_push_failure(result.stderr), result.stderr.strip()


def create_tarball(wiki_root: Path, backup_dir: Path, *, now: datetime | None = None) -> tuple[bool, Path | None, str]:
    import tarfile

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
            tar.add(wiki_root, arcname=wiki_root.name)
    except (OSError, tarfile.TarError) as exc:
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass
        return False, None, f"Tarball creation failed: {exc}"
    return True, target, ""


def backup(
    wiki_root: Path,
    backup_dir: Path | None = None,
    *,
    force_tarball: bool = False,
    keep: int = TARBALL_RETENTION_KEEP,
    now: datetime | None = None,
) -> BackupResult:
    """Top-level orchestrator: commit → push (unless forced/no remote) →
    tarball fallback → prune. See module docstring for the remote-name delta
    from donor. The Task 6.2 `write_gate` PreToolUse hook is what enforces
    "confirm before changing the backup remote" — this function does not
    re-implement that confirmation; see SKILL.md."""
    backup_dir = backup_dir or default_backup_dir()

    if not is_git_repo(wiki_root):
        return BackupResult(
            success=False, method="skipped", path_or_remote=str(wiki_root),
            message=f"Wiki at {wiki_root} is not a git repo. Run /ren:install to bootstrap.",
            error="not-a-git-repo",
        )

    if not commit_pending_changes(wiki_root, now=now):
        return BackupResult(
            success=False, method="skipped", path_or_remote=str(wiki_root),
            message="Could not commit pending changes. Run `git status` in the wiki to inspect.",
            error="commit-failed",
        )

    if force_tarball:
        return _do_tarball(
            wiki_root, backup_dir, now=now, keep=keep,
            method="tarball", success_message_prefix="Tarball created",
        )

    pushed, category, stderr = push_to_remote(wiki_root)
    if pushed:
        remote = get_remote_url(wiki_root) or "<unknown remote>"
        return BackupResult(
            success=True, method="git-push", path_or_remote=remote,
            message=f"✓ Wiki backed up to {remote}",
        )

    if category == "non-fast-forward":
        return BackupResult(
            success=False, method="git-push", path_or_remote=get_remote_url(wiki_root) or "",
            message=(
                "Push rejected: remote diverged from local. "
                "See RECOVERY.md §'remote-history-rewrite' before proceeding. "
                "Force-push is NOT performed automatically."
            ),
            error="non-fast-forward",
        )

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


def _do_tarball(wiki_root: Path, backup_dir: Path, *, now, keep, method, success_message_prefix) -> BackupResult:
    success, target, error = create_tarball(wiki_root, backup_dir, now=now)
    if not success:
        return BackupResult(
            success=False, method=method, path_or_remote=str(backup_dir),
            message="Tarball creation failed", error=error,
        )
    pruned = prune_old_tarballs(backup_dir, keep=keep)
    suffix = f" (pruned {pruned} old)" if pruned > 0 else ""
    return BackupResult(
        success=True, method=method, path_or_remote=str(target),
        message=f"{success_message_prefix} at {target}{suffix}",
        pruned_tarballs=pruned,
    )


__all__ = [
    "TARBALL_RETENTION_KEEP",
    "BACKUP_REMOTE_NAME",
    "BACKUP_TARBALL_MAX_AGE_DAYS",
    "BackupResult",
    "StatusResult",
    "looks_like_git_url",
    "tarball_filename_for",
    "default_backup_dir",
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
    "backup_configured",
    "backup",
]
