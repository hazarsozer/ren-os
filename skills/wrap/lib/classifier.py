"""
skills.wrap.lib.classifier — the durable-item classifier gate (Task 4.1,
RenOS 0.2 Phase 4).

Adapted from donor `skills/wrap/lib/classifier.py`'s KEY 0.1 finding (per the
harvest map): donor shipped an LLM prompt/parse path that was built but NEVER
WIRED IN — `classify()`'s deterministic heuristic was the only thing actually
called. That gap between "built" and "used" was the 0.1 capability audit's
headline broken promise (spec exit criterion 4).

0.2 fixes this by SWAPPING the roles rather than repeating the mistake:
  - `classify_llm` (adapted from donor's `build_classifier_prompt` +
    `parse_classifier_output` discipline: strict JSON-only parsing, no
    silent recovery of a bad verdict) is now the REAL gate — it is actually
    called by `gate()` below, not left dangling.
  - `classify_deterministic` (donor's role: NEVER raises, degrades safely)
    is now the FALLBACK, used only when there's no LLM available or the LLM
    path errors. Per spec §3.1 "no LLM at the queue"-adjacent discipline for
    durable writes: `classify_deterministic` may ONLY return "session-only" or
    "discard" — it can NEVER promote something to durable memory on its own.
    Fail-closed means "when in doubt, don't write it down forever", not
    "when in doubt, guess."

Donor's classifier answers "which of 7 whole-session signal labels fired?".
This one answers a narrower, per-candidate-item question: "should THIS one
item become durable memory?" — the shape is simpler (three verdicts, one
item at a time) because wrap's SKILL.md now does the session-level narrative
work (L1) and item extraction itself; this module only gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Final

from lib.adapter.worker import WorkerOutputError, parse_worker_json
from lib.instrument import collect
from lib.memory import scrub

VALID_VERDICTS: Final[frozenset[str]] = frozenset({"durable", "session-only", "discard"})

_MAX_ITEM_CHARS: Final[int] = 4_000
_PREVIEW_CHARS: Final[int] = 80

_CLASSIFIER_PROMPT_TEMPLATE: Final[str] = """\
You are deciding whether ONE candidate item from an end-of-session wrap
should be written to durable, cross-session memory.

Bias HARD toward NOT durable: durable memory is sacred and cheap to pollute,
expensive to clean up later. Only answer "durable" when the item is a
genuine, reusable lesson, decision, or fact that a FUTURE session would
concretely benefit from recalling.

The three verdicts:
- "durable" — a genuine, reusable, cross-session-worthy fact, decision, or
  lesson. NOT routine chatter, NOT an obvious restatement of the task.
- "session-only" — true and relevant to this session, but not worth carrying
  forward past it.
- "discard" — noise, ephemera, or anything that must never be written down,
  including anything that resembles a secret, credential, password, or token.

Output JSON ONLY (no surrounding prose, no code fence). Schema:

{{"verdict": "durable" | "session-only" | "discard", "reason": "<one sentence>"}}

Candidate item:
---
{item_text}
---
"""


class ClassifierError(Exception):
    """Raised by `classify_llm` when the LLM's response is malformed or
    carries an unrecognized verdict. Strict on purpose — silently coercing a
    bad response into a guess is exactly the failure mode fail-closed exists
    to avoid; `gate()` catches this and falls back to the deterministic path."""


@dataclass(frozen=True)
class Decision:
    verdict: str   # "durable" | "session-only" | "discard"
    reason: str


def build_classifier_prompt(item_text: str) -> str:
    """Build the strict, JSON-only classification prompt for one candidate
    item. Truncates defensively (from the end, keeping the most recent/final
    text) so a runaway-length item can't blow the prompt budget."""
    if not isinstance(item_text, str):
        raise TypeError(f"item_text must be str, got {type(item_text).__name__}")
    text = item_text
    if len(text) > _MAX_ITEM_CHARS:
        text = text[-_MAX_ITEM_CHARS:]
    return _CLASSIFIER_PROMPT_TEMPLATE.format(item_text=text)


def classify_llm(item_text: str, llm_call: Callable[[str], str]) -> Decision:
    """The REAL gate: ask `llm_call` to classify `item_text`, parse STRICTLY.

    Raises `ClassifierError` on anything that isn't a clean
    `{"verdict": <valid>, "reason": <str>}` object — malformed JSON, wrong
    shape, or an unrecognized verdict string all raise rather than guessing.
    `gate()` is the only intended caller in production; it catches this
    exception and falls back to `classify_deterministic`.
    """
    prompt = build_classifier_prompt(item_text)
    raw = llm_call(prompt)

    if not isinstance(raw, str):
        raise ClassifierError(f"llm_call must return str, got {type(raw).__name__}")

    try:
        data = parse_worker_json(raw)
    except WorkerOutputError as exc:
        raise ClassifierError(f"classifier output is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ClassifierError(
            f"classifier output must be a JSON object, got {type(data).__name__}"
        )

    verdict = data.get("verdict")
    if verdict not in VALID_VERDICTS:
        raise ClassifierError(
            f"unknown verdict {verdict!r}; must be one of {sorted(VALID_VERDICTS)}"
        )

    reason = data.get("reason", "")
    if not isinstance(reason, str):
        raise ClassifierError(f"'reason' must be a string; got {type(reason).__name__}")

    return Decision(verdict=verdict, reason=reason)


def classify_deterministic(item_text: str) -> Decision:
    """The FALLBACK: NEVER raises, and may ONLY return "session-only" or
    "discard" — never "durable". No LLM in this path means no basis to
    promote anything to durable memory; fail-closed is "don't write it down
    forever", not "guess and hope".
    """
    if not isinstance(item_text, str) or not item_text.strip():
        return Decision(verdict="discard", reason="empty or non-text input")
    return Decision(
        verdict="session-only",
        reason="deterministic fallback (no LLM verification available); never promotes to durable",
    )


def gate(item_text: str, llm_call: Callable[[str], str] | None = None) -> Decision:
    """The single entry point `wrap_session` (and anything else gating a
    durable-write candidate) calls.

    - `llm_call` given and it succeeds cleanly: returns `classify_llm`'s
      Decision directly.
    - `llm_call` given but it (or the parse) raises: records a
      `classifier_event` with `"event": "fail_closed"` via
      `lib.instrument.collect`, then falls back to `classify_deterministic`.
    - `llm_call` is `None` (no LLM available at all): records a
      `classifier_event` with `"event": "no_llm"`, then falls back to
      `classify_deterministic` directly — no attempt, no exception needed.
    """
    preview = str(item_text)[:_PREVIEW_CHARS]
    # Defense-in-depth: metrics JSONL is part of the instrumentation surface
    # (docs/data-flow.md); never let secret-shaped content into event previews.
    if scrub.scan(str(item_text)):
        preview = "<redacted: secret-shaped content>"

    if llm_call is not None:
        try:
            return classify_llm(item_text, llm_call)
        except Exception as exc:  # noqa: BLE001 - any failure here is fail-closed, not fatal
            collect.record(
                collect.KIND_CLASSIFIER_EVENT,
                {"event": "fail_closed", "reason": str(exc), "item_preview": preview},
            )
            return classify_deterministic(item_text)

    collect.record(
        collect.KIND_CLASSIFIER_EVENT,
        {"event": "no_llm", "item_preview": preview},
    )
    return classify_deterministic(item_text)


__all__ = [
    "VALID_VERDICTS",
    "Decision",
    "ClassifierError",
    "build_classifier_prompt",
    "classify_llm",
    "classify_deterministic",
    "gate",
]
