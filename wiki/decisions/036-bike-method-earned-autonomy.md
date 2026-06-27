---
title: "ADR-036: Bike-Method / Earned Autonomy for Self-Modifying Loops"
status: accepted
date: 2026-06-18
sunset-review: 2027-06-18
references-pages: [nate-herk-ai-os, nate-herk-skills-self-improvement, py-harness-engineering]
affects-components: [improve-skill, eval-runner, skill-schema]
relates-to: [012-two-layer-self-improvement, 031-solo-first-pivot, 009-consolidate-via-wrap, 003-no-daemon-rule]
---

# ADR-036: Bike-Method / Earned Autonomy for Self-Modifying Loops

> C5a roadmap slice — formalizes "earned autonomy" (the Nate-Herk framing already cited in
> ADR-031 §3) for self-modifying loops. Primary source: `docs/superpowers/specs/2026-06-18-c5a-self-improvement-loop-design.md` §9.
> Amends the autonomy posture implicit in ADR-012.

## Context

With C5a, the Layer-2 eval backend is now wired: `run_evals()` can actually run a skill against its
`eval.json`, score its binary assertions via an LLM-judge, and return a real pass rate. The
Karpathy loop orchestrator can now genuinely iterate — propose a change, re-score, keep or revert.

This is a capability milestone. **But capability is not a grant of autonomy.** The backend being
wired is what makes self-modifying autonomous runs possible; it is also what makes the autonomy
posture a load-bearing decision rather than a deferred one.

Two risks converge at this milestone:

1. **Unproven backend in production.** The eval loop has been unit-tested against mocked fixtures
   but has not yet accumulated real supervised runs on real skills. The judge's cost profile, failure
   modes under real prompts, and revert correctness have not been observed end-to-end. Shipping
   autonomous mode as the default grants unsupervised write access to skills before those properties
   are known.

2. **Solo-first constraint (ADR-031).** Building a trust-tracking subsystem — code that measures
   supervised run outcomes and automatically promotes the skill from EXPERIMENTAL — is speculative
   infrastructure. ADR-031's solo-first pivot explicitly removed this kind of subsystem. The
   autonomy gate must be enforceable without new speculative code.

The Nate-Herk framing from ADR-031 §3 names the right posture: **bike-method**. A learner rides a
bike with training wheels until they've demonstrated they can balance without them. The evidence
requirement is explicit; the downgrade to no-training-wheels is earned, not automatic.

## Decision

### 1. Interactive default

`/ren:improve-skill` stays **interactive by default.** The user sees each proposed change and
approves before it is applied and committed. This is the behavior that has always been documented;
this ADR makes it explicit governance rather than an implementation default.

### 2. `--autonomous` keeps both hard ceilings

Autonomous mode (`--autonomous`) is available but requires **both**:

- `--max-iterations N` (our framework cap; enforced in the pre-flight ceiling check already built)
- `--max-budget-usd X` (Claude Code native; enforced via the `--max-budget-usd` flag on inner
  sub-runs)

The pre-flight check rejects any `--autonomous` invocation that omits either ceiling. This is the
**only code gate** the bike-method posture requires — it already exists. No new trust-tracking code
is built or planned.

### 3. EXPERIMENTAL banner until ≥3 clean supervised runs

The skill stays marked **EXPERIMENTAL** with the banner:

```
# ⚠ EXPERIMENTAL — backend wired; unsupervised autonomy unproven
```

The banner is downgraded (to a stable marker or removed entirely) by the maintainer **manually**,
after:

- At least **3 logged clean supervised runs** on real skills
- Each run recorded in `skills/improve-skill/references/learnings.md` with: skill name, iteration
  count, final score, whether any reverts occurred, approximate cost

The downgrade is a documented posture + manual decision. **No code enforces the downgrade
threshold.** A built "trust tracker" is the kind of speculative subsystem ADR-031's solo-first
pivot removed; we don't rebuild it here.

### 4. Generalizes to future self-modifying loops

This ADR is intentionally phrased to cover future loops beyond `/ren:improve-skill`. Any
self-modifying loop (e.g., a hypothetical C5b dep-graph-driven re-improvement) ships with the same
training-wheels posture: interactive default, hard ceilings required for autonomous mode,
EXPERIMENTAL until ≥3 logged clean supervised runs. The maintainer explicitly opts each loop out
of EXPERIMENTAL; no loop escapes it automatically.

### 5. No new code

The concrete implementation of this ADR is:

1. The pre-existing pre-flight ceiling check in `skills/improve-skill/lib/__init__.py` — already
   enforces `--max-iterations` + `--max-budget-usd` for `--autonomous`.
