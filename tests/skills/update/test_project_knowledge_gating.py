"""Tests for skills/update/lib should_run_project_knowledge_1 (0.6.2, issue #20).

Mirrors the trust-backfill-1 shape: project-knowledge-1 is a standalone,
non-chain migration (see migrations/project-knowledge-1/README.md and
skills/wiki-migration/schemas.json's global_migrations note). This gate
decides whether a friend's /ren:update run crosses the 0.6.2 boundary and
should therefore invoke migrations/project-knowledge-1/migrate.py as a
post-update step. The migration itself is idempotent (see
tests/migrations/test_project_knowledge_1.py), so this gate only needs to
answer "did this update cross 0.6.2?"
"""

from __future__ import annotations

from skills.update import lib as update_lib


def test_crossing_0_6_2_runs_migration():
    assert update_lib.should_run_project_knowledge_1("0.6.1", "0.6.2") is True


def test_crossing_past_0_6_2_runs_migration():
    assert update_lib.should_run_project_knowledge_1("0.6.1", "0.6.3") is True


def test_landing_exactly_on_0_6_2_from_much_earlier_runs_migration():
    assert update_lib.should_run_project_knowledge_1("0.5.3", "0.6.2") is True


def test_not_crossing_0_6_2_does_not_run_migration():
    assert update_lib.should_run_project_knowledge_1("0.6.0", "0.6.1") is False


def test_already_past_0_6_2_does_not_rerun_migration():
    assert update_lib.should_run_project_knowledge_1("0.6.2", "0.6.3") is False


def test_downgrade_does_not_run_migration():
    assert update_lib.should_run_project_knowledge_1("0.6.2", "0.6.1") is False


def test_malformed_versions_fail_closed():
    assert update_lib.should_run_project_knowledge_1("garbage", "0.6.2") is False
    assert update_lib.should_run_project_knowledge_1("0.6.1", "") is False
