# 0.7.9 "doctrine holds" Train Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two guard bypasses found by the #68 generated tier, make the wake-up doctrine card carry the full execution pipeline in both variants, and byte-budget the wake-up render against the harness inline threshold with criticality ordering and tail-first cascade truncation.

**Architecture:** Three bounded fixes to existing flows. Task 1 widens two guard regexes and de-quotes refspec tokens. Task 2 rewrites both doctrine-card bodies and raises `DOCTRINE_BUDGET` so the full card survives its own budget check. Task 3 reorders two section appends in `compose_wake_up_context`, adds a byte-ceiling cascade that degrades sections tail-first (extras → pointers → dropped → next section up), and adds a persisted-output sentinel line.

**Tech Stack:** Python 3.11 dev / **py3.9-safe stdlib-only in `hooks/`** (the cold-machine CI seam runs hooks on `python:3.9-slim` with no deps), pytest, `uv run`.

**Spec:** Issues #69, #70, #71 (each carries the approved fix, verbatim from the 2026-08-18 chat approval). Background verification evidence: `docs/superpowers/specs/2026-08-18-post-0.7.7-fix-train-design.md` §5 filed #69.

## Global Constraints

- `hooks/**` files: stdlib-only, py3.9-compatible (keep `from __future__ import annotations`; no 3.10+ syntax outside annotations).
- Never write literal force-push- or secret-shaped strings in test source — assemble at runtime (convention: header comment in `tests/hooks/test_guards_generated.py`, and `tests/lib/memory/test_scrub.py`). The repo's own pre-push guard scans added lines with the INSTALLED scrub.
- Doctrine text speaks in model **classes**, never model names (`doctrine/model-classes.md` owns the mapping). A test enforces this.
- No implementer commits to `main`; work stays on this worktree branch. Each task commits its own files only.
- Run only your task's targeted test files plus directly-affected existing modules; the full suite runs at train review.
- Existing behaviors that must not regress (Task 3 especially): empty-wiki compose returns `""`; doctrine card and nudges ride real content only; no bare section headers; quarantine/foreign holds and the held-out count line; `miss_log.log_surface` + `KIND_INJECTED_BYTES` instrumentation unconditional.

---

### Task 1: #69 — guard bypass fixes (newline separators + quoted refspec)

**Files:**
- Modify: `hooks/guards/pre_push_scan.py:74` (`_GIT_PUSH_RE`), `:228-241` (`_has_force_refspec`)
- Modify: `hooks/guards/write_gate.py:70` (`_RM_RE`)
- Test: `tests/hooks/test_guards_generated.py` (flip the 10 strict xfails), `tests/hooks/test_guards.py` (run for regressions, expect zero edits)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks rely on. Fully independent.

- [ ] **Step 1: Turn the pinned findings into failing tests**

In `tests/hooks/test_guards_generated.py`, locate the 10 finding tests marked `@pytest.mark.xfail(strict=True, reason=...#68...)` (8 newline-prefix push/rm cases, 2 quoted-refspec cases). Remove the xfail decorators so they assert the guard blocks. Do not change the assertions or the runtime string assembly.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/hooks/test_guards_generated.py -q`
Expected: exactly 10 failures (the former xfails), everything else green.

- [ ] **Step 3: Implement the guard fixes**

`hooks/guards/pre_push_scan.py:74` — add `\n` to the separator class:

```python
_GIT_PUSH_RE = re.compile(r"(?:^|[;&|\n]\s*)git\s+push\b")
```

`hooks/guards/write_gate.py:70` — same:

```python
_RM_RE = re.compile(r"(?:^|[;&|\n]\s*)(rm|unlink)\b")
```

`hooks/guards/pre_push_scan.py` `_has_force_refspec` token loop — strip shell quotes before the `+` test (the shell strips them before git sees the refspec, so a quoted `+ref` is a real forced update):

```python
    for token in after.split():
        token = token.strip("\"'")
        if token.startswith("+") and len(token) > 1:
            return True
    return False
