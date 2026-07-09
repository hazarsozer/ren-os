"""
Tests for skills.doctor.lib — the health-check harness (Task 7.3).

Each check gets at least one firing test and one quiet test, using fixture
states (tmp_path wiki + monkeypatched env). The soft-wired harness-neutrality
check gets a dedicated "module absent" test via import monkeypatching.

Run with: uv run pytest tests/skills/doctor/test_doctor.py -v
"""

from __future__ import annotations

import importlib
import subprocess

import pytest

from lib.instrument import collect
from lib.ren_paths import wiki_root

doctor = importlib.import_module("skills.doctor.lib")


@pytest.fixture
def clean_path_env(monkeypatch):
    for var in (
        "REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT",
        "CLAUDE_PLUGIN_DATA", "CLAUDE_SESSION_ID",
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def wiki(clean_path_env, tmp_path):
    clean_path_env.setenv("REN_FRAMEWORK_ROOT", str(tmp_path))
    clean_path_env.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "plugin-data"))
    root = wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _init_git_repo(path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)


# --------------------------------------------------------------------- run_checks


def test_run_checks_returns_one_result_per_check(wiki):
    results = doctor.run_checks()
    names = {r.name for r in results}
    assert names == {
        "env", "wiki_structure", "frontmatter", "schema_versions",
        "budget_lint", "dangling_pointers", "graphify_status", "companions",
        "backup_configured", "execution_tiers", "global_drift", "harness_neutrality", "guard_health",
    }


def test_one_crashing_check_does_not_prevent_others(wiki, monkeypatch):
    def _boom():
        raise RuntimeError("simulated check crash")

    monkeypatch.setattr(doctor, "check_env", _boom)
    results = doctor.run_checks()

    env_result = next(r for r in results if r.name == "env")
    assert env_result.status == "error"
    assert "simulated check crash" in env_result.message

    other = next(r for r in results if r.name == "wiki_structure")
    assert other.status in ("ok", "warn")  # ran normally


# ------------------------------------------------------------------- check_env


