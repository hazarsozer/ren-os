---
title: Skill Creator (Anthropic Official) — Skills Authoring & Evaluation Toolkit
type: research
source_url: https://github.com/anthropics/skills
plugin_page: https://claude.com/plugins/skill-creator
source_fetched: 2026-05-28
license: Apache-2.0
ingested: 2026-05-28
tags: [skills-authoring, evals, official-anthropic, binary-assertions, sub-agents, claude-code, foreground-research]
status: ingested
related: [simon-scrapes-self-improving-skills, superpowers, simon-scrapes-claude-skills-upgrade]
---

# Skill Creator (Anthropic Official)

## TL;DR

The Anthropic-official skill for creating, evaluating, improving, and benchmarking other skills. **Apache-2.0**, 256K+ installs. Four operating modes (Create / Eval / Improve / Benchmark) backed by four sub-agent roles (Executor / Grader / Comparator / Analyzer). The eval mode IS the binary-assertion methodology Simon Scrapes described — Skill Creator was the source of his "Layer 1 description improvement loop." **Adopting this is essentially mandatory** — it's the official skill-authoring tool, free, foundational.

## The four modes

| Mode | What it does |
|---|---|
| **Create** | Guides initial skill concept development and requirements gathering |
| **Eval** | Runs skills against eval prompts (defines scenarios → runs skill → grades binary assertions) |
| **Improve** | Suggests targeted enhancements based on evaluation results |
| **Benchmark** | Measures performance across multiple runs with statistical variance analysis |

Invocation: `/skill-creator` followed by mode selection.

## The four sub-agent roles

- **Executor** — runs the skill against eval prompts
- **Grader** — evaluates outputs against defined assertions
- **Comparator** — compares variations across iterations
- **Analyzer** — produces statistical variance analysis

This is harness-engineering in action: skills evaluating skills via sub-agent delegation. Confirms PY's "90% of compute through delegated agents."

## How the description optimizer works (Simon's Layer 1)

Implementation files: `scripts/run_loop.py`, `scripts/improve_description.py`, `scripts/run_eval.py`

The loop:
1. Split eval set: **60% train / 40% held-out test**
2. Evaluate the current YAML description by running each query **3 times** to get a reliable trigger rate
3. Call Claude to propose improvements based on what failed
4. Re-evaluate each new description on BOTH train and test sets
5. Iterate up to **5 times**

This is the "Layer 1 description improvement" Simon Scrapes described in his self-improving-skills source. Skill Creator was where the pattern came from; Simon extended it with "Layer 2 output improvement" via Karpathy's auto-research loop.

## Install path

```
/plugin marketplace add anthropics/skills
/plugin install skill-creator@anthropic-agent-skills
```

(Plus optionally `document-skills`, `example-skills`, and other Anthropic-shipped collections from the same marketplace.)

## License

**Apache-2.0** for the skill-creator skill and most skills in the repo.

**Exception**: Document skills (docx, pdf, pptx, xlsx) are *source-available, not open-source*. If we adopt those, we need to note the license distinction.

## Important caveat: ANTHROPIC_API_KEY requirement

The description optimization loop **requires `ANTHROPIC_API_KEY`** (per [Issue #532](https://github.com/anthropics/skills/issues/532)). This means:
- Users on Claude subscriptions (Pro/Max) need to ALSO have an API key
- Enterprise/SSO-only users currently can't run the description optimizer
- For our friend group (each member has their own subscription + can get API keys), this is solvable but worth flagging in onboarding

## Disclaimer in the repo

> "These skills are provided for demonstration and educational purposes only. While some of these capabilities may be available in Claude, the implementations and behaviors you receive from Claude may differ from what is shown in these skills."

Anthropic positions these as reference implementations, not turnkey production tools. Implication: we should expect to adapt them for our specific needs.

## How this informs the framework

### Adoption confirmed — it's the foundation

Skill Creator is essentially mandatory for any framework that ships custom skills. It's:
- The official authoring tool
- Free and Apache-2.0 licensed
- The implementation of the binary-assertion methodology Simon and the framework rely on
- Already used by 256K+ developers

### Two-layer self-improvement architecture finalized

Combining sources:

| Layer | What it does | Implementation |
|---|---|---|
| **L1: Description** | Optimizes YAML description for skill activation reliability | Skill Creator's eval/improve modes (60/40 split, 3 runs per query, 5 iterations) |
| **L2: Body** | Optimizes skill.md instructions for output quality | Karpathy auto-research loop with binary assertions (per Simon Scrapes) — we build this on top |

Both layers are now mapped to concrete implementations. The framework ships:
- Recommend Skill Creator (does L1 out of the box)
- Provide our own L2 implementation (the auto-research loop pattern)

### The eval.json schema is partly defined by Skill Creator

Skill Creator's `scripts/run_eval.py` consumes a structured eval format. Our framework's prescribed `eval.json` schema (from Simon Scrapes synthesis) should be **compatible with Skill Creator's format** so skills can be evaluated by the official tool without reformatting.

Action item: review the eval.json format Skill Creator expects when we write the design doc, align our schema.

### The four-agent eval architecture matches our patterns

Executor + Grader + Comparator + Analyzer is exactly the "spawn, restrict, collect outputs" pattern from Prompt Engineering's harness source. Validates the architecture across yet another implementation.

## Tensions / open questions

1. **ANTHROPIC_API_KEY requirement** — manageable for our friend group but worth flagging in onboarding. May change in future; track.
2. **eval.json schema compatibility** — verify our framework's prescribed format matches what Skill Creator's `run_eval.py` expects.
3. **Document skills licensing** — if any of the document skills (docx, pdf, pptx, xlsx) become useful for friend-group projects, the "source-available, not open-source" license matters. Note in stack LICENSES.md.
4. **Per-skill train/test split** — 60/40 is Skill Creator's default. Is that the right default for our team-specific skills? Probably yes for v1.
5. **5-iteration cap on description optimization** — is that enough for our team-specific skills? May need tuning.

## Connections to prior research

| Prior source | Connection |
|---|---|
| Simon Scrapes Self-Improving Skills | Skill Creator IS the Layer 1 description optimizer Simon described. He extended it with Layer 2. |
| Simon Scrapes Skill Systems | Skill Creator + skill systems = same skills factory + composition pattern |
| Nate Herk Best 6 Skills | Confirmed as #1 in his list — "the skill that builds every other skill" |
| Superpowers | Both are skill-based frameworks; Skill Creator is the meta-skill for authoring Superpowers-style skills |
| PY Harness Engineering | The 4-agent eval architecture is harness-engineering applied to skill QA |

## Followups

- Verify eval.json schema compatibility for our prescribed format
- Look at example skills in `anthropics/skills` repo for reference implementations to base our team-specific skills on (e.g., `example-skills`)
- Track Anthropic-API-key issue (#532) for resolution

## Reference

- Repo: https://github.com/anthropics/skills
- Plugin page: https://claude.com/plugins/skill-creator
- Direct SKILL.md: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
- OpenCode port (informative): https://github.com/antongulin/opencode-skill-creator
- License: Apache-2.0 (most skills), source-available (document skills)
- 256K+ installs (as of fetch)
- Fetched: 2026-05-28
