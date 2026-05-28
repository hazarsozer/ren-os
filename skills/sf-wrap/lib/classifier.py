"""
sf-wrap classifier — signal-threshold prompt construction + LLM output parsing.

Per references/signal-threshold.md, the classifier evaluates a session
transcript against 7 labels (six signal categories + 'none') with a deliberate
BIAS TOWARD 'none'. The wiki is sacred; most sessions are routine; only
genuinely high-signal sessions get promoted.

This module isolates the LLM-dependent layer from the rest of /sf:wrap so the
prompt + parser can be unit-tested deterministically. The actual LLM
invocation (`classify()`) is stubbed pending integration; the prompt builder
and parser are real + ship as load-bearing primitives.

Per dotfiles python/coding-style.md: PEP 8, type annotations, frozen
dataclasses, no print statements (logging only).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final, get_args

from .types import CandidateArtifact, ClassifierResult, SignalLabel

logger = logging.getLogger(__name__)


# All valid label strings — derived from the SignalLabel Literal type.
VALID_LABELS: Final[frozenset[str]] = frozenset(get_args(SignalLabel))

# Token budget for the session transcript portion of the prompt.
# If transcripts are larger, the caller is responsible for truncation
# (most recent N turns) before invoking the classifier.
MAX_TRANSCRIPT_CHARS: Final[int] = 30_000

# The discipline-narrowing prompt — per references/signal-threshold.md's
# "Classifier prompt template" section. Keeps the LLM's output structure
# strict (JSON only; no surrounding prose).
_CLASSIFIER_PROMPT_TEMPLATE: Final[str] = """\
You are evaluating whether a Claude Code session produced wiki-worthy signal.
Per ADR-009 and references/signal-threshold.md: **bias toward `none`**. The
wiki is sacred; most sessions are routine. Only escalate when the criteria
are CLEARLY met.

The seven labels are:

- `none` — routine work; no architectural decision, reusable pattern, non-obvious lesson, stack change, milestone, or purpose shift. DEFAULT.
- `decision` — a deliberate architectural / scope / tooling choice future sessions must know to avoid re-litigating. NOT trial-and-error; NOT routine refactors.
- `pattern` — a reusable solution that other projects (or future sessions) would benefit from. NOT trivial stack choices.
- `lesson` — a non-obvious learning ("gotcha") that, if forgotten, would cost time again. NOT routine debugging or "tools doing their job."
- `stack_change` — the project's tech stack shifted in a way that affects future work. NOT patch bumps; NOT renames.
- `milestone` — a roadmap milestone is now complete, or a new phase starts. NOT sub-tasks within an ongoing milestone.
- `purpose_shift` — VERY RARE. The project's purpose, scope, or target user changed.

Output JSON ONLY (no surrounding prose). Schema:

{{
  "labels": ["<label1>", ...],
  "reasoning": "<1-3 sentences justifying the label(s); explicitly cite the transcript phrase or pattern that justifies escalating beyond 'none'>",
  "candidate_artifacts": [
    {{
      "label": "<one of the 7>",
      "proposed_title": "<kebab-case slug>",
      "proposed_summary": "<one paragraph, <=300 chars>",
      "target_file": "<wiki path relative to wiki root>"
    }}
  ]
}}

Multi-label is allowed but rare. `candidate_artifacts` is empty when labels is exactly `["none"]`.

Active project: {project_or_unscoped}

