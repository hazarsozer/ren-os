"""Tests for hooks/wake-up/verify/analyze.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


_ANALYZE_PATH = Path(__file__).resolve().parents[1] / "analyze.py"
_spec = importlib.util.spec_from_file_location("analyze", _ANALYZE_PATH)
_analyze = importlib.util.module_from_spec(_spec)
sys.modules["analyze"] = _analyze
_spec.loader.exec_module(_analyze)

ALPHA = _analyze.ALPHA
CACHE_RATIO_FLOOR_TURN_2_PLUS = _analyze.CACHE_RATIO_FLOOR_TURN_2_PLUS
CACHE_CREATION_MEDIAN_LIMIT = _analyze.CACHE_CREATION_MEDIAN_LIMIT
UsageSample = _analyze.UsageSample
Verdict = _analyze.Verdict
load_samples = _analyze.load_samples
evaluate_criteria = _analyze.evaluate_criteria
mann_whitney_u_pvalue = _analyze.mann_whitney_u_pvalue
write_verdict_json = _analyze.write_verdict_json


# ---------------------------------------------------------------------------
# Mann-Whitney U (hand-rolled stdlib implementation)
# ---------------------------------------------------------------------------


class TestMannWhitneyU:
    def test_identical_distributions_high_p(self):
        """Same distributions → high p-value (can't reject null)."""
        a = [1000, 1010, 1005, 998, 1002, 1003, 999, 1001, 1004, 1006]
        b = [1001, 1002, 1003, 1000, 1005, 999, 1004, 998, 1006, 1007]
        p = mann_whitney_u_pvalue(a, b)
        assert p is not None
        assert p > 0.05, f"identical-ish distributions should have p > 0.05; got {p:.4f}"

    def test_clearly_different_distributions_low_p(self):
        """Wildly different distributions → low p-value."""
        a = [100] * 10
        b = [10000] * 10
        p = mann_whitney_u_pvalue(a, b)
        assert p is not None
        assert p < 0.05, f"clearly different distributions should have p < 0.05; got {p:.4f}"

    def test_empty_samples_returns_none(self):
        assert mann_whitney_u_pvalue([], [1, 2, 3]) is None
        assert mann_whitney_u_pvalue([1, 2, 3], []) is None

    def test_tiny_samples_returns_none(self):
        """n < 4 total → cannot evaluate."""
        assert mann_whitney_u_pvalue([1], [2]) is None

    def test_all_identical_values(self):
        """If all values are identical, the test must fail to reject the null
        (high p-value). With the continuity correction +0.5 we don't get
        exactly p=1.0, but we get p well above α=0.05 — which is the
        load-bearing behavior (no false positive on identical data)."""
        a = [100, 100, 100, 100]
        b = [100, 100, 100, 100]
        p = mann_whitney_u_pvalue(a, b)
        assert p is not None
        # Strictly: any p > 0.5 means we're very far from rejecting.
        # In practice, this returns ~0.88 due to the continuity correction.
        assert p > 0.5, f"identical samples should produce high p; got {p:.4f}"


# ---------------------------------------------------------------------------
# Pass-criteria evaluation
# ---------------------------------------------------------------------------


def _make_sample(arm: str, turn: int, *, cache_read: int = 0, cache_creation: int = 0,
                 input_tokens: int = 100, output_tokens: int = 50, idx: int = 1) -> UsageSample:
    return UsageSample(
        session_id=f"{arm}-{idx}",
        arm=arm,
        session_index=idx,
        turn=turn,
        cache_read=cache_read,
        cache_creation=cache_creation,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _good_session(arm: str, idx: int) -> list[UsageSample]:
    """A 'healthy' session: turn 1 = cache creation; turn 2 = mostly cache reads."""
    return [
        _make_sample(arm, turn=1, cache_read=0, cache_creation=8000, input_tokens=50, idx=idx),
        _make_sample(arm, turn=2, cache_read=8000, cache_creation=0, input_tokens=30, idx=idx),
    ]


def _broken_session(arm: str, idx: int) -> list[UsageSample]:
    """A 'broken' session: cache_creation on every turn (cache prefix mismatched)."""
    return [
        _make_sample(arm, turn=1, cache_read=0, cache_creation=8000, input_tokens=50, idx=idx),
        _make_sample(arm, turn=2, cache_read=0, cache_creation=8000, input_tokens=50, idx=idx),
    ]


class TestPassCriteria:
    def test_healthy_dataset_passes_all_criteria(self):
        """Same cache behavior across arms A, B (and arm C absent) → pass criteria 1, 3, 4; trivially pass 2."""
        samples = []
        for arm in ("A", "B"):
            for idx in range(1, 11):
                samples.extend(_good_session(arm, idx))
        verdict = evaluate_criteria(samples)

        assert verdict.criterion_1_a_vs_b_pass
        assert verdict.criterion_2_b_vs_c_pass  # trivially: arm C absent
        assert verdict.criterion_3_cache_ratio_pass
        assert verdict.criterion_4_creation_limit_pass
        assert verdict.overall_pass

    def test_arm_b_cache_broken_fails_criterion_1(self):
        """Arm B is broken (no cache reads); A is healthy → criterion 1 fails."""
        samples = []
        for idx in range(1, 11):
            samples.extend(_good_session("A", idx))
            samples.extend(_broken_session("B", idx))
        verdict = evaluate_criteria(samples)

        # Mann-Whitney U should detect the difference
        assert verdict.mann_whitney_u_p_value_a_vs_b is not None
        assert verdict.mann_whitney_u_p_value_a_vs_b < ALPHA, (
            f"broken B should have p < {ALPHA}; got {verdict.mann_whitney_u_p_value_a_vs_b}"
        )
        assert not verdict.criterion_1_a_vs_b_pass
        # Criterion 3 should also fail (B's ratio at turn 2 is 0)
        assert not verdict.criterion_3_cache_ratio_pass
        assert not verdict.overall_pass

    def test_arm_b_creation_explosion_fails_criterion_4(self):
        """Arm B creation tokens vastly exceed A → criterion 4 fails."""
        samples = []
        for idx in range(1, 11):
            # Arm A: moderate creation
            samples.append(_make_sample("A", turn=1, cache_read=0, cache_creation=1000, idx=idx))
            samples.append(_make_sample("A", turn=2, cache_read=1000, cache_creation=0, idx=idx))
            # Arm B: explosion of creation tokens on every turn
            samples.append(_make_sample("B", turn=1, cache_read=0, cache_creation=10000, idx=idx))
            samples.append(_make_sample("B", turn=2, cache_read=1000, cache_creation=10000, idx=idx))
        verdict = evaluate_criteria(samples)

        assert not verdict.criterion_4_creation_limit_pass

    def test_no_samples_returns_failed_verdict(self):
        verdict = evaluate_criteria([])
        assert not verdict.overall_pass
        assert "No samples" in verdict.notes[0]

    def test_only_arm_a_b_with_no_c_trivially_passes_c_criterion(self):
        """Per plan §2.3: arm C is conditional; if not run, criterion 2 trivially passes."""
        samples = []
        for arm in ("A", "B"):
            for idx in range(1, 11):
                samples.extend(_good_session(arm, idx))
        verdict = evaluate_criteria(samples)
        assert verdict.criterion_2_b_vs_c_pass
        assert any("Arm C not run" in n for n in verdict.notes)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


class TestLoadSamples:
    def test_loads_canonical_csv(self, tmp_path: Path):
        path = tmp_path / "samples.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "session_id", "arm", "session_index", "timestamp", "turn",
                "model", "cache_read", "cache_creation", "input_tokens", "output_tokens",
            ])
            writer.writerow(["A-1-t", "A", "1", "t", "1", "x", "0", "800", "50", "30"])
            writer.writerow(["A-1-t", "A", "1", "t", "2", "x", "800", "0", "20", "30"])

        samples = load_samples(path)
        assert len(samples) == 2
        assert samples[0].arm == "A"
        assert samples[0].turn == 1
        assert samples[0].cache_creation == 800
        assert samples[1].turn == 2
        assert samples[1].cache_read == 800


