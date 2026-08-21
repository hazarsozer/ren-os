"""Tests for skills/update/lib should_run_frontmatter_type_1 (issue #77).

Mirrors the trust-backfill-1 / project-knowledge-1 / foreign-remint-1 shape:
frontmatter-type-1 is a standalone, non-chain global migration (see
migrations/frontmatter-type-1/README.md and skills/wiki-migration/schemas.json's
global_migrations note). This gate decides whether a friend's /ren:update run
crosses the 0.8.1 boundary and should therefore invoke
migrations/frontmatter-type-1/migrate.py as a post-update step.

Why the gate is needed at all (issue #77): `global_migrations` in schemas.json
is discoverability-only — being listed there causes /ren:update to run exactly
nothing. Every global migration is gated by its own version function here.
Without this one, the backfill would run on no install but the one it was
applied to by hand, and pages created before the write door derived `type:`
would keep manufacturing missing-frontmatter-type lint findings forever.

The migration itself is idempotent (see
tests/migrations/test_frontmatter_type_1.py::test_is_idempotent), so this gate
only needs to answer "did this update cross 0.8.1?"
"""

from __future__ import annotations

from skills.update import lib as update_lib


def test_crossing_0_8_1_runs_backfill():
    assert update_lib.should_run_frontmatter_type_1("0.8.0", "0.8.1") is True


def test_crossing_past_0_8_1_runs_backfill():
    assert update_lib.should_run_frontmatter_type_1("0.8.0", "0.9.0") is True


def test_landing_exactly_on_0_8_1_from_earlier_runs_backfill():
    assert update_lib.should_run_frontmatter_type_1("0.7.3", "0.8.1") is True


def test_not_crossing_0_8_1_does_not_run_backfill():
    assert update_lib.should_run_frontmatter_type_1("0.8.1", "0.8.2") is False


def test_staying_below_0_8_1_does_not_run_backfill():
    assert update_lib.should_run_frontmatter_type_1("0.7.0", "0.8.0") is False


def test_equal_versions_does_not_run_backfill():
    assert update_lib.should_run_frontmatter_type_1("0.8.1", "0.8.1") is False


def test_unparseable_versions_does_not_run_backfill():
    assert update_lib.should_run_frontmatter_type_1("garbage", "0.8.1") is False


def test_gate_is_not_above_the_shipped_version():
    """The gate fires on `old < GATE <= new`, so a gate ABOVE the shipped
    version can never fire for anyone upgrading TO this release — the silent
    no-op #77 exists to prevent.

    This asserted equality until 0.8.2, which was correct only for the release
    that INTRODUCED the migration. `frontmatter-type-1` shipped in 0.8.1 and
    its gate must stay at 0.8.1 forever: someone on 0.8.0 upgrading to any
    later version still needs the backfill (`0.8.0 < 0.8.1 <= new`), while
    someone who already came through 0.8.1 must not re-run it
    (`0.8.1 < 0.8.1` is false). Bumping the gate each release to satisfy an
    equality check would falsify what the constant means — it records where
    the migration was introduced, not what is shipping today.

    The real invariant is the one the rationale above actually supports:
    the gate must never exceed the shipped version.
    """
    from pathlib import Path
    import json

    repo_root = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (repo_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )

    def key(v: str) -> tuple[int, ...]:
        return tuple(int(part) for part in v.split("."))

    assert key(update_lib._FRONTMATTER_TYPE_GATE) <= key(manifest["version"]), (
        "the frontmatter-type-1 gate must not exceed the shipped plugin "
        "version, or nobody upgrading to this release runs the backfill"
    )
