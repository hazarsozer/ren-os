# Wrap Knowledge-Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let wrap UPDATE existing session-surfaced knowledge pages and place durable creates in project scope (unfreezing the KB — #60 doctrine-first slice, #57), and give aging facts a mechanical refresh path (#39).

**Architecture:** Extend the existing durable-item classifier (`gate`) with scope/action/target fields chosen from a mechanically-assembled eligibility set; add a strict merge call for updates; route trust-user updates to the suggestions store; land project-scoped creates under `projects/<slug>/knowledge/lessons/` with folder-note hubs so the dormant #54 D4 auto-pointer fires; add a `ren-volatile` marker convention plus a wiki-health `stale_facts` sweep with two mechanical checkers.

**Tech Stack:** Python 3.13 via `uv`, pytest, existing RenOS libs (`lib.memory.queue`, `lib.instrument.collect`, `lib.suggestions`).

**Spec:** `docs/superpowers/specs/2026-08-14-wrap-knowledge-flow-design.md`

## Global Constraints

- Run everything with `uv run pytest ...` from the repo root (never system python3).
- ALL wiki writes go through the single door (`propose_and_apply` / `apply_write`) — never `Path.write_text` to a wiki page.
- Fail-closed discipline: any malformed LLM output gates the item out; the deterministic fallback may NEVER return "durable" (existing invariant, keep it).
- Wrap close-out must never crash: new duties follow the #54 isolated-duty pattern (own try/except, warn on failure).
- Producer string for wrap's writes stays `"wrap"`; link/hub bookkeeping writes use `writer="routine"`, durable content writes use `writer="llm-auto"` (see `_run_link_duties`'s `_queue_update` docstring for why).
- `lib.suggestions.record()` does not validate `producer` (verified) — `producer="wrap"` is fine.
- Commit after every task; commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Classifier v2 — scope / action / target

**Files:**
- Modify: `skills/wrap/lib/classifier.py`
- Test: `tests/skills/wrap/test_classifier.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Decision(verdict, reason, scope, action, target_page)` (frozen dataclass; `scope: str = "global"`, `action: str = "create"`, `target_page: str | None = None`); `classify_llm(item_text, llm_call, *, eligible_targets: tuple[str, ...] = (), project: str | None = None) -> Decision`; `gate(item_text, llm_call=None, *, eligible_targets=(), project=None) -> Decision`; `VALID_SCOPES`, `VALID_ACTIONS` frozensets. Tasks 4 and 8 rely on these exact names.

- [ ] **Step 1: Write the failing tests** (append to `tests/skills/wrap/test_classifier.py`, following its existing fake-`llm_call` style):

```python
import json

from skills.wrap.lib.classifier import (
    Decision, gate, classify_llm, ClassifierError,
    VALID_SCOPES, VALID_ACTIONS,
)


def _llm(payload: dict):
    return lambda prompt: json.dumps(payload)


def test_decision_v2_defaults_are_create_global():
    d = Decision(verdict="durable", reason="r")
    assert d.scope == "global" and d.action == "create" and d.target_page is None


def test_classify_llm_accepts_update_to_eligible_target():
    d = classify_llm(
        "we learned X about the damage formula",
        _llm({"verdict": "durable", "reason": "reusable", "scope": "project",
              "action": "update", "target_page": "projects/p/knowledge/a.md"}),
        eligible_targets=("projects/p/knowledge/a.md",), project="p",
    )
    assert d.action == "update" and d.target_page == "projects/p/knowledge/a.md"


def test_classify_llm_rejects_target_outside_eligibility_set():
    with __import__("pytest").raises(ClassifierError):
        classify_llm(
            "item", _llm({"verdict": "durable", "reason": "r", "scope": "project",
                          "action": "update", "target_page": "projects/p/knowledge/other.md"}),
            eligible_targets=("projects/p/knowledge/a.md",), project="p",
        )


def test_classify_llm_rejects_update_with_null_target():
    with __import__("pytest").raises(ClassifierError):
        classify_llm(
            "item", _llm({"verdict": "durable", "reason": "r", "scope": "global",
                          "action": "update", "target_page": None}),
            eligible_targets=("a.md",),
        )


def test_classify_llm_rejects_create_with_target():
    with __import__("pytest").raises(ClassifierError):
        classify_llm(
            "item", _llm({"verdict": "durable", "reason": "r", "scope": "global",
                          "action": "create", "target_page": "a.md"}),
            eligible_targets=("a.md",),
        )


def test_classify_llm_rejects_unknown_scope_or_action():
    with __import__("pytest").raises(ClassifierError):
        classify_llm("item", _llm({"verdict": "durable", "reason": "r",
                                   "scope": "universe", "action": "create",
                                   "target_page": None}))


def test_classify_llm_missing_v2_fields_defaults_create_global():
    # Back-compat: a bare {"verdict","reason"} answer still parses.
    d = classify_llm("item", _llm({"verdict": "session-only", "reason": "r"}))
    assert d.action == "create" and d.scope == "global" and d.target_page is None


def test_gate_fail_closed_on_bad_target_falls_back_deterministic():
    d = gate("item", _llm({"verdict": "durable", "reason": "r", "scope": "global",
                           "action": "update", "target_page": "not-eligible.md"}),
             eligible_targets=("a.md",))
    assert d.verdict in {"session-only", "discard"}  # never durable via fallback
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/skills/wrap/test_classifier.py -v -k "v2 or eligible or scope_or_action or fail_closed_on_bad_target"`
Expected: FAIL (ImportError on `VALID_SCOPES` / TypeError on kwargs).

- [ ] **Step 3: Implement in `skills/wrap/lib/classifier.py`**

Add constants and extend `Decision`:

