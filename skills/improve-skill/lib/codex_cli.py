"""
The single module that shells the `codex` CLI — the A2 cross-vendor critic backend.

`run_exec` runs one non-interactive `codex exec` turn and returns a
`claude_cli.ClaudeRun`-shaped result, so it is a drop-in judge runner for
`eval_runner.judge_assertion` (same call signature, same return shape). Used ONLY
as a *judge* (the cross-model critic) — never to run a skill, which always runs
under `claude`.

Documented gap (A2 design §5): codex does not surface Anthropic-shaped token
usage, so `usage` is always `ApiUsage(0, 0)`. The critic is a single bounded
final-gate pass, so its cost is not budget-tracked here.

The exact `codex exec` flag surface was confirmed against `codex-cli 0.139.0`;
mirror `claude_cli.run_print` if the invocation needs to evolve.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .claude_cli import ClaudeRun
from .types import ApiUsage


def run_exec(
    prompt: str,
    *,
    model: str | None = None,
    bare: bool = False,  # accepted for runner-signature parity; codex has no --bare
    timeout_seconds: int = 120,
    cwd: Path | None = None,
    env: dict | None = None,
    **_ignored,
) -> ClaudeRun:
    """
    Run a single `codex exec` turn and return its final text as a ClaudeRun.

    Args:
        prompt: The judge prompt (instructs an exact TRUE/FALSE reply).
        model: Codex/OpenAI model id passed through as `--model`.
        timeout_seconds: Hard timeout; on expiry returns a timed_out ClaudeRun.
        cwd / env: Passed to the subprocess.
        **_ignored: Swallows extra judge-runner kwargs (e.g. detect_activation,
            max_budget_usd) so this stays a drop-in for the claude runner.

    Returns:
        ClaudeRun(output_text=<stdout>, usage=ApiUsage(0,0),
                  is_error=<nonzero exit>, timed_out=<on timeout>).
    """
    cmd = ["codex", "exec"]
    if model:
        cmd += ["--model", model]
    cmd.append(prompt)

    try:
        proc = subprocess.run(
            cmd, input=None, text=True, capture_output=True,
            timeout=timeout_seconds, cwd=cwd, env=env,
        )
    except subprocess.TimeoutExpired:
        return ClaudeRun(output_text="", usage=ApiUsage(0, 0), timed_out=True)

    text = (proc.stdout or "").strip()
    return ClaudeRun(
        output_text=text,
        usage=ApiUsage(0, 0),
        is_error=(proc.returncode != 0),
        raw=text,
    )
