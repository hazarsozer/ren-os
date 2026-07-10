"""
lib.memory.judge — the LLM pair-judge contract (Task 4, RenOS 0.5.x
learning-brain train).

This module ships the CONTRACT only: no consumer exists yet. 0.5.2's planned
consumers are `wrap` close-out (dedup/contradiction detection over candidate
items before they hit the write door) and a wiki-health sweep (finding
duplicate/contradicting/superseded pages across the existing wiki). Neither
is wired in by this task — that wiring is 0.5.2's job.

Structurally mirrors `skills/wrap/lib/classifier.py`: a prompt builder that
truncates defensively, strict JSON-only parsing via
`lib.adapter.worker.parse_worker_json` (no silent recovery of a bad verdict),
a typed error class, and a fail-closed wrapper that records events via
`lib.instrument.collect.record` instead of raising.

Fail-closed doctrine: any judge failure (no `llm_call` provided, `llm_call`
raises, or its output doesn't parse into a valid verdict) resolves to `None`
for that pair, never a crash and never a guessed verdict. A `None` verdict
means "fall back to whatever deterministic heuristics 0.5.2's caller already
has" — this module makes no claim about what that fallback does; it only
promises never to hand back an invented answer.

This module never writes wiki pages. It answers one narrow question per
pair — duplicate / contradicts / supersedes / unrelated — and returns; any
write decision based on that answer belongs to the (not-yet-built) caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final

from lib.adapter.worker import WorkerOutputError, parse_worker_json
from lib.instrument import collect

VALID_VERDICTS: Final[frozenset[str]] = frozenset(
    {"duplicate", "contradicts", "supersedes", "unrelated"}
)
JUDGE_PAIR_CAP: Final[int] = 10

_MAX_TEXT_CHARS: Final[int] = 4_000

_JUDGE_PROMPT_TEMPLATE: Final[str] = """\
You are comparing TWO pieces of memory text to decide how they relate.

The four verdicts:
- "duplicate" — both say the same thing, just reworded.
- "contradicts" — they assert incompatible facts; both cannot be true.
- "supersedes" — text B is an updated/corrected version of the fact in text A.
- "unrelated" — they concern different things; no meaningful relationship.

Output JSON ONLY (no surrounding prose, no code fence). Schema:

{{"verdict": "duplicate" | "contradicts" | "supersedes" | "unrelated", "confidence": <0.0-1.0>, "reason": "<one sentence>"}}

Text A:
---
{text_a}
---

Text B:
---
{text_b}
---
"""


class JudgeError(Exception):
    """Raised by `judge_pair` when the LLM's response is malformed, carries
    an unrecognized verdict, or a confidence outside [0, 1]. Strict on
    purpose, same discipline as `classifier.ClassifierError` — `judge_pairs`
    catches this and degrades that one pair to `None` rather than guessing."""


@dataclass(frozen=True)
class Verdict:
    kind: str  # "duplicate" | "contradicts" | "supersedes" | "unrelated"
    confidence: float
    reason: str


def _truncate(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    if len(text) > _MAX_TEXT_CHARS:
        return text[-_MAX_TEXT_CHARS:]
    return text


def build_judge_prompt(text_a: str, text_b: str) -> str:
    """Build the strict, JSON-only pair-judge prompt. Each text is
    defensively truncated (from the end, keeping the most recent/final text)
    so a runaway-length pair can't blow the prompt budget."""
    return _JUDGE_PROMPT_TEMPLATE.format(text_a=_truncate(text_a), text_b=_truncate(text_b))


def judge_pair(text_a: str, text_b: str, llm_call: Callable[[str], str]) -> Verdict:
    """Ask `llm_call` to judge how `text_a` and `text_b` relate, parse
    STRICTLY.

    Raises `JudgeError` on anything that isn't a clean
    `{"verdict": <valid>, "confidence": <0-1>, "reason": <str>}` object —
    malformed JSON, wrong shape, an unrecognized verdict string, or a
    confidence outside [0, 1] all raise rather than guessing. `judge_pairs`
    is the intended fail-closed caller; it catches this exception.
    """
    prompt = build_judge_prompt(text_a, text_b)
    raw = llm_call(prompt)

    if not isinstance(raw, str):
        raise JudgeError(f"llm_call must return str, got {type(raw).__name__}")

    try:
        data = parse_worker_json(raw)
    except WorkerOutputError as exc:
        raise JudgeError(f"judge output is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise JudgeError(f"judge output must be a JSON object, got {type(data).__name__}")

    verdict = data.get("verdict")
    if verdict not in VALID_VERDICTS:
        raise JudgeError(f"unknown verdict {verdict!r}; must be one of {sorted(VALID_VERDICTS)}")

    confidence = data.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise JudgeError(f"'confidence' must be a number; got {type(confidence).__name__}")
    if not (0.0 <= confidence <= 1.0):
        raise JudgeError(f"'confidence' must be in [0, 1]; got {confidence!r}")

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        raise JudgeError(f"'reason' must be a string; got {type(reason).__name__}")

    return Verdict(kind=verdict, confidence=float(confidence), reason=reason)


def judge_pairs(
    pairs: list[tuple[str, str]],
    llm_call: Callable[[str], str] | None,
    cap: int = JUDGE_PAIR_CAP,
) -> list[Verdict | None]:
    """Judge each `(text_a, text_b)` pair, NEVER raising. Preserves input
    order; length of the returned list always equals `len(pairs)`.

    - `llm_call` is `None`: every pair resolves to `None`, and exactly ONE
      `collect.record(KIND_JUDGE_EVENT, {"event": "no_llm"})` is emitted
      (not one per pair).
    - Pairs beyond `cap` (0-indexed) resolve to `None` without ever calling
      `llm_call`, and exactly ONE event `{"event": "capped", "dropped": N}`
      is emitted for the whole batch.
    - Any pair within the cap whose `judge_pair` call raises resolves to
      `None`, with one `{"event": "fail_closed"}` event recorded for that
      pair.

    No text content (previews or otherwise) is ever included in recorded
    event payloads — only counts and flags — so the scrub posture used by
    `classifier.gate` isn't needed here.
    """
    if llm_call is None:
        collect.record(collect.KIND_JUDGE_EVENT, {"event": "no_llm"})
        return [None] * len(pairs)

    in_cap = pairs[:cap]
    dropped = len(pairs) - len(in_cap)

    results: list[Verdict | None] = []
    for text_a, text_b in in_cap:
        try:
            results.append(judge_pair(text_a, text_b, llm_call))
        except Exception:  # noqa: BLE001 - any failure here is fail-closed, not fatal
            collect.record(collect.KIND_JUDGE_EVENT, {"event": "fail_closed"})
            results.append(None)

    if dropped > 0:
        collect.record(collect.KIND_JUDGE_EVENT, {"event": "capped", "dropped": dropped})
        results.extend([None] * dropped)

    return results


__all__ = [
    "VALID_VERDICTS",
    "JUDGE_PAIR_CAP",
    "Verdict",
    "JudgeError",
    "build_judge_prompt",
    "judge_pair",
    "judge_pairs",
]
