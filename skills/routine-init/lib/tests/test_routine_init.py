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


class TestSpecPage:
    def test_writes_routine_spec_page(self, tmp_path):
        r = _run(tmp_path)
        assert r.success, r.error
        page = tmp_path / "wiki" / "routines" / "daily-digest.md"
        assert page.is_file()
        assert r.spec_page == page
        content = page.read_text()
        assert "type: routine-spec" in content
        assert "schema_version: 1" in content
        assert "daily-digest" in content
        assert '"cron"' in content
        assert '"trusted"' in content

    def test_spec_page_has_required_fields(self, tmp_path):
        r = _run(tmp_path)
        content = (tmp_path / "wiki" / "routines" / "daily-digest.md").read_text()
        for key in ("name:", "trigger_type:", "linked_repo:", "network_tier:"):
            assert key in content
        assert 'framework_version: "1.0.0"' in content

    def test_refuses_existing_spec_page(self, tmp_path):
        (tmp_path / "wiki" / "routines").mkdir(parents=True)
        (tmp_path / "wiki" / "routines" / "daily-digest.md").write_text("x", encoding="utf-8")
        r = _run(tmp_path)
        assert not r.success and "routine-spec page" in r.error
        # No partial repo created when the spec page already exists.
        assert not (tmp_path / "repos" / "daily-digest").exists()

    def test_wiki_template_missing_cleans_up(self, tmp_path):
        # templates dir with repo/ present but the wiki/ template absent
        fake_templates = tmp_path / "tmpl"
        (fake_templates / "repo").mkdir(parents=True)
        for f in ("CLAUDE.md", "ROUTINE_PROMPT.md", "state.md", "run-log.md"):
            (fake_templates / "repo" / f"{f}.tmpl").write_text("{{routine_name}}", encoding="utf-8")
        # intentionally no wiki/routine-spec.md.tmpl
        r = _run(tmp_path, templates_dir=fake_templates)
        assert not r.success and "Wiki-page write failed" in r.error
        assert not (tmp_path / "repos" / "daily-digest").exists()
