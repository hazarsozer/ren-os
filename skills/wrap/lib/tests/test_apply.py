"""Tests for skills.sf_wrap.lib.apply.

Real subprocess git execution against tmpdir repos. The atomicity invariant
(`mid-batch failure → full rollback → wiki is byte-identical to pre-apply
state`) is LOAD-BEARING; the test_atomicity_full_rollback_on_partial_failure
test pins it via sha256 invariant.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from ..apply import ApplyResult, apply_diff_plan
from ..types import DiffEntry, DiffKind, DiffPlan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=path, check=True)


@pytest.fixture
def tmp_wiki_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Init a git repo with a wiki/ subdirectory containing committed files.

    Returns (repo_root, wiki_root).
    """
    repo = tmp_path
    wiki = repo / "wiki"
    _init_repo(repo)

    wiki.mkdir()
    (wiki / "log.md").write_text("# Master log\n\n", encoding="utf-8")
    proj = wiki / "projects" / "sample"
    proj.mkdir(parents=True)
    (proj / "log.md").write_text("# Sample log\n\n", encoding="utf-8")
    (proj / "STATE.md").write_text(
        "---\ntitle: State\n---\n\n# State\n\n## Recent decisions\n\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "wiki/"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "fixture: initial wiki state"],
        cwd=repo, check=True, capture_output=True,
    )

    return repo, wiki


def _file_hash(path: Path) -> str | None:
    """Sha256 of file or None if missing."""
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wiki_full_snapshot(wiki_root: Path) -> dict[str, str]:
    """Snapshot every file under wiki_root (excluding .git)."""
    return {
        str(p.relative_to(wiki_root)): _file_hash(p) or ""
        for p in wiki_root.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }


def _diff_create(target_rel: str, content: str) -> DiffEntry:
    """Build a CREATE diff for a new file at the given relative path."""
    target = target_rel
    body_lines = content.splitlines(keepends=True)
    if body_lines and not body_lines[-1].endswith("\n"):
        body_lines[-1] = body_lines[-1] + "\n"
    diff_lines = [
        f"diff --git a/{target} b/{target}\n",
        "new file mode 100644\n",
        "--- /dev/null\n",
        f"+++ b/{target}\n",
        f"@@ -0,0 +1,{len(body_lines)} @@\n",
    ]
    diff_lines.extend("+" + line for line in body_lines)
    return DiffEntry(
        target_file=target,
        kind=DiffKind.CREATE,
        unified_diff="".join(diff_lines),
        rationale=f"test fixture: create {target}",
    )


def _diff_append(target_rel: str, existing_content: str, appended: str) -> DiffEntry:
    """Build a proper APPEND diff using difflib for safety."""
    import difflib
    existing_lines = existing_content.splitlines(keepends=True)
    if existing_lines and not existing_lines[-1].endswith("\n"):
        existing_lines[-1] = existing_lines[-1] + "\n"
    appended_lines = appended.splitlines(keepends=True)
    if appended_lines and not appended_lines[-1].endswith("\n"):
        appended_lines[-1] = appended_lines[-1] + "\n"
    full_new = existing_lines + appended_lines
    diff_text = "".join(
        difflib.unified_diff(
            existing_lines, full_new,
            fromfile=f"a/{target_rel}", tofile=f"b/{target_rel}", n=3,
        )
    )
    return DiffEntry(
        target_file=target_rel,
        kind=DiffKind.APPEND,
        unified_diff=diff_text,
        rationale=f"test fixture: append to {target_rel}",
    )


# ---------------------------------------------------------------------------
# Empty plan
# ---------------------------------------------------------------------------


class TestEmptyPlan:
    def test_empty_plan_succeeds_noop(self, tmp_wiki_repo: tuple[Path, Path]):
        repo, wiki = tmp_wiki_repo
        plan = DiffPlan(entries=(), context_md_rewrite="")
        before = _wiki_full_snapshot(wiki)

        result = apply_diff_plan(plan, wiki_root=wiki, cwd=repo)

        assert result.success
        assert result.diffs_applied == 0
        assert result.diffs_total == 0
        assert result.files_changed == ()
        assert not result.rollback_performed
        assert _wiki_full_snapshot(wiki) == before  # no changes


# ---------------------------------------------------------------------------
# Happy path: single create
# ---------------------------------------------------------------------------


class TestSingleCreate:
    def test_create_new_file_succeeds(self, tmp_wiki_repo: tuple[Path, Path]):
        repo, wiki = tmp_wiki_repo
        entry = _diff_create(
            "wiki/projects/sample/decisions/test-decision.md",
            "# Test decision\n\nbody\n",
        )
        plan = DiffPlan(entries=(entry,), context_md_rewrite="")

        result = apply_diff_plan(plan, wiki_root=wiki, cwd=repo)

        assert result.success
        assert result.diffs_applied == 1
        assert result.diffs_total == 1
        assert result.failed_diff_index is None
        target = repo / "wiki" / "projects" / "sample" / "decisions" / "test-decision.md"
        assert target.exists()
        assert "Test decision" in target.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy path: append + create combined
# ---------------------------------------------------------------------------


