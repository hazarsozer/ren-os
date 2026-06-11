---
title: "ADR-033: Rebrand to RenOS — Command Namespace `/sf:` → `/ren:`"
status: accepted
date: 2026-06-11
sunset-review: 2027-06-11
references-pages: [new-angles-for-the-os, nate-herk-ai-os]
affects-components: [slash-commands, manifest, distribution, docs, branding, ux]
relates-to: [013-slash-command-namespacing, 019-framework-distribution, 022-identity-interview-skill, 027-schema-versioning, 031-solo-first-pivot]
supersedes: "ADR-013 (the /sf: namespace decision)"
---

# ADR-033: Rebrand to RenOS — Command Namespace `/sf:` → `/ren:`

> Supersedes [ADR-013](013-slash-command-namespacing.md). Designed in
> `docs/superpowers/specs/2026-06-11-renos-rebrand-design.md` via `superpowers:brainstorming`.

## Context

The positioning pivot (2026-06-08, `wiki/research/new-angles-for-the-os.md`) reoriented the framework to
**a governable second-brain OS for Claude Code**. The product needed a real identity. The interim
`displayName "Startup Framework"` + namespace `sf` (the startup-framework initials, set by ADR-013) was a
placeholder. The namespace-defect fix (merged `9555a2d`) made `/sf:` actually register — but was **never
re-published**, so no public surface has shipped `sf` yet. That makes this the ideal, no-churn moment to
land the real name before the first publish.

## Decision

**The product is RenOS. The command namespace is `ren` (`/ren:wrap`, `/ren:doctor`, …). The repo +
marketplace id is `ren-os`; install is `/plugin install ren@ren-os`.**

- **Name:** **RenOS**, from **仁 (rén)** — the Confucian virtue of *humaneness* / the irreducible human
  core. It encodes the thesis: the OS is the engine over Claude Code's native muscle; **Ren (仁) is the
  human brain the user brings.** *Ship the engine — you bring the 仁.*
- **Trio:** `RenOS` (displayName) / `ren` (plugin `name` = namespace) / `ren-os` (repo + marketplace).
- **Skill dirs unchanged** — the command verb is the dir name (`skills/wrap`); only the namespace prefix
  (plugin `name`) changes. No `git mv` of skill dirs.
- **Flip vs freeze:** `/sf:`→`/ren:` and the `sf`-derived literals (data-dir `sf-sf-marketplace`→
  `ren-ren-os`, install-id `sf@sf-marketplace`→`ren@ren-os`, repo URL) flip on the **shipped surface +
  live runbooks** (skills, wiki-skeleton, hooks, lib, tests, README, manifests, RECOVERY/RELEASING/
  SHIP_CHECKLIST). **Frozen history stays factual:** `wiki/` (ADRs incl. this record, log, research),
  `docs/superpowers/` (dated specs/plans/report), dated release/review docs. A blanket replace would
  falsify the trail.
- **User-data root unchanged:** `~/.startup-framework/` (ADR-017/027) is a *separate* breaking change and
  stays; renaming it is explicitly **out of scope** (reversible later; no users yet, but avoid scope creep).
- **Timing:** done before the first re-publish (roadmap F1 Phase 5), so `ren` / RenOS is the only public
  command surface any user ever encounters.

## Consequences

- **Easier:** a coherent brand; `/ren:` stays short + typeable; the name *is* the pitch.
- **Now superseded:** ADR-013's `/sf:` decision — its body is preserved as historical record (not edited
  beyond the status header).
- **Follow-up (outward, maintainer):** rename the GitHub repo `sf-marketplace`→`ren-os` (GitHub sets up
  redirects); Phase 5 re-publish then ships RenOS. An installed pre-publish copy still shows the old
  surface until republished — verify `/ren` autocomplete after.

## Alternatives considered

- **Keep `sf`, rebrand only the product** — rejected: a product named "RenOS" whose commands are `/sf:`
  is incoherent (`sf` = the abandoned "startup-framework").
- **Rename the user-data root to `~/.renos/` now** — deferred: a separate breaking change (ADR-017),
  reversible later, out of scope for this rebrand.
- **`renos` vs `ren` as the namespace** — chose `ren` (shorter prefix); the `displayName` carries the
  full "RenOS".

## References

- `docs/superpowers/specs/2026-06-11-renos-rebrand-design.md` — design + flip/freeze rule + availability check
- [ADR-013](013-slash-command-namespacing.md) (superseded) — the original `/sf:` namespace decision
- `wiki/research/new-angles-for-the-os.md` — the positioning pivot that motivated the identity
