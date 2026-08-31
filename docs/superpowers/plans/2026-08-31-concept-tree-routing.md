# Concept-Tree Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Durable *conceptual* knowledge routes into a project's schema-declared taxonomy tree (accreting concept pages + hubs) instead of flat `lessons/`; episodic lessons keep today's path.

**Architecture:** A new `lib/memory/taxonomy.py` parses a fenced `taxonomy` block in `projects/<slug>/schema.md`. The wrap classifier's output schema gains `kind`/`placement`/`title` (one LLM call, code-revalidated, additive-only). `_durable_create_page` gains a placement path; new leaves create page + hub + parent-hub link + schema.md taxonomy line as ordered queued writes. Concept items resolving to an existing node become updates (concepts accrete). No taxonomy ⇒ routing is blind: fall back to lessons and say so (Unknown convention). Ingest drafts the taxonomy; a manual distill `--seed-tree` mode backfills from existing lessons.

**Tech Stack:** Python ≥3.11, uv, pytest. All wiki writes via `propose_and_apply(Proposal(...))` (`lib/memory` write door). Metrics via `lib.instrument.collect.record`.

**Spec:** `docs/superpowers/specs/2026-08-31-concept-tree-routing-design.md`

## Global Constraints

- Python ≥3.11; run tests with `uv run pytest`; lint with `uv run ruff check .` and the repo's second lint if configured in CI.
- Every wiki write goes through `propose_and_apply` — never a direct file write.
- Additive-only auto-writes: agent may add taxonomy leaves; rename/merge/delete of branches is a suggestion (`record_suggestion`), never an auto-write.
- Fail-closed: an invalid placement NEVER discards a durable item — it falls back to a lesson create and records a metric.
- Page type stays `project-knowledge` for concept pages (spec §5 as amended); no new `derive_type` rule for concepts.
- Blindness is Unknown, not a guess: missing/unparseable taxonomy ⇒ report "concept routing blind", route everything to lessons (`lib/reporting.py` conventions; see `REPORTING_SURFACES`).
- Taxonomy depth cap: 2 levels below `knowledge/`. Split-suggestion threshold: `_CONCEPT_SPLIT_BULLETS = 40`.
- Match existing style: `Final` constants, frozen dataclasses, `# noqa: BLE001` only on established fail-closed seams, docstrings citing the spec section.

---

### Task 1: `lib/memory/taxonomy.py` — parse, validate, diff

**Files:**
- Create: `lib/memory/taxonomy.py`
- Test: `tests/lib/test_taxonomy.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Taxonomy` with `nodes: tuple[str, ...]` (sorted POSIX-style relative paths like `architecture/memory-plane`, no leading/trailing slash) and method `has(path: str) -> bool`.
  - `parse_taxonomy(schema_md_text: str) -> Taxonomy` — raises `TaxonomyError` on: no ```` ```taxonomy ```` fence, bad indentation (not multiple of 2), invalid segment (must match `^[a-z0-9][a-z0-9-]*$`), depth > 2, duplicate path.
  - `load_taxonomy(project: str) -> Taxonomy` — reads `projects/<project>/schema.md` via `ren_paths.safe_join(ren_paths.wiki_root(), ...)`; raises `TaxonomyError` (wrapping `OSError` too — the caller treats any raise as "blind").
  - `classify_placement(tax: Taxonomy, placement: str) -> str` — returns `"existing"` if `tax.has(placement)`, `"new-leaf"` if the parent (`placement.rsplit("/", 1)[0]`, or root for a single segment) is an existing node or root and depth ≤ 2, else raises `TaxonomyError`.
  - `render_added_line(placement: str) -> tuple[str, str]` — helper returning `(parent_line_prefix, new_line)` used by Task 3 to append the leaf into the fenced block (implement as: re-render the whole fenced block from `Taxonomy.nodes + (placement,)` — `render_block(tax: Taxonomy) -> str` producing the fence content with 2-space indentation; simpler and order-stable).
  - `TaxonomyError(Exception)`.

- [ ] **Step 1: Write failing tests**

```python
# tests/lib/test_taxonomy.py
import pytest
from lib.memory.taxonomy import (
    Taxonomy, TaxonomyError, parse_taxonomy, classify_placement, render_block,
)

