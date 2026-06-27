"""
sf-improve-skill pre-flight checks.

Six gates that must pass before the Karpathy loop starts:
  1. Target skill exists
  1b. Not a lightweight-tier skill (no eval surface → not self-improvable; ADR-011 amendment)
  2. eval/eval.json parseable
  3. Working tree clean
  4. Autonomous-mode safety (if --autonomous: max-iterations AND max-budget-usd set)
  5. Claude Code on PATH
  6. Initial eval run succeeds

Per SKILL.md §"Pre-flight check (mandatory)" and ADR-012 amendment 2026-05-28
(option a: --max-turns dropped from required set).

These functions are pure-with-side-effects (subprocess calls, file reads).
The argument-validation subset is fully unit-testable.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from .types import ImproveSkillArgs, PreFlightError

logger = logging.getLogger(__name__)


# Layout per ADR-011 — the skill's directory under skills/<name>/
SKILL_DIR_ROOT = Path("skills")
SKILL_MD_FILE = "SKILL.md"
EVAL_FILE = Path("eval") / "eval.json"


def pre_flight_check(
    args: ImproveSkillArgs,
    *,
    skills_root: Path | None = None,
    cwd: Path | None = None,
) -> None:
    """
    Run all six pre-flight gates. Raises PreFlightError on first failure.

    Args:
        args: Parsed CLI args.
        skills_root: Override the skills directory root (for testing).
            Defaults to ./skills/ in the current working directory.
        cwd: Override the working directory for the git working-tree check.
            Defaults to current working dir (None).

    Raises:
        PreFlightError: with a user-readable message describing the failure.
    """
    skills_root = skills_root or SKILL_DIR_ROOT
    skill_path = skills_root / args.skill_name

    # Gate 4 first — pure argument validation, fastest to fail
    validate_autonomous_flags(args)

    # Gate 1 — target skill exists
    _validate_skill_exists(skill_path)

    # Gate 1b — lightweight-tier skills have no eval surface and are not self-improvable
    # (ADR-011 lightweight-tier amendment). Refuse here, before the eval-file gate, so the
    # message is "not self-improvable" rather than the generic "eval.json not found".
    _refuse_if_lightweight(skill_path)

    # Gate 2 — eval.json parseable + has binary assertions
    _validate_eval_file(skill_path)

    # Gate 5 — Claude Code on PATH
    _validate_cc_available()

    # Gate 3 — working tree clean (in the same cwd the loop will git-operate in)
    validate_working_tree_clean(cwd=cwd)

    # Gate 6 — initial eval run is left to the loop runner (it's a long-running op
    # and belongs in the main loop body, not pre-flight). The pre-flight verifies the
    # eval file PARSES, not that it RUNS. The first iteration's eval-run failure is
    # treated as ExitReason.EVAL_UNRUNNABLE.

    # Gate 7 — eval-readiness advisory (A3, video-ingest). Non-blocking: surfaces a
    # thin-signal warning + the Karpathy preconditions before the loop spends budget.
    for _note in eval_readiness_notes(skill_path):
        logger.info("eval-readiness: %s", _note)

    logger.info("pre-flight checks passed for skill=%s autonomous=%s", args.skill_name, args.autonomous)


def validate_autonomous_flags(args: ImproveSkillArgs) -> None:
    """
    Gate 4: if --autonomous, require ALL of --max-iterations + --max-budget-usd.

    Per ADR-012 amendment 2026-05-28 (option a): --max-turns is NOT required
    because it doesn't exist as a CC CLI flag in CC 2.1.154. See
    references/cc-flag-watch.md for the watch.
    """
    if not args.autonomous:
        return  # interactive mode has no flag requirements

    missing: list[str] = []
    if args.max_iterations is None or args.max_iterations <= 0:
        missing.append("--max-iterations N")
    if args.max_budget_usd is None or args.max_budget_usd <= 0:
        missing.append("--max-budget-usd N")

    if missing:
        raise PreFlightError(
            "Autonomous mode requires "
            + " AND ".join(missing)
            + " set to positive values. Refusing to run unbounded. "
            + "See references/cc-flag-watch.md for why --max-turns is not required."
        )


def validate_working_tree_clean(*, cwd: Path | None = None) -> None:
    """
    Gate 3: the git working tree must be clean before starting.

    The loop uses `git reset --hard HEAD~1` to revert iterations; uncommitted
    changes in the working tree would be obliterated by that. Refuse outright.

    Args:
        cwd: directory to check (default: current working dir)
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise PreFlightError(
            f"git status failed (exit {result.returncode}). Are you in a git repo? "
            f"stderr: {result.stderr.strip()}"
        )
    if result.stdout.strip():
        raise PreFlightError(
            "Working tree has uncommitted changes. Commit or stash before running "
            "/ren:improve-skill. (The loop uses `git reset --hard` to revert iterations; "
            "we won't risk clobbering your WIP.)"
        )


def _validate_skill_exists(skill_path: Path) -> None:
    """Gate 1."""
    if not skill_path.is_dir():
        raise PreFlightError(
            f"Skill not found at {skill_path}. "
            "Run /skill-creator to bootstrap a new skill before improving it."
        )
    skill_md = skill_path / SKILL_MD_FILE
    if not skill_md.is_file():
        raise PreFlightError(
            f"{skill_md} not found. /ren:improve-skill needs an existing SKILL.md to work on."
        )


def _read_tier(skill_md: Path) -> str | None:
    """Parse the `tier:` frontmatter value from a SKILL.md.

    Returns the tier (e.g. "lightweight") or None if absent/unreadable. Never
    raises — an unreadable or frontmatter-less SKILL.md is treated as having no
    tier (i.e. a standard skill), leaving the downstream gates in charge.
    """
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, ValueError):  # ValueError covers UnicodeDecodeError on non-UTF-8 bytes
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.lstrip().startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        if key.strip() == "tier":
            return val.strip().strip('"').strip("'")
    return None


