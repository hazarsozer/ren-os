"""
sf-consolidate apply — atomic promotion-diff application with git-restore rollback.

A faithful copy of wrap's atomic-apply pattern (`skills/wrap/lib/apply.py`). Skill
libs can't cleanly cross-import (the documented `lib` package-name collision), so
the proven primitive is duplicated and separately tested rather than shared. It
takes a tuple of `PromotionDiff` (no wrap-specific `context_md_rewrite`).

Algorithm (all-or-nothing):
  1. `git apply --check` every diff (no writes). Any failure → return early, untouched.
  2. Apply each diff in order. On ANY failure → `git restore` + `git clean` rollback.
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


def _rollback_wiki(wiki_root: Path, *, cwd: Path) -> bool:
    rel = str(wiki_root)
    restore = _run_git(["restore", "--source=HEAD", "--", rel], cwd=cwd)
    clean = _run_git(["clean", "-fd", "--", rel], cwd=cwd)
    if restore.returncode != 0:
        logger.warning("git restore failed during rollback: %s", restore.stderr)
        return False
    if clean.returncode != 0:
        logger.warning("git clean failed during rollback: %s", clean.stderr)
        return False
    return True


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
            rollback_ok = _rollback_wiki(wiki_root, cwd=cwd)
            post_snapshot = _wiki_files_snapshot(wiki_root)
            if pre_snapshot != post_snapshot:
                logger.error("Rollback incomplete: %d files still differ",
                             _count_differing(pre_snapshot, post_snapshot))
            return ApplyResult(False, index, len(entries), index, err, rollback_ok, ())
        files_changed.append(entry.target_file)

    return ApplyResult(True, len(entries), len(entries), None, None, False, tuple(files_changed))


__all__ = ["ApplyResult", "apply_diff_entries"]
