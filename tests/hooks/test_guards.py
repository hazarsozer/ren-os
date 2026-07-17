"""
Tests for hooks/guards/{pre_push_scan,write_gate}.py — G8 enforced critical
few real PreToolUse hooks (Task 6.2).

Two layers under test per guard, matching hooks/wake-up's precedent:
  1. The pure decision functions (`check_push`, `check_direct_write`,
     `check_mass_delete`, `check_backup_remote_change`) — invoked directly.
  2. `main()`'s stdin/stdout/exit-code envelope — invoked directly with
     monkeypatched stdin (no subprocess needed; matches test_wakeup.py's
     precedent of calling the hook's own main() rather than shelling out).

Every test redirects ren_paths' framework root to tmp_path via
REN_FRAMEWORK_ROOT — never the real ~/.renos. Git repos used by the
pre_push_scan tests are real (`git init` in tmp_path) but entirely local —
nothing here pushes anywhere or touches the network.

Run with: uv run pytest tests/hooks/test_guards.py -v
"""

from __future__ import annotations

import io
import json
import os
import subprocess
from pathlib import Path

import pytest

from hooks.guards import pre_push_scan, write_gate
from lib.ren_paths import state_dir, wiki_root


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv(pre_push_scan.ALLOW_FORCE_ENV, raising=False)
    monkeypatch.delenv(write_gate.QUEUE_APPLY_ENV, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path / "framework"))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _make_renos_identity(repo: Path) -> None:
    """Mark `repo` as the RenOS plugin repo so the maintainer PATH_DENYLIST
    applies (B2 repo-identity scoping)."""
    manifest = repo / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{"name": "ren"}\n', encoding="utf-8")
    _git(repo, "add", ".claude-plugin/plugin.json")
    _git(repo, "commit", "-q", "-m", "renos identity")


@pytest.fixture
def renos_git_repo(git_repo):
    _make_renos_identity(git_repo)
    return git_repo