```

Update `_has_force_refspec`'s docstring sentence "Only checks whitespace-separated positional tokens…" to add: "Tokens are stripped of surrounding shell quotes first — the shell removes them before git parses the refspec."

- [ ] **Step 4: Run targeted tests to verify green**

Run: `uv run pytest tests/hooks/test_guards_generated.py tests/hooks/test_guards.py -q`
Expected: all pass, 0 xfailed remaining in the generated file, `test_guards.py` untouched and green. Generated file still < ~2s.

- [ ] **Step 5: Commit**

```bash
git add hooks/guards/pre_push_scan.py hooks/guards/write_gate.py tests/hooks/test_guards_generated.py
git commit -m "fix(guards): newline separators + quoted refspec detection — #69"
```

---

### Task 2: #70 — doctrine card carries the full pipeline (both variants)

**Files:**
- Modify: `hooks/wake-up/wakeup/doctrine_card.py` (both bodies, both gate variants)
- Modify: `hooks/wake-up/wakeup/__init__.py:150` (`DOCTRINE_BUDGET: 500 → 650`)
- Test: `tests/hooks/test_doctrine_card.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the exact section header `SECTION_DOCTRINE = "## How we work (execution doctrine)"` (unchanged) and `render_doctrine_card` / `render_doctrine_card_compact` signatures (unchanged) — Task 3's composer and tests rely on both staying stable.

- [ ] **Step 1: Read the existing test file, then write failing tests**