```python
VALID_SCOPES: Final[frozenset[str]] = frozenset({"project", "global"})
VALID_ACTIONS: Final[frozenset[str]] = frozenset({"create", "update"})

@dataclass(frozen=True)
class Decision:
    verdict: str   # "durable" | "session-only" | "discard"
    reason: str
    scope: str = "global"          # "project" | "global"
    action: str = "create"         # "create" | "update"
    target_page: str | None = None # required iff action == "update"
```

Replace `_CLASSIFIER_PROMPT_TEMPLATE` with the v2 template (keep the durable-bias paragraph verbatim, extend the schema):

```python
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

Eligible update targets (pages this session actually read; pick from these
EXACTLY or use "create"):
{targets_block}

Output JSON ONLY (no surrounding prose, no code fence). Schema:

{{"verdict": "durable" | "session-only" | "discard", "reason": "<one sentence>",
 "scope": "project" | "global", "action": "create" | "update",
 "target_page": "<one of the eligible targets>" | null}}

Candidate item:
---
{item_text}
---
"""
```

Update `build_classifier_prompt` to take the new context:

```python
def build_classifier_prompt(
    item_text: str, *, eligible_targets: tuple[str, ...] = (), project: str | None = None
) -> str:
    if not isinstance(item_text, str):
        raise TypeError(f"item_text must be str, got {type(item_text).__name__}")
    text = item_text
    if len(text) > _MAX_ITEM_CHARS:
        text = text[-_MAX_ITEM_CHARS:]
    targets_block = "\n".join(f"- {t}" for t in eligible_targets) or "(none — action must be \"create\")"
    return _CLASSIFIER_PROMPT_TEMPLATE.format(
        item_text=text, project=project or "(no project in scope)",
        targets_block=targets_block,
    )
```

Extend `classify_llm`'s strict parse (after the existing verdict/reason checks):

```python
def classify_llm(
    item_text: str, llm_call: Callable[[str], str], *,
    eligible_targets: tuple[str, ...] = (), project: str | None = None,
) -> Decision:
    prompt = build_classifier_prompt(
        item_text, eligible_targets=eligible_targets, project=project
    )
    ...  # existing raw/parse/verdict/reason checks unchanged

    scope = data.get("scope", "global")
    if scope not in VALID_SCOPES:
        raise ClassifierError(f"unknown scope {scope!r}; must be one of {sorted(VALID_SCOPES)}")
    action = data.get("action", "create")
    if action not in VALID_ACTIONS:
        raise ClassifierError(f"unknown action {action!r}; must be one of {sorted(VALID_ACTIONS)}")
    target = data.get("target_page")
    if action == "update":
        if not isinstance(target, str) or target not in eligible_targets:
            raise ClassifierError(
                f"update target {target!r} is not in the eligibility set"
            )
    else:
        if target is not None:
            raise ClassifierError('target_page must be null when action is "create"')
    return Decision(verdict=verdict, reason=reason, scope=scope, action=action,
                    target_page=target if action == "update" else None)
```

`classify_deterministic` is unchanged (its Decision picks up the create/global defaults). `gate` grows the same keyword-only params and passes them through to `classify_llm`; its fallback paths are otherwise untouched:

```python
def gate(
    item_text: str, llm_call: Callable[[str], str] | None = None, *,
    eligible_targets: tuple[str, ...] = (), project: str | None = None,
) -> Decision:
    ...
    if llm_call is not None:
        try:
            return classify_llm(item_text, llm_call,
                                eligible_targets=eligible_targets, project=project)
        except Exception as exc:  # noqa: BLE001
            ...  # existing fail_closed record + classify_deterministic fallback
```

Add `VALID_SCOPES` / `VALID_ACTIONS` to `__all__`.

- [ ] **Step 4: Run the full classifier + wrap suites**

Run: `uv run pytest tests/skills/wrap/ -v`
Expected: PASS (existing tests must survive the back-compat defaults).

- [ ] **Step 5: Commit**

```bash
git add skills/wrap/lib/classifier.py tests/skills/wrap/test_classifier.py
git commit -m "feat(wrap): classifier v2 — scope/action/target with eligibility-set enforcement (#60)"
```

---

### Task 2: Merge call for update-action items

**Files:**
- Create: `skills/wrap/lib/merge.py`
- Test: `tests/skills/wrap/test_merge.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `merge_update(current_text: str, item_text: str, llm_call: Callable[[str], str]) -> str` and `MergeError(Exception)`. Task 4 calls `merge_update` and treats `MergeError` as gate-out.

- [ ] **Step 1: Write the failing tests** (`tests/skills/wrap/test_merge.py`):

```python
import pytest

from skills.wrap.lib.merge import merge_update, MergeError

PAGE = """---
type: project-knowledge
ren_write_id: "w-01TEST"
ren_trust: "model"
---

# Damage Formula

Old fact: crit multiplier is 1.5.
"""


def test_merge_returns_llm_body_when_frontmatter_preserved():
    merged_ok = PAGE.replace("1.5", "2.0")
    out = merge_update(PAGE, "crit multiplier is actually 2.0", lambda p: merged_ok)
    assert "2.0" in out and out.startswith("---\ntype: project-knowledge")


def test_merge_rejects_frontmatter_tampering():
    tampered = PAGE.replace('ren_trust: "model"', 'ren_trust: "user"').replace("1.5", "2.0")
    with pytest.raises(MergeError):
        merge_update(PAGE, "item", lambda p: tampered)


def test_merge_rejects_empty_or_nonstring_output():
    with pytest.raises(MergeError):
        merge_update(PAGE, "item", lambda p: "   ")
    with pytest.raises(MergeError):
        merge_update(PAGE, "item", lambda p: None)  # type: ignore[arg-type]


def test_merge_rejects_unchanged_output():
    with pytest.raises(MergeError):
        merge_update(PAGE, "item", lambda p: PAGE)


