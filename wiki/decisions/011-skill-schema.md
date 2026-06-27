---
title: "ADR-011: Skill Schema — Frontmatter + References + Execution Contracts + Evals"
status: accepted
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: [simon-scrapes-self-improving-skills, simon-scrapes-claude-skills-upgrade, py-harness-engineering, skill-creator, superpowers]
affects-components: [skills, eval, install, authoring]
relates-to: [006-curated-stack, 012-self-improvement, 014-project-sub-wiki-taxonomy]
---

# ADR-011: Skill Schema — Frontmatter + References + Execution Contracts + Evals

## Context

ADR-006 adopted Superpowers + Skill Creator as the skill-authoring and methodology foundation. The research surfaced three concrete patterns that together define the **shape every framework-shipped skill should take**:

1. **Anthropic's Skill Creator format** (Apache-2.0): SKILL.md + YAML frontmatter with `name` + `description` + supporting files. This is the baseline format Claude Code expects.

2. **Tsinghua's NLH execution contracts** (per PY's harness-engineering research): bounded agent calls with five elements — required outputs, budgets, permissions, completion conditions, output paths. Think function signatures for agents.

3. **Simon Scrapes' two-layer self-improvement** (auto-research applied to skills, per Karpathy): `eval/eval.json` with binary assertions backing the description optimization + body iteration loops.

