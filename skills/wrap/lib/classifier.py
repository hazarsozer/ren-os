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

import re
from dataclasses import dataclass
from typing import Callable, Final

from lib.adapter.worker import WorkerOutputError, parse_worker_json
from lib.instrument import collect
from lib.memory import scrub
from lib.memory.taxonomy import Taxonomy, TaxonomyError, classify_placement

VALID_VERDICTS: Final[frozenset[str]] = frozenset({"durable", "session-only", "discard"})
VALID_SCOPES: Final[frozenset[str]] = frozenset({"project", "global"})
VALID_ACTIONS: Final[frozenset[str]] = frozenset({"create", "update"})
VALID_KINDS: Final[frozenset[str]] = frozenset({"concept", "lesson"})

_MAX_ITEM_CHARS: Final[int] = 4_000
_PREVIEW_CHARS: Final[int] = 80
_TITLE_SLUG_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_NO_TAXONOMY_BLOCK: Final[str] = (
    '(no taxonomy available — "kind" must be "lesson", "placement" must be null)'
)

_CLASSIFIER_PROMPT_TEMPLATE: Final[str] = """\
You are deciding whether ONE candidate item from an end-of-session wrap
should be written to durable, cross-session memory — and if so, WHERE.

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

If (and only if) the verdict is "durable", also decide placement:
- "action": "update" when the item is really a refinement, correction, or
  extension of one of the ELIGIBLE UPDATE TARGETS below — pick that page as
  "target_page". You may ONLY pick from that list; if the list is empty or
  nothing fits, use "create" with "target_page": null.
- "scope": "project" when the item is specific to the active project
  ({project}); "global" when it is a cross-project lesson.

Also decide "kind":
- "concept" — structural knowledge about the system being studied (how a
  component works, what connects to what, what owns what). Concepts are
  placed into the project taxonomy below: set "placement" to the
  best-matching node path, or an existing node + ONE new child segment if
  nothing fits (then also set "title": a 2-4 word name for the new node).
- "lesson" — episodic learning about how we work: what failed, what to
  avoid, process learnings. Lessons take no placement.
When in doubt, "lesson". Concepts require scope "project".

Project taxonomy (placement must come from here):
{taxonomy_block}
{branch_notes}

Eligible update targets (pages this session actually read; pick from these
EXACTLY or use "create"):
{targets_block}

Output JSON ONLY (no surrounding prose, no code fence). Schema:

{{"verdict": "durable" | "session-only" | "discard", "reason": "<one sentence>",
 "scope": "project" | "global", "action": "create" | "update",
 "target_page": "<one of the eligible targets>" | null,
 "kind": "concept" | "lesson", "placement": "<taxonomy path>" | null,
 "title": "<2-4 word name>" | null}}

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


class PlacementError(ClassifierError):
    """A DURABLE verdict whose placement (scope/action/target) is invalid.

    Distinct from garden-variety malformation on purpose: the classifier
    affirmed the item is durable, so discarding it silently would lose a
    learning — the caller routes these to the suggestions store instead
    (spec 2026-08-18 §2.3)."""

    def __init__(self, msg: str, *, claimed_scope=None, claimed_action=None,
                 claimed_target=None):
        super().__init__(msg)
        self.verdict = "durable"
        self.reason = msg
        self.claimed_scope = claimed_scope
        self.claimed_action = claimed_action
        self.claimed_target = claimed_target


class ConceptPlacementError(PlacementError):
    """A "concept" verdict whose taxonomy routing is invalid: no taxonomy is
    available, the placement doesn't resolve against it, a new leaf is
    missing a valid title, or the scope isn't "project" (no global taxonomy —
    spec §9).

    Distinct from `PlacementError` on purpose: the caller (Task 3) treats
    these as fail-closed lesson-fallbacks — degrade to a routable lesson
    rather than get stuck as a concept-shaped suggestion nobody can place."""

    def __init__(self, msg: str, *, claimed_scope=None, claimed_action=None,
                 claimed_target=None, claimed_kind=None, claimed_placement=None,
                 claimed_title=None):
        super().__init__(msg, claimed_scope=claimed_scope, claimed_action=claimed_action,
                          claimed_target=claimed_target)
        self.claimed_kind = claimed_kind
        self.claimed_placement = claimed_placement
        self.claimed_title = claimed_title


@dataclass(frozen=True)
class Decision:
    verdict: str   # "durable" | "session-only" | "discard"
    reason: str
    scope: str = "global"          # "project" | "global"
    action: str = "create"         # "create" | "update"
    target_page: str | None = None # required iff action == "update"
    kind: str = "lesson"           # "concept" | "lesson"
    placement: str | None = None   # concept only: taxonomy node path
    title: str | None = None       # concept new-leaf only: 2-4 word name


def build_classifier_prompt(
    item_text: str, *, eligible_targets: tuple[str, ...] = (), project: str | None = None,
    taxonomy_block: str = "", branch_notes: str = "",
) -> str:
    """Build the strict, JSON-only classification prompt for one candidate
    item. Truncates defensively (from the end, keeping the most recent/final
    text) so a runaway-length item can't blow the prompt budget.

    `taxonomy_block` is the rendered project taxonomy (Task 3 supplies it via
    `render_block`); when empty, concept routing is unavailable and the
    prompt tells the LLM "kind" must be "lesson"."""
    if not isinstance(item_text, str):
        raise TypeError(f"item_text must be str, got {type(item_text).__name__}")
    text = item_text
    if len(text) > _MAX_ITEM_CHARS:
        text = text[-_MAX_ITEM_CHARS:]
    targets_block = "\n".join(f"- {t}" for t in eligible_targets) or "(none — action must be \"create\")"
    return _CLASSIFIER_PROMPT_TEMPLATE.format(
        item_text=text, project=project or "(no project in scope)",
        targets_block=targets_block,
        taxonomy_block=taxonomy_block or _NO_TAXONOMY_BLOCK,
        branch_notes=branch_notes,
    )


def _valid_concept_title(title: object) -> bool:
    """A new-leaf title must be a 2-4 word string whose slug — words
    lowercased and joined with '-' — matches the taxonomy segment pattern
    (spec 2026-08-31 §3.1's `_SEGMENT_RE`)."""
    if not isinstance(title, str):
        return False
    words = title.split()
    if not 2 <= len(words) <= 4:
        return False
    slug = "-".join(words).lower()
    return bool(_TITLE_SLUG_RE.match(slug))


def decision_from_data(
    data: dict, *, eligible_targets: tuple[str, ...] = (),
    taxonomy: Taxonomy | None = None,
) -> Decision:
    """Validate one pre-computed verdict object (spec 2026-08-18 §2.2,
    extended 2026-08-31 §3 for concept-tree routing).

    EXACTLY `classify_llm`'s post-parse rules — this IS the extracted body —
    with one refinement: when the verdict is "durable" but scope/action/
    target is invalid, raise `PlacementError` (routable) rather than the
    plain `ClassifierError` (fail-closed discard). Concept-placement
    failures (no taxonomy, unresolvable placement, missing new-leaf title,
    or a global-scope concept) raise `ConceptPlacementError` instead — the
    caller (Task 3) routes those to a lesson-fallback, never a guess."""
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

    durable = verdict == "durable"

    def _placement_or_plain(msg: str) -> ClassifierError:
        if durable:
            return PlacementError(
                msg, claimed_scope=data.get("scope"),
                claimed_action=data.get("action"),
                claimed_target=data.get("target_page"),
            )
        return ClassifierError(msg)

    scope = data.get("scope", "global")
    if scope not in VALID_SCOPES:
        raise _placement_or_plain(
            f"unknown scope {scope!r}; must be one of {sorted(VALID_SCOPES)}")
    action = data.get("action", "create")
    if action not in VALID_ACTIONS:
        raise _placement_or_plain(
            f"unknown action {action!r}; must be one of {sorted(VALID_ACTIONS)}")
    target = data.get("target_page")
    if action == "update":
        if not isinstance(target, str) or target not in eligible_targets:
            raise _placement_or_plain(
                f"update target {target!r} is not in the eligibility set")
    else:
        if target is not None:
            raise _placement_or_plain('target_page must be null when action is "create"')

    kind = data.get("kind", "lesson")
    if kind not in VALID_KINDS:
        raise _placement_or_plain(
            f"unknown kind {kind!r}; must be one of {sorted(VALID_KINDS)}")

    placement = data.get("placement")
    title = data.get("title")

    def _concept_error(msg: str) -> ConceptPlacementError:
        return ConceptPlacementError(
            msg, claimed_scope=data.get("scope"), claimed_action=data.get("action"),
            claimed_target=data.get("target_page"), claimed_kind=kind,
            claimed_placement=placement, claimed_title=title,
        )

    if kind == "lesson":
        if placement is not None or title is not None:
            raise _placement_or_plain(
                'placement and title must be null when kind is "lesson"')
    else:  # kind == "concept"
        if scope == "global":
            raise _concept_error(
                'concepts require scope "project" — there is no global taxonomy (spec §9)')
        if taxonomy is None:
            raise _concept_error("no taxonomy available — concept routing is blind")
        if action == "create":
            if not isinstance(placement, str):
                raise _concept_error('"placement" must be a string for a concept create')
            try:
                result = classify_placement(taxonomy, placement)
            except TaxonomyError as exc:
                raise _concept_error(f"invalid placement: {exc}") from exc
            if result == "new-leaf" and not _valid_concept_title(title):
                raise _concept_error(
                    'a new taxonomy leaf requires a 2-4 word "title"')
        # action == "update": today's target_page eligibility rule (checked
        # above) already applies — no additional concept-specific check.

    return Decision(
        verdict=verdict, reason=reason, scope=scope, action=action,
        target_page=target if action == "update" else None,
        kind=kind,
        placement=placement if kind == "concept" else None,
        title=title if kind == "concept" else None,
    )


def classify_llm(
    item_text: str, llm_call: Callable[[str], str], *,
    eligible_targets: tuple[str, ...] = (), project: str | None = None,
    taxonomy: Taxonomy | None = None, taxonomy_block: str = "", branch_notes: str = "",
) -> Decision:
    """The REAL gate: ask `llm_call` to classify `item_text`, parse STRICTLY.

    Raises `ClassifierError` on anything that isn't a clean
    `{"verdict": <valid>, "reason": <str>, "scope": <valid>, "action": <valid>,
    "target_page": <str|null>, "kind": <valid>, "placement": <str|null>,
    "title": <str|null>}` object — malformed JSON, wrong shape, or an
    unrecognized verdict/scope/action/kind string all raise rather than
    guessing. `gate()` is the only intended caller in production; it catches
    this exception and falls back to `classify_deterministic`.
    """
    prompt = build_classifier_prompt(
        item_text, eligible_targets=eligible_targets, project=project,
        taxonomy_block=taxonomy_block, branch_notes=branch_notes,
    )
    raw = llm_call(prompt)

    if not isinstance(raw, str):
        raise ClassifierError(f"llm_call must return str, got {type(raw).__name__}")

    try:
        data = parse_worker_json(raw)
    except WorkerOutputError as exc:
        raise ClassifierError(f"classifier output is not valid JSON: {exc}") from exc

    return decision_from_data(data, eligible_targets=eligible_targets, taxonomy=taxonomy)


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


def gate(
    item_text: str, llm_call: Callable[[str], str] | None = None, *,
    eligible_targets: tuple[str, ...] = (), project: str | None = None,
    taxonomy: Taxonomy | None = None, taxonomy_block: str = "", branch_notes: str = "",
) -> Decision:
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
            return classify_llm(item_text, llm_call,
                                eligible_targets=eligible_targets, project=project,
                                taxonomy=taxonomy, taxonomy_block=taxonomy_block,
                                branch_notes=branch_notes)
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


def gate_precomputed(
    item_text: str, data: object, *,
    eligible_targets: tuple[str, ...] = (), project: str | None = None,
    taxonomy: Taxonomy | None = None,
) -> Decision:
    """`gate()`'s sibling for the verdicts-as-data transport (spec §2.2):
    validate a pre-computed verdict instead of calling an LLM.

    `PlacementError` (and its `ConceptPlacementError` subclass) PROPAGATES —
    the caller owns the route to suggestions / lesson-fallback. Any other
    malformation is fail-closed exactly like `gate()`'s LLM-error path:
    record a classifier_event and fall back to deterministic."""
    preview = str(item_text)[:_PREVIEW_CHARS]
    if scrub.scan(str(item_text)):
        preview = "<redacted: secret-shaped content>"
    try:
        return decision_from_data(data, eligible_targets=eligible_targets, taxonomy=taxonomy)  # type: ignore[arg-type]
    except PlacementError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail-closed, mirrors gate()
        collect.record(
            collect.KIND_CLASSIFIER_EVENT,
            {"event": "fail_closed", "reason": str(exc), "item_preview": preview},
        )
        return classify_deterministic(item_text)


__all__ = [
    "VALID_VERDICTS",
    "VALID_SCOPES",
    "VALID_ACTIONS",
    "VALID_KINDS",
    "Decision",
    "ClassifierError",
    "PlacementError",
    "ConceptPlacementError",
    "build_classifier_prompt",
    "decision_from_data",
    "classify_llm",
    "classify_deterministic",
    "gate",
    "gate_precomputed",
]
