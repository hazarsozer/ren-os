"""
sf-wrap apply — atomic diff-plan application with git restore rollback.

Per SKILL.md step 5 and references/wiki-page-mapping.md §Atomicity:

  All approved diffs in a wrap are applied as a single atomic batch:
    1. `git restore` checkpoint of wiki/ before any write
    2. Validate each diff applies cleanly (git apply --check)
    3. Apply diffs one by one
    4. If ANY application fails → `git restore wiki/` rollback;
       surface the apply_error to the user
    5. If ALL succeed → commit (or leave uncommitted per friend preference)

Atomicity guarantee: the wiki never ends up in a half-updated state. This
is load-bearing because the wake-up hook reads from the wiki next session;
partial writes would degrade context quality.

Pure subprocess wrappers around `git apply`. No LLM calls. tmpdir + real
git for tests.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .types import DiffEntry, DiffPlan

logger = logging.getLogger(__name__)


# Per references/wiki-page-mapping.md — git apply flags we use consistently.
# `--whitespace=nowarn` because diffs are LLM-generated and may have minor
# whitespace drift; `--unsafe-paths` is NOT used (defense against path traversal
# via crafted diffs — we want git apply's default safety).
_GIT_APPLY_FLAGS: Final[tuple[str, ...]] = ("--whitespace=nowarn",)


@dataclass(frozen=True)
class ApplyResult:
    """Result of attempting to apply a DiffPlan atomically."""

    success: bool
    diffs_applied: int       # how many entries succeeded
    diffs_total: int          # total entries attempted
    failed_diff_index: int | None  # 0-indexed entry that failed, or None
    failed_diff_reason: str | None
    rollback_performed: bool  # True if rollback fired (partial application detected)
    files_changed: tuple[str, ...]  # paths that ended up modified (empty if rollback)


def _run_git(args: list[str], *, cwd: Path, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run git command and return CompletedProcess; never raises on non-zero exit."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _wiki_files_snapshot(wiki_root: Path) -> dict[str, str]:
    """
    Build a sha256 snapshot of all files under wiki_root.

    Used by rollback verification: after `git restore`, every file's hash
    must match the pre-apply snapshot. If not, rollback was incomplete.
    """
    snapshot: dict[str, str] = {}
    if not wiki_root.is_dir():
        return snapshot
    for path in wiki_root.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            try:
                content = path.read_bytes()
                snapshot[str(path.relative_to(wiki_root))] = hashlib.sha256(content).hexdigest()
            except (OSError, PermissionError):
                continue
    return snapshot


def _count_differing(pre: dict[str, str], post: dict[str, str]) -> int:
    """Count files that differ between two wiki snapshots, counting files present
    in only one side (symmetric — a surviving NEW file in post must be counted)."""
    return sum(1 for k in (pre.keys() | post.keys()) if pre.get(k) != post.get(k))


def _git_check_apply(diff_text: str, *, cwd: Path) -> tuple[bool, str]:
    """
    Dry-run a diff via `git apply --check`. Returns (ok, error_message).

    `--check` validates the diff applies cleanly without performing the write.
    Used in the pre-batch validation pass per SKILL.md step 5.
    """
    args = ["apply", "--check", *_GIT_APPLY_FLAGS, "-"]
    result = _run_git(args, cwd=cwd, stdin=diff_text)
    if result.returncode == 0:
        return True, ""
    return False, result.stderr.strip()


def _git_apply(diff_text: str, *, cwd: Path) -> tuple[bool, str]:
    """Apply a diff via `git apply`. Returns (ok, error_message)."""
    args = ["apply", *_GIT_APPLY_FLAGS, "-"]
    result = _run_git(args, cwd=cwd, stdin=diff_text)
    if result.returncode == 0:
        return True, ""
    return False, result.stderr.strip()


def _rollback_wiki(wiki_root: Path, *, cwd: Path) -> bool:
    """
    Full rollback: `git restore <wiki_root>` + `git clean -fd <wiki_root>` to
    discard any new files the partial apply created.

    Args:
        wiki_root: the wiki directory (used for the path arg to git restore/clean).
        cwd: the working directory where git is invoked (typically the repo root).

    Returns:
        True if rollback succeeded; False on git failure (caller should surface).
    """
    rel = str(wiki_root)
    # `git restore` for tracked files
    restore = _run_git(["restore", "--source=HEAD", "--", rel], cwd=cwd)
    # `git clean -fd` for untracked files/dirs created during partial apply
    clean = _run_git(["clean", "-fd", "--", rel], cwd=cwd)
    if restore.returncode != 0:
        logger.warning("git restore failed during rollback: %s", restore.stderr)
        return False
    if clean.returncode != 0:
        logger.warning("git clean failed during rollback: %s", clean.stderr)
        return False
    return True


def apply_diff_plan(
    plan: DiffPlan,
    *,
    wiki_root: Path,
    cwd: Path,
) -> ApplyResult:
    """
    Apply a DiffPlan atomically. ALL or NOTHING semantics.

    Algorithm:
      1. Validate every diff applies cleanly via `git apply --check` (no writes yet).
         If any fails, return early with details; nothing was touched.
      2. Capture sha256 snapshot of wiki_root for post-rollback verification.
      3. Apply each diff in order. On ANY failure:
         a. Full rollback (`git restore` + `git clean`)
         b. Return ApplyResult(success=False, rollback_performed=True)
      4. On all success: return ApplyResult(success=True, ...).

    Args:
        plan: The DiffPlan to apply.
        wiki_root: Path to the wiki directory (used for rollback scope).
        cwd: Working directory for git commands (typically the repo root).

    Returns:
        ApplyResult capturing the outcome.
    """
    if not plan.entries:
        return ApplyResult(
            success=True,
            diffs_applied=0,
            diffs_total=0,
            failed_diff_index=None,
            failed_diff_reason=None,
            rollback_performed=False,
            files_changed=(),
        )

    # --- Pre-validation pass: dry-run every diff via --check ---
    for index, entry in enumerate(plan.entries):
        ok, err = _git_check_apply(entry.unified_diff, cwd=cwd)
        if not ok:
            return ApplyResult(
                success=False,
                diffs_applied=0,
                diffs_total=len(plan.entries),
                failed_diff_index=index,
                failed_diff_reason=f"validation failed: {err}",
                rollback_performed=False,  # nothing applied; no rollback needed
                files_changed=(),
            )

    # --- Apply pass ---
    pre_snapshot = _wiki_files_snapshot(wiki_root)
    files_changed: list[str] = []

    for index, entry in enumerate(plan.entries):
        ok, err = _git_apply(entry.unified_diff, cwd=cwd)
        if not ok:
            # Partial application detected — full rollback
            logger.warning(
                "Diff apply failed at entry %d (%s); rolling back. err=%s",
                index, entry.target_file, err,
            )
            rollback_ok = _rollback_wiki(wiki_root, cwd=cwd)

            # Verify rollback restored prior state (for diagnostics)
            post_snapshot = _wiki_files_snapshot(wiki_root)
            if pre_snapshot != post_snapshot:
                logger.error(
                    "Rollback incomplete: %d files still differ from pre-apply state",
                    _count_differing(pre_snapshot, post_snapshot),
                )

            return ApplyResult(
                success=False,
                diffs_applied=index,
                diffs_total=len(plan.entries),
                failed_diff_index=index,
                failed_diff_reason=err,
                rollback_performed=rollback_ok,
                files_changed=(),  # rollback succeeded → no net changes
            )

        files_changed.append(entry.target_file)

    return ApplyResult(
        success=True,
        diffs_applied=len(plan.entries),
        diffs_total=len(plan.entries),
        failed_diff_index=None,
        failed_diff_reason=None,
        rollback_performed=False,
        files_changed=tuple(files_changed),
    )


__all__ = [
    "ApplyResult",
    "apply_diff_plan",
]