def test_merge_prompt_contains_page_and_item():
    seen = {}
    def llm(prompt):
        seen["prompt"] = prompt
        return PAGE.replace("1.5", "2.0")
    merge_update(PAGE, "THE-ITEM-TEXT", llm)
    assert "THE-ITEM-TEXT" in seen["prompt"] and "Damage Formula" in seen["prompt"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/skills/wrap/test_merge.py -v`
Expected: FAIL with `ModuleNotFoundError: skills.wrap.lib.merge`.

- [ ] **Step 3: Implement `skills/wrap/lib/merge.py`**

```python
"""skills.wrap.lib.merge — the ONE extra LLM call an update-action durable
item makes (spec §1). Input: the target page's full text + the item; output:
the full merged body. Strict like the classifier: anything suspect raises
`MergeError` and the caller gates the item out (fail-closed) — a bad merge
must never reach the write door.

Frontmatter is the door's property (provenance stamping), never the
merge's: the returned text's frontmatter block must be byte-identical to
the input's, or we refuse.
"""

from __future__ import annotations

import re
from typing import Callable, Final

_FRONTMATTER_RE: Final[re.Pattern[str]] = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)

_MERGE_PROMPT_TEMPLATE: Final[str] = """\
You are updating ONE existing wiki page with ONE new durable learning.

Rules:
- Return the COMPLETE updated page as markdown, and NOTHING else (no code
  fence, no commentary).
- Change ONLY the section(s) the learning affects: correct, extend, or
  append. Preserve every other line exactly.
- Do NOT touch the YAML frontmatter block at the top — copy it verbatim.
- Keep the page's existing tone, heading structure, and link style.

The new durable learning:
---
{item_text}
---

The current page:
---
{page_text}
---
"""


class MergeError(Exception):
    """Merge output was malformed, unchanged, or tampered with frontmatter."""


def _frontmatter_block(text: str) -> str:
    m = _FRONTMATTER_RE.match(text)
    return m.group(0) if m else ""


def merge_update(
    current_text: str, item_text: str, llm_call: Callable[[str], str]
) -> str:
    prompt = _MERGE_PROMPT_TEMPLATE.format(item_text=item_text, page_text=current_text)
    raw = llm_call(prompt)
    if not isinstance(raw, str) or not raw.strip():
        raise MergeError("merge output empty or not a string")
    if _frontmatter_block(raw) != _frontmatter_block(current_text):
        raise MergeError("merge output altered the frontmatter block")
    if raw == current_text:
        raise MergeError("merge output is byte-identical to the current page")
    return raw


__all__ = ["merge_update", "MergeError"]
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/skills/wrap/test_merge.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/wrap/lib/merge.py tests/skills/wrap/test_merge.py
git commit -m "feat(wrap): strict merge call for update-action durable items (#60)"
```

---

### Task 3: Eligibility set from wake-up + recall logs

**Files:**
- Modify: `skills/wrap/lib/__init__.py` (new helper near `_session_queue_entries`, `skills/wrap/lib/__init__.py:1228`)
- Test: `tests/skills/wrap/test_eligibility.py`

**Interfaces:**
- Consumes: `lib.instrument.collect.read(kind=...)`, `collect.KIND_WAKEUP_SURFACE` (entries `{"pages": [...], "session": ...}`), `collect.KIND_L3_FETCH` (entries `{"page": ..., "query": ..., "session": ...}`), `lib.ren_paths.wiki_root()`.
- Produces: `_eligible_update_targets(session: str) -> tuple[str, ...]` — sorted, deduped, existing-on-disk wiki-relative paths. Task 4 passes this straight into `gate(..., eligible_targets=...)`.

- [ ] **Step 1: Write the failing test** (`tests/skills/wrap/test_eligibility.py`; use the repo's existing pattern for isolating the wiki root and metrics dir — copy the tmp-dir fixtures/monkeypatching used in `tests/skills/wrap/test_wrap_flow.py`, which already isolates `ren_paths` and `collect` state):

```python
from lib.instrument import collect
from skills.wrap.lib import _eligible_update_targets


def test_eligibility_unions_surface_and_fetch_for_session(tmp_wiki, isolated_metrics):
    # tmp_wiki: fixture that points ren_paths.wiki_root() at a tmp dir
    # (reuse/adapt the fixture from test_wrap_flow.py).
    (tmp_wiki / "projects/p/knowledge").mkdir(parents=True)
    (tmp_wiki / "projects/p/knowledge/a.md").write_text("x", encoding="utf-8")
    (tmp_wiki / "identity.md").write_text("x", encoding="utf-8")

    collect.record(collect.KIND_WAKEUP_SURFACE,
                   {"pages": ["projects/p/knowledge/a.md", "gone.md"], "session": "s1"})
    collect.record(collect.KIND_L3_FETCH,
                   {"page": "identity.md", "query": "q", "session": "s1"})
    collect.record(collect.KIND_L3_FETCH,
                   {"page": "projects/p/knowledge/a.md", "query": "q", "session": "OTHER"})

    got = _eligible_update_targets("s1")
    # gone.md dropped (not on disk); OTHER session's fetch excluded; sorted+deduped
    assert got == ("identity.md", "projects/p/knowledge/a.md")


def test_eligibility_empty_when_nothing_logged(tmp_wiki, isolated_metrics):
    assert _eligible_update_targets("s-none") == ()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/skills/wrap/test_eligibility.py -v`
Expected: FAIL with ImportError (`_eligible_update_targets` not defined).

- [ ] **Step 3: Implement in `skills/wrap/lib/__init__.py`**

```python
def _eligible_update_targets(session: str) -> tuple[str, ...]:
    """The mechanical eligibility set for update-action durable items (spec
    §1): pages THIS session actually surfaced — wake-up injections
    (`KIND_WAKEUP_SURFACE`) plus on-demand recalls (`KIND_L3_FETCH`) — that
    still exist on disk. Assembled from the instrumentation logs, re-checked
    in code after the classifier call; a target outside this set is treated
    as malformed classifier output (fail-closed), never written."""
    pages: set[str] = set()
    for entry in collect.read(kind=collect.KIND_WAKEUP_SURFACE):
        if entry.get("session") == session:
            pages.update(p for p in entry.get("pages", []) if isinstance(p, str))
    for entry in collect.read(kind=collect.KIND_L3_FETCH):
        if entry.get("session") == session and isinstance(entry.get("page"), str):
            pages.add(entry["page"])
    wiki = ren_paths.wiki_root()
    return tuple(sorted(p for p in pages if (wiki / p).is_file()))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/skills/wrap/test_eligibility.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/wrap/lib/__init__.py tests/skills/wrap/test_eligibility.py
