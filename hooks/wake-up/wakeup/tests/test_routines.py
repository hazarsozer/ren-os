"""Tests for the wake-up hook's live-automations (routine-spec) surfacing — C4 / ADR-034."""
from __future__ import annotations

from pathlib import Path

from ..__init__ import compose_wake_up_context, read_live_routines


def _write_routine(routines_dir: Path, slug: str, *, trigger="cron", tier="trusted",
                   repo="https://github.com/u/r") -> None:
    routines_dir.mkdir(parents=True, exist_ok=True)
    (routines_dir / f"{slug}.md").write_text(
        "---\n"
        "type: routine-spec\n"
        "schema_version: 1\n"
        'framework_version: "1.0.0"\n'
        f'name: "{slug}"\n'
        f'trigger_type: "{trigger}"\n'
        f'linked_repo: "{repo}"\n'
        f'network_tier: "{tier}"\n'
        "---\n\n"
        f"# {slug}\n",
        encoding="utf-8",
    )


def test_read_live_routines_empty(tmp_path):
    assert read_live_routines(tmp_path) == ""


def test_read_live_routines_lists_and_flags_full(tmp_path):
    _write_routine(tmp_path / "routines", "daily-digest", tier="trusted")
    _write_routine(tmp_path / "routines", "scraper", tier="full")
    out = read_live_routines(tmp_path)
    assert "daily-digest" in out and "scraper" in out
    assert out.count("⚠️ full-network") == 1   # only the full-tier one flagged


def test_read_live_routines_ignores_non_routine_md(tmp_path):
    rd = tmp_path / "routines"
    rd.mkdir(parents=True)
    (rd / "README.md").write_text("# not a routine\n", encoding="utf-8")
    assert read_live_routines(tmp_path) == ""


def test_read_live_routines_skips_malformed_frontmatter(tmp_path):
    rd = tmp_path / "routines"
    rd.mkdir()
    (rd / "broken.md").write_text("no frontmatter at all\n", encoding="utf-8")
    assert read_live_routines(tmp_path) == ""


def test_compose_includes_live_automations(tmp_path):
    (tmp_path / "index.md").write_text("# Master index\n", encoding="utf-8")
    _write_routine(tmp_path / "routines", "daily-digest")
    out = compose_wake_up_context(cwd=tmp_path, wiki_root=tmp_path)
    assert "Live automations" in out
    assert "daily-digest" in out


def test_compose_omits_when_no_routines(tmp_path):
    (tmp_path / "index.md").write_text("# Master index\n", encoding="utf-8")
    out = compose_wake_up_context(cwd=tmp_path, wiki_root=tmp_path)
    assert "Live automations" not in out
