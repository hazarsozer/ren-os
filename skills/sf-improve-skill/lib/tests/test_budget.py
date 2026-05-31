"""
Tests for skills.sf_improve_skill.lib.budget.

Pure-math coverage. Real model-pricing.json loaded as the default fixture;
custom tables built ad-hoc for edge-case tests.

Per dotfiles python/testing.md (pytest framework). Run with:
    python3 -m pytest skills/sf-improve-skill/lib/tests/ -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..budget import (
    MIN_VIABLE_REMAINING_USD,
    PricingTable,
    advance_budget,
    compute_usage_cost_usd,
    estimate_iterations_remaining,
    load_pricing_table,
    pre_iteration_check,
)
from ..types import ApiUsage, BudgetState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_pricing_table() -> PricingTable:
    """Load the actual shipped model-pricing.json from the skill."""
    return load_pricing_table()


@pytest.fixture
def tiny_pricing_file(tmp_path: Path) -> Path:
    """A minimal valid pricing JSON for parametric tests."""
    data = {
        "version": "test",
        "valid_as_of": "2026-01-01",
        "pricing_usd_per_million_tokens": {
            "test-model": {
                "input": 1.00,
                "output": 2.00,
                "cache_read": 0.10,
                "cache_creation": 1.50,
            }
        },
        "default_model": "test-model",
        "alias_resolution": {
            "_comment": "test aliases",
            "tm": "test-model",
        },
    }
    path = tmp_path / "test-pricing.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def tiny_table(tiny_pricing_file: Path) -> PricingTable:
    return load_pricing_table(tiny_pricing_file)


# ---------------------------------------------------------------------------
# load_pricing_table
# ---------------------------------------------------------------------------


class TestLoadPricingTable:
    def test_real_table_loads(self, real_pricing_table: PricingTable):
        assert real_pricing_table.default_model
        assert real_pricing_table.default_model in real_pricing_table.pricing
        assert real_pricing_table.valid_as_of  # non-empty string

    def test_real_table_has_required_rates(self, real_pricing_table: PricingTable):
        for model_id, rates in real_pricing_table.pricing.items():
            for field in ("input", "output", "cache_read", "cache_creation"):
                assert field in rates, f"{model_id} missing rate {field!r}"
                assert isinstance(rates[field], (int, float))
                assert rates[field] >= 0

    def test_real_table_aliases_resolve(self, real_pricing_table: PricingTable):
        # The shipped table maps "sonnet"/"opus"/"haiku" aliases. Validate they resolve.
        for alias in ("sonnet", "opus", "haiku"):
            if alias in real_pricing_table.aliases:
                resolved = real_pricing_table.resolve_model(alias)
                assert resolved in real_pricing_table.pricing

    def test_unknown_model_falls_back_to_default(self, real_pricing_table: PricingTable):
        resolved = real_pricing_table.resolve_model("totally-fake-model-2099")
        assert resolved == real_pricing_table.default_model

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_pricing_table(tmp_path / "nope.json")

    def test_invalid_json_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_pricing_table(path)

    def test_missing_pricing_section_rejected(self, tmp_path: Path):
        path = tmp_path / "no-pricing.json"
        path.write_text(json.dumps({"default_model": "x"}), encoding="utf-8")
        with pytest.raises(ValueError, match="pricing_usd_per_million_tokens"):
            load_pricing_table(path)

    def test_default_not_in_pricing_rejected(self, tmp_path: Path):
        path = tmp_path / "dangling-default.json"
        path.write_text(
            json.dumps(
                {
                    "pricing_usd_per_million_tokens": {"some-model": {"input": 1}},
                    "default_model": "different-model",
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="default_model"):
            load_pricing_table(path)

    def test_aliases_strip_underscore_keys(self, tiny_table: PricingTable):
        assert "tm" in tiny_table.aliases
        assert "_comment" not in tiny_table.aliases


# ---------------------------------------------------------------------------
# compute_usage_cost_usd
# ---------------------------------------------------------------------------


class TestComputeUsageCost:
    def test_zero_usage_zero_cost(self, tiny_table: PricingTable):
        usage = ApiUsage(input_tokens=0, output_tokens=0)
        assert compute_usage_cost_usd(usage, "test-model", tiny_table) == 0.0

    def test_input_only_cost(self, tiny_table: PricingTable):
        # 1M input tokens × $1.00 = $1.00
        usage = ApiUsage(input_tokens=1_000_000, output_tokens=0)
        cost = compute_usage_cost_usd(usage, "test-model", tiny_table)
        assert cost == pytest.approx(1.00)

    def test_output_only_cost(self, tiny_table: PricingTable):
        # 1M output tokens × $2.00 = $2.00
        usage = ApiUsage(input_tokens=0, output_tokens=1_000_000)
        cost = compute_usage_cost_usd(usage, "test-model", tiny_table)
        assert cost == pytest.approx(2.00)

    def test_all_four_token_kinds(self, tiny_table: PricingTable):
        # 100k in + 50k out + 100k cache_read + 100k cache_create
        # = 100k×$1 + 50k×$2 + 100k×$0.10 + 100k×$1.50 = $0.10+$0.10+$0.01+$0.15 = $0.36
        usage = ApiUsage(
            input_tokens=100_000,
            output_tokens=50_000,
            cache_read_input_tokens=100_000,
            cache_creation_input_tokens=100_000,
        )
        cost = compute_usage_cost_usd(usage, "test-model", tiny_table)
        assert cost == pytest.approx(0.36)

    def test_unknown_model_uses_default(self, tiny_table: PricingTable):
        usage = ApiUsage(input_tokens=1_000_000, output_tokens=0)
        cost = compute_usage_cost_usd(usage, "fake-model", tiny_table)
        # Falls back to test-model (the default in tiny_table)
        assert cost == pytest.approx(1.00)

    def test_alias_resolves(self, tiny_table: PricingTable):
        usage = ApiUsage(input_tokens=1_000_000, output_tokens=0)
        cost_alias = compute_usage_cost_usd(usage, "tm", tiny_table)
        cost_canonical = compute_usage_cost_usd(usage, "test-model", tiny_table)
        assert cost_alias == cost_canonical

    def test_realistic_sonnet_call(self, real_pricing_table: PricingTable):
        # Sanity: a moderate sub-run shouldn't break the bank.
        # 5k input + 2k output ≈ Claude Sonnet pricing → well under $0.10
        if "claude-sonnet-4-6" not in real_pricing_table.pricing:
            pytest.skip("sonnet not in shipped pricing table")
        usage = ApiUsage(input_tokens=5000, output_tokens=2000)
        cost = compute_usage_cost_usd(usage, "claude-sonnet-4-6", real_pricing_table)
        assert 0 < cost < 0.10


# ---------------------------------------------------------------------------
# advance_budget
# ---------------------------------------------------------------------------


class TestAdvanceBudget:
    def test_advance_immutability(self, tiny_table: PricingTable):
        initial = BudgetState(max_budget_usd=10.00, shadow_usd=0.0)
        usage = ApiUsage(input_tokens=1_000_000, output_tokens=0)
        new_state = advance_budget(initial, usage, "test-model", tiny_table)

        # Original is unchanged
        assert initial.shadow_usd == 0.0
        # New state reflects the spend
        assert new_state.shadow_usd == pytest.approx(1.00)
        assert new_state.max_budget_usd == 10.00  # unchanged

    def test_advance_accumulates(self, tiny_table: PricingTable):
        s0 = BudgetState(max_budget_usd=10.00)
        usage = ApiUsage(input_tokens=500_000, output_tokens=0)  # $0.50

        s1 = advance_budget(s0, usage, "test-model", tiny_table)
        s2 = advance_budget(s1, usage, "test-model", tiny_table)

        assert s2.shadow_usd == pytest.approx(1.00)
        assert s2.shadow_turns == 2

    def test_turns_tracked(self, tiny_table: PricingTable):
        s0 = BudgetState(max_budget_usd=10.00, max_turns_shadow=5)
        usage = ApiUsage(input_tokens=100, output_tokens=100)

        s1 = advance_budget(s0, usage, "test-model", tiny_table, turns_used=2)
        assert s1.shadow_turns == 2
        assert s1.max_turns_shadow == 5  # preserved

    def test_remaining_usd_property(self):
        state = BudgetState(max_budget_usd=10.00, shadow_usd=3.50)
        assert state.remaining_usd == pytest.approx(6.50)

    def test_remaining_clamps_at_zero(self):
        state = BudgetState(max_budget_usd=5.00, shadow_usd=8.00)
        assert state.remaining_usd == 0.0  # not negative


# ---------------------------------------------------------------------------
# pre_iteration_check
# ---------------------------------------------------------------------------


class TestPreIterationCheck:
    def test_fresh_state_continues(self):
        state = BudgetState(max_budget_usd=10.00)
        decision = pre_iteration_check(state)
        assert decision.should_continue
        assert decision.stop_reason is None
        assert decision.remaining_usd == 10.00

    def test_near_exhaustion_continues_if_above_threshold(self):
        # Just above the MIN_VIABLE_REMAINING_USD threshold
        state = BudgetState(max_budget_usd=10.00, shadow_usd=10.00 - MIN_VIABLE_REMAINING_USD - 0.01)
        decision = pre_iteration_check(state)
        assert decision.should_continue

    def test_below_threshold_stops_budget(self):
        # Below MIN_VIABLE_REMAINING_USD: we'd have no budget for a meaningful sub-run
        state = BudgetState(max_budget_usd=10.00, shadow_usd=10.00 - 0.01)
        decision = pre_iteration_check(state)
        assert not decision.should_continue
        assert decision.stop_reason == "max_budget_reached"

    def test_exact_zero_remaining_stops(self):
        state = BudgetState(max_budget_usd=5.00, shadow_usd=5.00)
        decision = pre_iteration_check(state)
        assert not decision.should_continue
        assert decision.stop_reason == "max_budget_reached"

    def test_turn_cap_stops(self):
        state = BudgetState(
            max_budget_usd=100.00, max_turns_shadow=3, shadow_turns=3
        )
        decision = pre_iteration_check(state)
        assert not decision.should_continue
        assert decision.stop_reason == "max_turns_shadow_reached"

    def test_turn_cap_under_limit_continues(self):
        state = BudgetState(
            max_budget_usd=100.00, max_turns_shadow=3, shadow_turns=2
        )
        decision = pre_iteration_check(state)
        assert decision.should_continue

    def test_budget_takes_precedence_over_turns(self):
        # Both caps hit; budget should be the reason since it's checked first
        state = BudgetState(
            max_budget_usd=1.00,
            shadow_usd=1.00,
            max_turns_shadow=5,
            shadow_turns=5,
        )
        decision = pre_iteration_check(state)
        assert not decision.should_continue
        assert decision.stop_reason == "max_budget_reached"

    def test_no_turn_cap_set_doesnt_block(self):
        state = BudgetState(
            max_budget_usd=10.00, shadow_usd=0.50,
            max_turns_shadow=None, shadow_turns=9999,
        )
        decision = pre_iteration_check(state)
        assert decision.should_continue


# ---------------------------------------------------------------------------
# estimate_iterations_remaining
# ---------------------------------------------------------------------------


class TestEstimateIterations:
    def test_basic(self):
        state = BudgetState(max_budget_usd=10.00, shadow_usd=2.00)
        # $8 remaining at $0.50/iter → 16 iter
        assert estimate_iterations_remaining(state, mean_usd_per_iter=0.50) == 16

    def test_zero_mean_returns_zero(self):
        state = BudgetState(max_budget_usd=10.00, shadow_usd=2.00)
        assert estimate_iterations_remaining(state, mean_usd_per_iter=0.0) == 0

    def test_negative_mean_returns_zero(self):
        state = BudgetState(max_budget_usd=10.00, shadow_usd=2.00)
        assert estimate_iterations_remaining(state, mean_usd_per_iter=-1.0) == 0

    def test_exhausted_budget_returns_zero(self):
        state = BudgetState(max_budget_usd=5.00, shadow_usd=5.00)
        assert estimate_iterations_remaining(state, mean_usd_per_iter=0.10) == 0


# ---------------------------------------------------------------------------
# compute_usage_cost_usd — missing cache keys
# ---------------------------------------------------------------------------


class TestComputeUsageCostMissingCacheKeys:
    def test_missing_cache_rates_no_keyerror(self, tmp_path):
        """A pricing entry that omits cache_read/cache_creation must not crash;
        the missing cache rates contribute $0 rather than raising KeyError."""
        data = {
            "valid_as_of": "2026-01-01",
            "pricing_usd_per_million_tokens": {"m": {"input": 1.0, "output": 2.0}},
            "default_model": "m",
            "alias_resolution": {},
        }
        path = tmp_path / "partial-pricing.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        table = load_pricing_table(path)
        usage = ApiUsage(
            input_tokens=1_000_000,
            output_tokens=0,
            cache_read_input_tokens=500_000,
            cache_creation_input_tokens=500_000,
        )
        cost = compute_usage_cost_usd(usage, "m", table)
        # 1M input × $1 = $1; both missing cache rates default to $0, so the
        # 500k cache_read + 500k cache_creation tokens contribute nothing.
        assert cost == pytest.approx(1.0)