def test_check_env_ok_when_tools_present(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    result = doctor.check_env()
    assert result.status == "ok"


def test_check_env_warns_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = doctor.check_env()
    assert result.status == "warn"


# ----------------------------------------------------------- check_wiki_structure


def test_check_wiki_structure_ok(wiki):
    (wiki / "identity.md").write_text("x", encoding="utf-8")
    (wiki / "log.md").write_text("x", encoding="utf-8")
    result = doctor.check_wiki_structure(wiki)
    assert result.status == "ok"


def test_check_wiki_structure_warns_when_missing_files(wiki):
    result = doctor.check_wiki_structure(wiki)
    assert result.status == "warn"


def test_check_wiki_structure_warns_when_no_wiki(tmp_path):
    result = doctor.check_wiki_structure(tmp_path / "no-wiki-here")
    assert result.status == "warn"


# --------------------------------------------------------------- check_frontmatter


def test_check_frontmatter_ok_on_clean_wiki(wiki):
    (wiki / "identity.md").write_text('---\ntitle: "x"\n---\nbody', encoding="utf-8")
    result = doctor.check_frontmatter(wiki)
    assert result.status == "ok"


def test_check_frontmatter_warns_on_malformed_yaml(wiki):
    (wiki / "bad.md").write_text("---\ntitle: [unclosed\n---\nbody", encoding="utf-8")
    result = doctor.check_frontmatter(wiki)
    assert result.status == "warn"


# ------------------------------------------------------------ check_schema_versions


def test_check_schema_versions_ok_when_current(wiki):
    (wiki / "identity.md").write_text('---\ntype: identity\nschema_version: 1\n---\n', encoding="utf-8")
    result = doctor.check_schema_versions(wiki)
    assert result.status == "ok"


def test_check_schema_versions_warns_when_behind(wiki):
    (wiki / "routines").mkdir()
    (wiki / "routines" / "sample.md").write_text(
        '---\ntype: routine-spec\nschema_version: 1\n---\n', encoding="utf-8"
    )
    result = doctor.check_schema_versions(wiki)
    assert result.status == "warn"
    assert "routine-spec-1-to-2" in result.message


# --------------------------------------------------------------- check_budget_lint


def test_check_budget_lint_skips_with_no_data(wiki):
    result = doctor.check_budget_lint(wiki)
    assert result.status == "skip"


def test_check_budget_lint_info_when_no_declared_ceiling(wiki):
    collect.record(collect.KIND_CAPABILITY_TOKENS, {"capability": "pin", "tokens": 500})
    result = doctor.check_budget_lint(wiki)
    assert result.status == "info"


def test_check_budget_lint_warns_when_over_declared_ceiling(wiki, tmp_path, monkeypatch):
    # Point _REPO_ROOT-relative skills dir lookup at a fake skill with a declared ceiling.
    fake_skill_dir = doctor._REPO_ROOT / "skills" / "__doctest_fake_skill__"
    fake_skill_dir.mkdir(parents=True, exist_ok=True)
    (fake_skill_dir / "SKILL.md").write_text(
        "---\nname: fake\nbudgets:\n  tokens: 100\n---\n", encoding="utf-8"
    )
    try:
        collect.record(collect.KIND_CAPABILITY_TOKENS, {"capability": "__doctest_fake_skill__", "tokens": 999})
        result = doctor.check_budget_lint(wiki)
        assert result.status == "warn"
        assert "__doctest_fake_skill__" in result.message
    finally:
        (fake_skill_dir / "SKILL.md").unlink()
        fake_skill_dir.rmdir()


# ---------------------------------------------------------- check_dangling_pointers


def test_check_dangling_pointers_ok_when_targets_exist(wiki):
    (wiki / "decisions").mkdir()
    (wiki / "decisions" / "db.md").write_text("# DB choice", encoding="utf-8")
    (wiki / "map.md").write_text(
        "---\ntype: l2-map\nproject: p\n---\n"
        "## Decision map\n"
        "- [db] → decisions/db.md#choice (w-1)\n",
        encoding="utf-8",
    )
    result = doctor.check_dangling_pointers(wiki)
    assert result.status == "ok"


def test_check_dangling_pointers_warns_on_missing_target(wiki):
    (wiki / "map.md").write_text(
        "---\ntype: l2-map\nproject: p\n---\n"
        "## Decision map\n"
        "- [db] → decisions/does-not-exist.md#choice (w-1)\n",
        encoding="utf-8",
    )
    result = doctor.check_dangling_pointers(wiki)
    assert result.status == "warn"


def test_check_dangling_pointers_warns_not_crashes_on_path_escaping_target(wiki):
    (wiki / "map.md").write_text(
        "---\ntype: l2-map\nproject: p\n---\n"
        "## Decision map\n"
        "- [topic] → ../../outside.md#a (w-1)\n",
        encoding="utf-8",
    )
    result = doctor.check_dangling_pointers(wiki)
    assert result.status == "warn"
    assert "../../outside.md" in result.message


# ------------------------------------------------------------ check_graphify_status


def test_check_graphify_status_info_when_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = doctor.check_graphify_status(tmp_path)
    assert result.status == "info"


# ------------------------------------------------------------- check_companions


def test_check_companions_warns_on_accepted_but_missing(monkeypatch, wiki):
    from lib import companions

    monkeypatch.setattr(companions, "is_installed", lambda c: False)
    companions.record_choice("graphify", "accepted")
    result = doctor.check_companions()
    assert result.status == "warn"
    assert "graphify" in result.message


def test_check_companions_info_when_undecided(monkeypatch, wiki):
    from lib import companions

    monkeypatch.setattr(companions, "is_installed", lambda c: False)
    result = doctor.check_companions()
    assert result.status == "info"


def test_check_companions_ok_when_consistent(monkeypatch, wiki):
    from lib import companions

    monkeypatch.setattr(companions, "is_installed", lambda c: True)
    result = doctor.check_companions()
    assert result.status == "ok"


# ----------------------------------------------------------- check_backup_configured


def test_check_backup_configured_warns_with_nothing_set_up(wiki):
    _init_git_repo(wiki)
    result = doctor.check_backup_configured(wiki)
    assert result.status == "warn"


def test_check_backup_configured_ok_with_recent_tarball(wiki, tmp_path):
    _init_git_repo(wiki)
    backups_dir = tmp_path / "plugin-data" / "backups"
    backups_dir.mkdir(parents=True)
    (backups_dir / "wiki-2026-01-01-000000.tar.gz").write_bytes(b"x")
    result = doctor.check_backup_configured(wiki)
    assert result.status == "ok"


# --------------------------------------------------------------- check_global_drift


def test_check_global_drift_ok_when_clean(wiki):
    result = doctor.check_global_drift()
    assert result.status == "ok"


def test_check_global_drift_warns_on_violation(wiki):
    global_dir = wiki / "global"
    global_dir.mkdir()
    (global_dir / "bad.md").write_text('---\ntype: research\n---\n', encoding="utf-8")
    result = doctor.check_global_drift()
    assert result.status == "warn"


# ----------------------------------------------------------- check_harness_neutrality


def test_check_harness_neutrality_skips_when_module_absent(wiki, monkeypatch):
    real_import_module = importlib.import_module

    def _fake_import_module(name, *args, **kwargs):
        if name == "lib.portability.agents_surface":
            raise ImportError("simulated absence")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(doctor.importlib, "import_module", _fake_import_module)
    result = doctor.check_harness_neutrality(wiki, doctor._REPO_ROOT)
    assert result.status == "skip"


def test_check_harness_neutrality_ok_when_clean(wiki):
    result = doctor.check_harness_neutrality(wiki, doctor._REPO_ROOT)
    assert result.status in ("ok", "skip")  # ok if module present+clean, skip if truly absent


def test_guard_health_quiet_on_healthy_guards(wiki):
    """Task 9.3 doc-note-3: healthy guards pass the safe synthetic payload."""
    result = doctor.check_guard_health()
    assert result.status == "ok", result.message


def test_guard_health_warns_on_broken_guard(wiki, tmp_path):
    broken_dir = tmp_path / "guards"
    broken_dir.mkdir()
    (broken_dir / "broken_guard.py").write_text("raise RuntimeError('guard is broken')\n")
    result = doctor.check_guard_health(guards_dir=broken_dir)
    assert result.status == "warn"
    assert "degraded" in result.message
    assert "broken_guard.py" in result.message

# ------------------------------------------------------- check_execution_tiers


def _skill(dir_: str, tier_line: str | None):
    def write(root):
        skill_dir = root / dir_
        skill_dir.mkdir(parents=True)
        lines = ["---", "name: " + dir_, "type: skill"]
        if tier_line is not None:
            lines.append(tier_line)
        lines += ["---", "", "# " + dir_, ""]
        (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return write


def test_check_execution_tiers_ok_on_valid_declarations(tmp_path):
    skills = tmp_path / "skills"
    _skill("alpha", "execution_tier: deterministic")(skills)
    _skill("beta", "execution_tier: worker")(skills)
    _skill("gamma", "execution_tier: judgment")(skills)

    result = doctor.check_execution_tiers(skills_dir=skills)

    assert result.status == "ok"


def test_check_execution_tiers_warns_on_missing_declaration(tmp_path):
    skills = tmp_path / "skills"
    _skill("alpha", "execution_tier: deterministic")(skills)
    _skill("beta", None)(skills)

    result = doctor.check_execution_tiers(skills_dir=skills)

    assert result.status == "warn"
    assert "beta" in result.message


def test_check_execution_tiers_warns_on_invalid_value(tmp_path):
    skills = tmp_path / "skills"
    _skill("alpha", "execution_tier: turbo")(skills)

    result = doctor.check_execution_tiers(skills_dir=skills)

    assert result.status == "warn"
    assert "alpha" in result.message


def test_check_execution_tiers_skips_when_no_skills_dir(tmp_path):
    result = doctor.check_execution_tiers(skills_dir=tmp_path / "missing")
    assert result.status == "skip"


def test_shipped_skills_all_declare_valid_execution_tiers():
    """The repo's own 17 skills must each declare a valid tier — the lint
    run doctor itself performs, executed directly against the shipped tree."""
    result = doctor.check_execution_tiers()
    assert result.status == "ok", result.detail
