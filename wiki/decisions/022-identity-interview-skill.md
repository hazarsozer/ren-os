---
title: "ADR-022: Identity-Interview Skill — `/sf:interview` Spec"
status: accepted
amended-by:
  - "ADR-031 (2026-05-30, solo-first pivot): the interview keeps the `handle:` field (reframed as a personal short-name) but no longer pushes a public summary to a shared feed. No feed identity sync. AMENDED, not superseded."
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [simon-scrapes-agentic-os, skill-creator, ecc-everything-claude-code]
affects-components: [skills, install, identity, onboarding]
relates-to: [011-skill-schema, 015-onboarding, 017-per-friend-wiki-scope, 018-activity-feed]
---

# ADR-022: Identity-Interview Skill — `/sf:interview` Spec

> 📝 **Amended by [ADR-031](031-solo-first-pivot.md) (2026-05-30).** Solo-first: the interview keeps the `handle:` field (a personal short-name) but no longer pushes a public summary to a shared feed. The interview itself stands.

## Context

ADR-015's Stage 4 (identity bootstrap) names an "identity-interview" skill but doesn't specify it. The skill needs to:

1. Be the AI-driven interview that runs during `/sf:install` to populate the friend's identity
2. Write to `wiki/identity.md` (per the ADR-015 amendment that corrected the framing — single local file, not shared)
3. Push a public summary to `<activity-feed>/identities/<handle>.md` (per ADR-020's joiner flow)
4. Be re-runnable anytime via `/sf:interview`, detecting existing identity content

Without this ADR, the install skill would attempt to run an unspecified interview and the output structure would be ad-hoc.

## Decision

### Slash command + invocation

- `/sf:interview` — runs the full interview from scratch, OR if `wiki/identity.md` exists, offers to refresh specific fields
- Invoked automatically by `/sf:install` Stage 4
- Can be re-run anytime by the friend (e.g., after a role change, after learning a new stack)

### Question structure: multiple-choice + open-ended mix, ~17-18 questions

The skill uses `AskUserQuestion` (Claude Code's built-in tool) for multiple-choice questions; falls back to open-ended prompts when the answer needs free-form input. Per user direction: multiple-choice questions always include an "Other" option for custom answers (this is `AskUserQuestion`'s default behavior).

**Question template (v1 — extensible later):**

#### Section A — About you (5 questions)
1. **Name + preferred handle for the Activity Feed?** (open-ended)
2. **Brief one-paragraph intro** — who are you, what do you focus on right now? (open-ended)
3. **Current role + background** — student / employed / freelance / between things / other? (multi-select choice + other)
4. **Strongest skill areas** (multi-select: AI/ML, frontend, backend, data eng, devops, design, product, content, other)
5. **Areas you want to grow in** (multi-select with same options + other)

#### Section B — Working style (4 questions)
6. **Preferred response length**: terse / balanced / verbose / case-by-case (choice)
7. **Communication style**: emojis welcome / emoji-free / formal / casual / case-by-case (choice)
8. **Plans before code**: always / often / sometimes / rarely (choice)
9. **Optional context**: working hours + time zone (open-ended; helps friends interpret Activity Feed timing)

#### Section C — Tech preferences (5 questions)
10. **Primary language(s)** (multi-select: Python, TypeScript/JavaScript, Go, Rust, Swift, Kotlin, Java, C++, PHP, Ruby, other)
11. **Preferred package managers** (open-ended; e.g., "uv for Python, pnpm for TS")
12. **Preferred cloud / hosting** (multi-select: AWS, GCP, Vercel, Cloudflare, Supabase, self-hosted, other)
13. **Preferred database(s)** (multi-select: PostgreSQL, SQLite, Supabase, MongoDB, DuckDB, other)
14. **Other key tools you live in** (open-ended; e.g., "Docker, Kubernetes, specific frameworks")

#### Section D — Opinions + non-goals (3 questions)
15. **TDD attitude**: mandatory / encouraged / case-by-case / not for me (choice)
16. **Patterns you want Claude to AVOID** (open-ended; e.g., "over-engineering, premature abstractions, excessive comments")
17. **Current phase + role**: ideation / building / shipping / other (choice — see Phase-toggling note below)

#### Section E — Contribution (1 question)
18. **What you'd contribute most to a friend-group project / your typical role** (open-ended)

Target completion: ~10 minutes. 70% complete is acceptable; friend can refine later by re-running `/sf:interview` or editing `wiki/identity.md` directly.

### Output structure: YAML frontmatter + markdown body (hybrid, matches ADR-004 wiki convention)

Per ADR-004 wiki convention, identity.md uses YAML frontmatter for machine-readable fields and markdown body for free-form content. This is the established pattern for ALL wiki pages; identity.md follows it.

**Template:**

```markdown
---
title: <Friend's Name>'s Identity
type: identity
handle: <handle>
name: <Full Name>
created: 2026-05-28
updated: 2026-05-28
framework_version: 1.0.0
schema_version: 1
phase: ideation                         # ideation | building | shipping | other
languages: [python, typescript]
package_managers: [uv, pnpm]
clouds: [vercel, supabase]
databases: [postgresql, supabase]
working_style: balanced                 # terse | balanced | verbose | case-by-case
communication_style: casual-no-emoji    # composed string
plans_before_code: often                # always | often | sometimes | rarely
tdd_attitude: case-by-case              # mandatory | encouraged | case-by-case | not-for-me
strong_skills: [ai-ml, backend]
growth_areas: [frontend, design]
---

# About <Name>

<one-paragraph intro from Q2>

## Background & current role

<from Q3 + Q4>

## Working style

<from Q6 + Q7 + Q8 + Q9 — narrative; free-form synthesis of the choices>

## Tech preferences

<from Q11 + Q14 — narrative; free-form details that didn't fit the multi-selects>

## Strong opinions + non-goals

<from Q15 + Q16 — explicit AVOID list>

## What I contribute

<from Q18>
```

YAML fields are machine-readable (used by skills, wake-up hook, etc.). Markdown body is human-friendly + AI-friendly narrative.

### Public summary in Activity Feed

Per ADR-020, identity-bootstrap also writes a public summary to `<activity-feed-repo>/identities/<handle>.md`. This file contains ONLY the public-facing fields:

```markdown
---
handle: hazar
name: Hazar Söz
phase: ideation
strong_skills: [ai-ml, backend]
clouds: [vercel, supabase]
---

# <handle>

<one-paragraph intro — copied from Q2>

What I typically contribute: <from Q18>
```

Local identity.md may contain more detail; public identity is a subset (friend can edit if they want less / more public).

### Re-running the interview

`/sf:interview` checks for existing `wiki/identity.md`:

**If file doesn't exist:**
- Run full interview from scratch
- Create both local + public files

**If file exists:**
- Show summary of current fields
- Ask: "Want to refresh fully (all questions) or update specific fields?"
- If "full": run all questions, with current values as defaults
- If "specific": let friend pick which sections (A/B/C/D/E) or individual questions
- Show diff before writing; require approval (similar to `/revise-claude-md`'s pattern)
- Sync the public summary in Activity Feed if relevant fields changed

### Phase-toggling note (per user clarification — soft, not mechanical)

ADR-006 originally proposed phase-based Superpowers skill toggling (TDD + subagent-driven-development + git-worktrees + finishing-a-development-branch active only at build phase). The user expressed uncertainty about whether this is necessary.

**Resolution**: keep the phase question (Q17) as INFORMATIONAL context for the friend's own AI. Skill toggling is NOT mechanically driven by this answer — all Superpowers skills are available at install. The framework's onboarding can SUGGEST disabling certain skills if the friend's phase suggests they're friction (e.g., "you said you're in ideation — want to disable strict TDD-mandatory enforcement for now?"). The friend decides.

This avoids the user's concern (phase toggling may not be necessary) while preserving the option for friends who DO want phase-appropriate defaults.

### Skill schema (per ADR-011)

The identity-interview skill ships with the full schema per ADR-011:

```
skills/identity-interview/
├── SKILL.md                       # <200 lines per progressive disclosure
├── references/
│   ├── question-template.md       # The 18-question default template
│   ├── output-format.md           # YAML frontmatter + markdown body spec
│   └── re-run-flow.md             # Behavior when identity.md already exists
├── eval/
│   └── eval.json                  # Binary assertions for skill quality
└── learnings.md                   # Optional, future feedback log
```

**eval.json binary assertions** (per ADR-011 + ADR-012):
- Output file matches the template structure (frontmatter + 5 markdown sections)
- All 18 fields are present in frontmatter (or marked "skipped" if friend declined a question)
- Handle is kebab-case (no spaces, no special chars)
- Phase is one of: ideation | building | shipping | other
- File is < 5KB (preventing accidental sprawl)
- No emojis if `communication_style: emoji-free` (test that the style preference is respected)

These assertions are checked by Skill Creator's eval loop (per ADR-012 Layer 1 + Layer 2 self-improvement).

## Consequences

**Easier:**
- Onboarding produces structured, machine-readable identity that other skills can read
- Re-runnable means friends can refine over time (not stuck with first-day answers)
- YAML frontmatter + markdown body matches wiki convention — no new format to learn
- Multiple-choice + open-ended hybrid keeps interview fast but expressive

**Harder:**
- Question template will need maintenance as the framework evolves (new tools become relevant, others fade)
- Re-running with diff approval adds UX work (similar pattern to `/revise-claude-md` but doubles the implementation)
- Public summary sync introduces a new failure mode (what if Activity Feed push fails during identity update?)

**Now impossible:**
- Ad-hoc identity files with inconsistent schema across friends
- Mandatory phase toggling that locks friends into rigid skill sets

**Sunset review trigger conditions:**
- Questions become stale (new categories of tools emerge that aren't covered)
- 70%-in-10-min target proves too ambitious or too easy
- Re-run flow has UX bugs (friends bypass `/sf:interview` to edit manually) — that's a signal the flow is broken

## Alternatives considered

### A) Fewer questions (~10 max for speed)

**Considered shape**: Trim to ~10 essentials; deprioritize "strong opinions" and "non-goals" sections.

**Why rejected per user direction**: "Being richer doesn't hurt if needed." Friends are investing in framework setup once; spending 10 minutes vs. 6 is fine. The non-goals section especially is high-value (preventing AVOID patterns is critical for friend's AI behavior).

### B) All open-ended (no multiple choice)

**Considered shape**: Conversational interview throughout; no preset options.

**Why rejected**: Slower, less consistent across friends. Some questions have well-defined option spaces (working style, TDD attitude, phase) that multiple-choice handles cleanly. The "Other" option preserves expressivity.

### C) Pure YAML frontmatter (no markdown body)

**Considered shape**: All identity info goes in frontmatter; no narrative body.

**Why rejected**: Forces unnatural compression. "What I contribute" + "patterns to avoid" + "working style" are inherently free-form. Hybrid is the right shape and matches every other page in the wiki.

### D) Pure markdown (no YAML frontmatter)

**Considered shape**: All identity info goes in markdown body; no YAML structure.

**Why rejected**: Makes machine-readable fields hard to query. Skills that need to know the friend's preferred language (e.g., the consolidate skill choosing a code-review approach) shouldn't have to parse free-form text.

### E) Phase-toggling is mechanically enforced

**Considered shape**: The phase answer mechanically disables build-phase Superpowers skills (TDD, sub-agent-dev, worktrees, finishing) if friend is in ideation.

**Why rejected per user direction**: User uncertain if necessary. Soft signal (suggestion at install, friend decides) is enough.

### F) Re-running starts from scratch every time

**Considered shape**: `/sf:interview` always asks all 18 questions from scratch, overwrites identity.md.

**Why rejected per user direction**: "Knows if there's an earlier interview file or not when the skill runs." Re-running should refresh, not restart.

## Open questions for implementation phase

1. **AskUserQuestion limitations** — Claude Code's `AskUserQuestion` tool has max 4 options per multi-select. Some of our questions (e.g., Q3 "role" with 5+ options) may need to be split into two passes or use open-ended fallback. Verify during implementation.

2. **Question ordering** — Section order (A→B→C→D→E) seems natural but user testing may reveal friends drop off in section C (tech preferences) because it's the most tedious. Consider re-ordering to put "What you contribute" earlier as a hook.

3. **Defaults across sessions** — when a friend re-runs `/sf:interview` to refresh, should the new answers DEFAULT to current values (low-friction refresh) or start blank (forces conscious re-affirmation)? Default to current values is friendlier; blank is more rigorous. Decide during implementation.

4. **Activity Feed public summary updates** — if friend updates identity locally but Activity Feed push fails (network down), is the local update aborted or stored locally for retry? Same general problem as ADR-018's graceful-degradation; mirror that pattern.

5. **Internationalization** — Question phrasings are English-only in v1. If the friend group ever has non-English-primary speakers, translation becomes a concern. Out of v1 scope; flag for v2.

## References

- `wiki/research/simon-scrapes-agentic-os.md` — original AI-interviewed identity pattern (Pillar 1 of his Agentic OS)
- `wiki/research/skill-creator.md` — the eval-loop infrastructure this skill's eval.json plugs into
- `wiki/research/ecc-everything-claude-code.md` — ECC's identity-elicitation patterns
- ADR-011 (Skill Schema) — defines the skill structure this skill follows
- ADR-012 (Two-Layer Self-Improvement) — defines how this skill's eval.json drives improvement
- ADR-015 (Onboarding) — Stage 4 calls this skill; this ADR specifies the skill itself
- ADR-017 (Per-Friend Wiki Scope) — identity.md is per-friend-local
- ADR-018 (Activity Feed) — public summary in `<activity-feed>/identities/<handle>.md`
- ADR-020 (Joiner & Leaver) — re-running the interview matters for friends evolving over time
