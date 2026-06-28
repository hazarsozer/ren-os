"""
Tests for skills.improve_skill.lib.experiment_log — B1 experiment-log writer.

Pure builders (history → entries → markdown) + append I/O against a tmp path.

Run with:
    python3 -m pytest skills/improve-skill/lib/tests/test_experiment_log.py -v
"""

from __future__ import annotations

from pathlib import Path

from ..experiment_log import (
    append_experiment_log,
    build_experiment_entries,
    render_run_section,
)
from ..types import ExperimentEntry, IterationOutcome, IterationStatus, ProposedChange


def _outcome(iteration, status, score_before, score_after, summary="a change"):
    return IterationOutcome(
        iteration=iteration,
        proposed_change=ProposedChange(
            target_file="skills/x/SKILL.md", unified_diff="", summary=summary, rationale="r"
        ),
        score_before=score_before,
        score_after=score_after,
        status=status,
        commit_sha=None if status is IterationStatus.REVERTED else "abc1234",
        usd_spent=0.1,
        turns_spent=2,
    )


class TestBuildExperimentEntries:
    def test_maps_improved_to_kept(self):
        entries = build_experiment_entries(
            (_outcome(1, IterationStatus.IMPROVED, 0.5, 0.75),), ts="2026-06-28"
        )
        assert entries == (
            ExperimentEntry(
                iteration=1, change="a change", score_before=0.5, score_after=0.75,
                disposition="kept", ts="2026-06-28",
            ),
        )

    def test_maps_neutral_to_kept(self):
        entries = build_experiment_entries(
            (_outcome(2, IterationStatus.NEUTRAL, 0.5, 0.5),), ts="2026-06-28"
        )
        assert entries[0].disposition == "kept"

    def test_maps_reverted_to_reverted(self):
        entries = build_experiment_entries(
            (_outcome(3, IterationStatus.REVERTED, 0.75, 0.6),), ts="2026-06-28"
        )
        assert entries[0].disposition == "reverted"

    def test_change_is_the_proposed_summary(self):
        entries = build_experiment_entries(
            (_outcome(1, IterationStatus.IMPROVED, 0.5, 0.75, summary="tighten the gate prompt"),),
            ts="2026-06-28",
        )
        assert entries[0].change == "tighten the gate prompt"

    def test_ts_injected_on_every_entry(self):
        entries = build_experiment_entries(
            (
                _outcome(1, IterationStatus.IMPROVED, 0.5, 0.75),
                _outcome(2, IterationStatus.REVERTED, 0.75, 0.6),
            ),
            ts="2026-06-28",
        )
        assert [e.ts for e in entries] == ["2026-06-28", "2026-06-28"]

    def test_empty_history_returns_empty(self):
        assert build_experiment_entries((), ts="2026-06-28") == ()


class TestRenderRunSection:
    def _entries(self):
        return build_experiment_entries(
            (
                _outcome(1, IterationStatus.IMPROVED, 0.5, 0.75, "first"),
                _outcome(2, IterationStatus.REVERTED, 0.75, 0.625, "second"),
            ),
            ts="2026-06-28",
        )

    def test_header_has_skill_baseline_final_disposition(self):
        s = render_run_section(
            self._entries(), skill_name="consolidate", baseline=0.5, final=0.75,
            disposition="squash-merged", ts="2026-06-28",
        )
        assert s.startswith("## 2026-06-28 — improve(consolidate):")
        assert "50% → 75%" in s
        assert "squash-merged" in s

    def test_one_bullet_per_entry_in_order(self):
        s = render_run_section(
            self._entries(), skill_name="x", baseline=0.5, final=0.75,
            disposition="kept", ts="2026-06-28",
        )
        bullets = [ln for ln in s.splitlines() if ln.startswith("- iter")]
        assert len(bullets) == 2
        assert "iter 1" in bullets[0] and "[kept]" in bullets[0] and "first" in bullets[0]
        assert "iter 2" in bullets[1] and "[reverted]" in bullets[1] and "second" in bullets[1]

    def test_empty_entries_renders_header_only(self):
        s = render_run_section(
            (), skill_name="x", baseline=0.0, final=0.0, disposition="kept", ts="2026-06-28"
        )
        assert isinstance(s, str)
        assert s.startswith("## 2026-06-28 — improve(x):")
        assert not [ln for ln in s.splitlines() if ln.startswith("- iter")]


class TestAppendExperimentLog:
    def test_first_write_creates_file_with_frontmatter(self, tmp_path: Path):
        path = tmp_path / "projects" / "dry" / "experiment-log.md"
        section = "## 2026-06-28 — improve(x): 50% → 100% (squash-merged)\n\n- iter 1 — [kept] 0.500 → 1.000 — c\n"
        append_experiment_log(path, section)
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "type: experiment-log" in text
        assert "schema_version: 1" in text
        assert "scope: project" in text
        assert section.strip() in text

    def test_second_write_appends_without_duplicating_frontmatter(self, tmp_path: Path):
        path = tmp_path / "projects" / "dry" / "experiment-log.md"
        append_experiment_log(path, "## run A\n\n- iter 1\n")
        append_experiment_log(path, "## run B\n\n- iter 1\n")
        text = path.read_text(encoding="utf-8")
        assert text.count("type: experiment-log") == 1  # frontmatter written once
        assert "## run A" in text and "## run B" in text
        assert text.index("## run A") < text.index("## run B")  # chronological append

    def test_round_trip(self, tmp_path: Path):
        entries = build_experiment_entries(
            (_outcome(1, IterationStatus.IMPROVED, 0.5, 1.0, "the fix"),), ts="2026-06-28"
        )
        section = render_run_section(
            entries, skill_name="recall", baseline=0.5, final=1.0,
            disposition="squash-merged", ts="2026-06-28",
        )
        path = tmp_path / "projects" / "p" / "experiment-log.md"
        append_experiment_log(path, section)
        text = path.read_text(encoding="utf-8")
        assert "improve(recall)" in text
        assert "the fix" in text
        assert "[kept]" in text
