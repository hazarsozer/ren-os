---
title: Self-Improving Skills via Karpathy's Auto-Research Loop (Simon Scrapes)
type: research
source: raw/transcripts/simon-scrapes-self-improving-skills
ingested: 2026-05-28
tags: [self-improvement, skills, evals, binary-assertions, karpathy, claude-code, automation]
status: ingested
attribution: Simon Scrapes (YouTube), video "Build Self-Improving Claude Code Skills. The Results Are Crazy."
duration: ~11 min
related: [simon-scrapes-agentic-os, py-harness-engineering, llm-wiki-pattern]
---

# Self-Improving Skills via Karpathy's Auto-Research Loop (Simon Scrapes)

## TL;DR

Practical implementation of Karpathy's "auto-research" pattern applied to Claude Code skills. Two layers: (1) Anthropic's skill creator already self-improves the YAML description for activation reliability; (2) we add a Karpathy-style loop on top to self-improve the skill body's outputs using **binary assertions** as the scoring primitive. Loop runs overnight, autonomous, never stops asking permission, only commits if test scores improved. **This is the concrete implementation of the self-evolution pattern PY's harness research identified as the only consistently-helpful ablation module.**

## Karpathy's "auto-research" core (the primitive)

Three files:
1. **`program.md`** — instructions for the agent (what to test, how)
2. **A data file** — recording results across iterations
3. **A training script** — the thing the agent edits

Core loop, ~10 lines of instructions:
- Tune the script with an experimental change (i.e. hack the code)
- Run the experiment
- Read the result metric
- If improved → advance the branch, `git commit`
- If worse → `git reset` and try something else
- **Never stop. Don't ask the human. Loop until manually interrupted.**

Quoting the prompt's most useful line:
> "Once the experiment loop has begun, do not pause to ask the human if you should continue. The human might be asleep or gone from the computer and expects you to continue working indefinitely until you are manually stopped."

## Applied to Claude Code skills — two layers

### Layer 1: Skill description improvement (activation)

**What it solves**: Claude reads each skill's YAML description to decide relevance. Community testing found activation rates as low as **20%** with vague descriptions. If the skill doesn't trigger, the rest doesn't matter.

**How it works**: Anthropic's built-in skill creator skill already includes this loop:
- Give it test queries — some should trigger the skill, some shouldn't
- It runs each multiple times
- Checks trigger accuracy
- Proposes a better description
- Retests

**Where it lives**: `improve_description.py` + a `run_loop` orchestrator inside Anthropic's skill creator.

**Implication for us**: don't reinvent. The skill creator skill goes in our curated set.

### Layer 2: Skill output improvement (quality)

**What it solves**: even when a skill triggers, its outputs may not consistently meet the skill's stated goals. Simon's example: a marketing copywriting skill, version 5, still scoring 23/24 on a fresh eval — one assertion failing because a rule was in `tone-of-voice.md` but not in `skill.md` (contrasting context).

**How it works** — Karpathy's loop with a different metric:

| Karpathy original | Our skill version |
|---|---|
| Read `train.py` | Read `skill.md` |
| Change a value | Change a skill instruction |
| Run test | Run prompt + assertions |
| Check metric (`val_bpb`) | Check pass rate |
| Keep or revert | Keep or revert |

## Binary assertions — the critical design primitive

> "The word binary is everything here, and this is where most people are getting it wrong."

| Good (binary) | Bad (subjective) |
|---|---|
| Does NOT contain em-dashes | Has a compelling subject line |
| Under 300 words | Reads well |
| Final line is a question | Sounds on-brand |
| First line is standalone (not part of a paragraph) | Persuasive enough |
| Contains at least one specific number or statistic | Engaging tone |

**Rule**: assertions must be true/false, not opinion-based. Two reviewers should always agree.

The loop can only optimize what it can measure unambiguously. Subjective qualities still need human judgment (Layer 1's qualitative dashboard handles this separately).

## The eval folder convention

Each skill ships an eval folder:

```
skills/
└── marketing-copywriting/
    ├── skill.md
    ├── references/
    │   ├── tone-of-voice.md
    │   ├── persuasion-toolkit.md
    │   └── examples.md
    └── eval/
        └── eval.json
```

`eval.json` shape (paraphrased from transcript):

```json
{
  "tests": [
    {
      "prompt": "Write a LinkedIn post about why simple automations beat complex ones",
      "expected": "A LinkedIn post following brand structure rules",
      "assertions": [
        "First line appears as standalone sentence, not part of a paragraph",
        "Contains at least one specific number or statistic",
        "Final line is NOT a question",
        "Total word count is under 300",
        "..."
      ]
    }
  ]
}
```

5 tests × 5 assertions each → 25 binary checks per evaluation run.

**Practical tip**: don't write `eval.json` manually. Ask Claude Code to generate it from `skill.md` (assertions derived from the skill's stated rules).

## The orchestrating prompt

Simon's actual prompt to start the loop (paraphrased):

