"""
sf-improve-skill git mechanics.

Subprocess wrappers for branch creation, commit-per-iteration, revert, and
squash-merge. Used by the Karpathy loop in lib/__init__.py.

Per references/git-mechanics.md (the design doc): git IS the memory; revert
is `git reset --hard HEAD~1`; squash-merge only on full success; never push
from the loop.

Each public function is a single git operation. Composability (the actual
loop) lives in lib/__init__.py's `improve_skill()` orchestration.

Per dotfiles python/coding-style.md: PEP 8, type annotations. Per
python/testing.md: pytest tests with tmpdir + real `git init` (no mocking
git — we exercise the real behavior).
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from .types import PreFlightError

logger = logging.getLogger(__name__)


# Branch naming format. Timestamp is YYYY-MM-DD-HHMMSS in UTC.
TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%d-%H%M%S"


# ---------------------------------------------------------------------------
# Branch lifecycle
# ---------------------------------------------------------------------------


def create_improve_branch(
    skill_name: str,
    *,
    prefix: str = "improve",
    base_ref: str = "HEAD",
    cwd: Path | None = None,
    now: datetime | None = None,
) -> str:
    """
    Create and switch to a new improve branch.

    Args:
        skill_name: The target skill (e.g., "sf-wrap").
        prefix: Branch name prefix (default "improve"; override via CLI).
        base_ref: Git ref to branch from (default "HEAD").
        cwd: Working directory (default: current).
        now: Override the timestamp (for tests).

    Returns:
        The created branch name (e.g., "improve/sf-wrap/2026-05-28-203012").

    Raises:
        subprocess.CalledProcessError: if git fails (likely: base_ref doesn't exist).
    """
    ts = (now or datetime.now(timezone.utc)).strftime(TIMESTAMP_FORMAT)
    branch_name = f"{prefix}/{skill_name}/{ts}"

    subprocess.run(
        ["git", "switch", "-c", branch_name, base_ref],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    logger.info("Created improve branch: %s", branch_name)
    return branch_name


def get_current_branch(*, cwd: Path | None = None) -> str:
    """Return the current branch name (or 'HEAD' if detached)."""
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def get_head_sha(*, cwd: Path | None = None) -> str:
    """Return the full SHA of HEAD."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Commit per iteration
# ---------------------------------------------------------------------------


def commit_iteration(
    iteration: int,
    proposal_summary: str,
    *,
    cwd: Path | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    """
    Stage all changes under skills/ and commit one iteration's work.

    The commit subject is `iter <N>: <proposal_summary>`. The body includes
    iteration metadata so `git log` carries the loop's full state — no
    separate state file needed.

    Args:
        iteration: The iteration number (1-indexed).
        proposal_summary: Short summary of the proposed change.
        cwd: Working directory.
        metadata: Optional metadata key-value pairs to embed in the commit body.

    Returns:
        The new commit's SHA.

    Raises:
        subprocess.CalledProcessError: if nothing was staged, or commit fails.
    """
    # Stage skills/ recursively (the only directory iterations should touch)
    subprocess.run(["git", "add", "skills/"], cwd=cwd, check=True, capture_output=True)

    subject = f"iter {iteration}: {proposal_summary}"
    body_lines = ["", "improve-skill metadata:"]
    body_lines.append(f"  iteration: {iteration}")
    body_lines.append(f"  status: pending")  # finalized later via amend_iteration_metadata
    if metadata:
        for key, value in metadata.items():
            body_lines.append(f"  {key}: {value}")
    message = subject + "\n" + "\n".join(body_lines) + "\n"

    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=cwd,
        check=True,
        capture_output=True,
    )

    sha = get_head_sha(cwd=cwd)
    logger.info("Committed iteration %d (%s): %s", iteration, sha[:8], proposal_summary)
    return sha


def amend_iteration_metadata(
    *,
    cwd: Path | None = None,
    **fields: str,
) -> str:
    """
    Update the iteration metadata on the latest commit via --amend.

    Used to fill in score_before / score_after / status after the eval runs
    (the initial commit_iteration call leaves them as "pending"). Pure metadata
    refresh; no working-tree changes are staged.

    Args:
        cwd: Working directory.
        **fields: Metadata key-value pairs to set/override. Existing values
            in the body for the same keys are replaced; new keys are appended.

    Returns:
        New HEAD SHA after amending.

    Note: amends are safe here because the iteration commit lives only on the
    improve branch (never on shared history).
    """
    # Read the current commit body
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%B"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    body = result.stdout.rstrip("\n")

    # Update existing keys + append missing ones
    lines = body.split("\n")
    updated_keys: set[str] = set()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        for key, value in fields.items():
            prefix_key = f"{key}: "
            if stripped.startswith(prefix_key):
                indent = line[: len(line) - len(stripped)]
                lines[i] = f"{indent}{key}: {value}"
                updated_keys.add(key)
                break

    # Append any keys that weren't already present (under the metadata block if present)
    missing = {k: v for k, v in fields.items() if k not in updated_keys}
    if missing:
        # Find the metadata block; append after it
        metadata_idx = -1
        for i, line in enumerate(lines):
            if line.strip() == "improve-skill metadata:":
                metadata_idx = i
                break
        if metadata_idx == -1:
            lines.append("")
            lines.append("improve-skill metadata:")
        for key, value in missing.items():
            lines.append(f"  {key}: {value}")

    new_message = "\n".join(lines) + "\n"

    subprocess.run(
        ["git", "commit", "--amend", "-m", new_message, "--no-edit"]
        if False  # --no-edit conflicts with -m; we drop it
        else ["git", "commit", "--amend", "-m", new_message],
        cwd=cwd,
        check=True,
        capture_output=True,
    )

    return get_head_sha(cwd=cwd)


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------


def revert_last_iteration(reason: str, *, cwd: Path | None = None) -> None:
    """
    Discard the last iteration's commit AND its working-tree changes.

    Uses `git reset --hard HEAD~1`. Safe because:
      1. We're on the improve branch (never run this on a shared branch).
      2. The git reflog still records the reset (recoverable via `git reflog` +
         `git checkout <sha>` if catastrophically needed).

    Args:
        reason: Logged for diagnostics; not committed anywhere.
        cwd: Working directory.

    Raises:
        subprocess.CalledProcessError: if reset fails (likely: no previous commit
        on the branch — i.e., we'd be wiping the branch root).
    """
    subprocess.run(
        ["git", "reset", "--hard", "HEAD~1"],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    logger.info("Reverted last iteration. Reason: %s", reason)


def cleanup_on_cancel(*, cwd: Path | None = None) -> None:
    """
    Discard any uncommitted iteration-in-progress changes.

    Called when the user Ctrl-C's mid-iteration. The last COMPLETED iteration
    commit stays on the branch; only the current dirty working tree is
    cleared.

    Args:
        cwd: Working directory.
    """
    subprocess.run(
        ["git", "checkout", "--", "."],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    logger.info("Cancelled mid-iteration: working tree cleared")


# ---------------------------------------------------------------------------
# Squash-merge on success
# ---------------------------------------------------------------------------


def squash_merge_on_success(
    branch: str,
    base_ref: str,
    *,
    commit_message: str,
    keep_branch: bool = False,
    cwd: Path | None = None,
) -> str | None:
    """
    Merge the improve branch back into base_ref as a single squashed commit.

    If `keep_branch` is True, this is a no-op (caller is responsible for
    informing the user that the branch is retained).

    Args:
        branch: The improve branch (e.g., "improve/sf-wrap/<ts>").
        base_ref: The base branch to merge into.
        commit_message: The squash commit's message (subject + body).
        keep_branch: If True, do nothing. Default False.
        cwd: Working directory.

    Returns:
        The squash commit's SHA on success; None if keep_branch was True.
    """
    if keep_branch:
        logger.info("Branch kept (--keep-branch): %s", branch)
        return None

    subprocess.run(["git", "switch", base_ref], cwd=cwd, check=True, capture_output=True)
    subprocess.run(
        ["git", "merge", "--squash", branch],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    sha = get_head_sha(cwd=cwd)
    subprocess.run(
        ["git", "branch", "-D", branch],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    logger.info("Squash-merged %s into %s (%s); branch deleted", branch, base_ref, sha[:8])
    return sha


# ---------------------------------------------------------------------------
# Crash recovery (skeleton — full resume logic is V2)
# ---------------------------------------------------------------------------


def parse_iteration_metadata(commit_body: str) -> dict[str, str]:
    """
    Parse the `improve-skill metadata:` block from a commit body.

    Returns a flat dict of key-value pairs. Missing block → empty dict.
    Used by crash-recovery to read the last commit's state.

    Args:
        commit_body: The full commit body (subject + body).

    Returns:
        Dict of metadata fields (all values as strings).
    """
    metadata: dict[str, str] = {}
    in_block = False
    for raw_line in commit_body.splitlines():
        line = raw_line.rstrip()
        if line.strip() == "improve-skill metadata:":
            in_block = True
            continue
        if not in_block:
            continue
        # Block continues while we see "<indent><key>: <value>" lines
        if not line.startswith("  ") or ":" not in line:
            # Block ended
            break
        key_raw, _, value_raw = line.lstrip().partition(":")
        key = key_raw.strip()
        value = value_raw.strip()
        if key:
            metadata[key] = value
    return metadata
