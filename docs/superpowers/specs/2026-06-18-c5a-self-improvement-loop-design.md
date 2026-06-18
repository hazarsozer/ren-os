# C5a — Self-Improvement Loop Made Real (Eval Backend + Change Proposer) — Design Spec

> **Status:** Approved design (2026-06-18). Brainstormed via `superpowers:brainstorming`; scope, backend,
> slice-size, and three implementation calls locked with the maintainer (see §2). This spec is the input
> to a `superpowers:writing-plans` pass and the contract for the subsequent `subagent-driven-development`
> build (the C1/C2/C4 recipe).
>
> **Roadmap slice:** C5 (Pillar 5, "Self-improvement") in
> `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`. C5 is decomposed; **this spec is C5a**
> (the self-improvement loop). **C5b** (dependency/call-graph + auto/cadence code-map refresh — the two
> C2 deferrals) is a separate, later slice and is **out of scope here**.
> **Builds on:** C2 (`code-map`) only insofar as C5b will; C5a has **no** dependency on the code-map.
> **Foundational ADRs:** ADR-012 (Two-Layer Self-Improvement), ADR-011 (Skill Schema / `eval.json`),
> ADR-031 (Solo-First Pivot — the "bike method" framing), ADR-003 (No-Daemon Rule).

---

## 1. Purpose

`/ren:improve-skill <skill>` ships built but **inert**: the Karpathy loop, six-gate pre-flight, git-as-memory,
budget tracker, and keep/revert machinery are all real and tested (**144 tests green** at baseline), but the
loop's two LLM-dependent layers are stubbed. C5a fills both, behind the **existing injected-callable seams**,
so the loop runs end-to-end and demonstrably improves a real skill — **proof-of-life**, supervised, with
autonomy still earned (not granted). Per the user's decisions: we **own the eval backend** (an LLM-judge we
write, not Skill Creator's `run_eval.py`), and the slice is **spike-gated** (mirroring C2's lean-ctx spike).

The discipline that makes it safe: **a self-modifying loop ships with training wheels.** The eval backend
becoming available is a *capability*, not a *grant of autonomy* — the bike-method ADR (§9) makes that explicit.

---

## 2. Locked scope decisions (maintainer, 2026-06-18)

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| 1 | **Which slice of C5** | **C5a — the loop only.** Dep/call-graph + auto/cadence refresh → C5b (deferred, named). | C5a has no code-map dependency; one subsystem per plan (the C1/C2 discipline). |
| 2 | **Eval backend owner** | **Own LLM-judge** (reimplement `run_evals` ourselves), **not** adopt Skill Creator's `run_eval.py`. | No dependency on an external script's path/format/installed-ness (the fragility class that bit C2's lean-ctx). We own `eval.json`'s schema (ADR-011), so "schema drift" is moot. Flips `references/eval-runner.md`'s tentative path-1 pick → path-2. |
| 3 | **Slice size** | **Wire BOTH layers** (eval-runner + change-proposer) in one slice. | A working eval-runner alone leaves the loop inert (it would score the baseline, hit the proposer stub, and exit `NO_IMPROVEMENT_POSSIBLE`). Both are symmetric (subprocess `claude` + parse) → bundling is coherent and delivers a demonstrable loop. |
| 4 | **improve-skill's own `eval.json`** | **Add a minimal one** (activation + pre-flight-refusal assertions only). | Closes an ADR-011 conformance gap (the dir has only `eval/README.md`); makes the self-improvement skill self-improvable (dogfooding). Loop-behavioral assertions are deferred (they'd recursively run the loop). |
| 5 | **Eval determinism vs cost** | **Single skill-run by default; `--eval-runs N` flag** for 3-run majority. Judge at **temp 0**. | The expensive nondeterminism is the *skill-run*, not the judge. Temp-0 judge satisfies eval-runner.md's "no stochastic noise in the score." Tripling skill-runs is opt-in (overnight stability), not the supervised-V1 default. |
| 6 | **Bike-method enforcement** | **Posture + manual gate; NO new trust-tracking code.** | The only *code* gate stays the existing autonomous-mode ceilings. "Earned" = a manual maintainer banner-downgrade after ≥3 logged clean supervised runs. Avoids building the speculative trust subsystem solo-first warns against. |

