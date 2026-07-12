"""Tests for skills/update/lib should_run_trust_backfill (0.5.1 Task 10a).

Mirrors the queue-governance-2-to-3 shape: trust-backfill-1 is a standalone,
non-chain migration (see migrations/trust-backfill-1/README.md and
skills/wiki-migration/schemas.json's global_migrations note). This gate
decides whether a friend's /ren:update run crosses the 0.5.1 boundary and
should therefore invoke migrations/trust-backfill-1/migrate.py as a
post-update step. The migration itself is idempotent (see
tests/migrations/test_trust_backfill_1.py::test_migration_is_idempotent_second_run_is_noop),
so this gate only needs to answer "did this update cross 0.5.1?"
"""

from __future__ import annotations

from skills.update import lib as update_lib


def test_crossing_0_5_1_runs_backfill():
    assert update_lib.should_run_trust_backfill("0.5.0", "0.5.1") is True


def test_crossing_past_0_5_1_runs_backfill():
    assert update_lib.should_run_trust_backfill("0.5.0", "0.5.2") is True


def test_landing_exactly_on_0_5_1_from_earlier_runs_backfill():
    assert update_lib.should_run_trust_backfill("0.4.3", "0.5.1") is True


def test_not_crossing_0_5_1_does_not_run_backfill():
    assert update_lib.should_run_trust_backfill("0.5.1", "0.5.2") is False


def test_staying_below_0_5_1_does_not_run_backfill():
    assert update_lib.should_run_trust_backfill("0.4.0", "0.4.9") is False


def test_equal_versions_does_not_run_backfill():
    assert update_lib.should_run_trust_backfill("0.5.1", "0.5.1") is False


def test_unparseable_versions_does_not_run_backfill():
    assert update_lib.should_run_trust_backfill("garbage", "0.5.1") is False
