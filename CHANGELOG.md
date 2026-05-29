# Changelog

All notable changes to the Startup Framework are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + a `### Schema` section custom to this framework (consumed by `/sf:doctor` for schema-drift notifications, per ADR-027).

Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (`MAJOR.MINOR.PATCH`) per ADR-019. Note that Claude Code itself does NOT parse semver — the framework's own tooling (`scripts/version-compare.sh`) implements semver semantics including pre-release suffix ordering. Schema-change rules tied to bump kind:

- **PATCH** — bug fixes only. No schema, hook, or command changes.
- **MINOR** — additive only. New optional fields with defaults; new commands; new skills; new page-types. NO renames, NO removals.
- **MAJOR** — anything else. Migrations required. RC dogfood week per ADR-019.

Cadence: monthly stable. Out-of-cycle PATCH releases only for security or broken-hook fixes.

---

## [Unreleased]

(work in progress on `main`; promoted to a versioned section on release)

---

## [1.0.0] — 2026-05-29

The first stable release. Establishes the friend-group distribution surface, the per-friend hierarchical wiki, the Activity Feed cross-friend visibility layer, schema-versioned wiki pages, and the curated plugin stack.

### Added

**Distribution + updates**
- `sf-marketplace` private Claude Code marketplace (per ADR-019). Friends install via `/plugin marketplace add hazarsozer/sf-marketplace` + `/plugin install startup-framework@sf-marketplace`.
- `sf-marketplace-rc` separate marketplace for release-candidate dogfooding (optional channel; opt-in via `userConfig.rcChannel = true`).
- `.claude-plugin/marketplace.json` + `.claude-plugin/plugin.json` manifests (both at the repo root, Crucible one-repo layout — `source: "./"`) conforming to the CC plugin marketplace schema (version-resolution via `plugin.json#version`, per CC docs).
- `/sf:doctor` — environment + plugin + schema + framework-update + backup verification (per ADR-025 + ADR-027).
- `/sf:update` — opt-in framework upgrade with snapshot, migration chain, per-page verify, diff-review, applying, post-update verification (per ADR-019 + ADR-027). Flags: `--rc`, `--to <ver>`, `--dry-run`, `--auto`, `--restore-snapshot`.

**Schema-versioning machinery**
- `skills/wiki-migration/` module (per ADR-027). `schemas.json` registers 12 page-types (identity, project-main, project-state, project-roadmap, project-requirements, project-context, research, decision, pattern, log-entry, feed-entry, skill).
- `schemas.schema.json` + `verify.schema.json` validators (enforced by CI).
- `MIGRATION_PATTERN.md` contributor guide + `migrations/_template/` scaffold.
- Snapshot retention: latest 3 (configurable via `userConfig.snapshotRetain`), stored at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/` (CC-blessed persistent location; overrides ADR-027's original `~/.startup-framework/wiki-snapshots/` suggestion — see amendment in ADR-027).
- Predicate vocabulary v1: `yaml.valid`, `yaml.equals`, `yaml.in`, `yaml.absent`, `yaml.present`, `regex.matches`, `snapshot.value-preserved`, `snapshot.body-identical`, `file.exists`.

**Onboarding (sf-onboarding)**
- `/sf:install` — 7-stage flow: env check → required plugins → Activity Feed setup + conditional plugins → identity bootstrap (`/sf:interview`) → wiki bootstrap → `/sf:doctor` verification → first-session walkthrough.
- `/sf:interview` — AI-driven identity-bootstrap interview (~17–18 questions across 5 sections).
- `/sf:bootstrap-project <name>` — instantiates a project sub-wiki from the per-friend skeleton.
- `wiki-skeleton/` templates for `identity.md`, master `index.md` + `log.md`, project sub-wiki taxonomy.

**Daily loop (sf-lifecycle)**
- `/sf:wake-up` — SessionStart hook that composes the wake-up context (master wiki index + current project + last `/sf:wrap` session pointer + recent friend activity + recent master log).
- `/sf:wrap` — session-end consolidation. Reads session log + `/sf:note` pins; high-signal threshold gating; wiki diffs shown for approval; Activity Feed terse-entry write.
- `/sf:improve-skill` — Karpathy auto-research loop with eval.json scoring + four safety primitives.
- Companions: `/sf:note "..."` (pin for `/sf:wrap`), `/sf:recall "..."` (wiki query without page loads).
- `/sf:backup` (per ADR-026) — git-remote primary + tarball fallback. Flags: `--setup <remote>`, `--tarball`, `--status`.

**Cross-friend visibility (sf-feed)**
- Activity Feed module — shared private GitHub repo with per-friend `<handle>.log.md` files. Terse format constraint as primary privacy mechanism (per ADR-021).
- `/sf:catch-up <project>` — summarises recent cross-friend activity for a project from the feed.
- `/sf:disable-feed` — per-session opt-out (also: `SF_SKIP_FEED=1` env var, `/sf:wrap --skip-feed` per-invocation).

**Curated stack** (per ADR-006)
- Required: Superpowers (MIT), Skill Creator (Apache-2.0), claude-mem (Apache-2.0), Context Mode (ELv2), context7 (TBD permissive), claude-md-management (TBD permissive).
- Conditional: Frontend Design (asked at onboarding).
- Documented-not-bundled: Ralph.
- License surface: `LICENSES.md` explicitly surfaces Context Mode's ELv2 SaaS-distribution restriction.

**Documentation**
- `README.md` friend-facing install + usage.
- `docs/RECOVERY.md` — 8 disaster scenarios with concrete recovery steps (per ADR-026 + ADR-027).
- `docs/RELEASING.md` — maintainer release process + RC pipeline + recovery from bad releases (per ADR-019).
- `LICENSES.md` — stack license summary (per ADR-015 Stage 6 + ADR-016).

### Changed
- Nothing — first release.

### Deprecated
- Nothing — first release.

### Removed
- Nothing — first release.

### Fixed
- Nothing — first release.

### Security
- Activity Feed entries enforce terse format (per ADR-021) preventing most accidental secret leakage.
- License mix surfaced in `LICENSES.md`; friends explicitly informed Context Mode's ELv2 restricts SaaS use.

### Schema
- All 12 page-types start at schema version 1, supported_from 1, no migrations. Future MINOR/MAJOR releases will add migrations here.

[Unreleased]: https://github.com/hazarsozer/sf-marketplace/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/hazarsozer/sf-marketplace/releases/tag/v1.0.0
