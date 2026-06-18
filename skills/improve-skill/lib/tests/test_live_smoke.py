"""
Gated live smoke test for skills.sf_improve_skill.lib.eval_runner.run_evals.

This test runs run_evals on a real skill ONLY when:
  1. The `claude` CLI is on PATH
  2. Either ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN environment variable
     is set (credential validation)

Otherwise, the test SKIPS. This is a deliberate gating mechanism to prevent
quota spend during routine pytest runs in environments without credentials
configured (e.g., CI, automated test suites). The live validation is a
separate manual step.

Run with:
    python3 -m pytest skills/improve-skill/lib/tests/test_live_smoke.py -v

In this environment, the test will SKIP unless both conditions are met.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from ..eval_runner import run_evals


REPO_ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.skipif(
    shutil.which("claude") is None
    or not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
    reason="Skipped: claude CLI not on PATH or credentials not configured (ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN)",
)
def test_live_smoke_run_evals_on_real_skill():
    """
    Live smoke test: run_evals on a real framework skill.

    This test is gated on:
      - shutil.which("claude") is not None (claude CLI available)
      - ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN is set (credentials available)

    If either condition is not met, the test SKIPS (does not consume quota).

    When run, it exercises the full eval pipeline:
      - Loads the eval spec
      - Creates a sandbox (isolated wiki/plugin-data)
      - Invokes the claude CLI
      - Judges assertions
      - Returns EvalResult

    This is a bounded proof-of-life test, not a full suite validation.
    """
    skill_name = "install"
    skill_dir = REPO_ROOT / "skills" / skill_name

    # Verify the skill exists and has an eval spec
    assert skill_dir.exists(), f"Skill directory {skill_dir} does not exist"
    assert (skill_dir / "eval" / "eval.json").exists(), (
        f"Skill {skill_name} has no eval.json"
    )

    # Run a single test from the skill's eval suite to verify the pipeline works
    result = run_evals(
        skill_name,
        eval_runs=1,
        timeout_seconds=60,
        skills_root=REPO_ROOT / "skills",
    )

    # Basic assertions: result is structured correctly
    assert result is not None
    assert hasattr(result, "skill_name")
    assert result.skill_name == skill_name
    assert hasattr(result, "exit_reason")
