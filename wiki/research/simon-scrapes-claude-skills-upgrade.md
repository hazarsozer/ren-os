---
title: Skill Systems — Composing Skills via Orchestrators (Simon Scrapes)
type: research
source: raw/transcripts/simon-scrapes-claude-skills-upgrade
ingested: 2026-05-28
tags: [skills, skill-systems, orchestration, composition, modularity, claude-code]
status: ingested
attribution: Simon Scrapes (YouTube), video "THIS Gives Claude Skills a Massive Upgrade (It's Easy!)"
duration: ~13 min
related: [simon-scrapes-agentic-os, simon-scrapes-self-improving-skills, py-harness-engineering]
note: |
  Despite the video title implying "skill upgrades," the actual content is about skill
  composition into chains (skill systems). The fifth ingested source.
---

# Skill Systems — Composing Skills via Orchestrators (Simon Scrapes)

## TL;DR

Skills should be **modular components**, not isolated endpoints OR megaskills. Real value comes from composing small focused skills into **skill systems** — chains wired together by orchestrator skills that handle ordering, input/output handoff, human-in-the-loop checkpoints, and result display. Anthropic's own guidance calls this **"sequential workflow orchestration"**. This pattern operationalizes PY's harness-research finding that ~90% of compute should flow through delegated child agents.

## The two anti-patterns

### Anti-pattern 1: Skills in isolation

Treat a downloaded skill as a complete process; manually copy outputs from one skill to the next.
- You're still the connector
- No time savings vs. just using ChatGPT
- "You've used Claude Code the same way in which you would actually use ChatGPT"

### Anti-pattern 2: Megaskills

A single 1000-line `skill.md` trying to do everything (research + writing + repurposing + scheduling + posting).
- **Loses modularity** — copywriting logic locked inside, can't reuse for newsletter intros or landing pages
- **Loses maintainability** — updates require hunting through huge file; same logic duplicated across workflows
- **Loses progressive disclosure** — everything loads at once → context bloat → quality drops
- **Surprisingly common in marketplaces** — many published skills are AI-generated and over-fit to "do everything"

> Anthropic's own growth marketing team explicitly broke their ad-copy automations into specialized **sub-agents** (one for headlines, one for descriptions) — *"because in their words, it makes debugging easier and improves output quality when dealing with complex requirements."*

## The right answer: skill systems

> "Skills are effectively components of the skill system. A skill system is a prompt and an instruction set wired around multiple skills."

### Skill = component. Skill system = automation built from them.

The orchestrator skill contains:
- The kickoff prompt
- The instruction set (the "brain" that runs the chain)
- Wiring between component skills

### Five things an orchestrator's instruction set must define

| # | Element | What it answers |
|---|---|---|
| 1 | Skill architecture | Which skills, in what order |
| 2 | Inputs per skill | What each step needs to do its job |
| 3 | Output handoff | How skill N's output becomes skill N+1's input |
| 4 | Human-in-the-loop checkpoints | Where the user steps in to approve/adjust |
| 5 | Visual results display | Markdown link? HTML dashboard? PNGs? — depends on output type |

### Anthropic alignment

Simon explicitly anchors this in Anthropic's own skills guide: **"sequential workflow orchestration"** — explicit step ordering, clear dependencies between steps, validation at each stage.

## Concrete example: 5-clip short-form video skill system

```
Video URL (input)
      │
      ▼
[Orchestrator skill]
      │
      ├─→ Skill 1: Transcript extraction
      │      (word-level timestamped transcript)
      │
      ├─→ Skill 2: Clip selection
      │      (5 candidate clips, each scored across 5 categories)
      │
      ├─→ Skill 3: Reframe / clip extraction
      │      (face detection, 9:16 portrait, face-tracking)
      │
      ├─→ Skill 4: Editing
      │      (pop-out illustrations via Remotion, timed to keywords)
      │
      └─→ Skill 5: Packaging + scheduling
             (thumbnail, title, description, → scheduling tool)
```

Outputs: 5 short-form clips ready for YouTube Shorts / LinkedIn / X — kicked off by a single prompt with a video URL.

### Context management within the chain

> "Each skill in the chain gets exactly what it needs to do its job. Nothing more and nothing less."

Sub-agents spin off at relevant points to keep each skill's context window narrow. This **operationalizes PY's harness-research finding** that ~90% of compute should flow through delegated child agents, not the parent.

## Reusability — the multiplier

Same transcript-extraction skill plugs into multiple skill systems:

```
                  ┌─→ Short-form video system
                  │
Transcript skill ─┼─→ Newsletter creation system
                  │
                  ├─→ Blog post / SEO content system
                  │
                  └─→ ...
```

**Rule of thumb**: 20–30 unique skills can power 10+ skill systems. Any change to the transcript skill propagates automatically to every system using it.