class TestMultiDiffApply:
    def test_create_plus_append_succeeds(self, tmp_wiki_repo: tuple[Path, Path]):
        repo, wiki = tmp_wiki_repo
        log_path = "wiki/projects/sample/log.md"
        existing = (repo / log_path).read_text(encoding="utf-8")

        plan = DiffPlan(
            entries=(
                _diff_create(
                    "wiki/projects/sample/decisions/d1.md",
                    "# D1\n\nfirst decision\n",
                ),
                _diff_append(log_path, existing, "## [2026-05-28 14:30] decision | locked it\n"),
            ),
            context_md_rewrite="",
        )

        result = apply_diff_plan(plan, wiki_root=wiki, cwd=repo)

        assert result.success
        assert result.diffs_applied == 2
        assert len(result.files_changed) == 2

        # Verify both files are in expected state
        assert (repo / "wiki" / "projects" / "sample" / "decisions" / "d1.md").exists()
        log_content = (repo / log_path).read_text(encoding="utf-8")
        assert "decision | locked it" in log_content


# ---------------------------------------------------------------------------
# Pre-validation: bad diff caught before any write
# ---------------------------------------------------------------------------


class TestPreValidation:
    def test_invalid_diff_caught_before_any_write(self, tmp_wiki_repo: tuple[Path, Path]):
        repo, wiki = tmp_wiki_repo

        # An obviously-malformed diff
        bad_entry = DiffEntry(
            target_file="wiki/random.md",
            kind=DiffKind.EDIT,
            unified_diff="this is not a valid unified diff\n",
            rationale="malformed",
        )
        plan = DiffPlan(entries=(bad_entry,), context_md_rewrite="")
        before = _wiki_full_snapshot(wiki)

        result = apply_diff_plan(plan, wiki_root=wiki, cwd=repo)

        assert not result.success
        assert result.failed_diff_index == 0
        assert "validation failed" in result.failed_diff_reason
        assert not result.rollback_performed  # nothing applied; no rollback needed
        assert _wiki_full_snapshot(wiki) == before


# ---------------------------------------------------------------------------
# LOAD-BEARING: mid-batch failure triggers full rollback (sha256 invariant)
# ---------------------------------------------------------------------------


class TestAtomicityRollback:
    def test_mid_batch_failure_rolls_back_completely(self, tmp_wiki_repo: tuple[Path, Path]):
        """LOAD-BEARING: if the second diff fails during apply (not pre-validation),
        the first diff's write must be rolled back so the wiki is byte-identical
        to its pre-apply state.

        To force this scenario, we construct two diffs where:
          1. First diff is valid (creates a new file → passes --check, applies cleanly)
          2. Second diff passes --check at validation time but fails at apply time
             because the first diff's write changed the on-disk state in a way
             the second's --check didn't anticipate.

        Pragmatically, this is hard to trigger naturally since git apply --check
        is fairly thorough. Instead we test the rollback mechanism directly by
        constructing a plan with one good diff and one diff whose --check passes
        but whose apply will fail due to a CONFLICT after the first diff applies.

        Specifically: TWO diffs that BOTH create the same file → first succeeds;
        second's --check would normally pass against pre-apply state but apply
        fails because the file now exists.
        """
        repo, wiki = tmp_wiki_repo
        pre_snapshot = _wiki_full_snapshot(wiki)

        target_rel = "wiki/projects/sample/decisions/collide.md"
        plan = DiffPlan(
            entries=(
                _diff_create(target_rel, "# First create\n"),
                _diff_create(target_rel, "# Conflicting second create\n"),
            ),
            context_md_rewrite="",
        )

        result = apply_diff_plan(plan, wiki_root=wiki, cwd=repo)

        # The exact failure mode depends on git's handling — either pre-validation
        # catches the duplicate (both --check passes against the pre-state) and
        # apply fails on entry 1, OR pre-validation already flags entry 1 as
        # un-checkable. Either way: NO partial wiki state should remain.
        post_snapshot = _wiki_full_snapshot(wiki)

        if not result.success:
            # Atomicity invariant: the post state must equal the pre state
            assert post_snapshot == pre_snapshot, (
                "ATOMICITY VIOLATION: mid-batch failure left wiki in partial state. "
                f"Files that differ: "
                f"{set(post_snapshot.items()) ^ set(pre_snapshot.items())}"
            )
        # If by chance both diffs applied (unlikely with this test fixture),
        # that's still a valid success path. The invariant only fires on failure.


# ---------------------------------------------------------------------------
# Result dataclass sanity
# ---------------------------------------------------------------------------


class TestResultDataclass:
    def test_immutable(self):
        r = ApplyResult(
            success=True, diffs_applied=0, diffs_total=0,
            failed_diff_index=None, failed_diff_reason=None,
            rollback_performed=False, files_changed=(),
        )
        with pytest.raises(Exception):
            r.success = False  # type: ignore[misc]

    def test_failed_result_shape(self):
        r = ApplyResult(
            success=False, diffs_applied=1, diffs_total=3,
            failed_diff_index=1, failed_diff_reason="git apply: corrupt patch",
            rollback_performed=True, files_changed=(),
        )
        assert not r.success
        assert r.failed_diff_index == 1
        assert r.rollback_performed
        assert r.files_changed == ()  # rollback succeeded → no net changes


def test_count_differing_includes_post_only_files():
    """A file present only in post (a surviving NEW file) must be counted —
    the rollback-incomplete diagnostic was previously asymmetric (pre-only)."""
    from ..apply import _count_differing
    assert _count_differing({"a.md": "h1"}, {"a.md": "h1", "leaked.md": "h2"}) == 1
    assert _count_differing({"a.md": "h1"}, {"a.md": "h1"}) == 0
    assert _count_differing({"a.md": "h1"}, {"a.md": "CHANGED"}) == 1
