"""
sf-wrap classifier — signal-threshold classification + LLM-path primitives.

Per references/signal-threshold.md, the classifier evaluates a session
transcript against 7 labels (six signal categories + 'none') with a deliberate
BIAS TOWARD 'none'. The wiki is sacred; most sessions are routine; only
genuinely high-signal sessions get promoted.

`classify()` is the **default production path (EXPERIMENTAL, ADR-031 bike-method)**:
a conservative DETERMINISTIC heuristic — it scans the combined transcript
(session log + `/ren:note` pins) for deliberate, word-boundary signal phrases,
biases HARD to `none`, and NEVER raises. Pinned notes DOMINATE (lower
threshold) because an explicit `/ren:note` is a deliberate signal. It only
proposes `candidate_artifacts` for fired `decision`/`pattern` labels (the page-
creating ones); the rest contribute their label (→ log append) without a new
file. Limits: phrase-driven, no semantic understanding — it can miss subtly-
phrased signal and (rarely) over-fire on a deliberate keyword used casually.

`build_classifier_prompt()` + `parse_classifier_output()` ship as the FUTURE
LLM path (unused by the default deterministic classify()). Per dotfiles
python/coding-style.md: PEP 8, type annotations, frozen dataclasses, no print.
"""

from __future__ import annotations

import json
import logging
import re
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
# Default production classifier — conservative deterministic heuristic
# (EXPERIMENTAL, ADR-031 bike-method). NEVER raises; biases hard to `none`.
# ---------------------------------------------------------------------------

# Priority order for picking the primary label + capping multi-label output.
# Mirrors diff_plan._primary_label so the deterministic path and the diff
# planner agree on which label dominates.
_PRIORITY_ORDER: Final[tuple[SignalLabel, ...]] = (
    "purpose_shift", "decision", "stack_change", "milestone", "pattern", "lesson",
)
_MAX_LABELS: Final[int] = 2
_MAX_SUMMARY_CHARS: Final[int] = 300

# Marker the orchestrator (lib/__init__.py:_gather_transcript) uses to join
# `/ren:note` pins onto the session log. Everything from here on is "pins".
_PINS_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"^#{1,6}\s+Pinned notes", re.IGNORECASE | re.MULTILINE
)

# Deliberate, high-signal phrases per label (word-boundary, case-insensitive).
# These fire in EITHER the session log OR the pinned-notes section. They are
# intentionally specific so routine coding chatter does not trip them — the
# whole discipline (ADR-009) is to keep the wiki high-signal, so we under-fire.
_STRICT_PATTERNS: Final[dict[SignalLabel, tuple[re.Pattern[str], ...]]] = {
    "decision": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\bwe\s+decided\b",
        r"\bdecided\s+to\s+(?:use|go\s+with|adopt|drop|switch|standardi[sz]e)\b",
        r"\bwe(?:'re|\s+are)\s+choosing\b",
        r"\bwe\s+chose\b",
        r"\bchoosing\b[^.\n]{0,40}\bover\b",
        r"\bstandardi[sz](?:e|ing|ed)\s+on\b",
        r"\bsettled\s+on\b",
        r"\bdecision:\s",
    )),
    "pattern": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\breusable\s+pattern\b",
        r"\b(?:let'?s\s+)?codify\b",
        r"\bis\s+reusable\b",
        r"\bshould\s+apply\s+across\b",
        r"\bpattern:\s",
    )),
    "lesson": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\bgotcha\b",
        r"\blesson\s+learned\b",
        r"\blearned\s+the\s+hard\s+way\b",
        r"\bthe\s+hard\s+way\b",
        r"\bfootgun\b",
        r"\blesson:\s",
        r"\bTIL\b",
    )),
    "stack_change": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\bswitch(?:ed|ing)?\s+from\b[^.\n]{0,40}\bto\b",
        r"\bmigrat(?:e|ed|ing)\s+(?:from|to)\b",
        r"\breplac(?:e|ed|ing)\b[^.\n]{0,40}\bwith\b",
        r"\b(?:removing|removed)\b[^.\n]{0,40}\bin\s+favor\s+of\b",
        r"\bstack\s+change\b",
    )),
    "milestone": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\bmilestone\b",
        r"\bphase\s+\w+\s+(?:is\s+)?(?:complete|done|finished)\b",
        r"\bentering\s+phase\b",
        r"\bshipped\s+to\s+(?:staging|production|prod)\b",
        r"\bMVP\s+(?:is\s+)?(?:done|complete|shipped)\b",
        r"\broadmap\s+item\b",
    )),
    "purpose_shift": tuple(re.compile(p, re.IGNORECASE) for p in (
        # STRONG exact phrases only — purpose_shift is VERY RARE (signal-threshold §6).
        r"\bpivot(?:ing|ed)?\s+from\b[^.\n]{0,40}\bto\b",
        r"\bpivot(?:ing|ed)?\s+to\b",
        r"\bscope\s+expanded\s+to\b",
        r"\btarget\s+users?\s+shifted\b",
        r"\bpurpose\s+(?:shift|changed)\b",
    )),
}

