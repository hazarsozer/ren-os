"""Tests for skills/update/lib should_run_foreign_remint_1 (issue #22).

Mirrors the trust-backfill-1 / project-knowledge-1 shape: foreign-remint-1
is a standalone, non-chain migration (see migrations/foreign-remint-1/
README.md and skills/wiki-migration/schemas.json's global_migrations note).
This gate decides whether a friend's /ren:update run crosses the 0.6.3
boundary and should therefore invoke migrations/foreign-remint-1/migrate.py
as a post-update step. The migration itself is idempotent (see
tests/migrations/test_foreign_remint_1.py), so this gate only needs to
answer "did this update cross 0.6.3?"
"""

from __future__ import annotations

from skills.update import lib as update_lib


def test_crossing_0_6_3_runs_migration():
    assert update_lib.should_run_foreign_remint_1("0.6.2", "0.6.3") is True


def test_crossing_past_0_6_3_runs_migration():
    assert update_lib.should_run_foreign_remint_1("0.6.2", "0.7.0") is True


def test_not_crossing_0_6_3_does_not_run_migration():
    assert update_lib.should_run_foreign_remint_1("0.6.1", "0.6.2") is False


def test_already_past_0_6_3_does_not_rerun_migration():
    assert update_lib.should_run_foreign_remint_1("0.6.3", "0.6.4") is False


def test_downgrade_does_not_run_migration():
    assert update_lib.should_run_foreign_remint_1("0.6.3", "0.6.2") is False


def test_malformed_versions_fail_closed():
    assert update_lib.should_run_foreign_remint_1("garbage", "0.6.3") is False
    assert update_lib.should_run_foreign_remint_1("0.6.2", "") is False
