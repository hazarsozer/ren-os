"""
lib.instrument.calibration — the closed estimator loop (Task 10, RenOS 0.6.1 E5a).

`lib.instrument.estimator.calibrate` has existed since 0.2 with no caller: the
cheap chars/ratio estimator stayed a guessed constant forever, and
`lib.instrument.collect.harvest_session_usage` (real transcript token
accounting) had no production caller either. This module is the loop that
closes both:

  wake-up  → `persist_last_injection(text)` writes the EXACT emitted
             additionalContext to `state_dir()/metrics/last_injection.txt`
             (overwritten each session — a scratch pairing file, not a log).
  wrap     → `harvest_and_calibrate(session, cwd=...)` resolves the session's
             transcript, records its real usage + one `subagent_spawn` metric
             per Task-tool spawn (the input 0.6.1 E4's routing audit reads),
             builds calibration pairs, and folds them into the stored ratio.
  wake-up  → its own cheap `estimate_tokens` reads the resulting
             `chars_per_token` back (one small stdlib JSON read, no deps).

## What counts as a calibration pair (and why the brief's pair is guarded)

A pair is only worth calibrating on if its char count and its token count
describe the SAME text.

  1. `output` pairs (primary, exactly attributable): a TEXT-ONLY assistant
     turn — every content block is a `text` block — pairs its rendered text
     length against its own `usage.output_tokens`. Nothing else contributed
     to that number, so it is a direct read on the real tokenizer. Turns
     carrying `tool_use`/`thinking` blocks are excluded: their
     `output_tokens` also covers serialized tool input we never measured.

  2. `injection` pair (the brief's designed pair, plausibility-guarded):
     `last_injection.txt` paired with the session's measured
     `cache_creation_input_tokens`. On a COLD session that token count covers
     the whole cached prompt prefix (system prompt + tool definitions +
     CLAUDE.md + the injection), so the implied ratio can be ~5x too low —
     calibrating on it unguarded would poison the estimator, not correct it.
     It is therefore only accepted when the implied ratio lands inside
     `PLAUSIBLE_RATIO_BAND`, which is the case when cache creation IS
     substantially the injection (resume/compact SessionStart appended to an
     already-cached prefix). Outside the band it is dropped silently.

Every guard is a silent skip, never an exception: a missing transcript, a
missing/empty pairing file, zero/absent token counts, and malformed transcript
lines all yield "nothing calibrated this session". Calibration is a
housekeeping refinement — it must never fail a wrap close-out or a wake-up
injection.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from lib import ren_paths
from lib.instrument import collect
from lib.instrument.estimator import calibrate

LAST_INJECTION_FILENAME = "last_injection.txt"
CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"

#: Chars-per-token band a pair must imply to be believable for English-ish
#: markdown. Real ratios cluster near 4; anything outside this means the two
#: sides of the pair are not describing the same text (see module docstring).
PLAUSIBLE_RATIO_BAND: tuple[float, float] = (1.5, 12.0)

#: Bound on output pairs folded in per session — calibration converges long
#: before this, and one chatty session should not out-vote every other.
MAX_OUTPUT_PAIRS = 20


# --------------------------------------------------------------- pairing file


def last_injection_path() -> Path:
    return ren_paths.state_dir() / collect.METRICS_DIRNAME / LAST_INJECTION_FILENAME


def _write_text_atomic(text: str) -> None:
    path = last_injection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def persist_last_injection(text: str) -> bool:
    """Persist the exact injected payload for wrap to pair against. Returns
    `True` if written, `False` if it degraded (empty payload, or any OS-level
    failure) — the caller is the wake-up hook, whose injection must never be
    put at risk by this bookkeeping write."""
    if not text:
        return False
    try:
        _write_text_atomic(text)
    except (OSError, UnicodeEncodeError):
        return False
    return True


def _read_last_injection() -> str:
    try:
        return last_injection_path().read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


# ------------------------------------------------------ transcript resolution


def _resolve_claude_dir(claude_dir: Path | None = None) -> Path:
    if claude_dir is not None:
        return claude_dir
    env = os.environ.get(CLAUDE_CONFIG_DIR_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def _encode_project_dir(cwd: str) -> str:
    """Claude Code's cwd→project-dir encoding (mirrors
    `skills.retrospective.lib._encode_project_dir`; duplicated rather than
    imported so `lib/` never depends on `skills/`)."""
    return cwd.replace("/", "-")


def resolve_transcript(
    session: str, cwd: Path | str | None = None, claude_dir: Path | None = None
) -> Path | None:
    """Locate the transcript for `session`, or `None`.

    Claude Code names each transcript `<sessionId>.jsonl` under
    `<CLAUDE_CONFIG_DIR>/projects/<encoded-cwd>/`, and `/ren:wrap` is invoked
    with that same session id (the value `hooks/wake-up/ren-wake-up.py` reads
    from the SessionStart event's `session_id`) while running with its cwd
    inside the project — so the path is derivable without wrap needing a
    `transcript_path` it is never handed. Deliberately EXACT-MATCH only: no
    newest-mtime fallback, because the newest transcript in a project dir may
    belong to a different, concurrent session, and calibrating one session's
    text against another's tokens is worse than not calibrating.
    """
    if not session:
        return None
    resolved_cwd = str(cwd) if cwd is not None else os.getcwd()
    path = (
        _resolve_claude_dir(claude_dir)
        / "projects"
        / _encode_project_dir(resolved_cwd)
        / f"{session}.jsonl"
    )
    return path if path.is_file() else None


def _text_only_output_pairs(transcript_path: Path) -> list[tuple[str, int]]:
    """`(rendered_text, output_tokens)` for every text-only assistant turn.
    Tolerant line-by-line parse (same discipline as `harvest_session_usage`) —
    never raises."""
    pairs: list[tuple[str, int]] = []
    try:
        with transcript_path.open("r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "assistant":
                    continue
                message = obj.get("message")
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if not isinstance(content, list) or not content:
                    continue
                if not all(
                    isinstance(b, dict) and b.get("type") == "text" for b in content
                ):
                    continue
                text = "".join(str(b.get("text", "")) for b in content)
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue
                try:
                    tokens = int(usage.get("output_tokens", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if not text or tokens <= 0:
                    continue
                pairs.append((text, tokens))
    except (OSError, UnicodeDecodeError):
        return pairs
    return pairs


def _is_plausible(chars: int, tokens: int) -> bool:
    if chars <= 0 or tokens <= 0:
        return False
    low, high = PLAUSIBLE_RATIO_BAND
    return low <= chars / tokens <= high


# ------------------------------------------------------------------ the loop


def harvest_and_calibrate(
    session: str, cwd: Path | str | None = None, claude_dir: Path | None = None
) -> dict:
    """Harvest `session`'s real usage, record it, and calibrate the estimator.

    Returns `{"calibrated": bool, "reason": str, "samples": [(kind, chars,
    tokens), ...], "already_recorded": bool, "usage": dict | None}`.
    `reason` is one of `"no-transcript"`, `"no-samples"`, `"already-recorded"`,
    `"calibrate-failed"`, or `"ok"`.

    Recording is once per session: a second wrap in the same session finds its
    own `subagent_spawn` records already present and skips (both the recording
    and the calibration) rather than double-counting them into the routing
    audit's denominator.
    """
    out: dict = {
        "calibrated": False,
        "reason": "no-transcript",
        "samples": [],
        "already_recorded": False,
        "usage": None,
    }

    transcript = resolve_transcript(session, cwd=cwd, claude_dir=claude_dir)
    if transcript is None:
        return out

    try:
        usage = collect.harvest_session_usage(transcript)
    except (OSError, UnicodeDecodeError):
        return out
    out["usage"] = usage

    already = any(
        entry.get("session") == session
        for entry in collect.read(kind=collect.KIND_SUBAGENT_SPAWN)
    ) or any(
        entry.get("session") == session
        for entry in collect.read(kind=collect.KIND_CACHE_READ)
    )
    if already:
        out["already_recorded"] = True
        out["reason"] = "already-recorded"
        return out

    collect.record(
        collect.KIND_CACHE_READ,
        {
            "session": usage["session"],
            "cache_read_input_tokens": usage["cache_read_input_tokens"],
            "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "turns": usage["turns"],
            "producer": "wrap",
        },
    )
    for spawn in usage["spawns"]:
        collect.record(collect.KIND_SUBAGENT_SPAWN, spawn)

    samples: list[tuple[str, int]] = []
    described: list[tuple[str, int, int]] = []

    for text, tokens in _text_only_output_pairs(transcript)[:MAX_OUTPUT_PAIRS]:
        if _is_plausible(len(text), tokens):
            samples.append((text, tokens))
            described.append(("output", len(text), tokens))

    injection = _read_last_injection()
    injection_tokens = usage["cache_creation_input_tokens"]
    if injection and _is_plausible(len(injection), injection_tokens):
        samples.append((injection, injection_tokens))
        described.append(("injection", len(injection), injection_tokens))

    if not samples:
        out["reason"] = "no-samples"
        return out

    try:
        calibrate(samples)
    except (ValueError, OSError):
        out["reason"] = "calibrate-failed"
        return out

    out["calibrated"] = True
    out["reason"] = "ok"
    out["samples"] = described
    return out


__all__ = [
    "LAST_INJECTION_FILENAME",
    "MAX_OUTPUT_PAIRS",
    "PLAUSIBLE_RATIO_BAND",
    "harvest_and_calibrate",
    "last_injection_path",
    "persist_last_injection",
    "resolve_transcript",
]
