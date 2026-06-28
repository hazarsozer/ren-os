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
import shutil
from dataclasses import dataclass
from pathlib import Path

from .types import ApiUsage, EvalResult

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
        skill_path: The skill directory (e.g., `skills/wrap/`).

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
            "Did pre-flight pass? Re-run with /ren:improve-skill pre-flight to surface the violation."
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
# LLM judge model constant
# ---------------------------------------------------------------------------

JUDGE_MODEL = "haiku"


# ---------------------------------------------------------------------------
# select_judge — A2 cross-model critic router
# ---------------------------------------------------------------------------

# OpenAI/codex model-name prefixes routed to the `codex` CLI critic backend.
_CODEX_MODEL_PREFIXES = ("codex", "gpt", "o1", "o3", "o4")


class CriticBackendUnavailable(RuntimeError):
    """
    Raised by `select_judge` when the chosen critic model's CLI is not on PATH.

    The critic gate catches this and ships WITHOUT cross-model confirmation
    (an explicit notice) rather than crashing — A2 graceful degradation, mirroring
    A4's missing-reference handling.
    """


def _is_codex_model(model: str) -> bool:
    return (model or "").strip().lower().startswith(_CODEX_MODEL_PREFIXES)


def select_judge(model: str):
    """
    Map a critic model name to `(judge_runner, model)`.

    Codex/OpenAI-shaped names (`codex*`, `gpt*`, `o1*`, `o3*`, `o4*`) route to the
    `codex` CLI adapter; everything else routes to the `claude` CLI (e.g.
    `claude-opus-4-8`). The skill under test is unaffected — this only selects the
    JUDGE.

    Raises:
        CriticBackendUnavailable: if the required CLI is not on PATH.
    """
    import shutil

    if _is_codex_model(model):
        if shutil.which("codex") is None:
            raise CriticBackendUnavailable(
                f"critic model {model!r} requires the `codex` CLI, which is not on PATH"
            )
        from .codex_cli import run_exec
        return run_exec, model

    if shutil.which("claude") is None:
        raise CriticBackendUnavailable(
            f"critic model {model!r} requires the `claude` CLI, which is not on PATH"
        )
    from .claude_cli import run_print
    return run_print, model


# ---------------------------------------------------------------------------
# load_reference_exemplar — A4: pull a "what good looks like" artifact for the judge
# ---------------------------------------------------------------------------