---

## 3. Architecture — the seam is already there

The orchestrator `improve_skill(args, *, skills_root, eval_runner, change_proposer, pricing_table, cwd)`
(`skills/improve-skill/lib/__init__.py`) already injects two callables and composes pre-flight + git +
budget + the keep/revert loop. C5a fills the two **default** implementations behind those seams; the
orchestrator's tested surface changes only in small, localized ways (the `ProposerError` skip-path in §4.2 and the eval-usage budget plumbing in §7).

| Unit | Path | Status | Responsibility |
|------|------|--------|----------------|
| **claude wrapper** | `skills/improve-skill/lib/claude_cli.py` | **NEW** | The single place that shells the `claude` CLI (`--print`, and `--bare` for the proposer), enforces a timeout, and returns a typed `ClaudeRun{output_text, usage, activated, raw}`. Both LLM layers depend only on this → swappable + mockable. The exact flags that surface output + token usage + skill-activation are a **spike deliverable** (§5). |
| **eval-runner** | `lib/eval_runner.py` → `run_evals()` | **FILL STUB** | Replace the `raise EvalBackendNotConfiguredError` body with the own-judge backend (§4.1). Composes the *already-tested* pure helpers (`load_eval_spec`, `filter_tests_by_ids`, `compute_total_assertions`, `make_failing_assertion_id`, `empty_eval_result`). |
| **judge** | `lib/eval_runner.py` (or `lib/judge.py` if it grows) | **NEW** | `judge_assertion(output, assertion) -> bool` — a cheap Haiku call (temp 0) through `claude_cli`. |
| **sandbox** | `lib/eval_runner.py` (or `lib/sandbox.py`) | **NEW** | Context manager: tmp CWD + `SF_WIKI_ROOT` / `CLAUDE_PLUGIN_DATA` → tmp dirs for the skill sub-run; teardown. Final shape confirmed by the spike (§5). |
| **change-proposer** | `lib/__init__.py` → `_default_change_proposer()` | **FILL STUB** | Replace the `raise NotImplementedError` body with a `claude --bare --print` call (§4.2) returning `(ProposedChange, ApiUsage, turns)`. |
| **types** | `lib/types.py` → `EvalResult` | **AMEND (additive)** | Add `usage: ApiUsage = ApiUsage(0, 0)` so eval-side token spend feeds the budget tracker (§7). Frozen-dataclass, default-valued → backward-compatible with all existing tests. |
| **improve-skill self-eval** | `skills/improve-skill/eval/eval.json` | **NEW (minimal)** | Activation + pre-flight-refusal assertions (decision 4). |

The engine (the `claude` CLI) sits behind `claude_cli.py`; unit tests mock that one wrapper.

---

## 4. The two LLM layers

### 4.1 Eval-runner flow (`run_evals`) — the heart

For `run_evals(skill_name, *, eval_subset_ids=None, timeout_seconds=300, cwd=None) -> EvalResult`:

1. `spec = load_eval_spec(skill_dir)`; apply `filter_tests_by_ids` if a subset was passed (existing helpers).
2. For each `test` in `spec.tests`, in a fresh **sandbox** (§6):
   - `run = claude_cli.run_skill(test.prompt, target=skill_name, eval_runs=N)` → captures `output_text`,
     `activated` (did the target skill fire?), and `usage`.
   - If `test.trigger_test`: one assertion = `activated` is True.
   - For each `binary_assertion[i]`: `judge_assertion(output_text, assertion)` → bool; on False, record
     `make_failing_assertion_id(test.id, i)`.
3. For each `non_trigger` in `spec.non_triggers`: run the prompt, assert the target did **not** activate.
4. `total = compute_total_assertions(spec)`; `passed = count(True)`; `score = passed / total`.
   `total == 0` → `empty_eval_result("...")` (orchestrator treats as `EVAL_UNRUNNABLE`).
5. Return `EvalResult(score, passed, total, failing_assertion_ids, raw_output, usage)`.