def _refuse_if_lightweight(skill_path: Path) -> None:
    """
    Gate 1b: refuse lightweight-tier skills — they are not self-improvable.

    Per the ADR-011 lightweight-tier amendment (2026-06-27), a `tier: lightweight`
    skill ships with no eval/eval.json surface ("a prompt you don't want to
    retype"). The Karpathy loop has nothing to score against, so refuse early with
    an actionable message. No-op for standard skills (the default).
    """
    if _read_tier(skill_path / SKILL_MD_FILE) == "lightweight":
        raise PreFlightError(
            f"'{skill_path.name}' is a lightweight-tier skill and cannot be self-improved: "
            "it has no eval surface for the loop to score against. To make it improvable, "
            "promote it to a standard skill — remove `tier: lightweight` and add "
            "eval/eval.json per ADR-011."
        )


def _validate_eval_file(skill_path: Path) -> None:
    """
    Gate 2: validate skill's eval.json against the canonical ADR-011 schema.

    Per ADR-011 §"eval/eval.json schema" (lines 104-129 of wiki/decisions/011-skill-schema.md),
    the shape is:

        {
          "name": "<skill-name>",
          "tests": [                                  ← top-level "tests"
            {
              "id": "test-1",
              "prompt": "<...>",
              "binary_assertions": [                  ← list of STRINGS
                "<unambiguous true/false assertion>"
              ],
              "trigger_test": true
            }
          ]
        }

    Earlier versions of this validator drifted (used `test_cases` + `assertions` +
    objects-with-binary-field) and would reject every framework-shipped skill's
    real eval.json. Pinning test in test_preflight.py loads sf-install/eval.json
    and sf-bootstrap-project/eval.json as canonical references to prevent drift.
    See learnings.md entry "validate against real contract instances".
    """
    eval_path = skill_path / EVAL_FILE
    if not eval_path.is_file():
        raise PreFlightError(
            f"{eval_path} not found. /ren:improve-skill requires an eval suite per ADR-011. "
            "Run /skill-creator to bootstrap evals."
        )

    try:
        with eval_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise PreFlightError(
            f"{eval_path} is not valid JSON: {exc}. Fix the file before invoking the loop."
        ) from exc

    tests = data.get("tests")
    if not isinstance(tests, list) or not tests:
        raise PreFlightError(
            f"{eval_path} must contain a non-empty 'tests' array per ADR-011 schema "
            "(see wiki/decisions/011-skill-schema.md §eval.json schema)."
        )

    total_assertions = 0
    for test in tests:
        if not isinstance(test, dict):
            raise PreFlightError(
                f"{eval_path}: each test in 'tests' must be an object, got {type(test).__name__}."
            )
        assertions = test.get("binary_assertions") or []
        if not isinstance(assertions, list):
            raise PreFlightError(
                f"{eval_path}: each test must have a 'binary_assertions' list per ADR-011."
            )
        for assertion in assertions:
            if not isinstance(assertion, str):
                raise PreFlightError(
                    f"{eval_path}: 'binary_assertions' items must be strings per ADR-011 "
                    "(unambiguous true/false statements). Objects with 'binary: true' belong to "
                    "a different (non-shipped) schema — likely drift from an assumed shape."
                )
        total_assertions += len(assertions)

    if total_assertions == 0:
        raise PreFlightError(
            f"{eval_path} has zero binary assertions. The loop has no scoring primitive."
        )


def _validate_cc_available() -> None:
    """Gate 5."""
    if shutil.which("claude") is None:
        raise PreFlightError(
            "Claude Code CLI ('claude') not found on PATH. "
            "Install Claude Code before running /ren:improve-skill."
        )


# Karpathy "Auto Research" eval-readiness preconditions (A3 video-ingest improvement).
# Mostly qualitative — surfaced for the author to self-confirm before spending budget.
_EVAL_READINESS_PRECONDITIONS = (
    "objective metric (binary assertions, not vibes)",
    "fast feedback (cheap to score)",
    "write access to the artifact",
    "high-volume signal (enough assertions to discriminate)",
    "cheap-to-fail (a bad iteration is reverted, not costly)",
    "a consistent measuring stick (the eval does not move under you)",
)


def eval_readiness_notes(skill_path: Path, *, thin_signal_below: int = 2) -> list[str]:
    """A3: advisory eval-readiness check (never blocks).

    Returns human-readable notes surfaced before a budget-spending improve-skill
    run. Mechanically flags a *thin signal* (too few binary assertions for the
    loop to discriminate against) and always lists the Karpathy preconditions for
    the author to self-confirm. Never raises — a missing/unreadable eval just
    yields the checklist.
    """
    notes: list[str] = []
    total_assertions = 0
    try:
        with (skill_path / EVAL_FILE).open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        for test in data.get("tests", []) or []:
            if isinstance(test, dict):
                total_assertions += len(test.get("binary_assertions") or [])
    except (OSError, ValueError):
        notes.append("⚠ eval/eval.json unreadable — cannot assess signal strength.")

    if total_assertions and total_assertions < thin_signal_below:
        notes.append(
            f"⚠ Thin eval signal: only {total_assertions} binary assertion(s). "
            "The loop has little to discriminate against — consider adding more "
            "before spending eval-run budget."
        )
    notes.append(
        "Eval-readiness — confirm these hold before an autonomous run: "
        + "; ".join(_EVAL_READINESS_PRECONDITIONS)
        + "."
    )
    return notes
