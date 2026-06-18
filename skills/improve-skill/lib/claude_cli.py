"""The single module that shells the `claude` CLI. All other modules mock this.

Invocation surface confirmed by the Phase-0 spike (see SPIKE_FINDINGS.md). If the
spike recorded different flags/JSON paths than the defaults below, update this file
to match and note it in SPIKE_FINDINGS.md.

SPIKE 2026-06-18: `--bare` does NOT authenticate (it skips the credential store) — every
authenticated call must be non-bare. `bare=True` is retained only for unauthenticated/local use.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .types import ApiUsage


@dataclass(frozen=True)
class ClaudeRun:
    output_text: str
    usage: ApiUsage
    activated: tuple[str, ...] = ()
    raw: str = ""
    timed_out: bool = False
    is_error: bool = False   # SPIKE: claude JSON carries is_error; treat True as a failed run


def _usage_from(obj: dict) -> ApiUsage:
    u = obj.get("usage") or {}
    return ApiUsage(
        input_tokens=int(u.get("input_tokens", 0)),
        output_tokens=int(u.get("output_tokens", 0)),
        cache_read_input_tokens=int(u.get("cache_read_input_tokens", 0)),
        cache_creation_input_tokens=int(u.get("cache_creation_input_tokens", 0)),
    )


def _activated_from_stream(raw: str) -> tuple[str, ...]:
    """Parse a stream-json transcript for Skill activation events.
    Event shape confirmed by the spike (SPIKE_FINDINGS.md §activation)."""
    names: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Spike-confirmed shape: a tool_use event for the Skill tool carries the skill name.
        if ev.get("type") == "tool_use" and ev.get("name") == "Skill":
            skill = (ev.get("input") or {}).get("name") or (ev.get("input") or {}).get("skill")
            if skill:
                names.append(str(skill))
    return tuple(names)


def run_print(
    prompt: str,
    *,
    bare: bool,
    model: str | None = None,
    detect_activation: bool = False,
    max_budget_usd: float | None = None,
    timeout_seconds: int = 300,
    cwd: Path | None = None,
    env: dict | None = None,
) -> ClaudeRun:
    cmd = ["claude", "--print"]
    if bare:
        cmd.append("--bare")
    cmd += ["--output-format", "stream-json", "--verbose"] if detect_activation else ["--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", f"{max_budget_usd:.4f}"]
    cmd.append(prompt)

    try:
        proc = subprocess.run(
            cmd, input=None, text=True, capture_output=True,
            timeout=timeout_seconds, cwd=cwd, env=env,
        )
    except subprocess.TimeoutExpired:
        return ClaudeRun(output_text="", usage=ApiUsage(0, 0), raw="", timed_out=True)

    raw = proc.stdout or ""
    if detect_activation:
        # stream-json: the final result event carries text + usage; events carry activation.
        text, usage = _last_result(raw)
        return ClaudeRun(output_text=text, usage=usage, activated=_activated_from_stream(raw), raw=raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return ClaudeRun(output_text=raw.strip(), usage=ApiUsage(0, 0), raw=raw)
    return ClaudeRun(output_text=str(obj.get("result", "")).strip(), usage=_usage_from(obj),
                     raw=raw, is_error=bool(obj.get("is_error", False)))


def _last_result(raw: str) -> tuple[str, ApiUsage]:
    text, usage = "", ApiUsage(0, 0)
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            text = str(ev.get("result", text))
            usage = _usage_from(ev)
    return text, usage
