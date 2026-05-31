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

Nothing yet.

---

## [1.0.0] — 2026-05-31

The first stable release — a **solo-first** framework organized under Nate Herk's **Four C's** (Context → Connections → Capabilities → Cadence): a per-builder hierarchical wiki, cache-preserving wake-up context injection, schema-versioned wiki pages, a deterministic session-consolidation loop, read-only insight + permission-audit surfaces, and a curated plugin stack.

The multi-user **Activity Feed was cut pre-ship** (ADR-031): the builder is solo, the feed was speculative complexity, and it was the source of four of seven pre-ship review findings. It is preserved in git history + the `baseline-v1.0-full-wiki` tag as a deferred layer — not rebuilt — so the framework ships with no cross-user channel. The remaining findings — **F1, F2, F5, F7** — are resolved in this release (F3/F4/F6 are moot without the feed).

### Added

**Context — wiki + wake-up**
- `lib/sf_paths.py` — the framework's path/handle/schema single source of truth (extracted so it outlives the cut feed; the **F1** fix). 3-tier `wiki_path()` resolves `SF_WIKI_ROOT` → `CLAUDE_PLUGIN_OPTION_WIKIROOT` → `framework_root()/wiki`, so the advertised `wikiRoot` plugin option is honored on its own.
- `/sf:wake-up` — SessionStart hook (ADR-008) composing the wake-up context (master wiki index + current project + last `/sf:wrap` pointer + recent master log). Pure, cache-preserving wiki injection.
- Per-builder hierarchical wiki + `wiki-skeleton/` templates (`identity.md`, master `index.md` + `log.md`, project sub-wiki taxonomy).

**Connections — distribution, updates, permissions**
- `sf-marketplace` private Claude Code marketplace (ADR-019): friends install via `/plugin marketplace add hazarsozer/sf-marketplace` + `/plugin install sf@sf-marketplace`. `sf-marketplace-rc` RC channel (opt-in via `userConfig.rcChannel`).
- `.claude-plugin/{marketplace,plugin}.json` manifests at the repo root (one-repo layout, `source: "./"`).
- `/sf:doctor` — environment + plugin + schema + framework-update + backup verification (ADR-025 + ADR-027).
- `/sf:doctor --permissions` — read-only permission audit ("keys on your ring"): MCP servers (name + transport + tool-key counts), `allow`/`deny`/`ask` tally, broad-grant flags, enabled plugins + hooks. Framing: **keys ≠ instructions**. Never prints secret/env/token values.
- `/sf:update` — opt-in framework upgrade with snapshot, migration chain, per-page verify, diff-review, post-update verification (ADR-019 + ADR-027). Flags: `--rc`, `--to <ver>`, `--dry-run`, `--auto`, `--restore-snapshot`. `gh` is a soft requirement, used by `/sf:doctor`'s update check.

**Capabilities — onboarding + the `/sf:*` skills**
- `/sf:install` — 7-stage onboarding: env check → required plugins → conditional plugins → identity bootstrap (`/sf:interview`) → wiki bootstrap → `/sf:doctor` verification → first-session walkthrough.
- `/sf:interview` — AI-driven identity-bootstrap interview (~17–18 questions across 5 sections); keeps a `handle:` field (a personal short-name).
- `/sf:bootstrap-project <name>` — instantiates a project sub-wiki from the per-builder skeleton.
- Companions: `/sf:note "..."` (pin for `/sf:wrap`), `/sf:recall "..."` (wiki query without page loads).
- `/sf:backup` (ADR-026) — git-remote primary + tarball fallback. Flags: `--setup <remote>`, `--tarball`, `--status`.
- **Schema-versioning machinery** (`skills/wiki-migration/`, ADR-027): `schemas.json` registers **15 page-types** (identity, master-index, project-index, licenses, project-main, project-state, project-roadmap, project-requirements, project-context, research, decision, pattern, log-entry, project-log-entry, skill); `schemas.schema.json` + `verify.schema.json` validators; `MIGRATION_PATTERN.md` + `migrations/_template/`; snapshot retention (latest 3, `userConfig.snapshotRetain`, at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/`); predicate vocabulary v1.

**Cadence — consolidation, improvement, insight**
- `/sf:wrap` — session-end consolidation: reads the session log + `/sf:note` pins, gates on a conservative **deterministic** signal classifier (the **F2** fix; EXPERIMENTAL, bike-method) that biases hard to `none`, never raises, lets pins dominate, and creates artifacts only for `decision`/`pattern`. **Wiki-only** (no cross-user write). The LLM classifier path ships as future-upgrade primitives.
- `/sf:improve-skill` — Karpathy auto-research loop with `eval.json` scoring + safety primitives. Its default path **fails fast honestly** with exit reason `requires_configured_backend` (EXPERIMENTAL) instead of crashing on an unconfigured eval backend (the other half of **F2**).
- `/sf:insights` — read-only skill that mines your local Claude Code session history (`~/.claude/projects/*.jsonl` + `~/.claude/session-data/*.tmp`) for what's working / what's slowing you down (`--days N`, `--project <name>`). No writes, no network.

**Curated stack** (ADR-006)
- Required: Superpowers (MIT), Skill Creator (Apache-2.0), claude-mem (Apache-2.0), Context Mode (ELv2), context7 (TBD permissive), claude-md-management (TBD permissive).
- Conditional: Frontend Design (asked at onboarding). Documented-not-bundled: Ralph.
- `LICENSES.md` explicitly surfaces Context Mode's ELv2 SaaS-distribution restriction.

**Documentation**
- `README.md` — friend-facing install + usage, framed around the Four C's.
- `docs/RECOVERY.md` — 8 disaster scenarios with concrete recovery steps (ADR-026 + ADR-027).
- `docs/RELEASING.md` — maintainer release process + RC pipeline + recovery from bad releases (ADR-019).
- `LICENSES.md` — stack license summary (ADR-015 Stage 6 + ADR-016).
- `wiki/decisions/031-solo-first-pivot.md` — ADR-031, the durable record of the solo-first pivot.

### Security
- `/sf:doctor --permissions` and `/sf:insights` are strictly read-only (no writes, no network) and **never print secret / env / token / header values** — verified by hermetic tests (a seeded fake token is asserted absent from output).
- `scripts/publish.sh` snapshots only tracked files via `git ls-files` and a guard that fails on `__pycache__` / `.pytest_cache` / `*.pyc` / `wiki/` (the **F5** fix), so caches and the private wiki never reach the published snapshot.
- License mix surfaced in `LICENSES.md`; friends explicitly informed of Context Mode's ELv2 SaaS restriction.

### Schema
- All **15 page-types** start at schema version 1, supported_from 1, no migrations. Future MINOR/MAJOR releases will add migrations here. (The `feed-entry` page-type was removed pre-ship with the Activity Feed — RETIRED, not migrated, per ADR-031 + ADR-027.)

[Unreleased]: https://github.com/hazarsozer/sf-marketplace/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/hazarsozer/sf-marketplace/releases/tag/v1.0.0