Plus the principles from prior research:
- **Progressive disclosure** (Simon's Agentic OS): name + description always loaded, SKILL.md loaded when matched, references loaded on demand. Target <200 lines SKILL.md.
- **Small + focused + reusable + composable** (Simon's Skill Systems): each skill is one job; orchestrators compose them.
- **Modular references** (Simon): `references/` subdirectory for context loaded by the skill itself when needed.

These need to combine into a single coherent schema that:
- Stays compatible with Anthropic's skill-creator tooling (so we don't lose Layer 1 description optimization)
- Adds the execution contract layer for predictability and quality
- Includes the eval surface for Layer 2 self-improvement (ADR-012's territory)

ADR-014 defines the project sub-wiki structure separately; this ADR is **purely about the shape of skill packages** the configuration ships, recommends, or helps users build.

## Decision

**Every framework-shipped skill follows this structure:**

```
skills/<skill-name>/
├── SKILL.md                  ← skill instructions (target <200 lines)
├── references/               ← context files loaded on demand by the skill itself
│   ├── <context>.md
│   └── ...
├── eval/
│   ├── eval.json             ← binary-assertion test cases (per Simon Scrapes)
│   └── fixtures/             ← optional input fixtures
└── learnings.md              ← optional, per-skill feedback log (per Simon Scrapes)
```

(Filenames `SKILL.md` follows Anthropic's convention; lowercase `skill.md` is also valid in some tools — use uppercase for new skills the framework authors.)

**SKILL.md frontmatter schema (extended from Anthropic's baseline):**

```markdown
---
name: <skill-name>                # required, kebab-case, must be unique
description: <one-line>           # required, drives activation matching (Layer 1)
version: <semver>                 # optional, follows the skill's release versioning
license: <SPDX-id>                # required for framework-shipped skills (e.g., MIT, Apache-2.0)

# Execution contract (new — Tsinghua NLH-inspired)
contract:
  required_outputs:               # what artifacts the skill must produce
    - <description of output>
  budgets:                        # operational bounds
    tokens: <max-tokens>          # optional cap on context usage
    turns: <max-turns>            # optional cap on agent turns
    files_written: <max-files>    # optional cap on file writes
    duration_seconds: <max-time>  # optional cap on wall-clock time
  permissions:                    # what the skill is allowed to do
    read: [paths or globs]        # what it can read
    write: [paths or globs]       # what it can write
    execute: [commands or none]   # what shell commands it may run
  completion_conditions:          # how "done" is decided
    - <unambiguous condition>
  output_paths:                   # where artifacts land (ties to ADR-014 output consolidation)
    - <path or glob>

# Optional fields
tags: [...]
related_skills: [...]
references_required: [...]        # files in references/ that MUST be loaded
references_on_demand: [...]       # files in references/ loaded when context warrants
---

# <Skill name>

<Skill instructions, <200 lines, progressive-disclosure-aware>

## When to use this skill
<Concrete triggers>

## How to use this skill
<Steps, with explicit completion criteria>

## Examples (optional)
<Concrete examples — but reference longer examples from references/ rather than inlining>

## Anti-patterns
<When NOT to use this; common mistakes>
```

**eval/eval.json schema (compatible with Skill Creator's `run_eval.py` per research):**

```json
{
  "name": "<skill-name>",
  "tests": [
    {
      "id": "test-1",
      "prompt": "<input that should trigger and exercise the skill>",
      "expected_output_summary": "<one-line description>",
      "binary_assertions": [
        "<unambiguous true/false assertion 1>",
        "<unambiguous true/false assertion 2>"
      ],
      "trigger_test": true
    }
  ],
  "non_triggers": [
    {
      "id": "non-trigger-1",
      "prompt": "<input that should NOT trigger this skill>",
      "expected_outcome": "skill_not_activated"
    }
  ]
}
```

**Binary assertion discipline (from Simon Scrapes):**

- Each assertion MUST be unambiguous true/false
- No subjective qualifiers ("compelling", "engaging", "natural") in binary assertions
- Subjective quality lives in optional `qualitative_review` fields (used by Skill Creator's qualitative dashboard, not by the autonomous loop)

Examples:

| Good (binary) | Bad (subjective) |
|---|---|
| "Output contains a code block in Python" | "Code is well-structured" |
| "Output is under 300 words" | "Output is concise" |
| "No m-dashes in the response" | "Tone matches our voice" |

**learnings.md** (optional, per Simon Scrapes' pattern):

Free-form per-skill feedback log. The skill reads this BEFORE running on each invocation (so it improves over time). Format:

```markdown
# Learnings for <skill-name>

## [2026-05-28] <category>
<observation, fix, or improvement note>
```

Not all skills need a learnings file. Add when the skill is genuinely improving from session-to-session feedback.

**References directory:**

`references/` holds context the skill loads on demand. Each file is its own markdown document, focused on one topic. The skill's main `SKILL.md` mentions when to load each reference (via `references_required` and `references_on_demand` in frontmatter).

This is the progressive-disclosure mechanic: SKILL.md stays under 200 lines; deeper context lives in references/, loaded only when the skill's logic decides it's needed.

## Consequences

**Easier:**
- **Compatibility with Skill Creator's tooling preserved.** Our SKILL.md format extends Anthropic's, doesn't replace it. Layer 1 description optimization works out of the box.
- **Execution contracts make skill behavior predictable.** The `contract` field is documentation + enforcement surface; future tooling can verify a skill's outputs meet its contract.
- **Quality bar is built in.** Skills without `eval/eval.json` are considered experimental; the bar for "production" is having binary tests.
- **Self-improvement infrastructure is teed up.** ADR-012 (next) builds Layer 2 on top of this schema.
- **Discoverable by the wake-up.** Skills with rich frontmatter can be discovered/described by index pages or future search tooling.

**Harder:**
- **Authoring a skill requires more than the minimum Anthropic format.** Friends building their own skills need to learn the framework's extensions. Mitigation: provide a `skill-template/` directory + Skill Creator can be tuned to emit our extended format.
- **Backwards compatibility with skills authored without contracts.** Skills that pre-date this ADR (or community skills we want to adopt) won't have `contract` fields. Treat as legacy / experimental until contracts are added.
- **eval.json discipline takes work.** Writing good binary assertions is harder than it looks. Onboarding (ADR-015) should include an "authoring evals" guide.

**Now impossible:**
- Shipping a framework skill without an eval (everything we ship has tests)
- Shipping a framework skill without an execution contract (everything we ship has clear input/output/budget definitions)

**Sunset review trigger conditions:**
- Anthropic changes the SKILL.md baseline format → align
- A community standard emerges for execution contracts → align if better than ours
- Skill Creator changes its eval.json format → adapt to maintain Layer 1 compatibility
- Our frontmatter grows to feel heavy → consider extracting some fields into separate files

## Alternatives considered

### A) Just use Anthropic's baseline format; skip contracts and evals

**Considered shape**: Don't extend the format. Ship simple SKILL.md files. Add evals only if Skill Creator's defaults aren't enough.

**Why rejected**: Loses the predictability that execution contracts give. Loses the self-improvement infrastructure that evals enable. The whole reason to ship a framework is to standardize quality patterns; this ADR is the heart of that.

### B) Use a richer schema with full JSON Schema validation

**Considered shape**: Define a formal JSON Schema for SKILL.md frontmatter; validate on install.

**Why rejected**: Premature. Validators add infrastructure (per ADR-003's no-daemon spirit). For v1, document the schema clearly and let humans + LLMs follow it. If validation becomes necessary, v2 can add a `/sf:lint-skills` slash command.

### C) Per-skill databases or specialized stores instead of eval.json

**Considered shape**: Store evals in SQLite or another database for queryability.

**Why rejected**: Plain JSON is simpler, git-versioned, human-readable, and compatible with Skill Creator's existing tooling. No reason to add infrastructure.

### D) Skip learnings.md as a separate file; fold into the skill itself

**Considered shape**: Inline the feedback log within SKILL.md.

**Why rejected**: SKILL.md is target <200 lines; learnings can grow large. Separate file is cleaner. Also, the LLM updates learnings.md without modifying SKILL.md — separation of concerns.

## References

- `wiki/research/simon-scrapes-self-improving-skills.md` — binary assertions, eval/eval.json pattern, learnings.md
- `wiki/research/simon-scrapes-claude-skills-upgrade.md` — small/focused/reusable skill design + skill systems composition
- `wiki/research/py-harness-engineering.md` — Tsinghua NLH execution contracts (5 elements: required outputs, budgets, permissions, completion conditions, output paths)
- `wiki/research/skill-creator.md` — Anthropic's baseline SKILL.md format + run_eval.py compatibility target
- `wiki/research/superpowers.md` — existing skills following progressive disclosure with <200 line bodies
- ADR-006 (Curated Stack) — adopts Skill Creator which expects compatible eval.json format
- ADR-012 (Two-Layer Self-Improvement) — uses this schema's eval/ directory + learnings.md
- ADR-014 (Project Sub-Wiki Taxonomy) — output_paths contract field ties to project output consolidation

---

## Amendment — 2026-06-27: Lightweight skill tier (H2)

The positioning pivot (`wiki/research/new-angles-for-the-os.md`) wants skills to also cover "a prompt you don't want to retype" — a personal or glue skill that exists purely to save typing. The original decision's *"Now impossible: shipping a skill without an eval / without an execution contract"* is the right bar for **production** skills but too heavy for that use, so this amendment adds an explicit, additive carve-out.

**Decision:** an optional `tier:` SKILL.md frontmatter field, additive and backward-compatible.

- `tier: standard` — **the default** (also implied when `tier:` is absent). The full ADR-011 contract above applies: frontmatter + execution `contract` + `eval/eval.json`.
- `tier: lightweight` — `SKILL.md` with `name` + `description` + a prompt body, nothing else required. **No** `eval/eval.json`, **no** execution `contract`; `version`/`license` optional.

**Rules for `tier: lightweight`:**

1. **Not self-improvable.** `/ren:improve-skill` refuses a lightweight skill (`skills/improve-skill/lib/preflight.py` → `_refuse_if_lightweight`, Gate 1b, *before* the eval-file gate) — it has no eval surface for the Karpathy loop to score against. The refusal message points to the promotion path.
2. **Lint-exempt.** `/ren:doctor`'s skill-size lint (`skills/doctor/scripts/check-context.sh`, H1) requires only `name` + `description` for lightweight skills (vs `name`/`description`/`version` for standard). Oversize warnings still apply to everyone.
3. **Promotion path.** Add `eval/eval.json` (+ a contract) and drop `tier: lightweight` → the skill becomes `standard` and self-improvable. By intent there is no auto-demotion.
4. **Framework-shipped skills stay `standard`.** This tier lowers the bar for the *personal / glue* skills a builder writes for themselves; it does **not** relax what the framework itself ships. The "Now impossible" clause above still governs production skills.

**Why additive, not a schema-version bump:** `tier:` is a `SKILL.md` frontmatter convention, not a wiki page-type (ADR-027) — no `schemas.json` change, no migration. A skill with no `tier:` is unchanged; removing the field reverts to standard.

**Implements:** roadmap H2 task 1.
