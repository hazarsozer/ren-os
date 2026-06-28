# Output Format — identity.md (hybrid YAML + markdown)

Per ADR-022 + plan §3 (ratified). The friend's local `~/.startup-framework/wiki/identity.md` uses YAML frontmatter for machine-readable fields and a markdown body for free-form narrative. Other framework skills (wake-up, doctor, peer-aware tools) read the YAML; humans + AI read the body.

## Canonical frontmatter schema (v1)

```yaml
---
title: "<Name>'s Identity"               # required; string
type: identity                           # required; const
schema_version: 1                        # required; int (per ADR-027)
framework_version: "<semver>"            # required; string

handle: <handle>                         # required; kebab-case ^[a-z][a-z0-9-]*$
name: "<Display Name>"                   # required; string
created: <YYYY-MM-DD>                    # required; ISO date
updated: <YYYY-MM-DD>                    # required; ISO date; rewritten every /ren:interview

phase: ideation                          # required; enum {ideation|building|shipping|other}
                                         # default: ideation

languages: []                            # required; list[enum]; may be empty
                                         # enum: python|typescript|javascript|go|rust|swift|
                                         #       kotlin|java|cpp|php|ruby|other
package_managers: []                     # optional; list[string]; free-form (e.g. "uv","pnpm")
clouds: []                               # optional; list[enum]
                                         # enum: aws|gcp|vercel|cloudflare|supabase|self-hosted|other
databases: []                            # optional; list[enum]
                                         # enum: postgresql|sqlite|supabase|mongodb|duckdb|other

working_style: balanced                  # required; enum {terse|balanced|verbose|case-by-case}
                                         # default: balanced
communication_style: balanced-with-emoji # required; string; composed from Q7a + Q7b
                                         # examples: casual-no-emoji, formal-some-emoji
plans_before_code: often                 # required; enum {always|often|sometimes|rarely}
                                         # default: often
tdd_attitude: case-by-case               # required; enum {mandatory|encouraged|case-by-case|not-for-me}
                                         # default: case-by-case

strong_skills: []                        # required; list[enum]; may be empty
                                         # enum: ai-ml|frontend|backend|data-eng|devops|
                                         #       design|product|content|other
growth_areas: []                         # required; list[enum]; same enum as strong_skills

contact:                                 # optional block
  timezone: ""                           #   IANA tz (e.g. "Europe/Istanbul")
  working_hours: ""                      #   free-form

skipped_questions: []                    # optional; list[string] of question IDs the friend skipped
---
```

## Markdown body structure

Five fixed top-level sections, in this order. Sections may be empty if the friend skipped the relevant questions.

```markdown
# About <Name>

<Q2's intro paragraph — free-form text>

## Background & current role

<Synthesis of Q3 (role/background) + a brief mention of strong_skills/growth_areas
 if the friend wants narrative context to complement the YAML lists>

## Working style

<Narrative synthesis of Q6 + Q7 + Q8 + Q9 — how the friend likes responses,
 communication tone, planning habits, hours/tz if shared>

## Tech preferences

<Narrative from Q11 (package managers free-form) + Q14 (other tools free-form).
 Optionally mention languages/clouds/databases if the friend wants narrative
 context — but don't restate the YAML lists verbatim; they're already there.>

## Strong opinions + non-goals

<Q16's free-form AVOID list, plus a sentence from Q15's TDD attitude framing
 if the friend chose mandatory or not-for-me (both strong signals worth narrating)>

## What I contribute

<Q18's contribution paragraph>
```

## Render rules

1. **YAML first, body second**. The frontmatter block must appear at the top of the file, delimited by `---` lines. Body follows.
2. **One blank line between frontmatter and body H1**.
3. **No emojis** in either YAML or body if `communication_style` contains `no-emoji`. This is asserted by `eval/eval.json`'s emoji-free test.
4. **Quote strings containing colons** in YAML. Otherwise leave unquoted for cleanliness.
5. **Preserve list shape** — `[]` for explicit empty, `[a, b, c]` flow-style for short lists, block style for long lists. Don't mix flow and block in the same file.
6. **Date format**: ISO YYYY-MM-DD only. No times. No timezones in the `created`/`updated` fields (timezone lives in `contact.timezone`).
7. **Total file size**: target < 5 KB. Eval asserts on this — sprawl is a smell that the interview overcaptured.
8. **Unknown enum values**: if Q4/Q5/Q10/Q12/Q13's "other" path captures a free-form value the enum can't represent, normalize to `other` in the list AND preserve the free-form text in the markdown body's relevant section. Don't silently drop information.
9. **Skipped questions**: record the question ID in `skipped_questions`. Don't write empty placeholders in YAML — use the schema's default value AND mark the question skipped so re-run knows to ask again.

## Venture pages (`venture-profile`) — broadened onboarding (H2.3)

Section F populates five **separate** pages under `~/.startup-framework/wiki/venture/`, NOT `identity.md`. Each
is a `venture-profile` page (loose schema: the universal triple + `section`). The interview writes the friend's
answer into the page body in place of the template's `_TBD_` placeholder; a skipped question leaves it intact.

| Page | section | F-question | Body |
|---|---|---|---|
| `venture/company.md` | company | F1 | what you're building + stage |
| `venture/market.md` | market | F2 | the space, why-now, alternatives |
| `venture/icp.md` | icp | F3 | ideal customer / user |
| `venture/team.md` | team | F4 | who's building |
| `venture/brain-dump.md` | brain-dump | F5 | freeform |

Frontmatter (per page):

```yaml
---
title: "Venture — <Section>"      # required; string
type: venture-profile             # required; const
schema_version: 1                 # required; int
framework_version: "<semver>"     # required; string
section: company|market|icp|team|brain-dump   # required; the page discriminator
updated: <YYYY-MM-DD>             # rewritten on each /ren:interview venture pass
---
```

Render rules (in addition to the identity rules above):
- **Don't invent.** Thin or skipped answer → keep the `_TBD_` placeholder (the ingest-project honest-placeholder
  ethic). The venture profile is allowed to be mostly-empty for a pre-idea friend.
- **One page per section**; never collapse them into `identity.md`. `identity.md` is the "you"; these are the venture.
- **Skip handling**: a skipped F question records its ID in `identity.md`'s `skipped_questions` (the single skip
  ledger), and the corresponding venture page keeps its placeholder body.

## What's NOT in the local identity.md

- Anything beyond the friend's own profile. No notes about peers. No project state. No session pointers.
- Anything that should live in `wiki/identity.md` of *another* friend. There's no such concept — each friend's identity is local-only per ADR-017.

## Migration from older schemas

When `schema_version` in an existing file is older than the current framework's expected version:

1. Re-run flow detects the mismatch.
2. Loads schema-migration rules from the framework's distribution layer (sf-distribution owns `migrations/`).
3. Shows the friend the proposed transformation (additive fields with defaults; renamed fields with explicit mapping).
4. Requires explicit approval. Mirrors the additive-diff pattern from `wiki-skeleton/`.
5. Writes the updated file with new `schema_version` and `updated` date.

Per ADR-017's backwards-compat commitment: old fields are NEVER silently dropped during migration; they're either preserved as deprecated or explicitly removed with the friend's consent.

## Cross-references

- ADR-004 — wiki page format conventions this file follows
- ADR-022 — identity-interview skill ADR
- ADR-017 — per-friend wiki scope; identity is local-only
- ADR-027 — schema versioning + migration mechanics
- plan §3 — cross-team-ratified friend-profile schema