2. A manual log entry process in `learnings.md` for supervised run records.
3. This ADR document (governance record).

Nothing else is built. The bike-method is a posture, not a subsystem.

## Consequences

**Easier:**

- **Safe first production runs.** Interactive default means the maintainer sees every change before
  it applies. Any judge misbehavior, unexpected cost spike, or revert failure surfaces immediately
  rather than silently at the end of an overnight run.
- **Evidence accumulates naturally.** Supervised runs log to `learnings.md` as they happen. The
  downgrade decision has real data behind it when it comes.
- **No speculative code debt.** A trust tracker that auto-promotes would need its own tests,
  maintenance, and edge-case handling. Not building it keeps the codebase smaller and the
  solo-first discipline intact.
- **Future loops get the pattern for free.** ADR-036 is a template: any self-modifying loop that
  ships after this one knows exactly what training-wheels posture looks like.

**Harder:**

- **Friction for power users.** A developer who trusts the backend and wants overnight runs must
  live with the EXPERIMENTAL banner until ≥3 supervised runs accumulate. The evidence requirement
  cannot be bypassed by willpower.
- **Manual downgrade process.** The maintainer must remember to check `learnings.md`, review the
  evidence, and remove the EXPERIMENTAL marker. There is no automated reminder. Mitigated by the
  sunset-review date on this ADR.

## Alternatives rejected

### A) Ship autonomous mode as default (ship-autonomous-now)

**Shape:** Remove the interactive default. Any invocation of `/ren:improve-skill` with
`--autonomous` + ceilings runs without approval gates.

**Why rejected:** The backend has not yet run end-to-end on real skills under real conditions. The
judge's cost profile ($0.36/call observed in the Phase-0 spike for non-bare Opus calls) means
runaway costs are real, not theoretical. An overnight run without prior supervised evidence is
unjustified trust in an unproven system. The spike findings make this concrete: cost is the gate.

### B) Never-autonomous (permanently interactive)

**Shape:** Remove `--autonomous` entirely. Every improvement loop requires human approval per
change, always.

**Why rejected:** The overnight autonomous improvement value is the core promise ADR-012 ships for
("Friends can improve skills overnight"). Removing it permanently defeats that. The goal is
*earned* autonomy, not *no* autonomy. Once ≥3 supervised runs demonstrate stable behavior, the
training wheels come off.

### C) Automated trust tracking (build a trust-tracker subsystem)

**Shape:** Code that counts supervised runs, checks the log, and auto-promotes the skill from
EXPERIMENTAL once the threshold is met.

**Why rejected:** Speculative infrastructure per ADR-031's solo-first pivot. A trust tracker needs
its own tests, its own state management, and its own failure modes. The downgrade criterion (≥3
clean runs) is simple enough for a human to verify by reading `learnings.md`. Building code to do
this is premature optimization on an already-over-engineered path.

## References

- `docs/superpowers/specs/2026-06-18-c5a-self-improvement-loop-design.md` §9 — design spec (bike-method ADR, scope, locked decisions)
- `skills/improve-skill/lib/SPIKE_FINDINGS.md` — Phase-0 spike findings: cost profile, auth, non-bare requirement
- `wiki/research/nate-herk-ai-os.md` — Nate-Herk's AI-OS framing; earned-autonomy posture origin
- `wiki/research/nate-herk-skills-self-improvement.md` — Karpathy loop + bike-method pattern
- `wiki/research/py-harness-engineering.md` — empirical evidence; self-evolution module; cost discipline
- ADR-012 (Two-Layer Self-Improvement) — the loop this ADR governs; see 2026-06-18 amendment
- ADR-031 (Solo-First Pivot) — solo-first constraint; speculative subsystem removal; earned-autonomy framing §3
- ADR-009 (Consolidate via Wrap) — manual-consolidate posture this ADR echoes for improvement loops
- ADR-003 (No-Daemon Rule) — no background autonomous processes; improvement loops are explicit, bounded, and user-initiated

---

## Amendment — 2026-06-27: eval-readiness advisory + reference exemplar (A3+A4)

Two additive, opt-in extensions to the loop from the parked video-ingest menu (`docs/superpowers/specs/2026-06-21-video-ingest-improvements.md`). Both leave the **default** scoring path byte-for-byte unchanged — the eval engine is the framework's most delicate subsystem, so nothing in the existing judge/score behavior moves unless explicitly opted in.