git commit -m "feat(wrap): mechanical eligibility set from wakeup/recall logs (#60)"
```

---

### Task 4: Rewire the durable loop — placement, updates, trust hold, outcomes

**Files:**
- Modify: `skills/wrap/lib/__init__.py` (the durable-items loop inside `wrap_session`, currently `skills/wrap/lib/__init__.py:790-820` — the `for item in durable_items:` block)
- Modify: `lib/instrument/collect.py` (add `KIND_DURABLE_OUTCOME = "durable_outcome"` beside the other KIND constants at `lib/instrument/collect.py:63`, and to `__all__`)
- Test: `tests/skills/wrap/test_durable_loop.py`

**Interfaces:**
- Consumes: Task 1's `gate(..., eligible_targets=, project=)` + `Decision.scope/action/target_page`; Task 2's `merge_update`/`MergeError`; Task 3's `_eligible_update_targets`.
- Produces: wrap result dict gains `"updated": list[dict]` and `"suggested": list[dict]` alongside the existing `applied`/`held`/`gated_out`/`refused`; a `durable_outcome` metric per wrap; `_durable_create_page(item, scope, project) -> str` and `_target_trust(page: str) -> str | None` helpers (Task 5 wires hub creation into `_durable_create_page`'s call site).

- [ ] **Step 1: Write the failing tests** (`tests/skills/wrap/test_durable_loop.py`; drive `wrap_session` the way `tests/skills/wrap/test_wrap_flow.py` does — reuse its fixtures for wiki root, metrics isolation, and its scripted-`llm_call` pattern; the scripted call must now answer the classifier prompt, the merge prompt, and wrap's other judge prompts — key off distinctive prompt substrings: `"Candidate item:"` → classifier JSON, `"The current page:"` → merged page text):

```python
# Behaviors under test (write these as real tests using test_wrap_flow.py's
# harness; each is one test function):
#
# 1. test_create_project_scoped: project in scope + classifier answers
#    {durable, scope=project, action=create} → page applied at
#    "projects/<slug>/knowledge/lessons/<slug-of-item>.md" (assert via the
#    result dict's applied[0]["page"] and the file existing under tmp wiki).
#
# 2. test_create_global_fallback: no project in scope → page applied at
#    "lessons/<slug>.md" (existing behavior preserved).
#
# 3. test_update_applies_merged_body: seed a model-trust page under
#    projects/p/knowledge/, log it as KIND_WAKEUP_SURFACE for the session,
#    classifier answers action=update targeting it, merge returns page with
#    one line changed → result["updated"] has the page; on-disk body carries
#    the change; op recorded as UPDATE.
#
# 4. test_update_to_user_trust_page_held_as_suggestion: same as (3) but the
#    seeded page's frontmatter has ren_trust: "user" → NO write applied;
#    result["suggested"] has one entry; lib.suggestions.pending_suggestions()
#    contains kind="page_write", producer="wrap",
#    fingerprint="wrap-update:<session>:<page>".
#
# 5. test_merge_error_gates_item_out: merge llm answer tampers frontmatter →
#    item lands in result["gated_out"] with reason mentioning "merge", no
#    write applied.
#
# 6. test_durable_outcome_metric_recorded: after wrap_session, collect.read
#    (kind="durable_outcome") has one entry with keys created/updated/
#    gated_out/suggested/held/refused and int values matching the run.
```

Write all six as concrete tests (no pseudocode in the final file) — the harness pieces (tmp wiki fixture, scripted llm) already exist in `test_wrap_flow.py`; import or copy them per that file's local conventions.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/skills/wrap/test_durable_loop.py -v`
Expected: FAIL (`updated`/`suggested` keys absent; placement still hardcoded).

- [ ] **Step 3: Implement**

In `lib/instrument/collect.py` add beside the other constants and in `__all__`:

```python
KIND_DURABLE_OUTCOME = "durable_outcome"
```

In `skills/wrap/lib/__init__.py` add helpers:

```python
def _target_trust(page: str) -> str | None:
    """`ren_trust` frontmatter of a wiki page, or None (unreadable/unstamped).
    Mirrors skills/wiki-health/lib `_page_trust` — fail closed: None is
    treated as NOT user-trust (auto path), because an unstamped page was
    never human-released."""
    try:
        text = ren_paths.safe_join(ren_paths.wiki_root(), page).read_text(encoding="utf-8")
    except OSError:
        return None
    data = _split_overview_frontmatter(text)[0]  # existing frontmatter parser
    trust = data.get("ren_trust")
    return trust if isinstance(trust, str) else None


def _durable_create_page(item: str, scope: str, project: str | None) -> str:
    """Placement for a durable CREATE (spec §2): project-scoped when the
    classifier said so AND a project is in scope; global lessons/ otherwise."""
    if scope == "project" and project:
        return f"projects/{project}/knowledge/lessons/{_slugify(item)}.md"
    return f"lessons/{_slugify(item)}.md"
```

Replace the loop body (`for item in durable_items:` at `skills/wrap/lib/__init__.py:790`):

