---
title: "The Karpathy auto-research loop — operational prose"
type: skill-reference
parent_skill: sf-improve-skill
version: 0.1.0
date: 2026-05-28
---

# The Karpathy loop, in prose

Andrej Karpathy's "auto-research" pattern, distilled in `wiki/research/llm-wiki-pattern.md` and reapplied in Simon Scrapes' self-improving-skills research, is this:

> Read code → make a change → run a test → keep if better, revert if worse → loop.

It is intentionally simple. The simplicity is the strength: fewer moving parts = fewer failure modes; the discipline lives in the loop body, not in elaborate state machines.

This skill applies the loop to **a skill's body** — `SKILL.md` instructions + `references/` content. Layer 1 (the `description` field) is Skill Creator's territory (per ADR-012). This skill does not touch the description.

## The five disciplines

### 1. **One change per iteration**

The LLM proposes the **single highest-leverage change** based on the current failing assertions. Not a refactor. Not a "while we're here" cluster. ONE change.

Why: keep-or-revert is meaningless if you bundle multiple changes — you can't isolate which one caused the score shift. Discipline-narrowing per PY's empirical findings (`wiki/research/py-harness-engineering.md`): the only consistently-helpful module in NLH ablation was the narrow self-evolution loop. We honor that.

Concrete shape of "one change":
- ✅ "Add a sentence to SKILL.md §3 clarifying when the skill should refuse"
- ✅ "Move the example from references/usage.md to SKILL.md inline"
- ✅ "Replace 'maybe' with 'always' in the When-to-use section"
- ❌ "Refactor the entire SKILL.md to a new structure"
- ❌ "Update SKILL.md and add three new reference files"

The inner sub-run prompt explicitly forbids multi-change proposals.

### 2. **Binary assertion only**

Per ADR-011, `eval/eval.json` contains binary assertions: each test either passes or fails. The "score" is the pass rate (passed / total).

Why: subjective qualifiers ("the SKILL.md is well-written") don't compose. You can't compare run N vs run N+1 reliably. Binary is the only reproducible primitive. Karpathy's loop depends on a clean keep-or-revert signal.

Skill Creator's qualitative dashboard exists for subjective evaluation. That's a different tool for a different purpose.

### 3. **Git as memory**

Every iteration is one commit. Revert is `git reset --hard HEAD~1`. The branch (`improve/<skill>/<timestamp>`) is the durable artifact of the run.

Why: we don't need a fancy state machine. Git already has atomic apply (`git apply`), atomic revert (`git reset`), and inspectable history (`git log`). The loop's state IS the git state. Crash recovery: re-read from `git log`. Inspection: same.

Implication: never `git push` from the loop. The branch is local-only until the user decides to share it.

### 4. **Autonomous mode never asks the human**

Per Simon Scrapes' "never stop, don't ask" prompt pattern: if the user invoked `--autonomous`, the loop runs to a hard stopping criterion (max-iterations / budget / shadow-turns / all-pass) WITHOUT pausing for confirmation.

Why: overnight runs need to be unattended. Mid-run human-in-the-loop defeats the purpose. The safety bounds are the substitute for human supervision — that's why the pre-flight check requires them.

The interactive mode (the default) does ask per change. Use autonomous deliberately.

### 5. **The score must monotonically improve (or stay flat)**

If a change DROPS the score → REVERT IMMEDIATELY. No "maybe it'll recover next iteration" speculation. Git reset, log it, move on.

