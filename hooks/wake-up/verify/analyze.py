"""
analyze.py — Statistical verdict on the cache-preservation experiment.

Per the ADR-008 cache-preservation verification plan (lifecycle plan §2):
loads the CSV emitted by collect.py and applies the four pass criteria.

Pass criteria (ALL must hold to declare ADR-008 verified):
  1. Arm A vs Arm B: cache_read_input_tokens at turn 2+ are statistically
     indistinguishable (Mann-Whitney U, α=0.05). Hook presence != cache breakage.
  2. Arm C vs Arm B: same (variable content doesn't break the prefix).
  3. Across all arms: cache_read / total_input ratio > 0.7 from session 2
     onward (warm-prefix benefit is REAL, not silently destroyed).
  4. No session in B or C shows cache_creation_input_tokens >> A on a warm-
     cache hit (operationalized as: B/C median is not >50% above A median).

Outputs:
  - Console summary
  - JSON verdict file (machine-readable; e.g., for CI gating)
  - REPORT.md draft sections (the experiment writeup template; analyst fills
    in the narrative + signs)

Usage:
    python3 analyze.py INPUT_CSV [--report-md PATH] [--verdict-json PATH] [-v]

Dependencies: stdlib only (we use Python's `statistics` module + a hand-rolled
Mann-Whitney U for portability — no scipy required).
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path

logger = logging.getLogger(__name__)


# Pass criteria thresholds (per lifecycle plan §2.3)
ALPHA: float = 0.05                         # significance threshold for Mann-Whitney U
CACHE_RATIO_FLOOR_TURN_2_PLUS: float = 0.7  # cache_read / total_input must exceed this from turn 2 onward
CACHE_CREATION_MEDIAN_LIMIT: float = 1.5    # B/C median creation tokens must NOT exceed A by >50%


@dataclass(frozen=True)
class UsageSample:
    """One row of the input CSV."""

    session_id: str
    arm: str
    session_index: int
    turn: int
    cache_read: int
    cache_creation: int
    input_tokens: int
    output_tokens: int


@dataclass
class Verdict:
    """The structured verdict object emitted to JSON."""

    overall_pass: bool = False
    criterion_1_a_vs_b_pass: bool = False
    criterion_2_b_vs_c_pass: bool = False
    criterion_3_cache_ratio_pass: bool = False
    criterion_4_creation_limit_pass: bool = False
    # Diagnostic stats
    n_sessions_by_arm: dict[str, int] = field(default_factory=dict)
    median_cache_read_turn2_by_arm: dict[str, float] = field(default_factory=dict)
    median_cache_ratio_turn2_by_arm: dict[str, float] = field(default_factory=dict)
    median_cache_creation_by_arm: dict[str, float] = field(default_factory=dict)
    mann_whitney_u_p_value_a_vs_b: float | None = None
    mann_whitney_u_p_value_b_vs_c: float | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


def load_samples(csv_path: Path) -> list[UsageSample]:
    """Load the CSV emitted by collect.py."""
    samples: list[UsageSample] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            samples.append(
                UsageSample(
                    session_id=row["session_id"],
                    arm=row["arm"],
                    session_index=int(row["session_index"]),
                    turn=int(row["turn"]),
                    cache_read=int(row["cache_read"]),
                    cache_creation=int(row["cache_creation"]),
                    input_tokens=int(row["input_tokens"]),
                    output_tokens=int(row["output_tokens"]),
                )
            )
    return samples


# ---------------------------------------------------------------------------
# Mann-Whitney U (hand-rolled; stdlib only)
# ---------------------------------------------------------------------------


def _rank(values: list[float]) -> list[float]:
    """Return ranks of values, averaging ties (the rank-sum convention)."""
    sorted_pairs = sorted(enumerate(values), key=lambda p: p[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(sorted_pairs):
        j = i
        while j + 1 < len(sorted_pairs) and sorted_pairs[j + 1][1] == sorted_pairs[i][1]:
            j += 1
        # average rank for the tied group (1-indexed)
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[sorted_pairs[k][0]] = avg_rank
        i = j + 1
    return ranks


def mann_whitney_u_pvalue(sample_a: list[float], sample_b: list[float]) -> float | None:
    """
    Compute a Mann-Whitney U two-sided p-value via the normal approximation.

    Returns None if either sample is empty or both samples are size 1.
    For accurate p-values with n<8, scipy is recommended; this normal
    approximation is acceptable for our n=10 per arm design.

    Returns:
        Two-sided p-value approximation.
    """
    n1, n2 = len(sample_a), len(sample_b)
    if n1 == 0 or n2 == 0:
        return None
    if n1 + n2 < 4:
        return None

    combined = sample_a + sample_b
    ranks = _rank(combined)
    rank_sum_a = sum(ranks[:n1])

    u1 = rank_sum_a - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    mean_u = n1 * n2 / 2
    sd_u = ((n1 * n2 * (n1 + n2 + 1)) / 12) ** 0.5
    if sd_u == 0:
        return 1.0  # all values identical → no evidence of difference

    # Normal approximation with continuity correction
    z = (u - mean_u + 0.5) / sd_u

    # Two-sided p-value via the standard normal survival function
    from math import erfc, sqrt
    p_two_sided = erfc(abs(z) / sqrt(2))
    return min(max(p_two_sided, 0.0), 1.0)


# ---------------------------------------------------------------------------
# Pass-criteria evaluation
# ---------------------------------------------------------------------------


def evaluate_criteria(samples: list[UsageSample]) -> Verdict:
    """Apply the 4 pass criteria; build the structured Verdict."""
    verdict = Verdict()

    if not samples:
        verdict.notes.append("No samples loaded; cannot evaluate.")
        return verdict

    # Group samples by arm
    by_arm: dict[str, list[UsageSample]] = {"A": [], "B": [], "C": []}
    for s in samples:
        if s.arm in by_arm:
            by_arm[s.arm].append(s)

    verdict.n_sessions_by_arm = {arm: len(by_arm[arm]) for arm in ("A", "B", "C")}

    # Extract turn-2 cache_read distributions per arm (cache benefit shows turn 2+)
    turn2_cache_read_by_arm: dict[str, list[float]] = {}
    turn2_cache_ratio_by_arm: dict[str, list[float]] = {}
    creation_by_arm: dict[str, list[float]] = {}

    for arm, arm_samples in by_arm.items():
        turn2 = [s for s in arm_samples if s.turn >= 2]
        turn2_cache_read_by_arm[arm] = [float(s.cache_read) for s in turn2]
        ratios = []
        for s in turn2:
            total = s.input_tokens + s.cache_read + s.cache_creation
            if total > 0:
                ratios.append(s.cache_read / total)
        turn2_cache_ratio_by_arm[arm] = ratios
        creation_by_arm[arm] = [float(s.cache_creation) for s in arm_samples]

    # Medians for the verdict's diagnostic fields
    for arm in ("A", "B", "C"):
        if turn2_cache_read_by_arm[arm]:
            verdict.median_cache_read_turn2_by_arm[arm] = statistics.median(
                turn2_cache_read_by_arm[arm]
            )
        if turn2_cache_ratio_by_arm[arm]:
            verdict.median_cache_ratio_turn2_by_arm[arm] = statistics.median(
                turn2_cache_ratio_by_arm[arm]
            )
        if creation_by_arm[arm]:
            verdict.median_cache_creation_by_arm[arm] = statistics.median(creation_by_arm[arm])

    # --- Criterion 1: A vs B Mann-Whitney U ---
    if turn2_cache_read_by_arm["A"] and turn2_cache_read_by_arm["B"]:
        p_ab = mann_whitney_u_pvalue(
            turn2_cache_read_by_arm["A"], turn2_cache_read_by_arm["B"]
        )
        verdict.mann_whitney_u_p_value_a_vs_b = p_ab
        verdict.criterion_1_a_vs_b_pass = (p_ab is not None) and (p_ab > ALPHA)
    else:
        verdict.notes.append("Missing arm A or B samples; criterion 1 not evaluated.")

    # --- Criterion 2: B vs C Mann-Whitney U ---
    if turn2_cache_read_by_arm["B"] and turn2_cache_read_by_arm["C"]:
        p_bc = mann_whitney_u_pvalue(
            turn2_cache_read_by_arm["B"], turn2_cache_read_by_arm["C"]
        )
        verdict.mann_whitney_u_p_value_b_vs_c = p_bc
        verdict.criterion_2_b_vs_c_pass = (p_bc is not None) and (p_bc > ALPHA)
    elif not turn2_cache_read_by_arm["C"]:
        # Arm C is conditional per plan §2.3 (only run if A+B pass)
        verdict.notes.append("Arm C not run; criterion 2 trivially passes if criteria 1+3+4 hold.")
        verdict.criterion_2_b_vs_c_pass = True
    else:
        verdict.notes.append("Missing arm B samples; criterion 2 not evaluated.")

    # --- Criterion 3: cache ratio > 0.7 across all arms ---
    all_arms_ratio_ok = True
    for arm in ("A", "B", "C"):
        ratios = turn2_cache_ratio_by_arm[arm]
        if ratios:
            median_ratio = statistics.median(ratios)
            if median_ratio < CACHE_RATIO_FLOOR_TURN_2_PLUS:
                all_arms_ratio_ok = False
                verdict.notes.append(
                    f"Arm {arm} median cache ratio at turn 2+ = {median_ratio:.2f} "
                    f"< {CACHE_RATIO_FLOOR_TURN_2_PLUS} (criterion 3 FAIL)"
                )
        elif arm in ("A", "B"):
            all_arms_ratio_ok = False
            verdict.notes.append(f"Arm {arm} has no turn-2 ratio data; criterion 3 cannot pass.")
    verdict.criterion_3_cache_ratio_pass = all_arms_ratio_ok

    # --- Criterion 4: B/C creation median ≤ 1.5 × A creation median ---
    if creation_by_arm["A"]:
        a_creation = statistics.median(creation_by_arm["A"])
        creation_ok = True
        for arm in ("B", "C"):
            if creation_by_arm[arm]:
                arm_creation = statistics.median(creation_by_arm[arm])
                # If A's creation is zero, "ratio" is meaningless; require B/C also small.
                if a_creation == 0:
                    if arm_creation > 100:  # heuristic: small absolute count
                        creation_ok = False
                        verdict.notes.append(
                            f"Arm A median creation tokens = 0; arm {arm} = {arm_creation:.0f} "
                            f"(criterion 4 FAIL)"
                        )
                elif arm_creation > a_creation * CACHE_CREATION_MEDIAN_LIMIT:
                    creation_ok = False
                    verdict.notes.append(
                        f"Arm {arm} median creation tokens = {arm_creation:.0f} > "
                        f"{CACHE_CREATION_MEDIAN_LIMIT}× arm A ({a_creation:.0f}) (criterion 4 FAIL)"
                    )
        verdict.criterion_4_creation_limit_pass = creation_ok
    else:
        verdict.notes.append("Arm A samples missing; criterion 4 not evaluated.")

    # --- Overall pass: all 4 criteria ---
    verdict.overall_pass = (
        verdict.criterion_1_a_vs_b_pass
        and verdict.criterion_2_b_vs_c_pass
        and verdict.criterion_3_cache_ratio_pass
        and verdict.criterion_4_creation_limit_pass
    )

    return verdict


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def render_verdict_summary(verdict: Verdict) -> str:
    """One-screen summary for the console + a draft REPORT.md section."""
    lines: list[str] = []
    overall = "✅ PASS" if verdict.overall_pass else "❌ FAIL"
    lines.append(f"## Cache-preservation verdict — {overall}")
    lines.append("")
    lines.append("### Criteria")
    lines.append(f"- (1) A vs B (Mann-Whitney U on turn-2+ cache_read): {_pass_emoji(verdict.criterion_1_a_vs_b_pass)} "
                 f"(p = {_fmt_p(verdict.mann_whitney_u_p_value_a_vs_b)})")
    lines.append(f"- (2) B vs C (Mann-Whitney U on turn-2+ cache_read): {_pass_emoji(verdict.criterion_2_b_vs_c_pass)} "
                 f"(p = {_fmt_p(verdict.mann_whitney_u_p_value_b_vs_c)})")
    lines.append(f"- (3) cache_read / total_input > {CACHE_RATIO_FLOOR_TURN_2_PLUS} from turn 2 onward: "
                 f"{_pass_emoji(verdict.criterion_3_cache_ratio_pass)}")
    lines.append(f"- (4) B/C creation tokens ≤ {CACHE_CREATION_MEDIAN_LIMIT}× A: "
                 f"{_pass_emoji(verdict.criterion_4_creation_limit_pass)}")
    lines.append("")
    lines.append("### Stats by arm")
    for arm in ("A", "B", "C"):
        n = verdict.n_sessions_by_arm.get(arm, 0)
        if n == 0:
            continue
        cache_read = verdict.median_cache_read_turn2_by_arm.get(arm)
        cache_ratio = verdict.median_cache_ratio_turn2_by_arm.get(arm)
        creation = verdict.median_cache_creation_by_arm.get(arm)
        lines.append(
            f"- Arm {arm}: n={n}, median cache_read@turn2={_fmt_n(cache_read)}, "
            f"median ratio={_fmt_f(cache_ratio)}, median creation={_fmt_n(creation)}"
        )
    if verdict.notes:
        lines.append("")
        lines.append("### Notes")
        for note in verdict.notes:
            lines.append(f"- {note}")
    return "\n".join(lines)


def _pass_emoji(passed: bool) -> str:
    return "✅" if passed else "❌"


def _fmt_p(p: float | None) -> str:
    return "—" if p is None else f"{p:.4f}"


def _fmt_n(v: float | None) -> str:
    return "—" if v is None else f"{int(v):,}"


def _fmt_f(v: float | None) -> str:
    return "—" if v is None else f"{v:.3f}"


def write_verdict_json(verdict: Verdict, path: Path) -> None:
    """Serialize the verdict to a structured JSON file for CI gating."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(verdict), fh, indent=2, sort_keys=True)