- **A3 — eval-readiness advisory (`preflight.eval_readiness_notes`, gate 7).** Surfaced before a budget-spending run: a mechanical thin-signal warning (too few binary assertions to discriminate) + the six Karpathy "Auto Research" preconditions (objective metric, fast feedback, write access, high-volume signal, cheap-to-fail, consistent measuring stick). **Advisory, never blocks** — five of the six preconditions are qualitative and cannot be honestly auto-detected, so a hard gate would be either dishonest or wrong. It informs; the author decides.
- **A4 — reference exemplar (`--reference PATH` → `ImproveSkillArgs.reference`).** `eval_runner.load_reference_exemplar` (bounded 4 KB, graceful on missing/non-UTF-8) threads a "what good looks like" artifact into the judge prompt via a `reference_text` parameter (default `None` → unchanged prompt) through `_judge_prompt` → `judge_assertion` → `run_evals`. Opt-in only; when set it grounds every assertion judgment for that run (intent: better-calibrated TRUE/FALSE, not a scoring shortcut).

**Deliberately deferred (still parked):** A1+A2 (tamper-proof locked scorer + cross-model critic) — the anti-Goodhart pair — change the *judge trust model* and deserve their own deliberate slice → **built in the 2026-06-27 second amendment below.** B1 (experiment-log page-type) batches with C3's page-type decisions (ADR-027).

---

## Amendment — 2026-06-27: locked scorer + cross-model critic (A1+A2)

The anti-Goodhart pair from the same parked menu, built as one slice (`feat/eval-trust-a1a2`; design spec `docs/superpowers/specs/2026-06-27-eval-trust-a1a2-design.md`). This amendment **changes the judge trust model** — the property the first amendment explicitly left for "its own deliberate slice." Before: the loop could silently game itself (apply an `eval/` diff → fake score gain) and a "success" rested on one model. After: the rubric is immutable from the loop's perspective, and an auto-shipped success can carry an independent cross-vendor confirmation. Both keep the **default** scoring path byte-for-byte unchanged.

- **A1 — locked scorer (edit-lock), a first-class invariant.** The improver may modify a skill's *asset* (`SKILL.md`, `references/`) but **never** its *scorer* (`eval/`), and never a path outside the skill directory. Enforced mechanically at the single choke point `apply_proposed_change` via `scorer_lock.diff_targets_locked_path` (parses the diff headers + the declared `target_file`), raising `ScorerTamperError` **before** any `git apply`. The orchestrator treats a rejection like a `ProposerError` — skip the iteration, count toward the 3-consecutive cap — so a proposer that keeps clawing at `eval/` exits cleanly. **Always-on** (no opt-out; nobody should be able to let the improver edit its own rubric), but behavior-preserving: no legitimate run targets `eval/`. Decision: edit-lock only, *not* read-isolation — assertions ARE the spec here (no held-out set to overfit), so a proposer sandbox is cost without much gain.
- **A2 — cross-model critic, a final-gate trust check (`--critic-model`, opt-in).** After a run reaches `ALL_ASSERTIONS_PASS`, and only then, a *different* model independently re-scores the skill **once** (`eval_runs=1`) before squash-merge. `select_judge` routes `codex`/`gpt*`/`o1*`/`o3*`/`o4*` to the `codex` CLI (cross-vendor — genuine OpenAI-vs-Anthropic diversity) and everything else to `claude --model`. Agreement contract: critic agrees → squash-merge (`confirmed`); critic disputes → **do not auto-merge**, keep the branch for human review (`critic-flagged`), never destroy work; critic backend absent → ship WITHOUT confirmation (explicit notice, never a silent pass). The judge model/runner are threaded separately from the skill runner (`judge_model`/`judge_runner` on `judge_assertion`/`run_evals`), so the skill under test still runs under `claude` — only the JUDGE switches. Default `critic_model=None` → today's single-Haiku path unchanged.
- **Relationship to §3 (EXPERIMENTAL banner).** These *strengthen* the evidence a supervised run produces (a tamper-proof score + an optional cross-model agreement) but do **not** change the downgrade rule — banner removal stays a manual maintainer decision after ≥3 clean runs. No trust-tracker code (ADR-031 solo-first still holds).
- **Documented gap (not solved here).** Codex does not surface Anthropic-shaped token usage, so a codex critic pass contributes `ApiUsage(0,0)` and is not budget-tracked. Acceptable: the critic is a single bounded final pass, not an in-loop cost. Gemini is excluded (maintainer: the Gemini CLI pattern is no longer supported).

**Still parked:** B1 (experiment-log page-type) — batches with C3's page-type decisions (ADR-027). C1 (path-guard) — optional hook-infra, only if the guardrail UX is wanted.