If a change keeps the score FLAT → KEEP (some changes don't move the needle individually but enable later changes). Log it as "neutral."

If a change IMPROVES the score → KEEP, update baseline, continue.

This is the "auto-research" part: each iteration is a tiny experiment with a clear outcome. Over many iterations, the score either reaches 1.0 (all assertions pass; success) or the loop runs out of budget (partial improvement; branch kept).

## What this skill is NOT

- **It is NOT a refactor tool.** It improves quality against existing assertions. If you want to restructure the skill, do that manually before invoking the loop.
- **It is NOT a magic skill-creator.** It needs an existing SKILL.md + an existing eval.json. Bootstrap with Skill Creator first.
- **It is NOT a description optimizer.** That's Layer 1 (Skill Creator). This is Layer 2 (body quality).
- **It is NOT a continuous-improvement daemon.** It runs when the friend invokes it. Per ADR-009 + the framework's no-daemons principle, no background process.

## Operating example (interactive mode)

```
$ /ren:improve-skill sf-bootstrap-project

Pre-flight:
  ✓ Skill found at skills/sf-bootstrap-project/SKILL.md
  ✓ eval/eval.json parses; 4 test_cases, 17 assertions
  ✓ Working tree clean
  ✓ Mode: interactive (default; autonomous flags not required)
  ✓ CC version: 2.1.154

Creating branch: improve/sf-bootstrap-project/2026-05-28-203012

Baseline eval: 14/17 assertions pass (82.4%)
Failing: bootstrap-creates-empty-context-md, bootstrap-refuses-on-existing-dir, bootstrap-log-init-entry-format

Iter 1:
  Proposed change: SKILL.md §"What this skill does NOT do" — add explicit refuse-on-existing-dir clause
  Diff: [shown to user]
  Approve? [y/n/e[dit]/a[ll-yes]/q[uit]]: y
  Applied + committed.
  Eval: 15/17 pass (88.2%). IMPROVED.

Iter 2:
  Proposed change: references/taxonomy-templates.md — fix CONTEXT.md template to default to "Just bootstrapped; first session pending"
  Diff: [shown to user]
  Approve? [y/n/e/a/q]: y
  Applied + committed.
  Eval: 16/17 pass (94.1%). IMPROVED.

Iter 3:
  Proposed change: SKILL.md "log.md init entry" — clarify exact format including timezone
  Diff: [shown to user]
  Approve? [y/n/e/a/q]: y
  Applied + committed.
  Eval: 17/17 pass (100%). SUCCESS.

All assertions pass. Squash-merging to main (use --keep-branch to override).
  improve/sf-bootstrap-project/2026-05-28-203012 → main
  Commit: improve(sf-bootstrap-project): 3 iterations; 82.4% → 100%

Done. 3 iterations, 0 reverts, $0.42 of API spend, 4m12s wall clock.
```

## Operating example (autonomous overnight)

```
$ /ren:improve-skill sf-wrap --autonomous --max-iterations 15 --max-budget-usd 8.00

Pre-flight:
  ✓ Skill found
  ✓ eval/eval.json parses; 5 test_cases, 23 assertions
  ✓ Working tree clean
  ✓ Mode: autonomous (--max-iterations 15 --max-budget-usd 8.00 set; pre-flight passes)
  ✓ CC version: 2.1.154

Creating branch: improve/sf-wrap/2026-05-28-220000
Baseline: 17/23 (73.9%)

[runs overnight, ~12 iterations, 2 reverts, $5.30 spend]
[no human input — pure autonomous]

Morning summary:
  Iterations: 12 (max 15)
  Reverts: 2
  Final score: 22/23 (95.7%)
  Branch kept at improve/sf-wrap/2026-05-28-220000 (not auto-squashed; not all assertions pass)
  Spend: $5.30 / $8.00
  
Next step: review the branch with `git log improve/sf-wrap/2026-05-28-220000`,
then `git switch main && git merge --squash improve/sf-wrap/...` if you like the result.
```

## References

- `wiki/research/llm-wiki-pattern.md` — Karpathy's original auto-research description
- `wiki/research/simon-scrapes-self-improving-skills.md` — the two-layer adaptation for Claude Code
- `wiki/research/py-harness-engineering.md` — empirical evidence that narrow self-evolution loops are the consistently-helpful module
- ADR-011 (Skill Schema) — eval.json shape
- ADR-012 (Two-Layer Self-Improvement) — the design decision
- `references/git-mechanics.md` — branch / commit / revert details
- `references/budget-tracking.md` — shadow-budget math
