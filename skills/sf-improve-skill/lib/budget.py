"""
sf-improve-skill shadow-budget tracking.

Pure math for:
  - Computing USD spent from an ApiUsage snapshot
  - Advancing a BudgetState across an iteration
  - Pre-iteration check (continue / stop with reason)

Used when CC's `--max-budget-usd` is unavailable (non-print contexts). Inner
sub-runs use print mode and inherit CC's native cap; the OUTER loop uses this
module to track cumulative spend across all sub-runs.

Per references/budget-tracking.md + references/cc-flag-watch.md. When CC ships
cross-mode `--max-budget-usd`, we can drop the shadow (or keep as belt-and-
suspenders — TBD).

Frozen dataclasses + type annotations per dotfiles python/coding-style.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .types import ApiUsage, BudgetState


# Resolved at import time. The pricing table is shipped with the skill.
_PRICING_FILE: Final[Path] = (
    Path(__file__).parent.parent / "references" / "model-pricing.json"
)

# Below this remaining USD, no inner sub-run can produce meaningful output.
# (One change-proposal sub-run typically costs $0.03-$0.50.)
MIN_VIABLE_REMAINING_USD: Final[float] = 0.05


@dataclass(frozen=True)
class PricingTable:
    """Loaded snapshot of model-pricing.json."""

    valid_as_of: str
    default_model: str
    # canonical_id → {"input": float, "output": float, "cache_read": float, "cache_creation": float}
    pricing: dict[str, dict[str, float]]
    # alias → canonical_id
    aliases: dict[str, str]

    def resolve_model(self, model: str) -> str:
        """Return canonical model ID; falls back to default if unknown."""
        if model in self.pricing:
            return model
        if model in self.aliases:
            return self.aliases[model]
        return self.default_model


@dataclass(frozen=True)
class PreIterationDecision:
    """Result of a pre-iteration budget gate check."""

    should_continue: bool
    stop_reason: str | None  # one of "max_budget_reached", "max_turns_shadow_reached", or None
    remaining_usd: float


def load_pricing_table(path: Path | None = None) -> PricingTable:
    """
    Load the model-pricing.json table.

    Args:
        path: Override the path (for tests). Default: shipped references/model-pricing.json.

    Returns:
        PricingTable.

    Raises:
        FileNotFoundError: if the file is missing.
        ValueError: if the file is structurally invalid.
    """
    actual_path = path or _PRICING_FILE
    with actual_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    pricing = data.get("pricing_usd_per_million_tokens")
    if not isinstance(pricing, dict) or not pricing:
        raise ValueError(f"{actual_path}: 'pricing_usd_per_million_tokens' must be a non-empty object")

    default_model = data.get("default_model")
    if default_model not in pricing:
        raise ValueError(
            f"{actual_path}: 'default_model' {default_model!r} not present in pricing table"
        )

    aliases = data.get("alias_resolution", {})
    if not isinstance(aliases, dict):
        raise ValueError(f"{actual_path}: 'alias_resolution' must be an object")
    # Strip metadata keys (anything starting with underscore)
    aliases = {k: v for k, v in aliases.items() if not k.startswith("_")}

    return PricingTable(
        valid_as_of=str(data.get("valid_as_of", "")),
        default_model=default_model,
        pricing=pricing,
        aliases=aliases,
    )


def compute_usage_cost_usd(usage: ApiUsage, model: str, table: PricingTable) -> float:
    """
    Compute the dollar cost of a single API call given its usage + model.

    Args:
        usage: ApiUsage from a single Anthropic API response.
        model: Model name (canonical ID or known alias).
        table: Loaded PricingTable.

    Returns:
        Cost in USD (always non-negative).
    """
    canonical = table.resolve_model(model)
    rates = table.pricing[canonical]

    cost = (
        usage.input_tokens * rates["input"]
        + usage.output_tokens * rates["output"]
        + usage.cache_read_input_tokens * rates.get("cache_read", 0.0)
        + usage.cache_creation_input_tokens * rates.get("cache_creation", 0.0)
    ) / 1_000_000.0

    return max(cost, 0.0)


def advance_budget(
    state: BudgetState,
    usage: ApiUsage,
    model: str,
    table: PricingTable,
    *,
    turns_used: int = 1,
) -> BudgetState:
    """
    Return a new BudgetState reflecting one iteration's API spend.

    Args:
        state: Current budget state.
        usage: ApiUsage from the iteration's inner sub-run(s) — summed if multiple.
        model: Model used.
        table: Loaded PricingTable.
        turns_used: How many turns this iteration consumed (default 1; rare to be >1).

    Returns:
        New BudgetState (frozen; old state is unchanged).
    """
    cost = compute_usage_cost_usd(usage, model, table)
    return BudgetState(
        max_budget_usd=state.max_budget_usd,
        shadow_usd=state.shadow_usd + cost,
        max_turns_shadow=state.max_turns_shadow,
        shadow_turns=state.shadow_turns + turns_used,
    )


def pre_iteration_check(state: BudgetState) -> PreIterationDecision:
    """
    Decide whether to start another iteration given the current budget state.

    Order of checks:
      1. USD-cap (cumulative shadow ≥ cap, or remaining < MIN_VIABLE_REMAINING_USD)
      2. Turn-cap (if max_turns_shadow set)

    Args:
        state: Current budget state.

    Returns:
        PreIterationDecision with should_continue + optional stop_reason.
    """
    remaining = state.remaining_usd

    if remaining < MIN_VIABLE_REMAINING_USD:
        return PreIterationDecision(
            should_continue=False,
            stop_reason="max_budget_reached",
            remaining_usd=remaining,
        )

    if state.max_turns_shadow is not None and state.shadow_turns >= state.max_turns_shadow:
        return PreIterationDecision(
            should_continue=False,
            stop_reason="max_turns_shadow_reached",
            remaining_usd=remaining,
        )

    return PreIterationDecision(
        should_continue=True,
        stop_reason=None,
        remaining_usd=remaining,
    )


def estimate_iterations_remaining(state: BudgetState, mean_usd_per_iter: float) -> int:
    """
    Crude projection for the user-facing "estimated iterations remaining" line.

    Args:
        state: Current budget state.
        mean_usd_per_iter: Mean USD-per-iter so far (caller computes from history).

    Returns:
        Approximate count of additional iterations the budget can support.
        Returns 0 if mean_usd_per_iter is non-positive (no data yet).
    """
    if mean_usd_per_iter <= 0:
        return 0
    return max(int(state.remaining_usd // mean_usd_per_iter), 0)