# Looser triggers applied ONLY to the pinned-notes section — pins DOMINATE
# (lower threshold). A friend who explicitly `/ren:note`-pinned something is
# signalling intent, so a single deliberate keyword in a pin is enough; the
# raw session log still needs a full strict phrase. purpose_shift is absent —
# it requires a strong exact phrase even in a pin.
_PIN_LOOSE_PATTERNS: Final[dict[SignalLabel, tuple[re.Pattern[str], ...]]] = {
    "decision": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\bdecided\b", r"\bdecision\b",
    )),
    "pattern": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\bpattern\b", r"\breusable\b",
    )),
    "lesson": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\blesson\b", r"\bgotcha\b", r"\bTIL\b",
    )),
    "stack_change": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\bmigrat(?:e|ed|ing)\b", r"\bswitched\s+from\b",
    )),
    "milestone": tuple(re.compile(p, re.IGNORECASE) for p in (
        r"\bmilestone\b", r"\bshipped\b",
    )),
}

# Filler/trigger words dropped when deriving a kebab title from a matched line.
_TITLE_STOPWORDS: Final[frozenset[str]] = frozenset({
    "we", "the", "a", "an", "to", "of", "on", "in", "for", "and", "or", "is",
    "are", "our", "i", "it", "this", "that", "with", "go", "use", "using",
    "decided", "decision", "choosing", "chose", "chose", "codify", "lesson",
    "gotcha", "pattern", "reusable", "over", "into",
})


def _split_pins(transcript_text: str) -> tuple[str, str]:
    """Split the combined transcript into (session_log, pinned_notes).

    The orchestrator joins pins under a `## Pinned notes …` header. If absent,
    everything is session log and pins is empty.
    """
    m = _PINS_MARKER_RE.search(transcript_text)
    if m is None:
        return transcript_text, ""
    return transcript_text[: m.start()], transcript_text[m.start():]


def _line_around(text: str, idx: int) -> str:
    """Return the (stripped) single line of `text` containing offset `idx`."""
    start = text.rfind("\n", 0, idx) + 1
    end = text.find("\n", idx)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def _first_match_snippet(
    patterns: tuple[re.Pattern[str], ...], text: str
) -> str | None:
    """Return the line containing the first matching pattern, or None."""
    if not text:
        return None
    for pat in patterns:
        m = pat.search(text)
        if m:
            return _line_around(text, m.start())
    return None


def _none_result(reason: str) -> ClassifierResult:
    """A `none` result with empty artifacts (honors the none⇒empty invariant)."""
    return ClassifierResult(
        labels=("none",),
        reasoning=f"none — {reason}.",
        candidate_artifacts=(),
    )


def _kebab_title(snippet: str, *, max_words: int = 8) -> str:
    """Derive a kebab-case title from a matched line, dropping filler words."""
    words = [w for w in re.findall(r"[a-z0-9]+", snippet.lower()) if w not in _TITLE_STOPWORDS]
    slug = "-".join(words[:max_words])
    return slug or "session-signal"


