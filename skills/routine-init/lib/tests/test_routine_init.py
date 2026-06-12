"""Tests for skills.routine-init.lib — scaffold + validation (C4 / ADR-034)."""
from __future__ import annotations

from pathlib import Path

from ..__init__ import RoutineInitResult, routine_init

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"  # skills/routine-init/templates


def _run(tmp_path: Path, **overrides) -> RoutineInitResult:
    kw = dict(
        name="daily-digest",
        dest_dir=tmp_path / "repos",
        wiki_root=tmp_path / "wiki",
        trigger_type="cron",
        linked_repo="https://github.com/u/daily-digest",
        skill="insights",
        network_tier="trusted",
        schedule="every day at 8am ET",
        expected_output="A digest of yesterday's activity.",
        env_secrets_ref="RESEND_API_KEY",
        failure_email="me@example.com",
        today="2026-06-11",
        templates_dir=TEMPLATES,
    )
    kw.update(overrides)
    return routine_init(**kw)


class TestValidation:
    def test_rejects_non_kebab_name(self, tmp_path):
        r = _run(tmp_path, name="DailyDigest")
        assert not r.success and "kebab" in r.error

    def test_rejects_empty_name(self, tmp_path):
        r = _run(tmp_path, name="")
        assert not r.success and "kebab" in r.error

    def test_rejects_bad_trigger(self, tmp_path):
        r = _run(tmp_path, trigger_type="hourly")
        assert not r.success and "trigger_type" in r.error

    def test_rejects_bad_tier(self, tmp_path):
        r = _run(tmp_path, network_tier="open")
        assert not r.success and "network_tier" in r.error

    def test_rejects_empty_skill(self, tmp_path):
        r = _run(tmp_path, skill="  ")
        assert not r.success and "skill" in r.error

    def test_refuses_existing_repo_dir(self, tmp_path):
        (tmp_path / "repos" / "daily-digest").mkdir(parents=True)
        r = _run(tmp_path)
        assert not r.success and "overwrite" in r.error


class TestScaffold:
    def test_creates_all_repo_files(self, tmp_path):
        r = _run(tmp_path)
        assert r.success, r.error
        repo = tmp_path / "repos" / "daily-digest"
        for f in ("CLAUDE.md", "ROUTINE_PROMPT.md", "state.md", "run-log.md"):
            assert (repo / f).is_file(), f"missing {f}"
        assert r.repo_dir == repo

    def test_prompt_bakes_in_conventions(self, tmp_path):
        r = _run(tmp_path)
        prompt = (tmp_path / "repos" / "daily-digest" / "ROUTINE_PROMPT.md").read_text()
        assert "mcp__resend__send-email" in prompt       # failure footer
        assert "me@example.com" in prompt                # owner email rendered
        assert "/ren:recall --routine ." in prompt       # state load
        assert "/ren:insights" in prompt                 # skill-as-prompt
        assert "SINGLE-PASS" in prompt                   # self-terminating

    def test_claude_md_env_var_sourcing(self, tmp_path):
        r = _run(tmp_path)
        claude = (tmp_path / "repos" / "daily-digest" / "CLAUDE.md").read_text()
        assert ".env" in claude
        assert "do NOT" in claude   # explicit env-var sourcing