# ---------------------------------------------------------------------------
# Verdict JSON serialization
# ---------------------------------------------------------------------------


class TestWriteVerdictJson:
    def test_round_trip(self, tmp_path: Path):
        verdict = Verdict(
            overall_pass=True,
            criterion_1_a_vs_b_pass=True,
            criterion_2_b_vs_c_pass=True,
            criterion_3_cache_ratio_pass=True,
            criterion_4_creation_limit_pass=True,
            n_sessions_by_arm={"A": 10, "B": 10},
            median_cache_read_turn2_by_arm={"A": 8000.0, "B": 8000.0},
            median_cache_ratio_turn2_by_arm={"A": 0.95, "B": 0.95},
            median_cache_creation_by_arm={"A": 4000.0, "B": 4000.0},
            mann_whitney_u_p_value_a_vs_b=0.5,
            mann_whitney_u_p_value_b_vs_c=None,
        )
        path = tmp_path / "verdict.json"
        write_verdict_json(verdict, path)

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["overall_pass"] is True
        assert loaded["criterion_1_a_vs_b_pass"] is True
        assert loaded["mann_whitney_u_p_value_a_vs_b"] == 0.5
        assert loaded["n_sessions_by_arm"]["A"] == 10


# ---------------------------------------------------------------------------
# Thresholds pinned
# ---------------------------------------------------------------------------


class TestThresholdConstants:
    def test_alpha_pinned(self):
        """Pin: significance threshold is α=0.05 per plan §2.3."""
        assert ALPHA == 0.05

    def test_cache_ratio_floor_pinned(self):
        """Pin: cache_read/total_input > 0.7 from turn 2+ per plan §2.3."""
        assert CACHE_RATIO_FLOOR_TURN_2_PLUS == 0.7

    def test_creation_limit_pinned(self):
        """Pin: B/C creation median ≤ 1.5× A creation median (50% leeway)."""
        assert CACHE_CREATION_MEDIAN_LIMIT == 1.5