FENCED = """---
type: project-schema
---
# Schema

```taxonomy
architecture/
  memory-plane/
  instrumentation/
governance/
```

prose after.
"""

def test_parse_extracts_nodes():
    tax = parse_taxonomy(FENCED)
    assert tax.nodes == (
        "architecture", "architecture/instrumentation",
        "architecture/memory-plane", "governance",
    )
    assert tax.has("architecture/memory-plane")
    assert not tax.has("nope")

def test_parse_no_fence_raises():
    with pytest.raises(TaxonomyError):
        parse_taxonomy("# Schema\n\nno block here\n")

def test_parse_bad_segment_raises():
    with pytest.raises(TaxonomyError):
        parse_taxonomy("```taxonomy\nBad_Name/\n```\n")

def test_parse_too_deep_raises():
    with pytest.raises(TaxonomyError):
        parse_taxonomy("```taxonomy\na/\n  b/\n    c/\n      d/\n```\n")

def test_classify_existing_and_new_leaf():
    tax = parse_taxonomy(FENCED)
    assert classify_placement(tax, "governance") == "existing"
    assert classify_placement(tax, "architecture/write-door") == "new-leaf"
    assert classify_placement(tax, "brand-new-root") == "new-leaf"

def test_classify_orphan_parent_raises():
    tax = parse_taxonomy(FENCED)
    with pytest.raises(TaxonomyError):
        classify_placement(tax, "missing-parent/child")

def test_render_block_round_trips():
    tax = parse_taxonomy(FENCED)
    text = "```taxonomy\n" + render_block(tax) + "```\n"
    assert parse_taxonomy(text).nodes == tax.nodes
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/lib/test_taxonomy.py -v`
Expected: FAIL — `ModuleNotFoundError: lib.memory.taxonomy`

- [ ] **Step 3: Implement `lib/memory/taxonomy.py`**

Sketch (implementer fills mechanics, keeps signatures exact):

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Final

_SEGMENT_RE: Final = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_FENCE_RE: Final = re.compile(r"```taxonomy\n(.*?)```", re.DOTALL)
MAX_DEPTH: Final[int] = 2  # levels below knowledge/

class TaxonomyError(Exception):
    """Unparseable/invalid taxonomy — callers treat any raise as 'blind'."""

@dataclass(frozen=True)
class Taxonomy:
    nodes: tuple[str, ...]
    def has(self, path: str) -> bool:
        return path in self.nodes

def parse_taxonomy(schema_md_text: str) -> Taxonomy:
    m = _FENCE_RE.search(schema_md_text)
    if not m:
        raise TaxonomyError("no ```taxonomy fence in schema.md")
    nodes: list[str] = []
    stack: list[str] = []
    for raw in m.group(1).splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            raise TaxonomyError(f"odd indentation: {raw!r}")
        depth = indent // 2
        seg = raw.strip().rstrip("/")
        if not _SEGMENT_RE.match(seg):
            raise TaxonomyError(f"invalid segment {seg!r}")
        if depth > len(stack):
            raise TaxonomyError(f"indentation jump: {raw!r}")
        if depth >= MAX_DEPTH + 1:
            raise TaxonomyError(f"deeper than cap {MAX_DEPTH}: {raw!r}")
        stack = stack[:depth] + [seg]
        path = "/".join(stack)
        if path in nodes:
            raise TaxonomyError(f"duplicate node {path!r}")
        nodes.append(path)
    if not nodes:
        raise TaxonomyError("taxonomy fence is empty")
    return Taxonomy(nodes=tuple(sorted(nodes)))
