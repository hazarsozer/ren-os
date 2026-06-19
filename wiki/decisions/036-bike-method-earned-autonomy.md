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
