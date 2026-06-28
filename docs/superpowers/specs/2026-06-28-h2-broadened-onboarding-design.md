# H2.3 — broadened onboarding (venture profile beyond identity)

**Date:** 2026-06-28
**Slice:** H2 part 3 (the deferred onboarding broadening)
**Status:** design → build
**ADRs:** amends ADR-022 (interview), ADR-014 (taxonomy), ADR-027 (registry)
**Greenlit approach:** separate pages, fully additive — `identity.md` stays v1, **no migration**.

## Context

The positioning spec (line 67) calls for "**BROADEN** the guided init ritual — Ben's 12-section population
(you/company/market/ICP/team + brain-dump) beyond identity-only" → a "day-1 populated brain." Today
`/ren:interview` captures only the **developer-identity** profile (18Q / 5 sections → `identity.md`). The
"you" is covered; **company / market / ICP / team / brain-dump are not.**

## Decision

The "you" stays in `identity.md`. The venture/studio layer lands as **separate pages** under **one new loose
page-type** — fully additive, so `identity.md` needs **no schema bump** (the cleanest reading of the greenlit
"separate pages" approach: identity fields don't change, so the friend-profile schema is untouched).

### 1. New page-type `venture-profile` (loose, like `research`/`pattern`)
Registered in `schemas.json` (`current: 1, supported_from: 1, migrations: []`, `owner_module: sf-onboarding`,
`path_pattern: wiki/venture/<section>.md`). Conformance `REQUIRED_FIELDS_BY_TYPE` requires the universal
triple + `section`. Frontmatter:
```yaml
type: venture-profile
schema_version: 1
framework_version: "<semver>"
section: company|market|icp|team|brain-dump
title / updated
```

### 2. Five venture pages under `wiki/venture/` (Ben's set minus "you")
`company.md` (what you're building + stage) · `market.md` (the space, why-now, alternatives) · `icp.md`
(ideal user/customer) · `team.md` (who's building — solo/collaborators/advisors) · `brain-dump.md`
(freeform: raw thoughts, open questions, goals/constraints). Ship as skeleton templates
`wiki-skeleton/templates/venture/*.md.tmpl` — conformance-scanned strict, and stamped (copy_if_missing) by
install Stage 5 via the manifest, exactly like `identity.md`.

### 3. Broadened interview — an OPTIONAL venture arc (Section F)
After the 5 identity sections, `/ren:interview` offers a **skippable** venture arc (~5 open questions, one
per page). Populates the `wiki/venture/*` pages in place (like it populates `identity.md`). **Explorer-safe:**
pre-idea friends skip it or leave `_TBD_` (the ingest-project honest-placeholder ethic) — no forced empty
startup profile. `references/question-template.md` gains Section F; `references/output-format.md` gains the
venture-page render rules; `SKILL.md` gains the broadened flow; `eval/eval.json` gains a venture test.

### 4. Hard constraints (lessons banked this session)
- **Placeholders:** venture templates use ONLY registered placeholders (`{{today}}`, `{{framework_version}}`)
  + quoted literals — no new `{{…}}` in frontmatter (the C2 unquoted-placeholder conformance break).
- **Lint-clean bodies:** zero `ADR-0`/founder-name/dev-lexicon substrings (the wiki-skeleton forbidden-substrings
  lint; the exact thing `routine-spec.md.tmpl` violated). Bodies are friendly placeholder prose, like `identity.md.tmpl`.
- **identity.md untouched** → no friend-profile migration; `venture-profile` is `current:1`, no migration.

## Build increments (each verified: conformance + wiki-skeleton lint + `plugin validate --strict`)
1. **Schema + templates** — register `venture-profile`; add the 5 lint-clean conformant `.md.tmpl`; manifest
   entries + `venture/` dir. → conformance scans the 5 templates green.
2. **Interview broadening** — Section F questions, venture output-format, SKILL.md flow, eval.json venture test.
3. **Wire-up** — ADR-022/014/027 amendments; CHANGELOG; roadmap H2 row → DONE; `wiki/log.md` milestone.

## Out of scope (named)
- Per-project venture context (the project-* taxonomy already owns that; this is the **master-level** init ritual).
- Mechanical migration of `identity.md` (none needed — additive). Dashboard/visualization (ADR-031, terminal-native).
