"""
sf-improve-skill eval-runner.

Pure-logic helpers for the eval primitive:
  - `load_eval_spec(skill_path)` — parse eval.json into a typed view
  - `filter_tests_by_ids(spec, subset_ids)` — apply --eval-subset
  - `compute_total_assertions(spec)` — count assertions including trigger + non-trigger
  - `parse_failing_assertion_id(s)` — decode `<test-id>:<idx>` strings
  - `run_evals(...)` — main entry; raises EvalBackendNotConfiguredError on the
    default path (the eval-backed loop is EXPERIMENTAL pending a configured backend)

The pure-logic layers are fully tested. The actual subprocess execution
(invoking Skill Creator's run_eval or our reimplemented LLM-judge path) is
deferred until the integration choice settles per
`references/eval-runner.md` §"Integration with Skill Creator". Until then the
default path fails HONESTLY via the typed `EvalBackendNotConfiguredError` so the
orchestrator can exit cleanly instead of crashing.

Per dotfiles python/coding-style.md: PEP 8, type annotations, frozen dataclasses.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .types import EvalResult

logger = logging.getLogger(__name__)


class EvalBackendNotConfiguredError(RuntimeError):
    """
    Raised by `run_evals` on the default path: the eval-execution backend has
    not been configured yet.

    The eval-backed self-improvement loop is EXPERIMENTAL — it needs a real
    eval backend (Skill Creator's `run_eval` subprocess wrapper, or our own
    LLM-judge reimplementation) before it can score a skill. Until that
    integration choice settles (see `references/eval-runner.md` §"Integration
    with Skill Creator"), the default `run_evals` raises this TYPED error so the
    orchestrator can catch it and exit honestly with
    `ExitReason.REQUIRES_CONFIGURED_BACKEND` rather than crash on a bare
    `NotImplementedError`.

    Subclasses `RuntimeError` so callers that only guard against the broad
    "eval failed" case still treat it as a runtime failure.
    """


@dataclass(frozen=True)
class EvalTest:
    """One test entry from eval.json's `tests` array."""

    id: str
    prompt: str
    binary_assertions: tuple[str, ...]
    expected_output_summary: str = ""
    trigger_test: bool = False  # adds "skill activated" assertion when True


@dataclass(frozen=True)
class NonTrigger:
    """One non-trigger from eval.json's `non_triggers` array."""

    id: str
    prompt: str
    expected_outcome: str = "skill_not_activated"


@dataclass(frozen=True)
class EvalSpec:
    """
    Loaded representation of a skill's eval.json.

    Per ADR-011 §"eval.json schema". Parsing is permissive (extra fields
    ignored) but the canonical-shape requirements are enforced upstream by
    `preflight._validate_eval_file`. By the time we reach this loader,
    the file has already passed pre-flight; this loader just reshapes JSON
    into typed Python.
    """

    name: str
    tests: tuple[EvalTest, ...]
    non_triggers: tuple[NonTrigger, ...] = ()


# ---------------------------------------------------------------------------
# load_eval_spec
# ---------------------------------------------------------------------------


def load_eval_spec(skill_path: Path) -> EvalSpec:
    """
    Parse `<skill_path>/eval/eval.json` into an EvalSpec.

    Expects the canonical ADR-011 shape (already validated upstream by
    preflight). On unexpected shape, raises ValueError with a hint to re-run
    pre-flight.

    Args:
        skill_path: The skill directory (e.g., `skills/sf-wrap/`).

    Returns:
        EvalSpec.
    """
    eval_path = skill_path / "eval" / "eval.json"
    with eval_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    name = data.get("name") or skill_path.name
    raw_tests = data.get("tests") or []
    if not isinstance(raw_tests, list):
        raise ValueError(
            f"{eval_path}: 'tests' must be a list per ADR-011. "
            "Did pre-flight pass? Re-run with /sf:improve-skill pre-flight to surface the violation."
        )

    tests: list[EvalTest] = []
    for raw in raw_tests:
        if not isinstance(raw, dict):
            raise ValueError(f"{eval_path}: each test must be a dict")
        assertions = tuple(raw.get("binary_assertions") or ())
        tests.append(
            EvalTest(
                id=str(raw.get("id", "")),
                prompt=str(raw.get("prompt", "")),
                binary_assertions=assertions,
                expected_output_summary=str(raw.get("expected_output_summary", "")),
                trigger_test=bool(raw.get("trigger_test", False)),
            )
        )

    raw_non_triggers = data.get("non_triggers") or []
    non_triggers: list[NonTrigger] = []
    for raw in raw_non_triggers:
        if not isinstance(raw, dict):
            continue  # skip malformed non_triggers; not a hard error
        non_triggers.append(
            NonTrigger(
                id=str(raw.get("id", "")),
                prompt=str(raw.get("prompt", "")),
                expected_outcome=str(raw.get("expected_outcome", "skill_not_activated")),
            )
        )

    return EvalSpec(name=name, tests=tuple(tests), non_triggers=tuple(non_triggers))


# ---------------------------------------------------------------------------
# Subset filtering
# ---------------------------------------------------------------------------


def filter_tests_by_ids(spec: EvalSpec, subset_ids: list[str] | None) -> EvalSpec:
    """
    Return a new EvalSpec with `tests` filtered to only those whose `id`
    appears in subset_ids.

    Non-triggers are passed through unchanged (per `references/eval-runner.md`:
    --eval-subset filters tests; non_triggers are activation-discipline checks
    that run independently — opt out by passing an empty subset that excludes
    them).

    Args:
        spec: The loaded EvalSpec.
        subset_ids: Test IDs to keep; if None, no filtering.

    Returns:
        New EvalSpec.

    Raises:
        ValueError: if subset_ids is non-empty but matches zero tests
            (degenerate state the loop should refuse).
    """
    if subset_ids is None:
        return spec

    keep = set(subset_ids)
    filtered = tuple(t for t in spec.tests if t.id in keep)

    if not filtered:
        raise ValueError(
            f"--eval-subset {subset_ids!r} matched zero tests in {spec.name}'s eval.json. "
            f"Available test IDs: {[t.id for t in spec.tests]}"
        )

    return EvalSpec(name=spec.name, tests=filtered, non_triggers=spec.non_triggers)


# ---------------------------------------------------------------------------
# Counting / parsing
# ---------------------------------------------------------------------------


def compute_total_assertions(spec: EvalSpec) -> int:
    """
    Count assertions a run will evaluate.

    Per `references/eval-runner.md`:
      - Each test contributes len(binary_assertions) assertions
      - Each `trigger_test: True` adds ONE more (skill-activated check)
      - Each non_trigger contributes ONE (skill-did-NOT-activate check)
    """
    total = 0
    for test in spec.tests:
        total += len(test.binary_assertions)
        if test.trigger_test:
            total += 1
    total += len(spec.non_triggers)
    return total


def make_failing_assertion_id(test_id: str, assertion_index: int) -> str:
    """
    Compose the canonical `<test-id>:<index>` identifier used in
    EvalResult.failing_assertion_ids.

    Args:
        test_id: Test identifier from eval.json.
        assertion_index: 0-indexed position within the test's binary_assertions.

    Returns:
        f"{test_id}:{assertion_index}"
    """
    if not test_id:
        raise ValueError("test_id must be non-empty")
    if assertion_index < 0:
        raise ValueError(f"assertion_index must be >= 0, got {assertion_index}")
    return f"{test_id}:{assertion_index}"


def parse_failing_assertion_id(packed: str) -> tuple[str, int]:
    """
    Inverse of `make_failing_assertion_id`. Decode `<test-id>:<index>` into
    its parts.

    Args:
        packed: The packed identifier.

    Returns:
        (test_id, assertion_index)

    Raises:
        ValueError: if the format is malformed.
    """
    if ":" not in packed:
        raise ValueError(
            f"Expected '<test-id>:<index>' format, got {packed!r} (no colon)"
        )
    # Use rsplit so test IDs containing colons (rare but possible) still work:
    # the LAST colon separates test_id from index.
    test_id, _, index_str = packed.rpartition(":")
    if not test_id:
        raise ValueError(f"Empty test_id in {packed!r}")
    try:
        index = int(index_str)
    except ValueError as exc:
        raise ValueError(
            f"Assertion index must be an integer in {packed!r}, got {index_str!r}"
        ) from exc
    if index < 0:
        raise ValueError(f"Assertion index must be >= 0 in {packed!r}, got {index}")
    return test_id, index


# ---------------------------------------------------------------------------
# Empty-result helper (degenerate eval-unrunnable case)
# ---------------------------------------------------------------------------


def empty_eval_result(reason: str = "") -> EvalResult:
    """
    Construct an EvalResult representing 'no tests ran' (e.g., when a
    subset filter excluded everything, or when the underlying eval runner
    failed before any test could complete).

    Args:
        reason: Optional diagnostic string captured in raw_output.

    Returns:
        EvalResult with score=0.0, passed=0, total=0.
    """
    return EvalResult(
        score=0.0,
        passed=0,
        total=0,
        failing_assertion_ids=(),
        raw_output=reason,
    )


# ---------------------------------------------------------------------------
# Main entry — honest fail-fast pending a configured eval backend (EXPERIMENTAL)
# ---------------------------------------------------------------------------


def run_evals(
    skill_name: str,
    *,
    eval_subset_ids: list[str] | None = None,
    timeout_seconds: int = 300,
    cwd: Path | None = None,
) -> EvalResult:
    """
    Execute the skill's eval suite and return scored results.

    V1 STATUS: the eval-backed self-improvement loop is EXPERIMENTAL — it
    requires a configured eval backend, which is one of:
      (a) Subprocess wrapper around Skill Creator's `run_eval.py` (default plan
          per `references/eval-runner.md`), OR
      (b) Reimplementation against the same eval.json schema with our own
          LLM-judge invocation.

    Both paths are documented in the design doc; neither is yet wired here
    because the integration choice depends on whether Skill Creator's runner
    output format is stable for our parser. Rather than crash on a bare
    `NotImplementedError`, this default path raises the TYPED
    `EvalBackendNotConfiguredError` so the orchestrator can catch it and exit
    honestly with `ExitReason.REQUIRES_CONFIGURED_BACKEND`.

    The pure-logic helpers above (`load_eval_spec`, `filter_tests_by_ids`,
    `compute_total_assertions`, `make_failing_assertion_id`,
    `parse_failing_assertion_id`, `empty_eval_result`) are real and tested
    — they ship as load-bearing primitives the actual run_evals() will
    compose with once a backend is configured.

    Args:
        skill_name: The target skill.
        eval_subset_ids: If set, run only these test IDs.
        timeout_seconds: Per-test timeout (default 300s = 5 minutes).
        cwd: Working directory (default: current).

    Returns:
        EvalResult.

    Raises:
        EvalBackendNotConfiguredError: always, on the default path — the
            eval-backed loop is EXPERIMENTAL and requires a configured backend.
    """
    raise EvalBackendNotConfiguredError(
        "run_evals() requires a configured eval backend — the eval-backed "
        "self-improvement loop is EXPERIMENTAL. See references/eval-runner.md "
        "§'Integration with Skill Creator' for the two design paths; the "
        "pure-logic helpers in lib/eval_runner.py (load_eval_spec, "
        "filter_tests_by_ids, compute_total_assertions, make_/parse_failing_"
        "assertion_id, empty_eval_result) are real and ship as composable "
        "primitives. Inject a working eval_runner to exercise the loop."
    )