> Use the skill creator skill. Run a self-improvement loop on my copywriting skill. Point to the evals file. Detect pass/fail per assertion. If any assertion fails, make ONE change to `skill.md`. Re-run tests, recalculate score. If improved → `git commit`. If worse → `git reset` and try a different change. Don't ask for permissions. Keep looping until I interrupt you or you hit a perfect score.

Notable: "make ONE change per iteration" — narrow attempt loop, matches PY's harness-engineering finding that self-evolution works best when it stays narrow.

## What the binary loop CANNOT handle

Acknowledged limitations:
- Tone of voice
- Creative quality
- Whether the skill is using its reference files properly (vs. just passing surface assertions)

These still require human judgment, but Anthropic's skill creator provides a qualitative dashboard for AB-testing reference files and reviewing outputs side-by-side.

## How this informs the framework

### Now actionable, was abstract before

We had three converging signals for self-improvement (Simon's earlier `learnings.md`, PY's harness research showing self-evolution is the only helpful module, Karpathy as the inventor of the auto-research primitive). This source gives us **the concrete implementation pattern**.

### Directly adopt
- **Two-layer self-improvement architecture** (description for activation + body for output)
- **Binary assertion methodology** — assertions must be unambiguous true/false
- **`eval/eval.json` per skill** — first-class artifact, ships alongside `skill.md`
- **Anthropic's skill creator skill** goes in our curated set (it implements Layer 1 + the dashboard)
- **The "never stop" autonomous prompt pattern** as the default mode for self-improvement runs
- **One change per iteration** — narrow attempt loop, matches PY's discipline-narrowing principle

### Skill schema implications

Every skill in the framework now has a richer structure:
```
skills/<skill-name>/
├── skill.md                   ← instructions, <200 lines (progressive disclosure)
├── references/                ← context files, loaded on demand
└── eval/
    └── eval.json              ← binary assertion tests
```

Optionally a `learnings.md` for the qualitative side (per Simon's earlier source).

This connects to **execution contracts** from PY's transcript — the skill's `eval.json` IS the operational form of its completion conditions.

## Tensions / open questions

1. **Mandate evals or optional?** Should every skill in the curated framework require an `eval.json`? Mandate makes the bar higher (skills are measured); optional makes adoption easier.
2. **Who writes the evals?** Manually authored, generated by Claude from `skill.md`, or hybrid? Simon recommends asking Claude to generate from `skill.md` — but binary-assertion-writing is a discipline; generated ones may need human cleanup.
3. **What runs the loops?** Anthropic's skill creator (Layer 1), but Layer 2 is a custom orchestration — do we provide an `improve-skill` skill that wraps the Karpathy loop, or leave it to the user?
4. **Overnight autonomy — trust boundary.** "Don't ask the human, keep going" is powerful but has implications: git history pollution, runaway costs, modified files the user didn't review. The framework needs guardrails: budget caps, file-allowlist, "stop after N iterations".
5. **Subjective quality still needs humans.** Layer 1 dashboard from Anthropic addresses this — but we should be honest in the framework that quality has a hard limit on automation.
6. **Cross-tool implication**: skills with evals become portable QA artifacts. A skill optimized for our team's stack could be shared with others; its eval gives them confidence it actually works.

## Convergence map

This source closes a loop across all four ingested sources:

| Source | Contribution to self-improvement |
|---|---|
| Karpathy LLM Wiki | The wiki is itself a self-improving artifact (lint pass, contradictions flagged, synthesis updated on each ingest) |
| Karpathy auto-research (cited here) | The primitive: file + metric + loop + revert |
| Simon Scrapes Agentic OS | `learnings.md` per skill — qualitative feedback loop |
| PY Harness Engineering | Empirical: self-evolution is the only consistently-helpful module across ablations |
| Simon Scrapes Self-Improving Skills (this) | **Concrete implementation** of all of the above for Claude Code skills |

**This is now the most strongly-supported design decision in the framework: ship skills with evals, self-improvement loops as first-class capability.**

## Quotes worth preserving

> "Once the experiment loop has begun, do not pause to ask the human if you should continue."

> "The word binary is everything here, and this is where most people are getting it wrong."

> "Get Claude Code to write your assertions once, set up the loop, and you can literally let it run overnight and come back to a skill the next day."

## External references mentioned

- **Karpathy's auto-research pattern** — original framing (`program.md` + data file + training script + ~10-line loop)
- **Anthropic skill creator skill** — built-in skill that includes Layer 1 description improvement loop, eval dashboard, AB-testing for reference files
- **`improve_description.py`** — file inside Anthropic's skill creator that drives Layer 1
- **`run_loop`** — orchestrator combining evaluation + description improvement
- Simon's previous video on the skill creator skill (worth tracking down — likely `simon-scrapes-claude-skills-upgrade` in our transcript set)

## Reference

- Raw source: `raw/transcripts/simon-scrapes-self-improving-skills`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: Simon Scrapes, YouTube video "Build Self-Improving Claude Code Skills. The Results Are Crazy."
- Transcript length: ~15KB, video duration ~11 minutes
