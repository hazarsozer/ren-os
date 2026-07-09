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


def test_history_rewrite_then_push_blocked(git_repo, capsys):
    rc = pre_push_scan.check_push("git rebase main && git push origin main", str(git_repo))
    assert rc == 2


def test_push_to_backup_remote_skips_both_scans(git_repo):
    _commit_file(git_repo, "wiki/secret-plan.md", "the founder's actual plan\n")
    _commit_file(git_repo, "fixtures/fake.env", "AWS_KEY=AKIAIOSFODNN7EXAMPLE\n")

    rc = pre_push_scan.check_push("git push backup main", str(git_repo))
    assert rc == 0


def test_push_to_other_remote_with_wiki_path_blocked(git_repo, capsys):
    _commit_file(git_repo, "wiki/secret-plan.md", "the founder's actual plan\n")

    rc = pre_push_scan.check_push("git push origin main", str(git_repo))
    assert rc == 2
    assert "wiki/secret-plan.md" in capsys.readouterr().err


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


def test_rm_of_two_wiki_files_under_threshold_allowed(wiki):
    for name in ("a.md", "b.md"):
        (wiki / name).write_text("x\n", encoding="utf-8")
    command = f"rm {wiki / 'a.md'} {wiki / 'b.md'}"
    rc = write_gate.check_mass_delete(command, str(wiki))
    assert rc == 0


# =============================================================================
# write_gate: backup-remote-change (ask, not block)
# =============================================================================


def test_backup_remote_set_url_is_ask_decision():
    decision = write_gate.check_backup_remote_change("git remote set-url backup git@example.com:x/y.git")
    assert decision == {"permissionDecision": "ask"}


def test_backup_remote_add_is_ask_decision():
    decision = write_gate.check_backup_remote_change("git remote add backup git@example.com:x/y.git")
    assert decision == {"permissionDecision": "ask"}


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
    assert json.loads(captured_out.getvalue()) == {"permissionDecision": "ask"}


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