def _commit_file(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", f"add {rel}")


# =============================================================================
# pre_push_scan
# =============================================================================


def test_force_push_blocked_and_allow_force_env_permits_it(git_repo, clean_path_env, capsys):
    rc = pre_push_scan.check_push("git push --force origin main", str(git_repo))
    assert rc == 2
    assert "force" in capsys.readouterr().err.lower()

    clean_path_env.setenv(pre_push_scan.ALLOW_FORCE_ENV, "1")
    rc = pre_push_scan.check_push("git push --force origin main", str(git_repo))
    assert rc == 0


def test_refspec_plus_main_force_push_blocked(git_repo, capsys):
    rc = pre_push_scan.check_push("git push origin +main", str(git_repo))
    assert rc == 2
    assert "force" in capsys.readouterr().err.lower()


def test_refspec_plus_head_colon_main_force_push_blocked(git_repo, capsys):
    rc = pre_push_scan.check_push("git push origin +HEAD:main", str(git_repo))
    assert rc == 2


def test_rebase_then_plain_push_allowed(git_repo, clean_path_env):
    # M8: the rewrite check applies only to the push SEGMENT. A local rebase
    # followed by a plain push is safe (git rejects it if non-ff) and must not
    # require REN_ALLOW_FORCE.
    rc = pre_push_scan.check_push("git rebase main && git push origin main", str(git_repo))
    assert rc == 0


def test_chained_double_push_with_trailing_force_blocked(git_repo, clean_path_env, capsys):
    # HIGH regression guard: a plain push chained with a forced push must NOT
    # slip through — every push segment is inspected, not just the first.
    rc = pre_push_scan.check_push(
        "git push origin main && git push --force origin main", str(git_repo)
    )
    assert rc == 2
    assert "force" in capsys.readouterr().err.lower()


def test_chained_pushes_to_different_remotes_each_evaluated(renos_git_repo, clean_path_env, capsys):
    # A backup push chained with an origin push must still run the denylist for
    # the origin leg — the backup skip only applies when EVERY push is backup.
    _commit_file(renos_git_repo, "wiki/secret-plan.md", "plan\n")
    rc = pre_push_scan.check_push(
        "git push backup main && git push origin main", str(renos_git_repo)
    )
    assert rc == 2
    assert "wiki/secret-plan.md" in capsys.readouterr().err


def test_all_backup_chained_pushes_skip_scans(renos_git_repo):
    # When every push targets backup, both legs skip denylist + secrets.
    _commit_file(renos_git_repo, "wiki/secret-plan.md", "plan\n")
    rc = pre_push_scan.check_push(
        "git push backup main && git push backup dev", str(renos_git_repo)
    )
    assert rc == 0


def test_force_with_lease_allowed_without_env(git_repo, clean_path_env):
    # M8: --force-with-lease is the SAFE idiom — allowed without REN_ALLOW_FORCE.
    rc = pre_push_scan.check_push("git push --force-with-lease origin main", str(git_repo))
    assert rc == 0


def test_mirror_push_in_segment_still_blocked(git_repo, clean_path_env, capsys):
    # M8: --mirror in the push segment is still a rewrite-shaped push and blocks.
    rc = pre_push_scan.check_push("git filter-repo --path x && git push --mirror origin", str(git_repo))
    assert rc == 2
    assert "mirror" in capsys.readouterr().err.lower()


def test_push_to_backup_remote_skips_both_scans(git_repo):
    _commit_file(git_repo, "wiki/secret-plan.md", "the founder's actual plan\n")
    _commit_file(git_repo, "fixtures/fake.env", "AWS_KEY=AKIAIOSFODNN7EXAMPLE\n")

    rc = pre_push_scan.check_push("git push backup main", str(git_repo))
    assert rc == 0


def test_push_to_other_remote_with_wiki_path_blocked(renos_git_repo, capsys):
    # B2: denylist applies because this repo IS the RenOS repo (plugin.json).
    _commit_file(renos_git_repo, "wiki/secret-plan.md", "the founder's actual plan\n")

    rc = pre_push_scan.check_push("git push origin main", str(renos_git_repo))
    assert rc == 2
    assert "wiki/secret-plan.md" in capsys.readouterr().err


def test_non_renos_repo_with_denylisted_paths_allowed(git_repo):
    # B2 repro: a user's OWN repo tracking tests/ (and .claude/, docs/) must
    # NOT be blocked by the maintainer denylist — no plugin.json => not RenOS.
    _commit_file(git_repo, "tests/test_x.py", "def test_x():\n    assert True\n")
    _commit_file(git_repo, ".claude/settings.json", "{}\n")
    rc = pre_push_scan.check_push("git push origin main", str(git_repo))
    assert rc == 0


def test_secret_in_non_outgoing_file_does_not_block(git_repo):
    # B2: with an upstream set, only files in @{u}..HEAD are scanned. A secret
    # committed BEFORE the upstream point is not part of this push => allowed.
    secret = "AKIAIOSFODNN7EXAMPLE"
    _commit_file(git_repo, "old/legacy.py", f"AWS_KEY = '{secret}'\n")
    # Establish an upstream at the current HEAD via a bare clone-style remote.
    remote = git_repo.parent / "remote.git"
    _git(git_repo, "clone", "-q", "--bare", str(git_repo), str(remote))
    _git(git_repo, "remote", "add", "origin", str(remote))
    _git(git_repo, "push", "-q", "-u", "origin", "HEAD")
    # New outgoing commit with NO secret.
    _commit_file(git_repo, "src/clean.py", "print('ok')\n")

    rc = pre_push_scan.check_push("git push origin main", str(git_repo))
    assert rc == 0


def test_push_with_planted_secret_blocked_naming_kind_not_secret(git_repo, capsys):
    secret = "AKIAIOSFODNN7EXAMPLE"
    _commit_file(git_repo, "src/config.py", f"AWS_KEY = '{secret}'\n")

    rc = pre_push_scan.check_push("git push origin main", str(git_repo))
    assert rc == 2
    err = capsys.readouterr().err
    assert "aws-access-key" in err
    assert secret not in err


def test_ordinary_safe_push_allowed(git_repo):
    _commit_file(git_repo, "src/app.py", "print('hello world')\n")
    rc = pre_push_scan.check_push("git push origin main", str(git_repo))
    assert rc == 0


def test_non_push_command_is_not_this_guards_concern(git_repo):
    assert pre_push_scan.check_push("git status", str(git_repo)) == 0


def test_main_malformed_stdin_allows_with_warning(monkeypatch, caplog):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all {{{"))
    rc = pre_push_scan.main()
    assert rc == 0
    assert any("could not parse stdin" in rec.message for rec in caplog.records)


def test_main_internal_exception_allows_with_warning(monkeypatch, git_repo, capsys):
    def _boom(command, cwd):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(pre_push_scan, "check_push", _boom)
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": str(git_repo)}
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    rc = pre_push_scan.main()
    assert rc == 0
    err = capsys.readouterr().err
    assert "WARNING" in err


# =============================================================================
# write_gate: direct-write gate
# =============================================================================


def test_direct_write_to_wiki_page_blocked_with_queue_message(wiki, capsys):
    target = wiki / "projects" / "demo" / "notes.md"
    rc = write_gate.check_direct_write(str(target))
    assert rc == 2
    assert "queue" in capsys.readouterr().err.lower()


def test_write_under_state_dir_allowed(wiki):
    target = state_dir() / "queue" / "q-123.json"
    rc = write_gate.check_direct_write(str(target))
    assert rc == 0


def test_write_with_queue_apply_env_allowed(wiki, monkeypatch):
    monkeypatch.setenv(write_gate.QUEUE_APPLY_ENV, "1")
    target = wiki / "projects" / "demo" / "notes.md"
    rc = write_gate.check_direct_write(str(target))
    assert rc == 0


def test_write_outside_wiki_entirely_allowed(wiki, tmp_path):
    target = tmp_path / "elsewhere" / "notes.md"
    rc = write_gate.check_direct_write(str(target))
    assert rc == 0


# =============================================================================
# write_gate: mass-delete
# =============================================================================


def test_rm_of_three_wiki_pages_blocked(wiki, capsys):
    for name in ("a.md", "b.md", "c.md"):
        (wiki / name).write_text("x\n", encoding="utf-8")

    command = f"rm {wiki / 'a.md'} {wiki / 'b.md'} {wiki / 'c.md'}"
    rc = write_gate.check_mass_delete(command, str(wiki))
    assert rc == 2
    assert "mass-delete" in capsys.readouterr().err.lower()


def test_rm_of_wiki_root_itself_blocked(wiki):
    command = f"rm -rf {wiki}"
    rc = write_gate.check_mass_delete(command, str(wiki))
    assert rc == 2


def test_rm_of_one_non_wiki_file_allowed(tmp_path, wiki):
    target = tmp_path / "scratch.txt"
    target.write_text("x\n", encoding="utf-8")
    command = f"rm {target}"
    rc = write_gate.check_mass_delete(command, str(tmp_path))
    assert rc == 0


def test_rm_rf_of_wiki_dir_with_three_pages_blocked(wiki, capsys):
    d = wiki / "projects" / "demo"
    d.mkdir(parents=True)
    for name in ("a.md", "b.md", "c.md"):
        (d / name).write_text("x\n", encoding="utf-8")

    rc = write_gate.check_mass_delete(f"rm -rf {d}", str(wiki))
    assert rc == 2
    assert "mass-delete" in capsys.readouterr().err.lower()


def test_rm_rf_of_wiki_dir_with_zero_pages_allowed(wiki):
    d = wiki / "projects" / "empty"
    d.mkdir(parents=True)

    rc = write_gate.check_mass_delete(f"rm -rf {d}", str(wiki))
    assert rc == 0


def test_rm_rf_of_non_wiki_dir_with_md_files_unaffected(tmp_path, wiki):
    d = tmp_path / "scratch_dir"
    d.mkdir()
    for name in ("a.md", "b.md", "c.md"):
        (d / name).write_text("x\n", encoding="utf-8")

    rc = write_gate.check_mass_delete(f"rm -rf {d}", str(tmp_path))
    assert rc == 0


def test_rm_rf_of_wiki_dir_with_symlink_to_outside_not_counted_or_followed(wiki, tmp_path):
    # D2 hardening (t4c review): a symlinked subdir inside the delete target
    # pointing OUTSIDE the wiki must never be traversed — its .md pages
    # (however many) must not inflate the count, and a cyclic/huge external
    # tree must not hang the guard.
    d = wiki / "projects" / "demo"
    d.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    for name in ("x.md", "y.md", "z.md"):
        (outside / name).write_text("x\n", encoding="utf-8")
    (d / "link").symlink_to(outside, target_is_directory=True)

    rc = write_gate.check_mass_delete(f"rm -rf {d}", str(wiki))
    assert rc == 0  # zero real (non-symlinked) pages under d — allowed, not blocked or hung


def test_rm_rf_of_nonexistent_wiki_dir_allowed(wiki):
    # D2 hardening (t4c review): `rm -rf` of a path that doesn't exist at
    # guard time falls back to the generic single-hit count (is_dir() is
    # False so the recursive walk branch isn't reached at all) — count 0/1
    # under threshold, allowed. `rm` itself would fail/no-op on the missing
    # path regardless.
    d = wiki / "projects" / "gone"  # never created

    rc = write_gate.check_mass_delete(f"rm -rf {d}", str(wiki))
    assert rc == 0


def test_rm_of_two_wiki_files_under_threshold_allowed(wiki):
    # Non-page files (not .md) so the single-page rule doesn't fire — this
    # test's intent is the THRESHOLD path, not the page rule.
    for name in ("a.txt", "b.txt"):
        (wiki / name).write_text("x\n", encoding="utf-8")
    command = f"rm {wiki / 'a.txt'} {wiki / 'b.txt'}"
    rc = write_gate.check_mass_delete(command, str(wiki))
    assert rc == 0


class TestQuotedRmTargets:
    """G4: mass-delete must resolve quoted rm targets, not slip past them."""

    @pytest.fixture(autouse=True)
    def _setup(self, wiki):
        self.wiki = wiki
        self.cwd = str(wiki)

    def test_single_quoted_wiki_page_blocked(self):
        # A single quoted wiki page hits the single-page rule (it's a .md).
        assert write_gate.check_mass_delete(
            f'rm "{self.wiki}/projects/notes.md"', self.cwd) == 2

    def test_quoted_multi_reaches_mass_tier(self):
        # Three quoted .txt (non-page) targets — only the COUNT threshold can
        # block them, proving quoted targets are actually counted.
        cmd = " ".join(f'"{self.wiki}/a{i}.txt"' for i in range(3))
        assert write_gate.check_mass_delete(f"rm {cmd}", self.cwd) == 2

    def test_quoted_path_with_spaces_blocked(self):
        assert write_gate.check_mass_delete(
            f'rm "{self.wiki}/my notes.md"', self.cwd) == 2

    def test_mixed_quoting_blocked(self):
        # One quoted, one bare .md — either single-page hit blocks.
        assert write_gate.check_mass_delete(
            f'rm "{self.wiki}/a.md" {self.wiki}/b.md', self.cwd) == 2

    def test_unquoted_still_blocked(self):
        # Regression guard: the original unquoted path still blocks.
        assert write_gate.check_mass_delete(
            f"rm {self.wiki}/projects/notes.md", self.cwd) == 2

    def test_quoted_two_non_page_under_threshold_allowed(self):
        # Two quoted .txt targets — under the mass threshold, no page rule.
        assert write_gate.check_mass_delete(
            f'rm "{self.wiki}/a.txt" "{self.wiki}/b.txt"', self.cwd) == 0


class TestRedirectFalsePositive:
    """`>` glued inside a word (a->b) is not a redirect; real redirects are."""

    @pytest.fixture(autouse=True)
    def _setup(self, wiki):
        (wiki / "projects").mkdir(parents=True, exist_ok=True)
        self.wiki = wiki
        # cwd INSIDE the wiki: a false redirect-target would resolve here.
        self.cwd = str(wiki / "projects")

    def test_glued_gt_in_word_not_a_redirect(self):
        assert write_gate.check_bash_wiki_write("ls a->b", self.cwd) == 0

    def test_glued_gt_arrow_arg_not_a_redirect(self):
        assert write_gate.check_bash_wiki_write("echo x->y", self.cwd) == 0

    def test_real_redirect_with_space_blocked(self):
        assert write_gate.check_bash_wiki_write(
            f"echo hi > {self.wiki}/projects/x.md", self.cwd) == 2

    def test_real_redirect_no_space_blocked(self):
        assert write_gate.check_bash_wiki_write(
            f"echo hi >{self.wiki}/projects/x.md", self.cwd) == 2

    def test_real_append_redirect_blocked(self):
        assert write_gate.check_bash_wiki_write(
            f"echo hi >> {self.wiki}/projects/x.md", self.cwd) == 2

    def test_fd_redirect_blocked(self):
        assert write_gate.check_bash_wiki_write(
            f"cmd 2> {self.wiki}/projects/x.md", self.cwd) == 2


class TestMvOutOfWiki:
    @pytest.fixture(autouse=True)
    def _setup(self, wiki):
        (wiki / "projects").mkdir(parents=True, exist_ok=True)
        self.wiki = wiki
        self.cwd = str(wiki.parent)

    def test_mv_wiki_page_out_is_blocked(self):
        assert write_gate.check_bash_wiki_write(
            f"mv {self.wiki}/projects/x.md /tmp/x.md", self.cwd) == 2

    def test_mv_into_wiki_still_blocked(self):
        assert write_gate.check_bash_wiki_write(
            f"mv /tmp/x.md {self.wiki}/projects/x.md", self.cwd) == 2

    def test_mv_entirely_outside_wiki_allowed(self):
        assert write_gate.check_bash_wiki_write(
            "mv /tmp/a.md /tmp/b.md", self.cwd) == 0


class TestSinglePageRm:
    @pytest.fixture(autouse=True)
    def _setup(self, wiki):
        (wiki / "projects").mkdir(parents=True, exist_ok=True)
        self.wiki = wiki
        self.cwd = str(wiki.parent)

    def test_rm_of_one_wiki_page_is_blocked(self):
        assert write_gate.check_mass_delete(
            f"rm {self.wiki}/projects/x.md", self.cwd) == 2

    def test_rm_of_one_non_wiki_file_still_allowed(self):
        assert write_gate.check_mass_delete("rm /tmp/x.md", self.cwd) == 0

    def test_rm_of_ren_state_file_still_allowed(self):
        assert write_gate.check_mass_delete(
            f"rm {self.wiki}/.ren/queue/q-x.json", self.cwd) == 0


# =============================================================================
# write_gate: backup-remote-change (ask, not block)
# =============================================================================


def _assert_ask_wire_shape(decision: dict) -> None:
    # Claude Code's PreToolUse contract: the decision MUST be nested under
    # `hookSpecificOutput` with the event name, or exit-0 output is ignored
    # (silently allowing). A bare top-level `permissionDecision` is the bug.
    assert set(decision) == {"hookSpecificOutput"}
    hso = decision["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "ask"
    assert isinstance(hso["permissionDecisionReason"], str) and hso["permissionDecisionReason"]


def test_backup_remote_set_url_is_ask_decision():
    decision = write_gate.check_backup_remote_change("git remote set-url backup git@example.com:x/y.git")
    _assert_ask_wire_shape(decision)


def test_backup_remote_add_is_ask_decision():
    decision = write_gate.check_backup_remote_change("git remote add backup git@example.com:x/y.git")
    _assert_ask_wire_shape(decision)


def test_unrelated_remote_command_is_no_decision():
    assert write_gate.check_backup_remote_change("git remote add origin git@example.com:x/y.git") is None


def test_main_emits_ask_decision_on_stdout(monkeypatch, wiki):
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git remote set-url backup git@example.com:x/y.git"},
            "cwd": str(wiki),
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    captured_out = io.StringIO()
    monkeypatch.setattr("sys.stdout", captured_out)

    rc = write_gate.main()
    assert rc == 0
    _assert_ask_wire_shape(json.loads(captured_out.getvalue()))


# --- write_gate main(): stdin contract + internal failure -------------------


def test_write_gate_main_malformed_stdin_allows_with_warning(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not valid"))
    rc = write_gate.main()
    assert rc == 0


def test_write_gate_main_internal_exception_allows_with_warning(monkeypatch, wiki, capsys):
    def _boom(file_path):
        raise RuntimeError("simulated internal failure")

    monkeypatch.setattr(write_gate, "check_direct_write", _boom)
    payload = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": str(wiki / "notes.md")}, "cwd": str(wiki)}
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    rc = write_gate.main()
    assert rc == 0
    assert "WARNING" in capsys.readouterr().err


# =============================================================================
# write_apply: REN_QUEUE_APPLY env set/unset (surgical addition, this task)
# =============================================================================


def test_write_apply_sets_queue_apply_env_during_write_and_clears_after(wiki, monkeypatch):
    from lib.memory import write_apply
    from lib.memory.provenance import new_provenance

    seen = {}
    original_replace = os.replace

    def spy_replace(*args, **kwargs):
        seen["during"] = os.environ.get(write_apply.QUEUE_APPLY_ENV)
        return original_replace(*args, **kwargs)

    monkeypatch.setattr(os, "replace", spy_replace)

    prov = new_provenance("human", "sess-1", "ADD", "notes.md")
    write_apply.apply_write("notes.md", "Hello.\n", prov)

    assert seen["during"] == "1"
    assert write_apply.QUEUE_APPLY_ENV not in os.environ


def test_write_apply_clears_queue_apply_env_even_on_error(wiki):
    from lib.memory import write_apply
    from lib.memory.provenance import new_provenance

    prov = new_provenance("human", "sess-1", "ADD", "notes.md")
    with pytest.raises(ValueError):
        write_apply.apply_write("notes.md", None, prov)  # ADD requires new_content -> raises

    assert write_apply.QUEUE_APPLY_ENV not in os.environ


# =============================================================================
# write_gate: bash wiki-write guard (best-effort, targeted extraction)
# =============================================================================


class TestBashWikiWriteGuard:
    """check_bash_wiki_write blocks shell WRITES into the wiki, allows reads."""

    @pytest.fixture(autouse=True)
    def _setup(self, wiki):
        (wiki / "projects").mkdir(parents=True, exist_ok=True)
        self.wiki = wiki
        self.cwd = str(wiki.parent)

    def test_redirect_into_wiki_blocked(self, capsys):
        rc = write_gate.check_bash_wiki_write(f"echo hi > {self.wiki}/projects/x.md", self.cwd)
        assert rc == 2
        assert "wiki" in capsys.readouterr().err.lower()

    def test_append_into_wiki_blocked(self):
        rc = write_gate.check_bash_wiki_write(f"echo hi >> {self.wiki}/projects/x.md", self.cwd)
        assert rc == 2

    def test_sed_inplace_on_wiki_blocked(self):
        rc = write_gate.check_bash_wiki_write(f"sed -i 's/a/b/' {self.wiki}/projects/x.md", self.cwd)
        assert rc == 2

    def test_cp_into_wiki_blocked(self):
        rc = write_gate.check_bash_wiki_write(f"cp /tmp/x.md {self.wiki}/projects/x.md", self.cwd)
        assert rc == 2

    def test_tee_into_wiki_blocked(self):
        rc = write_gate.check_bash_wiki_write(f"echo hi | tee {self.wiki}/projects/x.md", self.cwd)
        assert rc == 2

    def test_reading_wiki_allowed(self):
        assert write_gate.check_bash_wiki_write(f"cat {self.wiki}/projects/x.md", self.cwd) == 0

    def test_redirect_out_of_wiki_allowed(self, tmp_path):
        rc = write_gate.check_bash_wiki_write(
            f"cat {self.wiki}/projects/x.md > {tmp_path}/out.md", self.cwd
        )
        assert rc == 0

    def test_copy_out_of_wiki_allowed(self, tmp_path):
        rc = write_gate.check_bash_wiki_write(
            f"cp {self.wiki}/projects/x.md {tmp_path}/", self.cwd
        )
        assert rc == 0

    def test_state_dir_writes_allowed(self):
        target = state_dir() / "queue" / "q.json"
        rc = write_gate.check_bash_wiki_write(f"echo x > {target}", self.cwd)
        assert rc == 0

    def test_sanctioned_apply_allowed(self, monkeypatch):
        monkeypatch.setenv(write_gate.QUEUE_APPLY_ENV, "1")
        rc = write_gate.check_bash_wiki_write(f"echo hi > {self.wiki}/projects/x.md", self.cwd)
        assert rc == 0

    def test_relative_path_resolved_against_cwd(self):
        rc = write_gate.check_bash_wiki_write(
            f"echo hi > {self.wiki.name}/projects/x.md", str(self.wiki.parent)
        )
        assert rc == 2

    def test_quoted_gt_in_grep_with_cwd_inside_wiki_allowed(self):
        # Pure READ: the '>' is quoted data, not a redirect. With cwd INSIDE
        # the wiki, the stripped-empty token must not resolve to cwd and block.
        rc = write_gate.check_bash_wiki_write(
            f"grep -c '>' {self.wiki}/projects/x.md", str(self.wiki / "projects")
        )
        assert rc == 0

    def test_quoted_prose_gt_with_cwd_inside_wiki_allowed(self):
        rc = write_gate.check_bash_wiki_write(
            'echo "a > b"', str(self.wiki / "projects")
        )
        assert rc == 0

    def test_sed_multi_substitution_script_blocked(self):
        # Standard multi-sub idiom: the quoted ';' must not split the segment
        # and hide the file arg from extraction.
        rc = write_gate.check_bash_wiki_write(
            f"sed -i 's/a/b/;s/c/d/' {self.wiki}/notes.md", self.cwd
        )
        assert rc == 2

    def test_quoted_redirect_target_blocked(self):
        # Fully-quoted destinations are a common shell idiom — masking must
        # restore them, not drop them.
        rc = write_gate.check_bash_wiki_write(
            f'echo hi > "{self.wiki}/projects/x.md"', self.cwd
        )
        assert rc == 2

    def test_quoted_cp_destination_blocked(self):
        rc = write_gate.check_bash_wiki_write(
            f'cp /tmp/x.md "{self.wiki}/projects/x.md"', self.cwd
        )
        assert rc == 2

    def test_quoted_sed_file_arg_blocked(self):
        rc = write_gate.check_bash_wiki_write(
            f"sed -i 's/a/b/' \"{self.wiki}/projects/x.md\"", self.cwd
        )
        assert rc == 2

    def test_literal_placeholder_text_cannot_poison_restoration(self):
        # Adversarial collision: literal `_q0_` in the target is USER TEXT,
        # not a masking artifact. Restoration must not substitute the decoy
        # quoted span into it (which would traversal-poison the path so it
        # resolves outside the wiki while the real write lands inside).
        rc = write_gate.check_bash_wiki_write(
            f": '../../../../../../tmp' ; echo hi > {self.wiki}/projects/_q0_evil.md",
            self.cwd,
        )
        assert rc == 2

    def test_multi_quoted_span_command_still_blocked(self):
        # Two quoted spans: an earlier decoy plus a quoted sed script — the
        # unquoted wiki file arg must still be extracted and blocked.
        rc = write_gate.check_bash_wiki_write(
            f"echo 'decoy' ; sed -i 's/a/b/' '{self.wiki}/projects/x.md'",
            self.cwd,
        )
        assert rc == 2

    def test_newline_separated_sed_blocked(self):
        # Multi-line commands: '\n' is a command separator too — a sed on a
        # non-first line must not hide behind the first line's `echo`.
        rc = write_gate.check_bash_wiki_write(
            f"echo starting\nsed -i 's/x/y/' {self.wiki}/projects/target.md",
            self.cwd,
        )
        assert rc == 2

    def test_newline_separated_cp_blocked(self):
        rc = write_gate.check_bash_wiki_write(
            f"echo hi\ncp /tmp/x.md {self.wiki}/projects/y.md",
            self.cwd,
        )
        assert rc == 2

    def test_backslash_continuation_sed_blocked(self):
        # A backslash-newline is a line CONTINUATION (one logical command),
        # not a separator — the file arg on the continued line must still be
        # attributed to the sed on the first line.
        rc = write_gate.check_bash_wiki_write(
            f"sed -i \\\n's/a/b/' {self.wiki}/projects/target.md",
            self.cwd,
        )
        assert rc == 2
