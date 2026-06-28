# Identity Interview — Question Template (v2)

Eighteen identity questions across five sections (A–E), plus an **optional** venture arc (Section F, ~5
questions → the `venture-profile` pages). Per ADR-022 (broadened in H2.3). Loaded by `SKILL.md` step 2.

Each question entry has:

- **id** — stable identifier (used in `skipped_questions` and re-run flow)
- **section** — A / B / C / D / E
- **type** — `open` | `choice` | `multi-choice`
- **strategy** — input strategy; references `ask-user-question-pagination.md` patterns
- **field** — destination YAML key in `identity.md`
- **prompt** — the question text
- **options** — for choice/multi-choice, the option set
- **default** — sensible neutral default; never the framework developer's preference

Total target: ~10 minutes for the friend, 70% complete acceptable. Friend may skip any question.

---

## Section A — About you (5 questions)

### Q1 — Name + handle
- id: `q1-name-handle`
- section: A
- type: open (two open-ended sub-prompts: full name → handle suggestion)
- strategy: native open-ended
- field: `name`, `handle`
- prompt: |
    What name should I use for you (display name, free-form), and what short
    handle do you prefer as a personal label? (handle: lowercase, kebab-case,
    letters/digits/hyphens only)
- validation: handle matches `^[a-z][a-z0-9-]*$`
- prepopulation: if `/ren:install` Stage 3 supplied `proposed_handle`, pre-fill
  the handle answer. Friend confirms or changes.
- default: prompt user; no neutral default

### Q2 — Brief intro
- id: `q2-intro`
- section: A
- type: open
- strategy: native open-ended
- field: markdown body — "About you" section, first paragraph
- prompt: |
    One paragraph — who are you, what do you focus on right now?
- default: empty paragraph placeholder

### Q3 — Current role + background
- id: `q3-role`
- section: A
- type: choice
- strategy: **pagination** (5 options > cap; split into 2 prompts)
- field: markdown body — "Background & current role" section
- prompts:
  - page 1: "Closest match for your current role? — student / employed / freelance / other"
  - page 2 (only if "other"): "Refine — between things / contractor / founder / type your own"
- options:
  - page 1: [student, employed, freelance, other]
  - page 2: [between-things, contractor, founder, free-form]
- default: `other`

### Q4 — Strong skill areas
- id: `q4-strong-skills`
- section: A
- type: multi-choice
- strategy: **category cascade** (9 options > cap; 2-stage drill)
- field: `strong_skills`
- prompts:
  - stage 1: "Which broad categories are your strongest? — build / design / product-ops / other"
  - stage 2 (per category chosen): drill into sub-options
- categories:
  - build → [ai-ml, backend, frontend, data-eng, devops]
  - design → [design]
  - product-ops → [product, content]
  - other → free-form text
- fallback: "Or type a comma-separated list" — always offered as escape hatch
- default: `[]`

### Q5 — Areas to grow in
- id: `q5-growth-areas`
- section: A
- type: multi-choice
- strategy: **category cascade** (same as Q4)
- field: `growth_areas`
- prompts: same shape as Q4 with "want to grow in" framing
- categories: same as Q4
- default: `[]`

## Section B — Working style (4 questions)

### Q6 — Response length
- id: `q6-response-length`
- section: B
- type: choice
- strategy: native (4 options)
- field: `working_style`
- prompt: "Preferred response length when I'm replying to you?"
- options: [terse, balanced, verbose, case-by-case]
- default: `balanced`

### Q7 — Communication tone + emoji
- id: `q7-communication-style`
- section: B
- type: composite — two sub-questions whose answers compose
- strategy: **combine** (5 options collapsed to 4 by splitting orthogonal axes)
- field: `communication_style` (composed string)
- sub-question 7a:
    prompt: "Preferred tone?"
    options: [formal, casual, case-by-case, other]
- sub-question 7b:
    prompt: "Emojis welcome?"
    options: [yes, no, occasionally, case-by-case]
- composition: e.g. `casual` + `no` → `casual-no-emoji`; `formal` + `occasionally` → `formal-some-emoji`. The renderer joins with hyphens; new combinations are allowed without schema change.
- default: `balanced-with-emoji`

### Q8 — Plans before code
- id: `q8-plans-before-code`
- section: B
- type: choice
- strategy: native (4 options)
- field: `plans_before_code`
- prompt: "How often do you want me to write a plan before writing code?"
- options: [always, often, sometimes, rarely]
- default: `often`

### Q9 — Working hours + timezone
- id: `q9-hours-tz`
- section: B
- type: open
- strategy: native open-ended
- field: `contact.timezone`, `contact.working_hours`
- prompt: |
    Optional: what's your timezone (IANA format e.g. Europe/Istanbul) and
    typical working hours? Helps your AI adapt to when you work.
- default: empty strings

## Section C — Tech preferences (5 questions)

### Q10 — Primary languages
- id: `q10-languages`
- section: C
- type: multi-choice
- strategy: **category cascade** (11 options > cap)
- field: `languages`
- prompts:
  - stage 1: "Which language categories do you use most? — systems / web / mobile / data-or-other"
  - stage 2 (per category): drill into sub-options
- categories:
  - systems → [go, rust, cpp]
  - web → [typescript, javascript, php, ruby]
  - mobile → [swift, kotlin, java]
  - data-or-other → [python, other]
- fallback: "Or type a comma-separated list" — always offered
- default: `[]`

