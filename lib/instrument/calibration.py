"""
lib.instrument.calibration — the closed estimator loop (Task 10, RenOS 0.6.1 E5a).

`lib.instrument.estimator.calibrate` has existed since 0.2 with no caller: the
cheap chars/ratio estimator stayed a guessed constant forever, and
`lib.instrument.collect.harvest_session_usage` (real transcript token
accounting) had no production caller either. This module is the loop that
closes both:

  wake-up  → `persist_last_injection(text, session)` writes the EXACT emitted
             additionalContext **together with the harness `session_id` the
             SessionStart event carried** to
             `state_dir()/metrics/last_injection.json` (overwritten each
             session — a scratch pairing file, not a log).
  wrap     → `harvest_and_calibrate(cwd=...)` resolves the session's
             transcript **from that PERSISTED id**, records its real usage +
             one `subagent_spawn` metric per Task-tool spawn (the input 0.6.1
             E4's routing audit reads), builds calibration pairs, and folds
             them into the stored ratio.
  wake-up  → its own cheap `estimate_tokens` reads the resulting
             `chars_per_token` back (one small stdlib JSON read, no deps).

## Why the id comes from the hook, not from wrap's caller (fix round 1)

`/ren:wrap` is a MODEL-invoked skill, so its `session` argument is a
model-supplied label — the model has no reliable source for Claude Code's real
`session_id`, so that label is usually not the transcript's name. Resolving
`<config>/projects/<encoded-cwd>/<label>.jsonl` therefore missed in
production and the whole loop was dead (tests hand-fed a matching id and were
green over it). The SessionStart hook, by contrast, IS handed the real
`session_id`; it stamps it into the pairing file, and this module treats that
stamp as the only authority — then cross-checks it against the transcript's
own `sessionId` before recording anything. Wrap's `session` argument is kept
for logging only and is never used for resolution.

Stamping also removes a whole defect class: pairing can only ever happen
WITHIN one session, because the file's id must equal the id of the session
whose tokens were harvested.

## What counts as a calibration pair

A pair is only worth calibrating on if its char count and its token count
describe the SAME text. Exactly one shape qualifies today:

  `output` pairs — a TEXT-ONLY assistant turn (every content block is a
  `text` block) pairs its rendered text length against its own
  `usage.output_tokens`. Nothing else contributed to that number, so it is a
  direct read on the real tokenizer. Turns carrying `tool_use`/`thinking`
  blocks are excluded: their `output_tokens` also covers serialized tool
  input we never measured. `PLAUSIBLE_RATIO_BAND` is retained as a cheap
  sanity filter on these pairs.

The brief's designed `injection` pair (persisted payload chars ÷
`cache_creation_input_tokens`) is **deliberately not implemented.** It is
unsound in both directions: on a cold session that count covers the whole
cached prefix (system prompt + tool definitions + CLAUDE.md), and
`collect.harvest_session_usage` *sums* `cache_creation_input_tokens` across
every turn, so even a warm session's denominator is not the injection's. A
plausibility band cannot rescue it — landing in-band would be coincidence.
Injection-shaped calibration needs a PER-TURN cache-creation accessor that
`harvest_session_usage` does not expose: an explicit 0.6.2 decision, not
silent drift. The payload is still persisted (it costs nothing and is the
input that work will need).

Note the consequence of one global `chars_per_token`: the SAME ratio now
sizes prose (wake-up injections) and source code (`skills/code-map` token
accounting) — one number, two very different text shapes. Accepted for now
(both are ballpark budget arithmetic, never billing); per-shape ratios are
the 0.6.2 follow-up if either budget starts mattering precisely.

Every guard is a silent skip, never an exception: a missing/empty pairing
file, a missing transcript, an id mismatch, zero/absent token counts, and
malformed transcript lines all yield "nothing calibrated this session".
Calibration is a housekeeping refinement — it must never fail a wrap
close-out or a wake-up injection.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from lib import ren_paths
from lib.instrument import collect
from lib.instrument.estimator import calibrate

LAST_INJECTION_FILENAME = "last_injection.json"
#: The eb6b932 format (payload only, no session id). Superseded by the JSON
#: file above; unlinked whenever the new one is written so a stale orphan
#: can't sit in `metrics/` forever pretending to be current state.
LEGACY_LAST_INJECTION_FILENAME = "last_injection.txt"
CLAUDE_CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
#: Marker key written into the pairing file once its session has been
#: harvested — see `mark_last_injection_consumed`.
CONSUMED_KEY = "consumed"

#: Chars-per-token band a pair must accept to be believable for English-ish
#: markdown. Real ratios cluster near 4; anything outside this means the two
#: sides of the pair are not describing the same text (see module docstring).
PLAUSIBLE_RATIO_BAND: tuple[float, float] = (1.5, 12.0)

#: Bound on output pairs folded in per session — calibration converges long
#: before this, and one chatty session should not out-vote every other.
MAX_OUTPUT_PAIRS = 20


# --------------------------------------------------------------- pairing file


def last_injection_path() -> Path:
    return ren_paths.state_dir() / collect.METRICS_DIRNAME / LAST_INJECTION_FILENAME


def legacy_last_injection_path() -> Path:
    return ren_paths.state_dir() / collect.METRICS_DIRNAME / LEGACY_LAST_INJECTION_FILENAME


def _write_text_atomic(text: str) -> None:
    path = last_injection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def persist_last_injection(text: str, session: str) -> bool:
    """Persist `{"session": ..., "text": ...}` — the harness session id the
    SessionStart event carried, plus the exact payload injected under it.

    The id is the load-bearing half: it is the ONLY authority wrap has for
    naming this session's transcript (see module docstring). Returns `True` if
    written, `False` if it degraded (empty payload, missing/placeholder
    session id, or any OS-level failure) — the caller is the wake-up hook,
    whose injection must never be put at risk by this bookkeeping write.
    """
    if not text or not session or session == "unknown":
        return False
    try:
        _write_text_atomic(
            json.dumps({"session": session, "text": text}, ensure_ascii=False)
        )
    except (OSError, UnicodeEncodeError, TypeError, ValueError):
        return False
    try:
        legacy_last_injection_path().unlink(missing_ok=True)
    except OSError:
        pass  # an orphaned legacy file is cosmetic; never fail the write over it
    return True


def _read_stamp() -> dict:
    """The raw pairing-file dict, or `{}` on absent/unreadable/malformed/
    wrong-shaped content. Never raises."""
    try:
        data = json.loads(last_injection_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def stamp_is_consumed() -> bool:
    """Whether the pairing file carries the `consumed` marker — i.e. some wrap
    already harvested the session it names (see `mark_last_injection_consumed`)."""
    return bool(_read_stamp().get(CONSUMED_KEY))


def read_last_injection() -> tuple[str, str]:
    """`(session, text)` from the pairing file, or `("", "")` on absent,
    unreadable, malformed, or wrong-shaped content — and also on an
    ALREADY-CONSUMED stamp. Never raises.

    Refusing a consumed stamp is load-bearing (fix round 2). A stamp survives
    the session that wrote it, so a session whose own wake-up never stamped
    (degraded, no-wiki, or hook write failure) would otherwise harvest the
    PREVIOUS session's stamp — and because that transcript self-identifies with
    the old id, the session cross-check cannot catch it: the same session gets
    calibrated and usage-recorded twice. Consuming the stamp closes that.
    """
    data = _read_stamp()
    if data.get(CONSUMED_KEY):
        return "", ""
    session = data.get("session")
    text = data.get("text")
    if not isinstance(session, str) or not isinstance(text, str):
        return "", ""
    return session, text


def harness_session_id() -> str | None:
    """The harness `session_id` the wake-up hook stamped into the pairing
    file, or None when there is no usable stamp. Never raises.

    Unlike `read_last_injection`, this deliberately IGNORES the `consumed`
    marker: consumption exists to stop a second harvest of the same
    transcript, not to forget which session this is. Callers that need to
    match instrumentation logged under the REAL session id — e.g.
    `skills.wrap.lib._eligible_update_targets`, whose own `session` argument
    is a model-supplied label — read it through here rather than
    re-deriving the id from anywhere else (there is no other authority; see
    the module docstring).
    """
    session = _read_stamp().get("session")
    if not isinstance(session, str):
        return None
    session = session.strip()
    return session or None


def mark_last_injection_consumed() -> bool:
    """Stamp the pairing file `consumed` so no later wrap can harvest the same
    session again. Kept (rather than unlinked) so the persisted payload stays
    available for the 0.6.2 injection-pair work; `read_last_injection` refuses
    it either way. Returns `False` on any failure — a double-harvest guard must
    never itself break a wrap close-out."""
    data = _read_stamp()
    if not data:
        return False
    data[CONSUMED_KEY] = True
    try:
        _write_text_atomic(json.dumps(data, ensure_ascii=False))
    except (OSError, UnicodeEncodeError, TypeError, ValueError):
        return False
    return True


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
    `<CLAUDE_CONFIG_DIR>/projects/<encoded-cwd>/`. `session` MUST be the real
    harness `session_id` — i.e. the one `hooks/wake-up/ren-wake-up.py` read
    from the SessionStart event and stamped into the pairing file, never a
    model-supplied label — so the path is derivable without wrap needing a
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
    session: str | None = None,
    cwd: Path | str | None = None,
    claude_dir: Path | None = None,
) -> dict:
    """Harvest the PERSISTED session's real usage, record it, and calibrate.

    `session` is wrap's model-supplied label. It is accepted for logging and
    deliberately IGNORED for resolution — the authoritative id is the one the
    wake-up hook stamped into the pairing file (see module docstring), because
    the model has no reliable source for the harness `session_id`.

    Returns `{"calibrated": bool, "reason": str, "samples": [(kind, chars,
    tokens), ...], "already_recorded": bool, "new_spawns": int,
    "session": str, "label": str | None, "usage": dict | None,
    "transcript_session": str}`. `reason` is
    one of `"no-session"`, `"already-harvested"`, `"no-transcript"`,
    `"session-mismatch"`, `"harvest-failed"`, `"no-samples"`,
    `"calibrate-failed"`, or `"ok"`.

    The stamp is CONSUMED once its session has been harvested, so a second
    wrap in the same session — or a later session whose own wake-up never
    stamped — is a no-op (`"already-harvested"`) rather than a second
    calibration of the same text.

    Repeat wraps in one session record the DELTA, never a duplicate: spawn
    records already present for the session are counted and only the tail
    (`spawns[already_count:]`) is appended, so the routing audit's denominator
    is neither double-counted nor missing the spawns of the session's later
    half. The usage summary is re-snapshotted (latest row wins) rather than
    skipped, so it doesn't freeze at the first wrap's totals.
    """
    out: dict = {
        "calibrated": False,
        "reason": "no-session",
        "samples": [],
        "already_recorded": False,
        "new_spawns": 0,
        "session": "",
        "label": session,
        "usage": None,
    }

    persisted_session, _persisted_text = read_last_injection()
    if not persisted_session:
        if stamp_is_consumed():
            out["reason"] = "already-harvested"
        return out
    out["session"] = persisted_session

    out["reason"] = "no-transcript"
    transcript = resolve_transcript(persisted_session, cwd=cwd, claude_dir=claude_dir)
    if transcript is None:
        return out

    try:
        usage = collect.harvest_session_usage(transcript)
    except (OSError, UnicodeDecodeError, ValueError, TypeError, KeyError):
        # ValueError/TypeError: `int()` over a malformed `usage` value; a
        # corrupt transcript must degrade to "not calibrated", never raise
        # into wrap's close-out.
        out["reason"] = "harvest-failed"
        return out
    out["usage"] = usage

    # Cross-check keyed on the transcript FILENAME id, which
    # `resolve_transcript` guarantees. Fix round 2 replaced the previous
    # first-line-`sessionId` equality test: the reviewer flagged that a
    # compact/resume transcript might open with copied pre-compact lines
    # bearing the OLD id, which would reject exactly the resume sessions we
    # want. Evidence (all 430 transcripts under this machine's
    # ~/.claude/projects): `sessionId` is single-valued within every file and
    # equals the filename in every file — so the first-line test carried no
    # information the filename doesn't, at the cost of that false-reject risk.
    # The transcript's self-reported id is kept as advisory output only.
    out["transcript_session"] = usage["session"]
    if transcript.stem != persisted_session:
        out["reason"] = "session-mismatch"
        return out

    already_spawns = sum(
        1
        for entry in collect.read(kind=collect.KIND_SUBAGENT_SPAWN)
        if entry.get("session") == persisted_session
    )
    out["already_recorded"] = already_spawns > 0 or any(
        entry.get("session") == persisted_session
        for entry in collect.read(kind=collect.KIND_SESSION_USAGE)
    )

    collect.record(
        collect.KIND_SESSION_USAGE,
        {
            "session": persisted_session,
            "cache_read_input_tokens": usage["cache_read_input_tokens"],
            "cache_creation_input_tokens": usage["cache_creation_input_tokens"],
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "turns": usage["turns"],
            "producer": "wrap",
        },
    )
    new_spawns = usage["spawns"][already_spawns:]
    for spawn in new_spawns:
        collect.record(collect.KIND_SUBAGENT_SPAWN, spawn)
    out["new_spawns"] = len(new_spawns)

    # The stamp has now done its job. Consume it so a LATER session whose own
    # wake-up never stamped cannot re-harvest this one (see
    # `read_last_injection`). Done after recording, so a failure between the
    # two can only cost a calibration, never duplicate a record.
    mark_last_injection_consumed()

    samples: list[tuple[str, int]] = []
    described: list[tuple[str, int, int]] = []

    # Output pairs are the ONLY calibration source; the injection pair is not
    # implemented (unsound denominator — see module docstring, 0.6.2 note).
    for text, tokens in _text_only_output_pairs(transcript)[:MAX_OUTPUT_PAIRS]:
        if _is_plausible(len(text), tokens):
            samples.append((text, tokens))
            described.append(("output", len(text), tokens))

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
    "CONSUMED_KEY",
    "LAST_INJECTION_FILENAME",
    "LEGACY_LAST_INJECTION_FILENAME",
    "mark_last_injection_consumed",
    "stamp_is_consumed",
    "legacy_last_injection_path",
    "MAX_OUTPUT_PAIRS",
    "PLAUSIBLE_RATIO_BAND",
    "harness_session_id",
    "harvest_and_calibrate",
    "last_injection_path",
    "persist_last_injection",
    "read_last_injection",
    "resolve_transcript",
]