def _build_artifact(
    label: SignalLabel, snippet: str, project_name: str | None
) -> CandidateArtifact:
    """Build a CandidateArtifact for a fired `decision`/`pattern` label.

    `target_file` is informational (per signal-threshold.md's wiki targets);
    the diff planner recomputes the real path from project_name + title.
    """
    title = _kebab_title(snippet)
    summary = snippet[:_MAX_SUMMARY_CHARS].strip() or f"{label} signal from this session"
    kind_dir = "decisions" if label == "decision" else "patterns"
    if project_name:
        target_file = f"wiki/projects/{project_name}/{kind_dir}/{title}.md"
    else:
        target_file = f"wiki/{kind_dir}/{title}.md"
    return CandidateArtifact(
        label=label,
        proposed_title=title,
        proposed_summary=summary,
        target_file=target_file,
    )


def classify(
    transcript_text: str,
    *,
    project_name: str | None,
) -> ClassifierResult:
    """
    Classify a session transcript against the 7 signal labels.

    DEFAULT PRODUCTION PATH (EXPERIMENTAL — ADR-031 bike-method): a conservative
    deterministic heuristic. It scans the combined transcript (session log +
    `/ren:note` pins) for deliberate, word-boundary signal phrases. It biases
    HARD to `none` and NEVER raises — every failure mode degrades to `none`.

    Behavior:
      - Pinned notes DOMINATE: a single deliberate keyword in a pin fires its
        label (lower threshold); the raw session log needs a full strict phrase.
      - `candidate_artifacts` are produced ONLY for fired `decision`/`pattern`
        (the page-creating labels). Other labels contribute their label (→ log
        append) with no new file. Honors `none ⇒ no artifacts`.
      - Multi-label is capped at ~2, ordered by priority.

    Limits (why EXPERIMENTAL): phrase-driven, no semantic understanding — misses
    subtly-phrased signal; can rarely over-fire on a deliberate keyword used
    casually. The LLM path (`build_classifier_prompt` + `parse_classifier_output`)
    is the future upgrade. Deliberately takes NO file-change-count input (that
    would conflate wiki-maintenance files with project files — the F3 trap).

    Args:
        transcript_text: Combined session transcript (log + pins). Any non-str
            or empty value degrades to `none`.
        project_name: Active project, or None for unscoped.

    Returns:
        ClassifierResult (never raises).
    """
    if not isinstance(transcript_text, str) or not transcript_text.strip():
        return _none_result("empty or non-text transcript")

    log_text, pins_text = _split_pins(transcript_text)

    fired: dict[SignalLabel, str] = {}  # label -> matched-line snippet

    # 1) Strict deliberate phrases — fire in EITHER the log or the pins.
    for label, patterns in _STRICT_PATTERNS.items():
        snippet = _first_match_snippet(patterns, log_text)
        if snippet is None:
            snippet = _first_match_snippet(patterns, pins_text)
        if snippet is not None:
            fired[label] = snippet

    # 2) Looser pin-only triggers — pins dominate (lower threshold).
    for label, patterns in _PIN_LOOSE_PATTERNS.items():
        if label in fired:
            continue
        snippet = _first_match_snippet(patterns, pins_text)
        if snippet is not None:
            fired[label] = snippet

    if not fired:
        return _none_result("no deliberate high-signal phrase detected; routine session")

    # Multi-label cap (~2), ordered by priority.
    ordered: list[SignalLabel] = [l for l in _PRIORITY_ORDER if l in fired][:_MAX_LABELS]

    artifacts = tuple(
        _build_artifact(label, fired[label], project_name)
        for label in ordered
        if label in ("decision", "pattern")
    )

    matched = "; ".join(f'{l}: "{fired[l][:80]}"' for l in ordered)
    reasoning = (
        "Deterministic classifier (EXPERIMENTAL) matched "
        + ", ".join(f"`{l}`" for l in ordered)
        + f" on a deliberate phrase — {matched}"
    )

    return ClassifierResult(
        labels=tuple(ordered),
        reasoning=reasoning[:500],
        candidate_artifacts=artifacts,
    )