```

`load_taxonomy(project)` wraps the read (`except OSError as exc: raise TaxonomyError(...) from exc`). `classify_placement` and `render_block` per the interface block. Export all names via `__all__`.

- [ ] **Step 4: Run tests, verify pass** — `uv run pytest tests/lib/test_taxonomy.py -v`
- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check lib/memory/taxonomy.py tests/lib/test_taxonomy.py
git add lib/memory/taxonomy.py tests/lib/test_taxonomy.py
git commit -m "feat(taxonomy): parse/validate/diff the schema.md taxonomy block"
```

---

### Task 2: Classifier schema — `kind`, `placement`, `title`

**Files:**
- Modify: `skills/wrap/lib/classifier.py`
- Test: `tests/skills/wrap/test_classifier.py` (extend the existing file; find it with `ls tests/skills/wrap/`)

**Interfaces:**
- Consumes: `Taxonomy` from Task 1 (passed as `taxonomy: Taxonomy | None`).
- Produces (used by Tasks 3, 6, 7):
  - `VALID_KINDS: Final[frozenset[str]] = frozenset({"concept", "lesson"})`
  - `Decision` gains fields `kind: str = "lesson"`, `placement: str | None = None`, `title: str | None = None`.
  - `build_classifier_prompt(item_text, *, eligible_targets=(), project=None, taxonomy_block: str = "", branch_notes: str = "")` — new kwargs; when `taxonomy_block` is empty the prompt says concept routing is unavailable and `kind` must be `"lesson"`.
  - `decision_from_data(data, *, eligible_targets=(), taxonomy=None)` — new validation rules below.
  - `gate(...)` and `gate_precomputed(...)` pass the new kwargs through.

Validation rules in `decision_from_data` (all raised via the existing `_placement_or_plain` so durable items become routable `PlacementError`s, EXCEPT the concept-placement failures marked ⤵ which Task 3 handles by lesson-fallback — implement those as a distinct exception `ConceptPlacementError(PlacementError)` carrying the parsed Decision-so-far):

1. `kind` defaults to `"lesson"` when absent (backward compatible with stored verdicts-as-data); must be in `VALID_KINDS`.
2. `kind == "lesson"` ⇒ `placement` and `title` must be null; behavior otherwise identical to today.
3. `kind == "concept"` and `taxonomy is None` ⇒ ⤵ `ConceptPlacementError("no taxonomy")`.
4. `kind == "concept"` and `action == "create"`: `placement` must be a str; `classify_placement(taxonomy, placement)` must not raise (⤵ on raise); if it returns `"new-leaf"`, `title` must be a 2–4 word str whose slug matches `^[a-z0-9][a-z0-9-]*$` after lowercasing/joining with `-` (⤵ otherwise).
5. `kind == "concept"` and `action == "update"`: today's `target_page` eligibility rule, with the eligibility set extended by the caller (Task 3) — no classifier change beyond accepting it.
6. `scope == "global"` with `kind == "concept"` ⇒ ⤵ (no global taxonomy; spec §9).

- [ ] **Step 1: Write failing tests** (append to existing classifier tests)