def write_report_section(verdict: Verdict, path: Path) -> None:
    """Write a draft REPORT.md section (analyst fills in narrative)."""
    summary = render_verdict_summary(verdict)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Cache-preservation experiment — analysis section\n\n"
        + summary
        + "\n\n---\n\n"
        + "## Analyst narrative\n\n"
        + "(fill in: was the verdict expected? any anomalies? follow-up actions?)\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze cache-preservation probe CSV.")
    parser.add_argument("input_csv", type=Path, help="CSV emitted by collect.py")
    parser.add_argument("--verdict-json", type=Path, default=None, help="Write structured verdict JSON here")
    parser.add_argument("--report-md", type=Path, default=None, help="Write draft REPORT.md analysis section here")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    samples = load_samples(args.input_csv)
    logger.info("Loaded %d samples from %s", len(samples), args.input_csv)

    verdict = evaluate_criteria(samples)
    print(render_verdict_summary(verdict))

    if args.verdict_json:
        write_verdict_json(verdict, args.verdict_json)
        logger.info("Wrote verdict JSON: %s", args.verdict_json)
    if args.report_md:
        write_report_section(verdict, args.report_md)
        logger.info("Wrote draft report: %s", args.report_md)

    # Exit non-zero if the verdict failed — CI gating
    return 0 if verdict.overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