Read `tests/hooks/test_doctrine_card.py` first — it pins current card text; update pinned-text assertions as part of this step rather than leaving them to break silently. Add these tests (adapt naming to the file's existing style):

```python
_PIPELINE_PHASES = [
    "brainstorm", "worktree", "plan", "decompose", "per-task review", "review gate", "finish",
]
_SKILL_NAMES_FULL = [
    "superpowers:brainstorming",
    "superpowers:using-git-worktrees",
    "superpowers:writing-plans",
    "superpowers:subagent-driven-development",
    "superpowers:test-driven-development",
    "superpowers:finishing-a-development-branch",
]
_MODEL_NAMES = ["sonnet", "haiku", "opus", "fable", "claude-"]


def test_full_card_names_every_phase_and_skill():
    card = render_doctrine_card(superpowers=True)
    low = card.lower()
    for phase in _PIPELINE_PHASES:
        assert phase in low, phase
    for skill in _SKILL_NAMES_FULL:
        assert skill in card, skill
    assert "model-classes.md" in card          # routing pointer
    assert "per-task" in low                    # review before chaining


def test_fallback_card_names_phases_without_superpowers_refs_breaking():
    card = render_doctrine_card(superpowers=False)
    low = card.lower()
    for phase in _PIPELINE_PHASES:
        assert phase in low, phase
    assert "model-classes.md" in card
    assert "recommended companion" in low       # footer still points at superpowers


def test_compact_card_keeps_skill_names_and_routing():
    card = render_doctrine_card_compact()
    assert "superpowers:writing-plans" in card
    assert "superpowers:subagent-driven-development" in card
    assert "model-classes.md" in card
    assert len(card) <= 1200  # head-preserving fallback must stay small


def test_no_model_names_anywhere():
    for card in (
        render_doctrine_card(True),
        render_doctrine_card(False),
        render_doctrine_card_compact(),
    ):
        low = card.lower()
        for name in _MODEL_NAMES:
            assert name not in low, name


def test_full_card_fits_doctrine_budget_at_default_ratio():
    from wakeup import DOCTRINE_BUDGET, CHARS_PER_TOKEN
    card = render_doctrine_card(superpowers=True)
    assert len(card) <= DOCTRINE_BUDGET * CHARS_PER_TOKEN
```

(Match the file's existing import mechanism for the `wakeup` package — it already imports these modules; reuse its conftest/path approach.)

- [ ] **Step 2: Run to verify the new tests fail**

Run: `uv run pytest tests/hooks/test_doctrine_card.py -q`
Expected: new tests FAIL (missing phases/skills/routing); pre-existing tests pass or fail only on pinned old text you are about to update.

- [ ] **Step 3: Rewrite the card bodies**

In `hooks/wake-up/wakeup/doctrine_card.py`, replace the gates and bodies with the seven-phase pipeline. Exact content:

```python
_GATE_1_SP = (
    "1. **Brainstorm gate.** You MUST NOT design or build anything without an "
    "approved spec/plan. If none exists, invoke `superpowers:brainstorming` "
    "first — pin purpose, constraints, and approaches with the user before code."
)
_GATE_1_FALLBACK = (
    "1. **Brainstorm gate.** You MUST NOT design or build anything without an "
    "approved spec/plan. If none exists, work the idea back and forth with the "
    "user first — purpose, constraints, 2-3 approaches with trade-offs — and get "
    "explicit approval on a written design before code."
)
_GATE_2_SP = (
    "2. **Isolate & plan.** Set up an isolated workspace "
    "(`superpowers:using-git-worktrees`), then write the implementation plan "
    "with `superpowers:writing-plans` — the MAIN planning step; bite-sized "
    "TDD tasks with exact files and code."
)
_GATE_2_FALLBACK = (
    "2. **Isolate & plan.** Work on an isolated branch/worktree, then write "
    "the implementation plan — bite-sized test-first tasks with exact files "
    "and code — before any implementation."
)
_GATE_3 = (
    "3. **Decompose.** For multi-part plans, spawn the `ren-planner` agent to "
    "cut approved work into atomic briefs (one subtask ≈ one clean context). "
    "Skip only when the plan is already atomic — lowest rung that fits."
)
_GATE_4_SP = (
    "4. **Dispatch.** Execute via `superpowers:subagent-driven-development`: "
    "one fresh subagent per task, independent tasks in parallel, chained ones "
    "sequentially, test-first (`superpowers:test-driven-development`) inside "
    "each. Route every subagent to the cheapest class that fits per "
    "`doctrine/model-classes.md` — orchestrator-class workers are an "
    "anti-pattern."
)
_GATE_4_FALLBACK = (
    "4. **Dispatch.** One fresh subagent per subtask; independent tasks in "
    "parallel, chained ones sequentially; test-first inside each (failing "
    "test, implement, pass, commit). Route every subagent to the cheapest "
    "class that fits per `doctrine/model-classes.md` — orchestrator-class "
    "workers are an anti-pattern."
)
_GATE_5 = (
    "5. **Per-task review.** Review each task's work before chaining to the "
    "next — do not let unreviewed work compound."
)
_GATE_6 = (
    "6. **Review gate.** Before claiming done, spawn the `ren-reviewer` agent "
    "on the full train. Findings must be verified with runnable repros. Do "
    "NOT proceed past unresolved CRITICAL/HIGH findings. Work is not done "
    "until its open-work ledger line is closed."
)
_GATE_7_SP = (
    "7. **Finish.** Integrate via `superpowers:finishing-a-development-branch` "
    "and follow the repo's publish checklist when releasing."
)
_GATE_7_FALLBACK = (
    "7. **Finish.** Merge/integrate deliberately and follow the repo's "
    "publish checklist when releasing."
)
```

`_BODY` becomes (keep the red-flags table, trimmed to these three rows to pay for the new gates):

```python
_BODY = """
RenOS execution doctrine — these gates are MANDATORY for design/build work.

{gate1}
{gate2}
{gate3}
{gate4}
{gate5}
{gate6}
{gate7}

Red flags — if you catch yourself thinking any of these, STOP: the gate applies.

| Thought | Reality |
|---|---|
| "Too simple to need a design" | Simple work with unexamined assumptions wastes the most time. |
| "The plan is in my head" | If it isn't written and approved, it doesn't exist. |
| "This subagent needs the strongest model" | Route by class per `doctrine/model-classes.md`; judgment stays up, work goes down. |
"""
```

`render_doctrine_card` formats all seven gates (`gate2`/`gate4`/`gate7` switch on `superpowers` like `gate1`; `gate3`/`gate5`/`gate6` are shared). `_COMPACT_BODY` becomes:

```python
_COMPACT_BODY = """
RenOS execution doctrine — these gates are MANDATORY for design/build work.

1. **Brainstorm gate.** No design or build work without an approved spec/plan.
2. **Isolate & plan.** Worktree (`superpowers:using-git-worktrees`), then the
   implementation plan via `superpowers:writing-plans`.
3. **Decompose.** `ren-planner` briefs for multi-part plans (skip if atomic).
4. **Dispatch.** `superpowers:subagent-driven-development`, test-first per task;
   route subagents by class per `doctrine/model-classes.md` — never
   orchestrator-class workers.
5. **Per-task review** before chaining; then the **`ren-reviewer` gate** on the
   full train — clear every CRITICAL/HIGH and close the open-work ledger line.
"""
```

In `hooks/wake-up/wakeup/__init__.py:150`: `DOCTRINE_BUDGET: Final[int] = 650` (the new full card is ~2,400 chars; 500 × 4.0 = 2,000 would force the compact fallback on every compose — the exact regression #70 exists to prevent. 650 × 4.0 = 2,600).

- [ ] **Step 4: Run to verify green**

Run: `uv run pytest tests/hooks/test_doctrine_card.py tests/hooks/test_wakeup.py -q`
Expected: all pass (wakeup tests catch any budget/pointer interplay).

- [ ] **Step 5: Commit**

```bash
git add hooks/wake-up/wakeup/doctrine_card.py hooks/wake-up/wakeup/__init__.py tests/hooks/test_doctrine_card.py
git commit -m "feat(wakeup): doctrine card carries the full 7-phase pipeline + class routing — #70"
```

---

### Task 3: #71 — wake-up byte ceiling, criticality order, cascade truncation, sentinel

**Files:**
- Modify: `hooks/wake-up/wakeup/__init__.py` (`compose_wake_up_context` ~:1213-1500, new constants near :139, new helper)
- Test: `tests/hooks/test_wakeup.py`

**Interfaces:**
- Consumes: Task 2's unchanged `SECTION_DOCTRINE` header and render functions.
- Produces: new public constants `WAKEUP_BYTE_CEILING_DEFAULT: int = 9_500`, env override name `REN_WAKEUP_BYTE_CEILING`, sentinel line constant `SENTINEL_LINE`. Add all to `__all__`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/hooks/test_wakeup.py`, reusing its existing wiki-fixture helpers (it already builds stamped temp wikis for compose tests — follow the file's established fixture pattern):

```python
def test_section_order_is_criticality_first(populated_wiki_with_everything):
    # fixture must yield a wiki producing: pending suggestions, open work,
    # identity, overview, L1, L2, extras — see existing fixtures for each piece
    out = compose(...)  # via the file's existing compose harness
    positions = {
        name: out.index(name)
        for name in (SECTION_DOCTRINE, SECTION_PENDING, SECTION_IDENTITY,
                     SECTION_OVERVIEW, SECTION_OPENWORK, SECTION_L1,
                     SECTION_L2, SECTION_EXTRAS)
        if name in out
    }
    ordered = sorted(positions, key=positions.get)
    expected = [n for n in (SECTION_DOCTRINE, SECTION_PENDING, SECTION_IDENTITY,
                            SECTION_OVERVIEW, SECTION_OPENWORK, SECTION_L1,
                            SECTION_L2, SECTION_EXTRAS) if n in positions]
    assert ordered == expected


def test_sentinel_is_second_line(any_populated_wiki):
    out = compose(...)
    assert out.splitlines()[1] == SENTINEL_LINE


def test_byte_ceiling_respected(monkeypatch, oversize_wiki):
    monkeypatch.setenv("REN_WAKEUP_BYTE_CEILING", "4000")
    out = compose(...)
    assert len(out.encode("utf-8")) <= 4000


def test_cascade_degrades_extras_before_any_other_section(monkeypatch, oversize_wiki_with_extras):
    # ceiling chosen so that shrinking extras to pointer lines is sufficient
    monkeypatch.setenv("REN_WAKEUP_BYTE_CEILING", <fitting value>)
    out = compose(...)
    assert SECTION_EXTRAS in out                  # pointers survive
    assert "#### " in out.split(SECTION_EXTRAS)[1]  # rel-path pointer lines
    # every non-extras section's content is byte-identical to an unceilinged compose
    monkeypatch.delenv("REN_WAKEUP_BYTE_CEILING")
    full = compose(...)
    for name in (SECTION_PENDING, SECTION_OPENWORK, SECTION_L1, SECTION_L2):
        if name in full:
            assert _section_body(full, name) == _section_body(out, name)


def test_cascade_never_touches_doctrine_pending_openwork(monkeypatch, oversize_wiki_with_extras):
    monkeypatch.setenv("REN_WAKEUP_BYTE_CEILING", "2500")  # brutal ceiling
    out = compose(...)
    assert SECTION_DOCTRINE in out
    assert SECTION_PENDING in out or SECTION_PENDING not in compose_without_ceiling
    assert SECTION_OPENWORK in out or SECTION_OPENWORK not in compose_without_ceiling
```

Write `_section_body(text, header)` as a small local test helper (slice from header to the next `"## "`). Replace `compose(...)` placeholders with the file's actual compose invocation pattern; the fixture names above are descriptive — build them from the file's existing fixture vocabulary.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/hooks/test_wakeup.py -q -k "order or sentinel or ceiling or cascade"`
Expected: FAIL (`SENTINEL_LINE` undefined, order wrong, no ceiling behavior).

- [ ] **Step 3: Implement**

(a) **Constants** (near the budget block, ~:139):

```python
# Harness inline threshold defense (#71): Claude Code persists SessionStart
# hook output past ~10KB and shows only a ~2KB preview — bytes past the
# cliff cost the whole tail. Budget in BYTES against that cliff, under it.
WAKEUP_BYTE_CEILING_DEFAULT: Final[int] = 9_500
SENTINEL_LINE: Final[str] = (
    "*(If this context appears truncated or as a persisted-file preview, "
    "Read the full file before proceeding.)*"
)


def _byte_ceiling() -> int:
    raw = os.environ.get("REN_WAKEUP_BYTE_CEILING", "")
    try:
        value = int(raw)
    except ValueError:
        return WAKEUP_BYTE_CEILING_DEFAULT
    return value if value > 0 else WAKEUP_BYTE_CEILING_DEFAULT
```

(b) **Sentinel**: seed the sections list with the sentinel as part of the head:

```python
sections: list[str] = [f"## RenOS wake-up context (source={source})\n{SENTINEL_LINE}\n"]
```

(c) **Reorder** (two relocations, no other flow changes):
- Move the open-work block (`read_open_work` / `SECTION_OPENWORK`, currently after the L1 block at ~:1353) up to directly after the overview block inside the same `project_dir is not None` region (it only needs `openwork_rel`, defined at the top of that region).
- Move the pending block (`suggestion_line()` / `SECTION_PENDING`, currently at ~:1382) up to directly before the identity block. Final append order: header+sentinel → pending → identity → overview → open work → L1 → L2 → routines → extras → held-count → nudges; the doctrine card still `insert(1, ...)`s after the emptiness verdict, landing between header and pending.
- Track keys alongside: maintain `section_keys: list[str]` appended in lockstep with `sections` (use the `SECTION_*` constant for header appends, a same-key value for each section's content append, `"_head"` for the seed, `"_misc"` for held-count/nudge lines, `"_doctrine"` inserted in lockstep with the card).

(d) **Cascade**, after the existing token guard and before instrumentation. Cascade order — least critical first, and the protected head is never touched:

```python
_CASCADE_ORDER: Final[tuple[str, ...]] = (
    SECTION_EXTRAS, SECTION_ROUTINES, SECTION_L2, SECTION_L1,
    SECTION_OVERVIEW, SECTION_IDENTITY,
)
```

Algorithm (implement as a helper `_apply_byte_ceiling(section_keys, sections, ceiling, chars_per_token) -> str`):
1. Join and measure `len(composed.encode("utf-8"))`; under ceiling → return as-is.
2. Stage 1 — degrade extras to pointers: replace each extras content block with only its `#### {rel}` line plus a single trailing line `*(excerpts elided for size — fetch via /ren:recall)*`. Re-measure.
3. Stage 2 — still over: drop the extras section (header + blocks) entirely. Re-measure.
4. Stage 3 — walk the remaining `_CASCADE_ORDER` one section at a time: truncate THAT section's content to fit the overshoot (reuse `truncate_text_to_tokens` with a budget computed from the byte overshoot via `chars_per_token`, floor 0) and append `*(truncated for size — fetch via /ren:recall)*`; if its budget reaches 0, drop the section (header included). Re-measure after each section; stop as soon as under ceiling. Never modify `_head`, `_doctrine`, `SECTION_PENDING`, `SECTION_OPENWORK`, or `_misc` lines.
5. Log one warning naming what was degraded: `logger.warning("wake-up over byte ceiling (%d > %d); degraded: %s", ...)`.

Wire it in: `composed = _apply_byte_ceiling(section_keys, sections, _byte_ceiling(), chars_per_token)` replacing the current final `"\n\n".join`-based assembly (keep the existing #48 token guard semantics by running it before the byte cascade, operating on the same keyed lists).

(e) Add `WAKEUP_BYTE_CEILING_DEFAULT` and `SENTINEL_LINE` to `__all__`.

- [ ] **Step 4: Run the full wake-up test module**

Run: `uv run pytest tests/hooks/test_wakeup.py tests/hooks/test_doctrine_card.py -q`
Expected: all pass, including every pre-existing compose test (empty-wiki `""`, no-bare-header, quarantine holds, instrumentation).

- [ ] **Step 5: Commit**

```bash
git add hooks/wake-up/wakeup/__init__.py tests/hooks/test_wakeup.py
git commit -m "feat(wakeup): byte ceiling vs harness threshold, criticality order, cascade truncation, sentinel — #71"
```

---

### Task 4: Train close-out (orchestrator, after per-task reviews)

**Files:**
- Modify: `CHANGELOG.md`, version sites via `scripts/bump_version.py`

- [ ] **Step 1:** Full suite + lints: `uv run pytest -q` (expect ~3349+ passed, **0 xfailed** — Task 1 consumed all 10), `scripts/lint-yaml-frontmatter.py`, `scripts/lint_no_dev_wiki_content.py`.
- [ ] **Step 2:** ren-reviewer gate on the whole train (adversarial; clear CRITICAL/HIGH).
- [ ] **Step 3:** `uv run python scripts/bump_version.py 0.7.9`; write the `## [0.7.9] — "doctrine holds"` CHANGELOG section covering #69/#70/#71; release commit.
- [ ] **Step 4:** Finish via superpowers:finishing-a-development-branch (merge to main), then the publish checklist: annotated tag `v0.7.9`, `git push origin main --follow-tags`, watch CI, `gh release create`, close #69/#70/#71 with evidence.

---

## Execution notes

- Task 1 is independent; Tasks 2 → 3 are sequential (Task 3's tests exercise the card Task 2 ships). Run Task 1 in parallel with Task 2 if desired; Task 3 starts only after Task 2's review passes.
- Implementer subagents run **worker-class (Sonnet)** per `doctrine/model-classes.md`. Per-task review before chaining (subagent-driven-development's two-stage review). The train-level ren-reviewer gate stays orchestrator-class.
- Test code in this plan is the specification of intent; adapt mechanically to each test file's existing fixture/import vocabulary rather than inventing parallel harnesses.