**Graceful-degrade (reuse, don't reinvent):** when the `claude` binary or an API credential is **absent**,
`run_evals` raises the **existing** `EvalBackendNotConfiguredError`. The orchestrator already catches it and
exits cleanly as `REQUIRES_CONFIGURED_BACKEND` — so the honest-exit path is *repointed* from "not implemented"
to "backend unavailable", with zero orchestrator change. (Rename considered: `EvalBackendUnavailableError`;
keep the existing name to avoid churn unless the plan finds a clarity win.)

### 4.2 Change-proposer flow (`_default_change_proposer`)

`_default_change_proposer(spec, failing_ids, budget) -> (ProposedChange, ApiUsage, turns)`:

1. Build the load-bearing prompt (per `references/karpathy-loop.md §3` + `references/eval-runner.md`):
   the target skill's current files + *"these binary assertions are failing: `<failing_ids>`. Propose ONE
   change to SKILL.md or references/ that fixes ≥1 without regressing the others. Output JSON
   `{target_file, unified_diff, summary, rationale}`."*
2. `claude --bare --print --output-format json --max-budget-usd <remaining>` with that prompt (via `claude_cli`).
3. Parse the JSON → `ProposedChange`; return it with the run's `ApiUsage` + turn count.
4. **Robustness:** malformed/empty output → typed `ProposerError`. The orchestrator treats `ProposerError`
   as a **skipped iteration** (log + continue, subject to a small consecutive-failure cap), distinct from the
   `NotImplementedError` "give up → `NO_IMPROVEMENT_POSSIBLE`" path. This is a small, tested addition to the
   loop's existing `try/except` around the proposer call.

`apply_proposed_change` (already real — `git apply` on the improve branch) consumes the `unified_diff` unchanged.

---

## 5. Phase-0 spike — gates the build (mirrors C2)

lean-ctx taught us not to assume an external CLI surface. Before building, a spike verifies, against the
**real `claude` binary**:

1. **Headless skill execution:** can we run ONE skill via `claude --print` (non-`--bare`, so skills load)
   on a prompt and capture its text output? Which `--output-format` / flags expose output + `usage`?
2. **Activation detection:** can we tell *which* skill activated (for `trigger_test` / `non_trigger`
   assertions)? If not directly, what is the reliable proxy (e.g., an activation marker in the transcript)?
3. **Side-effect containment:** does a representative skill honor `SF_WIKI_ROOT` / `CLAUDE_PLUGIN_DATA`
   redirection, leaving the real wiki/project byte-identical?
4. **Proposer parse:** does `claude --bare --print --output-format json` reliably return parseable JSON?

Findings recorded in `skills/improve-skill/lib/SPIKE_FINDINGS.md` (next to the code, as C2 did).
**If activation cannot be detected, or side-effects cannot be contained → STOP and return to the maintainer**
(options: defer trigger/non-trigger assertions to a follow-up; or adopt a heavier sandbox such as a tmp git
clone). **Do not silently degrade.**

**Spike target:** 1–2 skills — a low/redirectable-side-effect one for the mechanic (candidate: `recall` or
`code-map`) plus one trigger-heavy skill for activation detection. Final pick made in the spike.

---

## 6. Isolation & safety

- Eval skill-runs execute in a **sandbox**: a tmp working directory plus `SF_WIKI_ROOT` and
  `CLAUDE_PLUGIN_DATA` pointed at throwaway tmp dirs, so any wiki / plugin-data writes land in scratch space.
  Skills are **read** from the real install (the skill files are not mutated during eval).
- The **proposer** runs `--bare` (no skill loading needed — it only emits a diff); its sole effect is the diff,
  applied by the already-tested `apply_proposed_change` on the isolated `improve/<skill>/<ts>` branch.
- Skills whose side-effects are **not** redirectable or are destructive are **excluded from V1 eval targets**
  (spike-informed list). The capability is a bonus, never a hard dependency.

---

## 7. Budget accounting for eval sub-runs

The proposer already threads `ApiUsage` → `advance_budget`. The eval side currently does not (the
`EvalRunner` callable returns only `EvalResult`). Fix: the additive `EvalResult.usage` field (§3) carries the
skill-run + judge token spend; the orchestrator advances the budget from each eval's `usage` so autonomous-mode
cost stays honest (a bike-method concern). The `EvalRunner` *callable signature is unchanged* (usage rides on
the returned `EvalResult`). Build detail for `writing-plans`: the baseline eval currently runs before
`BudgetState` is constructed — either initialize the budget earlier or fold baseline usage in immediately
after; pick the smaller diff.

A Haiku price row must exist in `references/model-pricing.json` for the judge's spend to be costed (add if absent).

---

## 8. Determinism & cost (decision 5, expanded)

- **Judge:** temp 0, one call per assertion → the *scoring layer* is deterministic.
- **Skill-run:** inherently nondeterministic (full generation). V1 default `--eval-runs 1`; `--eval-runs 3`
  opts into majority-binarized scoring for stability (overnight/autonomous use). Documented in SKILL.md.
- **Cost shape:** one eval = (`eval_runs` × skill-runs) + (N judge calls) per test, × tests. Mitigations:
  cheap Haiku judge, `--eval-subset`, the existing budget ceilings, and interactive-default supervision.

---

## 9. Bike-method ADR — new ADR-036

Formalizes "earned autonomy" (the Nate-Herk framing already cited in ADR-031 §3). Records:

- **Principle:** autonomous, self-modifying loops ship with training wheels; autonomy is *earned* through
  evidence (supervised runs), not granted at ship time.
- **Concrete gate:** `/ren:improve-skill` stays **interactive by default**; `--autonomous` keeps requiring the
  existing hard ceilings (`--max-iterations` **and** `--max-budget-usd`, enforced in pre-flight — already built).
  The skill stays **EXPERIMENTAL** (banner reworded: "backend wired; unsupervised autonomy unproven") until the
  maintainer downgrades it after **≥3 logged clean supervised runs** on real skills (logged in `learnings.md`).
- **No new code** enforces the downgrade — it is a documented posture + manual decision. The only code gate is
  the pre-existing autonomous-mode ceiling check. (This is deliberate: a built "trust tracker" is the kind of
  speculative subsystem ADR-031's solo-first pivot removed.)
- **Generalizes** to future self-modifying loops (e.g., C5b's dep-graph-driven re-improvement).
- **Alternatives rejected:** ship-autonomous-now (unproven backend); never-autonomous (defeats the
  overnight-improvement value ADR-012 ships for).
- **Relates-to:** ADR-012, ADR-031, ADR-009 (manual-consolidate posture), ADR-003 (no-daemon).

---

## 10. Two load-bearing invariants

1. **Read-only on the user's real wiki/project during eval** (inherited from C1/C2/ADR-032 in spirit, though
   here the skill *intentionally* writes — into the sandbox). A property-style test asserts the real
   `SF_WIKI_ROOT` tree is **byte-identical** before/after an eval run.
2. **Honest failure over a fake pass.** If the backend can't run (no `claude` / no key) the loop exits cleanly
   via the existing `REQUIRES_CONFIGURED_BACKEND` path — it never fabricates a score. An eval that lies is
   worse than no eval.

---

## 11. ADRs

- **New — ADR-036: Bike-Method / Earned Autonomy** (§9).
- **Amend ADR-012 (Two-Layer Self-Improvement):** the Layer-2 eval backend is now **wired** via the own
  LLM-judge path (path 2), chosen over Skill Creator adoption (path 1); record the EXPERIMENTAL→earned-autonomy
  posture deferring to ADR-036.
- **Update reference `skills/improve-skill/references/eval-runner.md`:** flip "V1 decision: adopt (path 1)" →
  "own LLM-judge (path 2), per C5a (2026-06-18)"; keep the `run_evals` contract section (it already matches).
- **No `schemas.json` change.** No new wiki page-type; `eval.json`'s schema is unchanged. The
  schema-conformance gate is untouched (as in C1/C2).

---

## 12. Scope boundaries

**In scope (this slice):**
- `lib/claude_cli.py` (wrapper) + tests.
- `lib/eval_runner.py` `run_evals()` real body + judge + sandbox + tests (mocked wrapper).
- `lib/__init__.py` `_default_change_proposer()` real body + orchestrator `ProposerError` handling + eval-usage
  budget plumbing + orchestrator tests.
- `lib/types.py` `EvalResult.usage` additive field.
- Minimal `skills/improve-skill/eval/eval.json` (activation + refusal assertions).
- Phase-0 spike + `SPIKE_FINDINGS.md`.
- ADR-036 + ADR-012 amendment + `eval-runner.md` flip.
- `SKILL.md` banner/flags update (`--eval-runs`), `learnings.md`, model-pricing Haiku row.
- Wire-up: README, CHANGELOG, `wiki/index.md`, `wiki/log.md`, roadmap C5 row → **C5a DONE** (C5b noted as remaining).

**Out of scope (deferred, named):**
- **Dependency / reference / call graph** → **C5b**.
- **Auto / git-hook / cadence-driven code-map refresh** → **C5b**.
- **Removing EXPERIMENTAL globally / greenlighting unsupervised autonomous runs** → earned later, per ADR-036.
- **Adopting Skill Creator's `run_eval.py`** → rejected (decision 2).
- **Loop-behavioral self-eval assertions** for improve-skill (recursive) → later.

---

## 13. Testing & eval (mirrors C1/C2)

- **Unit — eval-runner** (wrapper **mocked** via recorded `ClaudeRun` fixtures, as C2 mocked lean-ctx):
  judge TRUE/FALSE paths, trigger + non-trigger scoring, score math, failing-id composition,
  timeout/crash → `score=0.0`, subset → empty result, `usage` aggregation.
- **Unit — proposer** (wrapper mocked): JSON parse success, malformed → `ProposerError`, usage/turns threading.
- **Orchestrator** (extend `test_orchestrator.py`): full loop with a mocked wrapper improving a **fixture
  skill** from `score < 1.0` to `1.0`; eval-usage budget accounting; `ProposerError` skip-iteration; the
  existing exit-reason matrix stays green.
- **Isolation property test:** the real `SF_WIKI_ROOT` tree is byte-identical after an eval run.
- **Live smoke (gated; needs `claude` + API key — not in CI):** `run_evals` on ONE real skill end-to-end —
  the spike's live proof, like C2's. Records real activation + a real score.
- **Canonical fixture conformance:** the new `improve-skill/eval/eval.json` must load cleanly; **add** it to
  the parametrized `CANONICAL_SKILL_DIRS` set used by `test_eval_runner.py` / `test_preflight.py` so it is covered.
- **Full gate:** `( cd <plugin-root> && python3 -m pytest skills/improve-skill/lib/tests/ -q )` +
  `claude plugin validate ./ --strict` + schema CI-parity (unchanged — no `schemas.json` touch).

---

## 14. Risks & open questions

- **Headless skill-activation detection** — the central spike unknown (the lean-ctx-CLI analogue). §5 gates it.
- **Skill-run nondeterminism vs the keep/revert decision** — mitigated by temp-0 judging + `--eval-runs`;
  residual noise is acceptable under supervised V1, flagged for the bike-method downgrade review.
- **Cost** — eval runs spawn real `claude` sub-runs; bounded by Haiku judge + subset + ceilings + interactive default.
- **Destructive/un-redirectable skills** — excluded from V1 eval targets (spike-informed).
- **Credential requirement** — autonomous/eval needs `claude` logged-in or `ANTHROPIC_API_KEY`; absence →
  the clean `REQUIRES_CONFIGURED_BACKEND` exit (graceful, no crash).
- **`--output-format json` availability/shape** — assumed, **spike-verified** (no assumption shipped).

---

## 15. Implementation sequencing hint (for `writing-plans`)

1. **Phase 0 — spike** (gate; may bounce to maintainer). Record `SPIKE_FINDINGS.md`.
2. `lib/claude_cli.py` wrapper + tests (mock subprocess).
3. `EvalResult.usage` additive field (+ keep existing tests green).
4. `lib/eval_runner.py` `run_evals()` real body + judge + sandbox + tests (mocked wrapper).
5. `_default_change_proposer()` real body + orchestrator `ProposerError` handling + eval-usage budget plumbing
   + orchestrator tests.
6. Minimal `improve-skill/eval/eval.json` + conformance test.
7. Isolation property test + live smoke (gated).
8. ADR-036 + ADR-012 amendment + `eval-runner.md` flip + `model-pricing.json` Haiku row.
9. `SKILL.md` banner/flags + `learnings.md` + wire-up (README/CHANGELOG/wiki/roadmap) + full gate.