```python
    eligible = _eligible_update_targets(session)
    updated: list[dict] = []
    suggested: list[dict] = []

    for item in durable_items:
        decision = gate(item, llm_call, eligible_targets=eligible, project=project)

        if decision.verdict != "durable":
            gated_out.append(
                {"item": item, "verdict": decision.verdict, "reason": decision.reason}
            )
            continue

        if decision.action == "update":
            target = decision.target_page
            try:
                current = ren_paths.safe_join(
                    ren_paths.wiki_root(), target
                ).read_text(encoding="utf-8")
                merged = merge_update(current, item, llm_call)
            except (OSError, MergeError) as exc:
                gated_out.append(
                    {"item": item, "verdict": "durable",
                     "reason": f"update to {target} gated out (merge): {exc}"}
                )
                continue

            proposal_kwargs = dict(
                op="UPDATE", page=target, content=merged,
                reason=decision.reason, producer="wrap",
                writer="llm-auto", session=session,
            )
            if _target_trust(target) == "user":
                entry = record_suggestion(
                    SuggestionSpec(
                        producer="wrap",
                        title=f"Update human-authored page: {target}",
                        rationale=decision.reason,
                        evidence={"item": item, "session": session, "page": target},
                        kind="page_write",
                        payload=proposal_kwargs,
                        fingerprint=f"wrap-update:{session}:{target}",
                    )
                )
                suggested.append({"page": target, "sid": entry["sid"] if entry else None})
                continue
            try:
                entry, prov = propose_and_apply(Proposal(**proposal_kwargs))
            except SecretsFound as exc:
                refused.append({"item": item, "reason": str(exc)})
                continue
            if prov is not None:
                updated.append({"qid": entry.qid, "write_id": prov.write_id,
                                "page": target, "op": prov.op})
            else:
                held.append({"qid": entry.qid, "page": target,
                             "conflicts": entry.conflicts})
            continue

        page = _durable_create_page(item, decision.scope, project)
        # ... existing ADD propose_and_apply block unchanged, using `page` ...
```

(Import `SuggestionSpec` alongside the existing `record as record_suggestion` import at `skills/wrap/lib/__init__.py:56`, and `from .merge import merge_update, MergeError` beside the `from .classifier import gate` import.)

After the loop (beside the existing `fail_closed` computation), record the outcome metric and extend the result dict:

```python
    collect.record(
        collect.KIND_DURABLE_OUTCOME,
        {"session": session, "created": len(applied), "updated": len(updated),
         "gated_out": len(gated_out), "suggested": len(suggested),
         "held": len(held), "refused": len(refused)},
    )
```

Add `"updated": updated, "suggested": suggested` to the `result` dict, and surface both in `render_wrap_screen`'s summary lines (one line each, mirroring how `applied`/`held` render).