```python
from lib.memory.taxonomy import parse_taxonomy
from skills.wrap.lib.classifier import (
    ConceptPlacementError, Decision, decision_from_data,
)

TAX = parse_taxonomy("```taxonomy\narchitecture/\n  memory-plane/\n```\n")

def _durable(**kw):
    return {"verdict": "durable", "reason": "r", "scope": "project",
            "action": "create", "target_page": None, **kw}

def test_kind_defaults_to_lesson():
    d = decision_from_data(_durable(), taxonomy=TAX)
    assert d.kind == "lesson" and d.placement is None

def test_concept_existing_node():
    d = decision_from_data(
        _durable(kind="concept", placement="architecture/memory-plane"),
        taxonomy=TAX)
    assert d.kind == "concept" and d.placement == "architecture/memory-plane"

def test_concept_new_leaf_needs_title():
    with pytest.raises(ConceptPlacementError):
        decision_from_data(
            _durable(kind="concept", placement="architecture/write-door"),
            taxonomy=TAX)
    d = decision_from_data(
        _durable(kind="concept", placement="architecture/write-door",
                 title="Write Door"),
        taxonomy=TAX)
    assert d.title == "Write Door"

def test_concept_without_taxonomy_routes_to_fallback():
    with pytest.raises(ConceptPlacementError):
        decision_from_data(_durable(kind="concept",
                                    placement="architecture"), taxonomy=None)

def test_concept_bad_placement():
    with pytest.raises(ConceptPlacementError):
        decision_from_data(
            _durable(kind="concept", placement="missing/child"), taxonomy=TAX)

def test_global_concept_rejected():
    with pytest.raises(ConceptPlacementError):
        decision_from_data(
            _durable(kind="concept", placement="architecture",
                     scope="global"), taxonomy=TAX)

def test_lesson_with_placement_rejected():
    with pytest.raises(Exception):
        decision_from_data(_durable(kind="lesson", placement="architecture"),
                           taxonomy=TAX)
```

- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/skills/wrap/test_classifier.py -v` (new tests FAIL: `ImportError: ConceptPlacementError`)
- [ ] **Step 3: Implement** — extend `Decision`, `VALID_KINDS`, `ConceptPlacementError(PlacementError)` (constructor also stores `claimed_kind`, `claimed_placement`, `claimed_title`), the six rules above inside `decision_from_data`, and thread `taxonomy=`/prompt kwargs through `classify_llm`, `gate`, `gate_precomputed`. Prompt addition (inserted after the scope paragraph of `_CLASSIFIER_PROMPT_TEMPLATE`):

```
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
```

With no taxonomy, substitute: `(no taxonomy available — "kind" must be "lesson", "placement" must be null)`.
- [ ] **Step 4: Run full classifier test file, verify pass**
- [ ] **Step 5: Commit** — `git commit -m "feat(classifier): kind/placement/title — concept-vs-lesson routing schema"`

---

### Task 3: Wrap routing — placement-aware creates, hubs, accretion, fallback

**Files:**
- Modify: `skills/wrap/lib/__init__.py` (`_durable_create_page` ~:652, `_ensure_lessons_hub` ~:673, durable loop ~:990–1130, durable-outcome counters ~:1141)
- Modify: `lib/instrument/collect.py` (add `KIND_PLACEMENT_EVENT = "placement_event"`, register in `__all__` and any kinds registry list in that module)
- Test: `tests/skills/wrap/test_wrap_session.py` (extend; locate the existing durable-loop tests with `grep -rln "_durable_create_page\|wrap_session" tests/skills/wrap/`)

**Interfaces:**
- Consumes: `load_taxonomy`, `classify_placement`, `render_block`, `TaxonomyError` (Task 1); `ConceptPlacementError`, `Decision.kind/placement/title` (Task 2).
- Produces (Task 7 reuses): `_durable_create_page(item, scope, project, *, placement=None, title=None) -> str`; `_ensure_hub(dir_rel, session, project, *, heading: str) -> bool` (rename of `_ensure_lessons_hub`; keep a `_ensure_lessons_hub = partial(...)`-style alias OR update the two call sites — update call sites, no alias); `_apply_concept_create(item, decision, project, session) -> dict` returning the same shape as today's create-branch bookkeeping.

Behavior to implement in `wrap_session`'s durable loop:

1. **Load taxonomy once per wrap** (before the loop): `taxonomy = None`; if `project`: `try: taxonomy = load_taxonomy(project) except TaxonomyError as exc: routing_blind = str(exc)`. Pass `taxonomy=` into `gate`/`gate_precomputed`.
2. **ConceptPlacementError handling** (both gate paths): catch it, record `collect.record(KIND_PLACEMENT_EVENT, {"event": "placement_rejected", "reason": ..., "session": session})`, and continue as a **lesson create** with the Decision-so-far (verdict durable, kind coerced to lesson). Never `_route_unplaced` for this class — the fact is placeable, just not conceptually.
3. **Concept create to a new leaf**: page path `projects/<project>/knowledge/<placement>/<slug(title)>.md` where the *last* placement segment is the new node — i.e. page is the node's own page: `projects/<project>/knowledge/<placement-parent>/<leaf>/<leaf>.md`? **No** — decision: the node page IS `knowledge/<placement>.md`'s folder-note? Keep it simple and consistent with folder-note hubs: a new leaf creates directory `knowledge/<placement>/`, its folder-note hub `<leaf>/<leaf>.md` via `_ensure_hub`, and the concept page as `knowledge/<placement>/<slug(title)>.md`. Ordered writes: (a) concept page, (b) `_ensure_hub` on its dir, (c) `_ensure_hub` on the parent dir (which now must also advertise subdirectory hubs — extend `_ensure_hub` to list child directory folder-notes as `- [name](name/name.md)` alongside `*.md` files), (d) schema.md taxonomy line: read `projects/<project>/schema.md`, splice the fence with `render_block(Taxonomy(nodes=tax.nodes + (placement,)))`, `propose_and_apply` an UPDATE with `reason="taxonomy: additive leaf <placement>"`, producer `wrap`, writer `llm-auto`. If schema.md is trust-user (`_target_trust`), the taxonomy line goes to `record_suggestion` instead (kind `page_write`, same payload shape as the trust-user update branch at ~:1066) — the page/hub writes still proceed (the tree exists on disk; wiki-health reconciles).
4. **Concept create to an existing node**: convert to an UPDATE against the node's page (`knowledge/<placement>/<lastseg>.md` if that file exists, else the single `*.md` whose stem == last segment, else fall back to lesson with a `placement_event {"event": "node_page_missing"}`). Merge = append `- <item text>` under a `## Facts` heading (create the heading if absent) using the same merge machinery the update branch uses today (reuse `_merge_update` — locate with `grep -n "def _merge" skills/wrap/lib/__init__.py` — if its LLM merge is what updates use, route through the same call; the mechanical append is the no-LLM fallback, replacing MergeError-to-unplaced for this branch).
5. **Concept page content** (new create): frontmatter `type: project-knowledge`, `schema_version: 1`, `project: <project>`, `title: "<title>"` + body `# <title>\n\n<one-line definition: the item text's first sentence>\n\n## Facts\n\n- <item text>`.
6. **Counters**: extend `KIND_DURABLE_OUTCOME` payload with `"created_concept"`, `"created_lesson"` (partition of `created`), `"concept_updates"`, `"placement_rejected"` — existing keys unchanged.
7. **Blindness**: when `routing_blind` is set and any durable item existed, add to the wrap result dict a `"concept_routing": {"blind": reason}` entry; when taxonomy loaded fine, `"concept_routing": {"blind": None}`. (Task 4 wires reporting.)
8. **Split suggestion**: after a successful concept UPDATE, count `^- ` bullets under `## Facts`; if > `_CONCEPT_SPLIT_BULLETS = 40`, `record_suggestion` (fingerprint `wrap-split:<page>`, so repeats dedupe) proposing a split. No auto-split.

