"""
sf-consolidate apply — atomic promotion-diff application with git-restore rollback.

A faithful copy of wrap's atomic-apply pattern (`skills/wrap/lib/apply.py`). Skill
libs can't cleanly cross-import (the documented `lib` package-name collision), so
the proven primitive is duplicated and separately tested rather than shared. It
takes a tuple of `PromotionDiff` (no wrap-specific `context_md_rewrite`).

Algorithm (all-or-nothing):
  1. `git apply --check` every diff (no writes). Any failure → return early, untouched.
  2. Apply each diff in order. On ANY failure → roll back exactly the files
     applied so far (restore tracked / remove created) — never the whole wiki.
  3. All succeed → report files changed.

Atomicity matters: a promotion is a PAIR (curated-page edit + source marking); a
half-applied pair would either lose the promotion or mark-without-promoting.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .types import PromotionDiff

logger = logging.getLogger(__name__)

_GIT_APPLY_FLAGS: Final[tuple[str, ...]] = ("--whitespace=nowarn",)


@dataclass(frozen=True)
class ApplyResult:
    """Result of attempting to apply a promotion-diff batch atomically."""

    success: bool
    diffs_applied: int
    diffs_total: int
    failed_diff_index: int | None
    failed_diff_reason: str | None
    rollback_performed: bool
    files_changed: tuple[str, ...]


def _run_git(args: list[str], *, cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True, check=False)


def _wiki_files_snapshot(wiki_root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    if not wiki_root.is_dir():
        return snapshot
    for path in wiki_root.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            try:
                snapshot[str(path.relative_to(wiki_root))] = hashlib.sha256(path.read_bytes()).hexdigest()
            except (OSError, PermissionError):
                continue
    return snapshot


def _count_differing(pre: dict[str, str], post: dict[str, str]) -> int:
    return sum(1 for k in (pre.keys() | post.keys()) if pre.get(k) != post.get(k))


def _git_check_apply(diff_text: str, *, cwd: Path) -> tuple[bool, str]:
    result = _run_git(["apply", "--check", *_GIT_APPLY_FLAGS, "-"], cwd=cwd, stdin=diff_text)
    return (result.returncode == 0, result.stderr.strip())


def _git_apply(diff_text: str, *, cwd: Path) -> tuple[bool, str]:
    result = _run_git(["apply", *_GIT_APPLY_FLAGS, "-"], cwd=cwd, stdin=diff_text)
    return (result.returncode == 0, result.stderr.strip())


def _rollback_files(files_changed: tuple[str, ...], *, cwd: Path) -> bool:
    """Undo ONLY the files this batch touched — never the whole wiki.

    Tracked files are restored to HEAD; files the batch newly created (absent
    from HEAD) are removed. Scoping to ``files_changed`` is what keeps a partial
    failure from reverting or deleting a friend's unrelated uncommitted wiki work
    — critical for --fix-links, which can target arbitrary pages. Each path is
    relative to ``cwd`` (the git root the diffs apply against).
    """
    ok = True
    for rel in files_changed:
        in_head = _run_git(["cat-file", "-e", f"HEAD:{rel}"], cwd=cwd).returncode == 0
        if in_head:
            res = _run_git(["restore", "--source=HEAD", "--", rel], cwd=cwd)
            if res.returncode != 0:
                logger.warning("git restore failed during rollback for %s: %s", rel, res.stderr)
                ok = False
        else:
            res = _run_git(["clean", "-fd", "--", rel], cwd=cwd)
            if res.returncode != 0:
                logger.warning("git clean failed during rollback for %s: %s", rel, res.stderr)
                ok = False
    return ok


def apply_diff_entries(
    entries: tuple[PromotionDiff, ...],
    *,
    wiki_root: Path,
    cwd: Path,
) -> ApplyResult:
    """Apply a promotion-diff batch atomically. ALL or NOTHING."""
    if not entries:
        return ApplyResult(True, 0, 0, None, None, False, ())

    # --- Pre-validation: dry-run every diff (no writes) ---
    for index, entry in enumerate(entries):
        ok, err = _git_check_apply(entry.unified_diff, cwd=cwd)
        if not ok:
            return ApplyResult(False, 0, len(entries), index, f"validation failed: {err}", False, ())

    # --- Apply pass ---
    pre_snapshot = _wiki_files_snapshot(wiki_root)
    files_changed: list[str] = []
    for index, entry in enumerate(entries):
        ok, err = _git_apply(entry.unified_diff, cwd=cwd)
        if not ok:
            logger.warning("Diff apply failed at entry %d (%s); rolling back. err=%s",
                           index, entry.target_file, err)
            rollback_ok = _rollback_files(tuple(files_changed), cwd=cwd)
            post_snapshot = _wiki_files_snapshot(wiki_root)
            if pre_snapshot != post_snapshot:
                logger.error("Rollback incomplete: %d files still differ",
                             _count_differing(pre_snapshot, post_snapshot))
            return ApplyResult(False, index, len(entries), index, err, rollback_ok, ())
        files_changed.append(entry.target_file)

    return ApplyResult(True, len(entries), len(entries), None, None, False, tuple(files_changed))


__all__ = ["ApplyResult", "apply_diff_entries"]