Note: `applied` entries keep `op` — the D4 duty at `skills/wrap/lib/__init__.py:1062` filters `op != "ADD"`, so UPDATE entries in `updated` are correctly invisible to it (they're in a separate list anyway).

- [ ] **Step 4: Run the wrap suite**

Run: `uv run pytest tests/skills/wrap/ -v`
Expected: PASS, including all pre-existing `test_wrap_flow.py` tests (their scripted llm answers without v2 fields still parse via the back-compat defaults).

- [ ] **Step 5: Commit**

```bash
git add skills/wrap/lib/__init__.py lib/instrument/collect.py tests/skills/wrap/test_durable_loop.py
git commit -m "feat(wrap): durable loop learns update/placement; trust-user holds; outcome metric (#60 #57)"
```

---

### Task 5: Lessons folder-note hubs (project + global) with idempotent backfill

**Files:**
- Modify: `skills/wrap/lib/__init__.py` (new `_ensure_lessons_hub`, called from the create path added in Task 4)
- Test: `tests/skills/wrap/test_lessons_hub.py`

**Interfaces:**
- Consumes: Task 4's create path (`_durable_create_page` call site).
- Produces: `_ensure_lessons_hub(dir_rel: str, session: str, project: str | None) -> bool` (True when a hub write applied; False = already current or failed-with-warning). Hub page path is `<dir_rel>/<dirname>.md` per the 0.7.2 folder-note convention.

- [ ] **Step 1: Write the failing tests** (`tests/skills/wrap/test_lessons_hub.py`, same tmp-wiki fixtures):

```python
# Concrete tests to write (same harness as Task 4's file):
#
# 1. test_global_hub_created_with_backfill: seed lessons/old-one.md and
#    lessons/old-two.md (plain files, no hub). Call
#    _ensure_lessons_hub("lessons", "s1", None). Assert lessons/lessons.md
#    now exists, its frontmatter contains "hub: true", and its body links
#    both pages as "- [old-one](old-one.md)" style file-relative links.
#
# 2. test_hub_idempotent: call _ensure_lessons_hub twice; second call
#    returns False and the file content is unchanged (byte-compare).
#
# 3. test_project_hub_frontmatter: _ensure_lessons_hub(
#    "projects/p/knowledge/lessons", "s1", "p") creates
#    projects/p/knowledge/lessons/lessons.md with type: project-knowledge,
#    project: p, hub: true in frontmatter.
#
# 4. test_hub_failure_never_raises: monkeypatch propose_and_apply to raise;
#    _ensure_lessons_hub returns False, no exception escapes.
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/skills/wrap/test_lessons_hub.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement `_ensure_lessons_hub` in `skills/wrap/lib/__init__.py`**

```python
def _ensure_lessons_hub(dir_rel: str, session: str, project: str | None) -> bool:
    """Folder-note hub for a lessons/ directory (spec §2, 0.7.2 hub
    convention: `<dir>/<dirname>.md`, `hub: true`). Rebuilds the link list
    from disk every call and writes ONLY when the rendered text differs —
    idempotent, and the first call backfills links to every pre-existing
    lesson page. Isolated-duty posture: never raises; returns False on any
    failure (caller appends a warning)."""
    try:
        wiki = ren_paths.wiki_root()
        dirname = PurePosixPath(dir_rel).name
        hub_rel = f"{dir_rel}/{dirname}.md"
        hub_path = ren_paths.safe_join(wiki, hub_rel)
        dir_path = ren_paths.safe_join(wiki, dir_rel)

        entries = sorted(
            p.name for p in dir_path.glob("*.md")
            if p.is_file() and p.name != f"{dirname}.md"
        ) if dir_path.is_dir() else []
        links = "\n".join(f"- [{PurePosixPath(n).stem}]({n})" for n in entries)

        if project:
            fm = (f"---\ntype: project-knowledge\nschema_version: 1\n"
                  f"project: {project}\nhub: true\ntitle: \"Lessons Hub\"\n---\n")
        else:
            fm = "---\nhub: true\ntitle: \"Lessons\"\n---\n"
        body = f"{fm}\n# Lessons\n\nDurable lessons in this folder:\n\n{links}\n"

        if hub_path.is_file() and hub_path.read_text(encoding="utf-8") == body:
            return False
        _, prov = propose_and_apply(
            Proposal(
                op="UPDATE" if hub_path.is_file() else "ADD",
                page=hub_rel, content=body,
                reason="lessons folder-note hub (spec 2026-08-14 §2)",
                producer="wrap", writer="routine", session=session,
            )
        )
        return prov is not None
    except Exception:  # noqa: BLE001 - hub upkeep must never fail wrap close-out
        return False
```

Wire it into Task 4's create path, immediately AFTER a successful durable ADD (so the fresh page is on disk when the hub list rebuilds):

```python
        if prov is not None:
            applied.append({...})  # existing
            hub_dir = str(PurePosixPath(page).parent)
            _ensure_lessons_hub(hub_dir, session,
                                project if page.startswith("projects/") else None)
```

Note the exact-byte comparison makes re-runs no-ops; content is fully derived from disk, so ordering is stable (sorted names).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/skills/wrap/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/wrap/lib/__init__.py tests/skills/wrap/test_lessons_hub.py
git commit -m "feat(wrap): lessons folder-note hubs with idempotent backfill (#57)"
```

---

### Task 6: Volatile-facts marker library

**Files:**
- Create: `lib/memory/volatile.py`
- Test: `tests/governance/test_volatile.py` (beside the other lib-level test dirs; `tests/governance/` exists)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `MARKER_RE` (regex), `find_markers(md_text: str) -> list[Marker]` where `Marker = namedtuple("Marker", "kind line_no line_text")`; `CHECKERS: dict[str, Callable[[Path], str | None]]` with keys `"framework-version"` and `"release-count"`; `check_marker(marker: Marker, repo_root: Path | None = None) -> tuple[str, str | None]` returning `(status, ground_truth)` with status in `{"ok", "stale", "unverifiable"}`. Task 7 consumes all of these.

- [ ] **Step 1: Write the failing tests** (`tests/governance/test_volatile.py`):

```python
from pathlib import Path

from lib.memory.volatile import find_markers, check_marker, CHECKERS


def test_find_markers_extracts_kind_and_line():
    text = (
        "# Page\n\n"
        "RenOS is currently at 0.7.2. <!-- ren-volatile: framework-version -->\n"
        "27 tagged releases so far. <!-- ren-volatile: release-count -->\n"
        "No marker here.\n"
    )
    markers = find_markers(text)
    assert [m.kind for m in markers] == ["framework-version", "release-count"]
    assert markers[0].line_no == 3
    assert "0.7.2" in markers[0].line_text


def test_unknown_kind_is_inventoried_not_checked():
    text = "The frontier model is X. <!-- ren-volatile: current-frontier -->\n"
    (marker,) = find_markers(text)
    status, truth = check_marker(marker)
    assert status == "unverifiable" and truth is None


def test_release_count_checker_against_fixture_repo(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for cmd in (["git", "-C", str(tmp_path), "commit", "--allow-empty", "-q",
                 "-m", "x"],
                ["git", "-C", str(tmp_path), "tag", "v0.1.0"],
                ["git", "-C", str(tmp_path), "tag", "v0.2.0"]):
        subprocess.run(cmd, check=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": __import__("os").environ["PATH"]})
    (marker,) = find_markers("2 releases <!-- ren-volatile: release-count -->\n")
    status, truth = check_marker(marker, repo_root=tmp_path)
    assert status == "ok" and truth == "2"

    (stale,) = find_markers("99 releases <!-- ren-volatile: release-count -->\n")
    status, truth = check_marker(stale, repo_root=tmp_path)
    assert status == "stale" and truth == "2"


def test_missing_ground_truth_is_unverifiable(tmp_path):
    # tmp_path is not a git repo → release-count checker can't run
    (marker,) = find_markers("2 releases <!-- ren-volatile: release-count -->\n")
    status, truth = check_marker(marker, repo_root=tmp_path)
    assert status == "unverifiable"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/governance/test_volatile.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `lib/memory/volatile.py`**

```python
"""lib.memory.volatile — the ren-volatile marker convention (#39, spec §3).

A fact that ages gets tagged inline where it lives:

    RenOS is currently at 0.7.2. <!-- ren-volatile: framework-version -->

The registry maps marker KINDS to mechanical ground-truth checkers. Kinds
without a checker are valid markers but only inventoried, never
auto-corrected — the sweep (wiki-health `stale_facts`) reports them as
"unverifiable" and moves on. Checkers return the current ground-truth value
as a string, or None when it cannot be established (missing repo,
unreadable pyproject) — fail closed: no evidence, no correction.

Staleness test is deliberately dumb-mechanical: the marked LINE is stale
when it does not contain the ground-truth string. No NLP, no fuzzy match —
a false "stale" only queues a correction proposal, which the sweep renders
with the evidence for review.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from collections import namedtuple
from pathlib import Path
from typing import Callable, Final

MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*ren-volatile:\s*(?P<kind>[a-z0-9-]+)\s*-->"
)

Marker = namedtuple("Marker", "kind line_no line_text")

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


def find_markers(md_text: str) -> list[Marker]:
    out: list[Marker] = []
    for i, line in enumerate(md_text.splitlines(), start=1):
        m = MARKER_RE.search(line)
        if m:
            out.append(Marker(kind=m.group("kind"), line_no=i, line_text=line))
    return out


def _framework_version(repo_root: Path) -> str | None:
    pyproject = repo_root / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version = data.get("project", {}).get("version")
        return version if isinstance(version, str) else None
    except (OSError, tomllib.TOMLDecodeError):
        return None


def _release_count(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "tag", "--list", "v*"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    tags = [t for t in proc.stdout.splitlines() if t.strip()]
    return str(len(tags)) if tags else None


CHECKERS: Final[dict[str, Callable[[Path], str | None]]] = {
    "framework-version": _framework_version,
    "release-count": _release_count,
}


def check_marker(marker: Marker, repo_root: Path | None = None) -> tuple[str, str | None]:
    """(status, ground_truth): "ok" | "stale" | "unverifiable"."""
    checker = CHECKERS.get(marker.kind)
    if checker is None:
        return ("unverifiable", None)
    truth = checker(repo_root or _REPO_ROOT)
    if truth is None:
        return ("unverifiable", None)
    return ("ok" if truth in marker.line_text else "stale", truth)


__all__ = ["MARKER_RE", "Marker", "find_markers", "CHECKERS", "check_marker"]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/governance/test_volatile.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/memory/volatile.py tests/governance/test_volatile.py
git commit -m "feat(memory): ren-volatile marker convention + mechanical checkers (#39)"
```

---

### Task 7: wiki-health `stale_facts` check

**Files:**
- Modify: `skills/wiki-health/lib/__init__.py` (new `_stale_facts` scanner; wire into `sweep()` at `skills/wiki-health/lib/__init__.py:715` and `render_report` at `:834`)
- Test: `tests/skills/wiki_health/test_stale_facts.py`

**Interfaces:**
- Consumes: Task 6's `find_markers` / `check_marker`.
- Produces: `sweep()` result dict gains `"stale_facts": {"stale": [...], "unverifiable": [...], "corrections_queued": int}`; each stale item is `{"page", "line_no", "kind", "line", "ground_truth"}`. `render_report` prints one warn-not-block section for it.

- [ ] **Step 1: Write the failing tests** (`tests/skills/wiki_health/test_stale_facts.py`, using this dir's existing tmp-wiki fixtures):

```python
# Concrete tests to write (this dir's existing fixture conventions):
#
# 1. test_stale_fact_detected_and_correction_queued: seed a model-trust page
#    whose marked line disagrees with ground truth (monkeypatch
#    lib.memory.volatile.CHECKERS["release-count"] to lambda root: "30").
#    Run sweep(). Assert one entry in result["stale_facts"]["stale"] with
#    ground_truth == "30", and corrections_queued == 1, and the queued
#    UPDATE proposal's content has the marked line's number replaced with
#    "30" (read the page back — writer "routine", producer "routine").
#
# 2. test_user_trust_page_routes_to_suggestion: same but the page's
#    frontmatter has ren_trust: "user" → corrections_queued == 0 and
#    lib.suggestions.pending_suggestions() has a producer="wiki-health"
#    entry with fingerprint "stale-fact:<page>:<line_no>".
#
# 3. test_unverifiable_kind_inventoried_only: a page with an unknown-kind
#    marker → listed under result["stale_facts"]["unverifiable"], nothing
#    queued, nothing suggested.
#
# 4. test_checker_without_ground_truth_skips_with_no_queue: monkeypatch the
#    checker to return None → item under "unverifiable", nothing queued.
#
# 5. test_report_renders_stale_facts_section: render_report(result) output
#    contains the page path and the ground-truth value.
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/skills/wiki_health/test_stale_facts.py -v`
Expected: FAIL (`stale_facts` key absent).

- [ ] **Step 3: Implement in `skills/wiki-health/lib/__init__.py`**

```python
def _stale_facts(wiki_root: Path, session: str) -> dict:
    """#39's freshness sweep (spec 2026-08-14 §3): scan durable pages for
    `ren-volatile` markers, verify checkable kinds against ground truth, and
    queue a correction through the write queue for each stale line —
    writer="routine" (mechanical bookkeeping; never quarantines), trust-user
    targets routed to the suggestions store instead. Warn-not-block: any
    per-page failure is skipped, never raises."""
    from lib.memory.volatile import check_marker, find_markers
    from lib.memory.queue import Proposal, propose_and_apply
    from lib.suggestions import SuggestionSpec, record

    stale: list[dict] = []
    unverifiable: list[dict] = []
    queued = 0

    for path in sorted(wiki_root.rglob("*.md")):
        rel = path.relative_to(wiki_root).as_posix()
        parts = tuple(PurePosixPath(rel).parts)
        if _in_archive(parts) or "raw" in parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for marker in find_markers(text):
            status, truth = check_marker(marker)
            if status == "ok":
                continue
            item = {"page": rel, "line_no": marker.line_no, "kind": marker.kind,
                    "line": marker.line_text.strip(), "ground_truth": truth}
            if status == "unverifiable":
                unverifiable.append(item)
                continue
            stale.append(item)
            try:
                lines = text.splitlines(keepends=True)
                old_line = lines[marker.line_no - 1]
                new_line = re.sub(r"\d+(?:\.\d+)*", truth, old_line, count=1)
                if new_line == old_line:
                    continue  # nothing mechanically replaceable — report only
                lines[marker.line_no - 1] = new_line
                corrected = "".join(lines)
                if _page_trust(text) == "user":
                    record(SuggestionSpec(
                        producer="wiki-health",
                        title=f"Stale fact on human-authored page: {rel}",
                        rationale=f"{marker.kind} ground truth is {truth}",
                        evidence=item,
                        kind="page_write",
                        payload=dict(op="UPDATE", page=rel, content=corrected,
                                     reason=f"stale-fact refresh ({marker.kind})",
                                     producer="routine", writer="routine",
                                     session=session),
                        fingerprint=f"stale-fact:{rel}:{marker.line_no}",
                    ))
                    continue
                _, prov = propose_and_apply(Proposal(
                    op="UPDATE", page=rel, content=corrected,
                    reason=f"stale-fact refresh ({marker.kind}: {truth})",
                    producer="routine", writer="routine", session=session,
                ))
                if prov is not None:
                    queued += 1
            except Exception:  # noqa: BLE001 - warn-not-block
                continue

    return {"stale": stale, "unverifiable": unverifiable, "corrections_queued": queued}
```

Wire into `sweep()`: add `findings["stale_facts"] = _stale_facts(wiki_root, session)` alongside the other checks (`sweep` already threads a session; follow how `record_orphan_suggestions` gets its session). In `render_report`, add a section mirroring the orphan section's tone:

```
Stale facts (ren-volatile): N stale (M corrected), K unverifiable
  - <page>:<line_no> [<kind>] ground truth: <value>
```

Note: the naive number-substitution correction only fires when the marked line contains a number to replace; otherwise the finding is report-only. That is deliberate (spec: no NLP guessing).

- [ ] **Step 4: Run wiki-health suite**

Run: `uv run pytest tests/skills/wiki_health/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/wiki-health/lib/__init__.py tests/skills/wiki_health/test_stale_facts.py
git commit -m "feat(wiki-health): stale_facts sweep over ren-volatile markers (#39)"
```

---

### Task 8: Classifier eval cases

**Files:**
- Modify: `skills/wrap/eval_cases.json`
- Test: whatever runner already consumes `eval_cases.json` (find it: `grep -rn "eval_cases" tests/ lib/evalkit/` — extend that runner's fixtures if cases carry expected v2 fields).

**Interfaces:**
- Consumes: Task 1's v2 schema.
- Produces: eval coverage the retrospective/evalkit loop can score.

- [ ] **Step 1: Read the existing file and its runner** to learn the exact case schema (`skills/wrap/eval_cases.json` + `grep -rn "eval_cases" tests lib`). Follow that schema exactly for the new cases.

- [ ] **Step 2: Add these cases** (adapting field names to the file's schema; each case = item text, any context the schema supports, expected verdict/scope/action/target):

1. Update-to-surfaced-page: item "the damage formula's crit multiplier was corrected to 2.0 this session", eligible targets containing `projects/p/knowledge/damage-formula.md` → expect `durable/project/update` with that target.
2. Create-project-scoped: item "lesson: always run the RSD linter before committing iOS snapshot baselines", project `flux`, empty targets → expect `durable/project/create`.
3. Create-global-fallback: item "lesson: uv run, never system python3, on macOS", no project → expect `durable/global/create`.
4. Session-only chatter: item "we ran the tests three times today" → expect `session-only`.
5. Secret-shaped: item containing `token=abc123...` → expect `discard`.

- [ ] **Step 3: Run whatever suite covers the eval file** (the grep from Step 1 tells you the command; typically `uv run pytest tests/evalkit/ -v` plus any wrap eval test).
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add skills/wrap/eval_cases.json
git commit -m "test(wrap): classifier v2 eval cases — placement, update, fallback (#60)"
```

---

### Task 9: Docs, seeding, and live proof (train close-out)

**Files:**
- Modify: `skills/wrap/SKILL.md` (document scope/action/target + trust-user hold, one short paragraph in the durable-items section)
- Modify: `skills/wiki-health/SKILL.md` (document the `stale_facts` check, one bullet)
- Modify: `wiki-skeleton/templates/projects/schema.md.tmpl` (one line documenting the `ren-volatile` marker convention)
- Live wiki (via write path only — NEVER direct edits): seed markers, dogfood run.

**Interfaces:**
- Consumes: everything above, merged.
- Produces: the spec §8 live-proof evidence.

- [ ] **Step 1: Docs edits** — add to each SKILL.md/template exactly what the spec §1-§3 defines (copy the marker syntax line verbatim: `<!-- ren-volatile: <kind> -->`). Run `uv run pytest tests/ -q` for a full green sweep.

- [ ] **Step 2: Commit docs**

```bash
git add skills/wrap/SKILL.md skills/wiki-health/SKILL.md wiki-skeleton/templates/projects/schema.md.tmpl
git commit -m "docs: wrap placement/update semantics, stale_facts check, ren-volatile convention"
```

- [ ] **Step 3: Seed markers on the two known stale spots** (spec §3) — queue UPDATEs through the write door (a small `uv run python` snippet calling `propose_and_apply` with producer `"routine"`, writer `"routine"`) appending ` <!-- ren-volatile: framework-version -->` / ` <!-- ren-volatile: release-count -->` to the stale lines in `projects/ren-os/map.md` (release count) and `identity.md` (framework_version line's prose mention if present; if the fact lives only in frontmatter, mark the map only and note it). Trust-user pages will hold → approve via `/ren:suggestions`.

- [ ] **Step 4: Live proof** — in a fresh session on this repo: do real work briefly, run `/ren:wrap`. Verify: ≥1 project-scoped durable under `projects/ren-os/knowledge/lessons/` with a D4 pointer in the ren-os map; `lessons` hub exists. Then run `/ren:wiki-health` and verify the `stale_facts` section reports the seeded markers as ok/corrected. Record outcomes on issues #57, #39, #60 (comment with evidence, close #57 and #39; #60 stays open pending the §4 measurement window).

- [ ] **Step 5: Release** — changelog entry, version bump, tag, `gh release create` (matching the 0.7.x release format).
