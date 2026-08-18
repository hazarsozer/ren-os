"""Tests for skills/update/lib should_run_distiller_watermark_seed (0.8.0 Task 7).

Mirrors the pattern of should_run_trust_backfill: this gate
decides whether a friend's /ren:update run crosses the 0.8.0 boundary and
should therefore seed the distiller watermark as a post-update step
(idempotent, only if the watermark doesn't exist yet).
"""

from __future__ import annotations

from skills.update import lib as update_lib


def test_crossing_0_8_0_runs_seed():
    assert update_lib.should_run_distiller_watermark_seed("0.7.9", "0.8.0") is True


def test_crossing_past_0_8_0_runs_seed():
    assert update_lib.should_run_distiller_watermark_seed("0.7.0", "0.9.0") is True


def test_not_crossing_0_8_0_does_not_run_seed():
    assert update_lib.should_run_distiller_watermark_seed("0.8.0", "0.8.1") is False


def test_staying_below_0_8_0_does_not_run_seed():
    assert update_lib.should_run_distiller_watermark_seed("0.7.0", "0.7.9") is False


def test_equal_versions_does_not_run_seed():
    assert update_lib.should_run_distiller_watermark_seed("0.8.0", "0.8.0") is False


def test_unparseable_versions_does_not_run_seed():
    assert update_lib.should_run_distiller_watermark_seed("garbage", "0.8.0") is False
