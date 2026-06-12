---
title: "ADR-032: Project Ingest — Brownfield Onboarding via /ren:ingest-project"
status: accepted
date: 2026-06-12
sunset-review: 2026-12-12
affects-components: [skills, onboarding, wiki, projects, install]
relates-to: [014-project-sub-wiki-taxonomy, 015-onboarding, 017-per-friend-wiki-scope, 027-schema-versioning, 031-solo-first-pivot, 033-renos-rebrand]
amends:
  - "ADR-015 (Onboarding): adds a brownfield path — onboarding is no longer additive/empty-only; existing projects can be ingested."
---

# ADR-032: Project Ingest — Brownfield Onboarding

## Context

Onboarding was additive, forward-only, and manual (ADR-015): `/ren:install`
stamps an empty master skeleton, the wake-up hook only sees a project if its
sub-wiki already exists, and `/ren:bootstrap-project` seeds empty placeholders.
A founder with N mature projects got an empty wiki + N manual empty bootstraps —
a real adoption gap. The framework neither ignored nor ingested prior work; it
simply didn't see it.

## Decision

Ship `/ren:ingest-project` — a user-invoked skill (`ingest-project`) that turns
an existing project into a first-class citizen with a **populated** ADR-014
sub-wiki, drafted from the repo's real README, stack, docs, and git history.

Key properties (load-bearing):

1. **Read-only on the project.** A Python scanner (`scripts/scan.py`) emits a
   facts JSON; it writes nothing into the project and never reads secret/oversized
   files. The skill writes only under `wiki/projects/<name>/` + 2 master lines.
2. **Extract → preview → one approval.** The LLM drafts every page, shows one
   preview, and writes only on approval — honoring ADR-027's no-silent-writes
   discipline (the backwards-compat clause in ADR-027 + ADR-017's historical
   "show diffs, require approval" principle).
3. **Additive / never overwrite.** Re-runs fill only missing pages (reuses the
   `template-loader.md` discipline; idempotent master registration).
4. **No invention.** Thin evidence → honest placeholder, never fabricated.
5. **Registration-only global footprint.** Master wiki gains one `index.md`
   line + one `log.md` line — same footprint as `bootstrap-project`. All
   extracted knowledge lives in the sub-wiki.

`bootstrap-project` (greenfield, empty stamp) and `ingest-project`
(brownfield, populated) are kept as separate single-responsibility skills.

## Reconciliation with ADR-031 ("wiki starts empty")

ADR-031 (the live principle, superseding ADR-017) still holds. "Wiki starts
empty" means the framework ships no framework-developer content into the user's
wiki. Ingest fills the **user's own project knowledge**, on explicit invocation
+ approval — it never injects our content. The principle is "your wiki, your
machine, your business"; ingest serves exactly that by importing *the user's*
prior work, not ours.

ADR-017 (historical origin, `status: superseded` by ADR-031) established the
same "framework ships skeleton, not content" principle; ADR-031 is the live
home of this guarantee.

## Scope (v1) and deliberate non-goals

In: single-project ingest, standard/light/deep depth, additive writes.
Out (filed as fast-follows): the wake-up discovery nudge (its own plan — must use
a cheap presence check in the hook hot path, NOT the scanner), bulk `~/Dev`
scan, and refresh-on-drift re-ingest.

## Consequences

**Easier:** founders adopt the framework without abandoning prior work; existing
projects become navigable wiki citizens; the gap ADR-015 left is closed.

**Harder:** the scanner must stay bounded + safe across arbitrary repos (caps +
never-read globs + read-only tests carry this); extraction quality varies with
how well-documented a repo is (mitigated by honest placeholders).

**Now impossible:** silently importing a project (always one approval); the
framework writing into a user's project directory (read-only by construction).

## Alternatives considered

- **Merge ingest into `bootstrap-project` as a `--from-existing` flag** — rejected:
  the plan is explicit that `bootstrap-project` must not be refactored. Ingest is a
  distinct responsibility (brownfield *read + draft* vs. greenfield *empty scaffold*);
  bundling the two would muddy both skills' contracts and evals for no gain. Two
  single-responsibility skills are clearer than one branching one.
- **Pure-LLM extraction (no Python scanner) — let the model read the project
  directly** — rejected: the bounded read-safety, never-read-secrets, and read-only
  invariants are load-bearing — they *are* the skill's honesty guarantee. Those
  guarantees require a deterministic, testable scanner with caps + never-read globs
  (carried by the read-only property tests), not free-form model file-reading that
  can't be asserted safe.
- **Auto-scan `~/Dev` on install / bulk-ingest every project** — rejected/deferred:
  out of v1 scope. Ingest stays user-invoked, single-project, and gated on one
  approval (ADR-027's no-silent-writes). Bulk ingest would mean autonomous writes
  across many repos at once; the wake-up discovery nudge + bulk scan are filed as
  fast-follows with their own plans.

## References

- `docs/superpowers/specs/2026-05-31-project-ingest-design.md` — full design
- `docs/superpowers/plans/2026-05-31-project-ingest.md` — implementation plan
- ADR-014 (taxonomy), ADR-015 (onboarding, amended), ADR-027 (schema versioning +
  no-silent-writes), ADR-031 (solo-first pivot, live "wiki starts empty" home),
  ADR-017 (historical origin, superseded by ADR-031), ADR-033 (RenOS rebrand,
  `/ren:ingest-project` namespace)