def load_reference_exemplar(path: str | Path, *, max_chars: int = 4000) -> str | None:
    """Read a reference exemplar file for the eval judge (A4).

    Returns the file text (truncated to max_chars with a marker) or None if the
    path is missing/unreadable. Never raises — a bad reference must not crash the
    loop; it just means "no exemplar".
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError):  # missing / non-UTF-8 / not a file
        return None
    if len(text) > max_chars:
        text = text[:max_chars] + "\n… [truncated]"
    return text


# ---------------------------------------------------------------------------
# judge_assertion — single TRUE/FALSE call via the LLM judge
# ---------------------------------------------------------------------------


def _judge_prompt(output_text: str, assertion: str, reference_text: str | None = None) -> str:
    reference_block = ""
    if reference_text:
        reference_block = (
            "--- REFERENCE EXEMPLAR (what good output looks like; for grounding only, "
            "NOT the statement to judge) ---\n"
            f"{reference_text}\n"
            "--- END REFERENCE EXEMPLAR ---\n\n"
        )
    return (
        "Given the following skill output, is the statement TRUE or FALSE?\n"
        "Reply with exactly TRUE or FALSE and nothing else.\n\n"
        f"{reference_block}"
        f"--- OUTPUT ---\n{output_text}\n--- END OUTPUT ---\n\n"
        f"STATEMENT: {assertion}"
    )


def judge_assertion(
    output_text: str,
    assertion: str,
    *,
    timeout_seconds: int = 120,
    reference_text: str | None = None,
    judge_model: str = JUDGE_MODEL,
    _runner=None,
) -> tuple[bool, ApiUsage]:
    """
    Ask the LLM judge whether `assertion` holds for `output_text`.

    Args:
        output_text: The skill's output to evaluate.
        assertion: A natural-language statement to verify as TRUE/FALSE.
        timeout_seconds: Per-call timeout passed to the runner.
        _runner: Callable matching claude_cli.run_print's signature. Defaults
            to claude_cli.run_print. Tests inject a fake.

    Returns:
        (verdict, usage) where verdict is True if the judge replied "TRUE".
    """
    from .claude_cli import run_print
    runner = _runner or run_print
    # SPIKE: non-bare — --bare skips auth (SPIKE_FINDINGS.md §2)
    run = runner(
        _judge_prompt(output_text, assertion, reference_text=reference_text),
        bare=False,
        model=judge_model,
        timeout_seconds=timeout_seconds,
    )
    verdict = run.output_text.strip().upper().startswith("TRUE")
    return verdict, run.usage


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _add(a: ApiUsage, b: ApiUsage) -> ApiUsage:
    return ApiUsage(
        a.input_tokens + b.input_tokens,
        a.output_tokens + b.output_tokens,
        a.cache_read_input_tokens + b.cache_read_input_tokens,
        a.cache_creation_input_tokens + b.cache_creation_input_tokens,
    )


def _majority(votes) -> bool:
    votes = list(votes)
    if not votes:
        return False
    return sum(1 for v in votes if v) * 2 > len(votes)


# ---------------------------------------------------------------------------
# Main entry — own LLM-judge backend
# ---------------------------------------------------------------------------


def run_evals(
    skill_name: str,
    *,
    eval_subset_ids: list[str] | None = None,
    timeout_seconds: int = 300,
    cwd: Path | None = None,
    eval_runs: int = 1,
    skills_root: Path | str | None = None,
    reference_text: str | None = None,
    judge_model: str = JUDGE_MODEL,
    judge_runner=None,
    _runner=None,
) -> EvalResult:
    """
    Execute the skill's eval suite and return scored results.

    Uses the own LLM-judge backend (see SPIKE_FINDINGS.md). Each test is run
    via eval_sandbox, and each assertion is judged via judge_assertion.

    Args:
        skill_name: The target skill (directory under skills_root).
        eval_subset_ids: If set, run only these test IDs.
        timeout_seconds: Per-skill-run timeout in seconds.
        cwd: Unused (sandbox overrides cwd). Kept for interface compat.
        eval_runs: Number of skill-runs per test; each run's own output is judged
            and the per-assertion verdict is a majority across the N runs.
        skills_root: Root of the skills directory. Defaults to Path("skills").
        _runner: Callable matching claude_cli.run_print. Defaults to
            claude_cli.run_print (requires `claude` on PATH). Tests inject a fake.

    Returns:
        EvalResult.

    Raises:
        EvalBackendNotConfiguredError: when `_runner` is None and `claude` is
            not on PATH — the eval backend is unavailable.
    """
    from .claude_cli import run_print
    from .sandbox import eval_sandbox

    runner = _runner
    if runner is None:
        if shutil.which("claude") is None:
            raise EvalBackendNotConfiguredError(
                "run_evals() requires a configured eval backend — the eval-backed "
                "self-improvement loop is EXPERIMENTAL. `claude` is not on PATH. "
                "See references/eval-runner.md "
                "§'Integration with Skill Creator' for the two design paths; the "
                "pure-logic helpers in lib/eval_runner.py (load_eval_spec, "
                "filter_tests_by_ids, compute_total_assertions, make_/parse_failing_"
                "assertion_id, empty_eval_result) are real and ship as composable "
                "primitives. Inject a working eval_runner to exercise the loop."
            )
        runner = run_print

    # The skill ALWAYS runs under `runner` (claude). The judge MAY be a different
    # model/vendor (A2 cross-model critic); default it to the skill runner so the
    # standard single-judge path is byte-for-byte unchanged.
    judge_runner_resolved = judge_runner or runner

    root = Path(skills_root) if skills_root else Path("skills")
    # Plugin-active CWD: the worktree root (parent of skills/) so the nested
    # `claude` loads the worktree's own — possibly mid-iteration-edited — skill.
    # Writes stay redirected to the sandbox tmp tree (eval_sandbox env), so the
    # real wiki/plugin-data are untouched. (C5b skill-loading fix; SPIKE_FINDINGS.)
    plugin_root = root.resolve().parent
    spec = load_eval_spec(root / skill_name)
    spec = filter_tests_by_ids(spec, eval_subset_ids)
    total = compute_total_assertions(spec)
    if total == 0:
        return empty_eval_result("no tests after subset filter")

    passed = 0
    failing: list[str] = []
    usage = ApiUsage(0, 0)

    def _run_skill(prompt: str):
        with eval_sandbox(skill_cwd=plugin_root) as sb:
            return runner(
                prompt,
                bare=False,
                detect_activation=True,
                timeout_seconds=timeout_seconds,
                cwd=sb.cwd,
                env=sb.env,
            )

    for test in spec.tests:
        runs = [_run_skill(test.prompt) for _ in range(max(1, eval_runs))]
        for r in runs:
            usage = _add(usage, r.usage)

        # Treat a timed-out or errored run as all-fail for its assertions (+trigger)
        if any(r.timed_out or r.is_error for r in runs):
            for i in range(len(test.binary_assertions)):
                failing.append(make_failing_assertion_id(test.id, i))
            if test.trigger_test:
                failing.append(make_failing_assertion_id(test.id, len(test.binary_assertions)))
            continue

        activated = _majority(
            r.activated and (skill_name in r.activated) for r in runs
        )
        if test.trigger_test:
            if activated:
                passed += 1
            else:
                failing.append(make_failing_assertion_id(test.id, len(test.binary_assertions)))

        # Judge each run's OWN output once, majority across the N runs (true
        # skill-run variance). NOT runs[0] re-judged N times. (C5b variance fix.)
        for i, assertion in enumerate(test.binary_assertions):
            votes = []
            for r in runs:
                ok, ju = judge_assertion(
                    r.output_text, assertion, reference_text=reference_text,
                    judge_model=judge_model, _runner=judge_runner_resolved,
                )
                usage = _add(usage, ju)
                votes.append(ok)
            if _majority(votes):
                passed += 1
            else:
                failing.append(make_failing_assertion_id(test.id, i))

    for nt in spec.non_triggers:
        with eval_sandbox(skill_cwd=plugin_root) as sb:
            r = runner(
                nt.prompt,
                bare=False,
                detect_activation=True,
                timeout_seconds=timeout_seconds,
                cwd=sb.cwd,
                env=sb.env,
            )
        usage = _add(usage, r.usage)
        if r.timed_out or r.is_error:
            # Cannot verify non-activation on a failed run; treat as fail.
            pass
        elif skill_name not in (r.activated or ()):
            passed += 1

    return EvalResult(
        score=passed / total,
        passed=passed,
        total=total,
        failing_assertion_ids=tuple(failing),
        raw_output="",
        usage=usage,
    )