## How this informs the framework

### Curation rule (now sharper)

Each skill we ship must be:
- **Small** (target <200 lines `skill.md`, per progressive disclosure from earlier source)
- **Focused** on one job
- **Reusable** across multiple skill systems
- **Composable** (clean inputs/outputs, no assumed siblings)

This is the curation discipline. It rejects both ECC-style kitchen sinks AND oversized "do-everything" skills.

### Skill system as a first-class concept

Our framework should explicitly support TWO artifact types:
- **Skills** — single-purpose, reusable, well-described
- **Skill systems** — orchestrators that wire skills into end-to-end workflows

Possible directory layout:
```
plugin/
├── skills/                  ← components
│   ├── transcript-extract/
│   ├── clip-select/
│   └── ...
└── skill-systems/           ← orchestrators
    ├── video-to-shorts/
    ├── newsletter-from-video/
    └── ...
```

### Orchestrator schema (adopt from Simon)

Each skill system's orchestrator `skill.md` codifies the five elements (architecture / inputs / handoffs / HITL / visual output). Becomes a frontmatter schema we enforce.

### Sub-agent spawning as a design pattern

Connect to PY's harness finding: design skills to spin sub-agents when they need to do bounded work that shouldn't pollute the parent context. The orchestrator decides when to delegate vs. inline.

### Reinforces the curation thesis

> "There's no point in doing this if you're going to generate rubbish outputs."

The framework's value is in the **quality** of the curated set, not the size. 30 well-designed skills + 10 orchestrators > 200 generic kitchen-sink skills.

## Tensions / open questions

1. **Skill systems vs. agents** — when do you use a skill system vs. a sub-agent? Anthropic's growth team used **sub-agents** for ad copy (not skill systems). What's the decision rule?
2. **HITL vs. autonomy conflict** — the self-improving skills source preaches "never stop, don't ask the human." This source preaches HITL checkpoints in skill systems. When is each appropriate? Likely answer: autonomy for measurable improvement loops; HITL for creative/strategic decisions. But the framework should document this.
3. **Where do skill systems live in the curated set?** Ship a starter set? Provide a template? Stay neutral and let users build them?
4. **Eval.json per skill vs. per skill system** — if a skill system has its own success criteria, does it ship its own `eval.json`? How do we test orchestration vs. individual skill quality?
5. **Cross-skill-system reuse model** — when one team member builds a skill system for their workflow, can another member fork pieces? How do we make orchestrators portable?
6. **Naming convention** — Simon uses "skill systems"; Anthropic uses "sequential workflow orchestration"; sub-agents are something different again. The framework needs precise vocabulary so the friend group doesn't talk past each other.

## Convergence with other sources

| Source | What this source adds |
|---|---|
| Simon Agentic OS | The skill-system pattern was hinted at as pillar #4 ("multi-step workflows on a schedule") — this source unpacks it concretely |
| Simon Self-Improving Skills | Each component skill in a chain gets its own evals.json; orchestrators may need separate test methodology |
| PY Harness Engineering | "90% of compute flows through delegated child agents" — this is the architectural pattern that achieves that |
| Karpathy LLM Wiki | "Modular, composable building blocks" — same thesis applied to documents (wiki pages) vs. skills (code components) |

**Sharpening for our framework**: skills + skill systems become the **unit of curation**, with execution contracts + evals as the **unit of quality assurance**, and orchestration / sub-agent delegation as the **unit of cost control**.

## Quotes worth preserving

> "Skills are modular, composable building blocks."

> "It makes debugging easier and improves output quality when dealing with complex requirements." — Anthropic's growth team, on why they used sub-agents not megaskills

> "Each skill in the chain gets exactly what it needs to do its job. Nothing more and nothing less."

> "Build them small, build them really focused, build them around real workflows. Design every single skill for reuse from day one."

> "There's no point in doing this if you're going to generate rubbish outputs."

## External references mentioned

- **Cory Haynes' marketing skill pack** — example of downloadable skills (cited as case)
- **Anthropic's skills guide** — "sequential workflow orchestration" terminology
- **Anthropic growth marketing team's ad copy automations** — sub-agent decomposition example
- **Open Claw, Hermes** — other LLM tools that execute multi-step workflows
- **Remotion** — used by Enrique's video skill system for programmatic illustration generation
- **zioo.com** — scheduling tool used in the example skill system
- **Enrique** — community member who built v1 of the video-to-shorts system

## Reference

- Raw source: `raw/transcripts/simon-scrapes-claude-skills-upgrade`
- Captured: 2026-05-28 from transcript dump by user
- Attribution: Simon Scrapes, YouTube video "THIS Gives Claude Skills a Massive Upgrade (It's Easy!)"
- Transcript length: ~18KB, video duration ~13 minutes