The session transcript follows:
---
{transcript}
"""


def build_classifier_prompt(
    transcript_text: str,
    *,
    project_name: str | None,
) -> str:
    """
    Construct the classifier prompt from a session transcript.

    Args:
        transcript_text: The session log (already truncated to MAX_TRANSCRIPT_CHARS
            if needed by the caller; this function will hard-cap defensively).
        project_name: The active project name, or None for unscoped sessions.

    Returns:
        The complete prompt string ready to send to an LLM.
    """
    if not isinstance(transcript_text, str):
        raise TypeError(f"transcript_text must be str, got {type(transcript_text).__name__}")

    if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
        truncated = transcript_text[-MAX_TRANSCRIPT_CHARS:]
        logger.info(
            "Truncated transcript from %d to %d chars (keeping last)",
            len(transcript_text), MAX_TRANSCRIPT_CHARS,
        )
        transcript_text = "[...earlier turns truncated for length...]\n" + truncated

    project_label = project_name if project_name else "unscoped"

    return _CLASSIFIER_PROMPT_TEMPLATE.format(
        project_or_unscoped=project_label,
        transcript=transcript_text,
    )


def parse_classifier_output(raw_json: str) -> ClassifierResult:
    """
    Parse the LLM's JSON output into a ClassifierResult.

    Validates:
      - JSON is well-formed
      - `labels` is a non-empty list of valid SignalLabel strings
      - `reasoning` is a string (may be empty if labels == ['none'] is the
        common case, but we accept it either way)
      - `candidate_artifacts` is a list of objects with the required fields
        (when labels == ['none'], MUST be empty per the prompt's schema)

    Args:
        raw_json: The LLM's raw output. May have surrounding whitespace; will
            be stripped. If the LLM wrapped its JSON in a code fence or
            preamble despite the "JSON ONLY" instruction, this function tries
            to recover the embedded JSON block; if recovery fails, raises.

    Returns:
        ClassifierResult with frozen tuples (labels, candidate_artifacts).

    Raises:
        ValueError: if the JSON is malformed or doesn't match the expected
            schema. The error message names the specific violation so
            re-prompting can be targeted.
    """
    if not isinstance(raw_json, str):
        raise ValueError(f"raw_json must be str, got {type(raw_json).__name__}")

    # Defensive recovery: if the LLM despite instructions wrapped in fences
    # or added preamble, try to find a JSON object substring.
    text = raw_json.strip()
    text = _extract_json_block(text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"classifier output is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"classifier output must be a JSON object, got {type(data).__name__}"
        )

    # Validate labels
    raw_labels = data.get("labels")
    if not isinstance(raw_labels, list) or not raw_labels:
        raise ValueError(
            f"'labels' must be a non-empty list; got {raw_labels!r}"
        )
    for label in raw_labels:
        if not isinstance(label, str):
            raise ValueError(f"'labels' items must be strings; got {label!r}")
        if label not in VALID_LABELS:
            raise ValueError(
                f"unknown label {label!r}; must be one of {sorted(VALID_LABELS)}"
            )
    labels: tuple[SignalLabel, ...] = tuple(raw_labels)

    reasoning = data.get("reasoning", "")
    if not isinstance(reasoning, str):
        raise ValueError(f"'reasoning' must be a string; got {type(reasoning).__name__}")

    # Validate candidate_artifacts
    raw_artifacts = data.get("candidate_artifacts", [])
    if not isinstance(raw_artifacts, list):
        raise ValueError(
            f"'candidate_artifacts' must be a list; got {type(raw_artifacts).__name__}"
        )

    # When labels == ['none'], the schema requires candidate_artifacts to be empty.
    if list(labels) == ["none"] and raw_artifacts:
        raise ValueError(
            "'candidate_artifacts' must be empty when labels is exactly ['none']; "
            f"got {len(raw_artifacts)} artifact(s)"
        )

    artifacts = tuple(_parse_artifact(a, i) for i, a in enumerate(raw_artifacts))

    return ClassifierResult(
        labels=labels,
        reasoning=reasoning,
        candidate_artifacts=artifacts,
    )


def _parse_artifact(raw: Any, index: int) -> CandidateArtifact:
    """Parse one candidate_artifacts entry."""
    if not isinstance(raw, dict):
        raise ValueError(
            f"candidate_artifacts[{index}] must be an object; got {type(raw).__name__}"
        )

    label = raw.get("label")
    if label not in VALID_LABELS:
        raise ValueError(
            f"candidate_artifacts[{index}].label is {label!r}; must be a valid SignalLabel"
        )

    title = raw.get("proposed_title")
    if not isinstance(title, str) or not title:
        raise ValueError(
            f"candidate_artifacts[{index}].proposed_title must be a non-empty string"
        )

    summary = raw.get("proposed_summary")
    if not isinstance(summary, str) or not summary:
        raise ValueError(
            f"candidate_artifacts[{index}].proposed_summary must be a non-empty string"
        )

    target_file = raw.get("target_file")
    if not isinstance(target_file, str) or not target_file:
        raise ValueError(
            f"candidate_artifacts[{index}].target_file must be a non-empty string"
        )

    return CandidateArtifact(
        label=label,
        proposed_title=title,
        proposed_summary=summary,
        target_file=target_file,
    )


def _extract_json_block(text: str) -> str:
    """
    Defensive recovery: if the LLM ignored "JSON ONLY" and wrapped its output
    in a code fence or added preamble/trailing prose, try to find the JSON
    object.

    Strategy (no startswith shortcut — see comment below):
      1. If it contains a ```json ... ``` fence, extract that block.
      2. If it contains a bare ``` ... ``` fence, extract that block.
      3. Otherwise, slice from the FIRST `{` to the LAST `}` and use that as
         the JSON candidate. This handles three cases uniformly:
           a. Clean JSON (whole string is the object) — first/last bracket the full text
           b. Preamble + JSON ("Here is the result: {...}") — leading prose trimmed
           c. JSON + trailing prose ("{...}\n\nHope that helps!") — trailing prose trimmed
      4. If no braces found, return text as-is and let `json.loads` raise.

    Why no `startswith("{")` shortcut: it would return the whole text including
    any trailing prose, which would cause json.loads to fail on the trailing
    junk. The first-{/last-} strategy handles cleanly-formatted input AND
    trailing-prose input via the same code path.
    """
    # Look for fenced code block first (most explicit recovery signal)
    for fence in ("```json\n", "```\n"):
        if fence in text:
            start = text.index(fence) + len(fence)
            end = text.find("\n```", start)
            if end == -1:
                end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()

    # First `{` to last `}` — handles clean JSON, preamble, AND trailing prose
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return text[first : last + 1]

    return text  # no braces; let json.loads fail with a clearer error


# ---------------------------------------------------------------------------
# Main entry — STUBBED pending LLM-subprocess integration
# ---------------------------------------------------------------------------


def classify(
    transcript_text: str,
    *,
    project_name: str | None,
) -> ClassifierResult:
    """
    Classify a session transcript against the 7 signal labels.

    V1 STATUS: STUBBED. The LLM invocation layer (subprocess `claude --bare
    --print --output-format=json ...` or equivalent) is deferred until the
    /sf:wrap orchestration layer is wired (in `lib/__init__.py`'s `wrap()`).

    The pure-logic primitives in this module — `build_classifier_prompt()`
    and `parse_classifier_output()` — are real and tested. They compose:

        prompt = build_classifier_prompt(transcript, project_name=project)
        raw_response = <invoke LLM with prompt>      # the stubbed part
        result = parse_classifier_output(raw_response)

    Args:
        transcript_text: Session transcript.
        project_name: Active project, or None for unscoped.

    Returns:
        ClassifierResult.

    Raises:
        NotImplementedError: until the LLM invocation is wired in.
    """
    raise NotImplementedError(
        "classify() LLM invocation layer not yet implemented. The prompt "
        "builder + output parser ship as composable primitives; the actual "
        "subprocess call will be wired when lib/__init__.py's wrap() "
        "orchestration lands. See SKILL.md §pipeline step 2 + "
        "references/signal-threshold.md for the design."
    )