- [ ] **Step 1: Write failing tests** — cover: (a) concept create new-leaf produces page + leaf hub + parent hub link + schema.md fence gains the node; (b) concept to existing node appends a Facts bullet (no new page); (c) `ConceptPlacementError` ⇒ lesson create + `placement_event` recorded; (d) absent schema.md ⇒ all durable items land as lessons and result carries `concept_routing.blind`; (e) trust-user schema.md ⇒ taxonomy edit suggested, page still created; (f) 41st bullet triggers split suggestion; (g) counters partition correctly. Use the existing wrap test fixtures (`grep -rn "wiki_root\|tmp_wiki" tests/skills/wrap/conftest.py tests/conftest.py` for the tmp-wiki fixture; follow the file's existing pattern of driving `wrap_session` with `verdicts=` precomputed data to avoid an LLM).
- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/skills/wrap/ -v -k concept`
- [ ] **Step 3: Implement** per behaviors 1–8. Keep the durable loop's create tail small by extracting `_apply_concept_create`.
- [ ] **Step 4: Run wrap suite** — `uv run pytest tests/skills/wrap/ -v` — all pass, zero regressions.
- [ ] **Step 5: Commit** — `git commit -m "feat(wrap): concept-tree routing — placement-aware creates, accreting nodes, lesson fallback"`

---

### Task 4: Blindness reporting + audit registration

**Files:**
- Modify: `lib/reporting.py` (the `REPORTING_SURFACES` registry — follow the four existing converted surfaces' pattern exactly; read the module docstring first)
- Modify: wrap's report rendering (locate: `grep -rn "render\|report" skills/wrap/lib/ skills/wrap/SKILL.md` — the surface that presents wrap results to the friend)
- Test: `tests/audit/` — the existing "every reporting surface must signal when it is blind" audit (from commit `bd639bb`) should pick the new blindness up; extend `tests/skills/wrap/` with a render-level assertion.

**Interfaces:**
- Consumes: `wrap_session` result's `concept_routing` dict (Task 3).

- [ ] **Step 1: Write failing test** — rendering a wrap result with `concept_routing.blind == "no ```taxonomy fence in schema.md"` must include the literal phrase `concept routing blind` plus the reason; with `blind: None` it must not. If wrap's `blind_when` declaration lives in `REPORTING_SURFACES`, extend that entry's declaration and assert the audit passes (`uv run pytest tests/audit/ -v`).
- [ ] **Step 2: Run, verify fail**
- [ ] **Step 3: Implement** — smallest change consistent with the existing Unknown conventions; do NOT restructure `lib/reporting.py`.
- [ ] **Step 4: Run** — `uv run pytest tests/audit/ tests/skills/wrap/ -v`
- [ ] **Step 5: Commit** — `git commit -m "feat(reporting): wrap declares concept-routing blindness"`

---

### Task 5: `rank()` path-kind boost for concept pages

**Files:**
- Modify: `skills/recall/lib/__init__.py` (the path-kind multiplier fn at ~:46–75)
- Test: the existing recall scoring tests (`grep -rln "multiplier\|path_kind\|rank" tests/skills/recall/`)

**Interfaces:** none new — internal to `rank`.

- [ ] **Step 1: Failing test** — a page path `projects/p/knowledge/architecture/write-door.md` gets the same multiplier as `decisions/` pages; `projects/p/knowledge/lessons/x.md` keeps its current (lower/neutral) multiplier; hubs unchanged.
- [ ] **Step 2: Run, verify fail**
- [ ] **Step 3: Implement** — in the multiplier mapping, add: path contains `/knowledge/` and its parent dir is not `lessons` ⇒ the `decisions/` boost value (copy the constant already used there; do not invent a new number).
- [ ] **Step 4: Run recall suite** — also run the retrieval-eval fixture if one exists (`uv run pytest tests/evalkit -v -k retrieval` — skip-if-absent is fine).
- [ ] **Step 5: Commit** — `git commit -m "feat(recall): concept-tree pages get the decisions-tier rank boost"`

---

### Task 6: Ingest drafts the taxonomy (Karpathy order)

**Files:**
- Modify: `skills/ingest-project/SKILL.md` (the live-session drafting instructions, ~:73–80)
- Modify: `skills/ingest-project/lib/__init__.py` (`assemble_l2` ~:69–125 — pointer section points at hubs; `ingest()` ~:128–224 — accept and queue the schema/hub pages)
- Test: `tests/skills/ingest_project/` (locate exact dir: `ls tests/skills/ | grep -i ingest`)

**Interfaces:**
- Consumes: `parse_taxonomy` (Task 1) — ingest validates the drafted taxonomy before writing.
- Produces: `ingest(..., schema_page: str | None = None, hub_pages: dict[str, str] | None = None)` — extended signature (check the current one first and extend minimally; if `schema_page` already exists as a payload per SKILL.md:73, wire it for real).

Behavior:
1. SKILL.md flow change: after the scan, the live session drafts the `taxonomy` fence + per-branch one-liners, **shows the friend the proposed tree in chat and waits for a yes** (the one human gate — spec §6), then calls `ingest()` with `schema_page` and `hub_pages` (one folder-note per branch).
2. `ingest()` validates `schema_page` with `parse_taxonomy` — `TaxonomyError` ⇒ refuse with a clear message (no partial tree), queue nothing new, existing map-only behavior proceeds.
3. Queue order: schema.md, branch hubs, then `map.md` whose Decision-map pointers reference the hubs (`- [architecture](knowledge/architecture/architecture.md)` style).
4. Initial concept pages for strong scan facts stay a SKILL.md instruction to the live session (each lands through the normal write door as `project-knowledge` pages under the right branch) — no new code path.

- [ ] **Step 1: Failing tests** — (a) `ingest` with a valid `schema_page` + two `hub_pages` queues schema, hubs, and a map whose pointer lines hit the hub paths; (b) invalid taxonomy ⇒ raises/returns refusal, no schema or hub writes queued; (c) legacy call without `schema_page` behaves exactly as today (regression).
- [ ] **Step 2: Run, verify fail**
- [ ] **Step 3: Implement** lib changes; then rewrite the SKILL.md drafting section to the Karpathy order with the explicit in-chat approval sentence.
- [ ] **Step 4: Run** — `uv run pytest tests/skills/ -v -k ingest`
- [ ] **Step 5: Commit** — `git commit -m "feat(ingest): draft the taxonomy first — Karpathy order, one human gate"`

---

### Task 7: Distill `--seed-tree` backfill mode

**Files:**
- Modify: `skills/distill/lib/__init__.py` (the candidate loop ~:150–220 already calls `gate_precomputed` and `_durable_create_page`; add a `seed_tree(project, ...)` entry point)
- Modify: `skills/distill/SKILL.md` (document `--seed-tree <project>`; declare the widened write surface: `projects/<slug>/knowledge/**` and `projects/<slug>/schema.md`)
- Test: `tests/skills/distill/` (locate exact dir)

**Interfaces:**
- Consumes: Task 3's `_apply_concept_create` + `_ensure_hub` (import from `skills.wrap.lib` exactly as the distiller already imports `_durable_create_page` at `skills/distill/lib/__init__.py:25`); Task 1's `load_taxonomy`.
- Produces: `seed_tree(project: str, llm_call, *, cap: int | None = None) -> dict` — result mirrors `distill_run`'s shape plus `{"annotated": [...]}`.

Behavior:
1. Manual trigger only — never part of the scheduled distill path; SKILL.md says so.
2. Enumerate `projects/<project>/knowledge/lessons/*.md` newer than a dedicated watermark (`seed_tree_watermark`, stored beside the distiller's existing watermark — copy that mechanism, key it per project).
3. Each lesson body runs through `gate` (live LLM path — this mode has an `llm_call`) with `taxonomy=load_taxonomy(project)`; `TaxonomyError` ⇒ refuse the whole run: "no taxonomy — run ingest's taxonomy draft first" (blind, not a guess).
4. `kind == "concept"` ⇒ place via Task 3's shared machinery; then annotate the source lesson: append `\nSee: [[<placement last segment>]]\n` via an UPDATE proposal (lesson pages are model-trust; the `_target_trust == "user"` guard still applies). `kind == "lesson"` or non-durable ⇒ skip, advance watermark.
5. Cap: reuse the distiller's `WRITE_CAP` semantics (annotation UPDATEs count toward the cap — they are writes).
6. Metrics: record under `KIND_DISTILLER_RUN` with `"mode": "seed_tree"` plus the Task 3 counter names.
7. Distiller hub gap: `seed_tree` (and the existing distill create path, one-line fix) call `_ensure_hub` after creates — closing the exploration-found gap where distiller writes never maintained hubs.

- [ ] **Step 1: Failing tests** — (a) a lessons dir with one conceptual + one episodic lesson: concept lands in the tree, source lesson gains the `See:` line, episodic lesson untouched, watermark advances past both; (b) no schema.md ⇒ run refuses, zero writes; (c) cap stops the run with `capped_remainder` and a resumable watermark; (d) re-run after completion writes nothing (idempotent via watermark + noop-duplicate).
- [ ] **Step 2: Run, verify fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run** — `uv run pytest tests/skills/distill/ -v` (also the existing distill regression tests)
- [ ] **Step 5: Commit** — `git commit -m "feat(distill): --seed-tree backfill — mine lessons into the concept tree"`

---

### Task 8: Doctrine, docs, and full-suite gate

**Files:**
- Modify: `skills/wrap/SKILL.md` (line ~120's placement instruction now describes the REAL mechanism: classifier `kind`/`placement`, additive rule, lesson fallback — no longer an unimplementable ask)
- Modify: `skills/bootstrap-project` skeleton source (`wiki-skeleton/manifest.yaml` ~:135–150 — the `schema.md` stub gains an empty `taxonomy` fence with a comment line `# add branches as slug/ lines, two-space indent`; verify YAML escaping of the fence)
- Modify: `CHANGELOG.md` (follow the existing entry format under an Unreleased/next-version heading; check `scripts/bump_version.py` conventions first — memory: it maintains version artifacts)
- Test: run everything.

- [ ] **Step 1: Update the three docs/files above** — SKILL.md text must match the shipped API exactly (the review criterion that caught the last spec drift).
- [ ] **Step 2: Skeleton test** — extend the wiki-skeleton test (`tests/wiki_skeleton/`) asserting the stamped `schema.md` stub parses with `parse_taxonomy` raising `TaxonomyError("taxonomy fence is empty")`... note: empty fence raises — so instead assert the stub CONTAINS the fence and that wrap treats empty-fence as blind-with-reason (already covered by Task 3's TaxonomyError path). Assert the stub fence exists and `parse_taxonomy` raises the empty-fence error specifically (defined behavior, not a crash).
- [ ] **Step 3: Full gates**

```bash
uv run pytest
uv run ruff check .
```
Expected: full suite green (was 3660 + new tests), lint clean.
- [ ] **Step 4: Commit** — `git commit -m "docs: concept-tree routing — SKILL.md truth, skeleton stub, changelog"`

---

## Self-review notes (run, findings fixed inline)

- **Spec coverage:** §3→Task 1+8(stub); §4→Tasks 2,3; §5→Tasks 3,5; §6→Task 6; §7→Task 7; §8→Tasks 3,4,7 (counters + blindness); §9 respected (no global concepts — Task 2 rule 6; no auto-split — Task 3.8; lesson naming untouched). Restructure-suggestion path (§2.2) is covered by: split suggestions (Task 3.8) + trust-user schema.md routing (Task 3.3); a general "agent proposes a restructure" producer is NOT built — nothing in this plan needs it, and no code path would trigger it (YAGNI; the suggestion store accepts hand-raised ones later).
- **Type consistency:** `Decision.kind/placement/title` names match across Tasks 2/3/7; `_ensure_hub` signature consumed by Task 7 as produced by Task 3; `Taxonomy.has`/`classify_placement`/`render_block` per Task 1.
- **Known judgment point for implementers:** Task 3 behavior 4's node-page resolution and merge reuse requires reading the existing `_merge` machinery first; the task text says exactly where to look. Task boundaries let a reviewer reject Task 3 without touching Tasks 1–2.