### Q11 — Package managers
- id: `q11-package-managers`
- section: C
- type: open
- strategy: native open-ended
- field: `package_managers`
- prompt: |
    Preferred package managers? Free-form; comma-separated. (e.g. "uv for
    Python, pnpm for TypeScript, cargo for Rust")
- default: `[]`

### Q12 — Cloud / hosting
- id: `q12-clouds`
- section: C
- type: multi-choice
- strategy: **pagination** (7 options > cap)
- field: `clouds`
- prompts:
  - page 1: [aws, vercel, supabase, more...]
  - page 2 (only if "more..."): [gcp, cloudflare, self-hosted, other]
- default: `[]`

### Q13 — Databases
- id: `q13-databases`
- section: C
- type: multi-choice
- strategy: **pagination** (6 options > cap)
- field: `databases`
- prompts:
  - page 1: [postgresql, sqlite, supabase, more...]
  - page 2 (only if "more..."): [mongodb, duckdb, other]
- default: `[]`

### Q14 — Other key tools
- id: `q14-other-tools`
- section: C
- type: open
- strategy: native open-ended
- field: markdown body — "Tech preferences" section
- prompt: |
    Other key tools you live in? Free-form. (e.g. Docker, Kubernetes,
    specific frameworks, editors, terminals.)
- default: empty paragraph placeholder

## Section D — Opinions + non-goals (3 questions)

### Q15 — TDD attitude
- id: `q15-tdd`
- section: D
- type: choice
- strategy: native (4 options)
- field: `tdd_attitude`
- prompt: "Where do you sit on test-driven development?"
- options: [mandatory, encouraged, case-by-case, not-for-me]
- default: `case-by-case`

### Q16 — Patterns to avoid
- id: `q16-avoid-patterns`
- section: D
- type: open
- strategy: native open-ended
- field: markdown body — "Strong opinions + non-goals" section
- prompt: |
    What patterns do you want me to AVOID? Free-form. (Examples: "over-engineering,
    premature abstractions, excessive comments, magic numbers". Don't worry
    about being exhaustive — surface what's top of mind.)
- default: empty list placeholder

### Q17 — Current phase
- id: `q17-phase`
- section: D
- type: choice
- strategy: native (4 options)
- field: `phase`
- prompt: |
    What phase is your friend group / your work in right now?
    (Informational only; we don't mechanically toggle skills off this answer
    — per ADR-022 it's a soft signal so your AI can adapt response defaults.)
- options: [ideation, building, shipping, other]
- default: `ideation`

## Section E — Contribution (1 question)

### Q18 — Contribution
- id: `q18-contribution`
- section: E
- type: open
- strategy: native open-ended
- field: markdown body — "What I contribute" section
- prompt: |
    What do you contribute most to a friend-group project? What role do you
    typically land in?
- default: empty paragraph placeholder

## Section F — Venture context (OPTIONAL, ~5 questions) — broadened onboarding (H2.3)

> **Skippable as a whole.** Gate first: "Want to sketch your venture/studio context now? (optional — you can
> always run `/ren:interview` later or fill the `wiki/venture/` pages by hand)." If **no** → skip all of F,
> record `f-venture` in `skipped_questions`, leave the venture stubs as placeholders. Each answer populates one
> `wiki/venture/<section>.md` page (type `venture-profile`); every question is independently skippable and
> `_TBD_` is always acceptable (the friend may be pre-idea / still exploring).

### F1 — Company / what you're building
- id: `f1-company`
- section: F
- type: open
- strategy: native open-ended
- field: `wiki/venture/company.md` body
- prompt: |
    What are you building? One line, then a short paragraph if you have it.
    What stage is it at — idea / prototype / launched / scaling?
- default: leave the template's `_TBD_` placeholder

### F2 — Market / the space
- id: `f2-market`
- section: F
- type: open
- strategy: native open-ended
- field: `wiki/venture/market.md` body
- prompt: |
    The space you're playing in — who else is there, and why now? Rough is fine.
- default: leave `_TBD_`

### F3 — Ideal customer
- id: `f3-icp`
- section: F
- type: open
- strategy: native open-ended
- field: `wiki/venture/icp.md` body
- prompt: |
    Who is this for? The person or team you most want to help first — their
    context and their pain.
- default: leave `_TBD_`

### F4 — Team
- id: `f4-team`
- section: F
- type: open
- strategy: native open-ended
- field: `wiki/venture/team.md` body
- prompt: |
    Who's building this — just you, or collaborators / advisors / future hires?
    (Solo is a complete answer.)
- default: leave `_TBD_`

### F5 — Brain dump
- id: `f5-brain-dump`
- section: F
- type: open
- strategy: native open-ended
- field: `wiki/venture/brain-dump.md` body
- prompt: |
    Anything else worth capturing on day one — raw thoughts, goals, constraints,
    open questions? No structure needed.
- default: leave `_TBD_`

---

## Question-template revision policy

Adding / removing / renaming questions = a schema bump. Bump `schema_version`
in the friend-profile schema, document the migration in ADR-027's
schema-versioning ADR, and ensure the re-run flow handles old-schema
identity.md files gracefully (additive migration; never silently drop fields).

Adding / removing options inside a question = no schema bump if the field
type stays the same. Document in this file's revision history below.

**Section F (venture) is exempt from the identity-bump rule:** its answers populate separate
`venture-profile` pages, not `identity.md` fields, so adding/changing F questions never bumps the
friend-profile schema (additive new page-type, H2.3).

## Revision history

- v1 (2026-05-28) — initial 18-question template per ADR-022.
- v2 (2026-06-28) — added the optional **Section F** venture arc (→ `venture-profile` pages); the identity
  friend-profile schema stays at v1 (broadened onboarding, H2.3).
