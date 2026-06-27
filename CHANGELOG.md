# Changelog

All notable changes to RenOS are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + a `### Schema` section custom to this framework (consumed by `/ren:doctor` for schema-drift notifications, per ADR-027).

Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (`MAJOR.MINOR.PATCH`) per ADR-019. Note that Claude Code itself does NOT parse semver — the framework's own tooling (`scripts/version-compare.sh`) implements semver semantics including pre-release suffix ordering. Schema-change rules tied to bump kind:

- **PATCH** — bug fixes only. No schema, hook, or command changes.
- **MINOR** — additive only. New optional fields with defaults; new commands; new skills; new page-types. NO renames, NO removals.
- **MAJOR** — anything else. Migrations required. RC dogfood week per ADR-019.

Cadence: monthly stable. Out-of-cycle PATCH releases only for security or broken-hook fixes.

---

## [Unreleased]

RenOS is **pre-1.0 and not yet published** — everything below is staged for the first public release. Version `1.0.0` is reserved for when the product is actually done and shipped. The framework is **solo-first**, organized under Nate Herk's **Four C's** (Context → Connections → Capabilities → Cadence): a per-builder hierarchical wiki, cache-preserving wake-up context injection, schema-versioned wiki pages, a deterministic session-consolidation loop, read-only insight + permission-audit surfaces, and a curated plugin stack.

The multi-user **Activity Feed was cut pre-ship** (ADR-031): the builder is solo, the feed was speculative complexity, and it was the source of four of seven pre-ship review findings. It is preserved in git history + the `baseline-v1.0-full-wiki` tag as a deferred layer — not rebuilt — so the framework has no cross-user channel. The findings it raised — **F1, F2, F5, F7** — are resolved (F3/F4/F6 are moot without the feed).

### Added

- **C5c — dependency-map + auto-refresh:** `lib/codemap/deps.py` adds a stdlib-`ast` **module-level import dependency graph** (`{src: (deps,…)}`); resolves absolute + relative imports (incl. bare `from . import x`); never raises (unparseable / non-UTF-8 / missing / non-Python files produce no edges). `CodeMap.dependencies` field + `depends_on()` / `dependents_of()` queries; persisted in the cache sidecar (backward-compatible). `core.load_fresh()` auto-refreshes the cache when stale at consumption time (on-demand only — no daemon/wake-up injection, per ADR-008). `/ren:code-map --deps` renders the dependency graph (auto-refreshes); the digest gains a `## Dependencies` section. `skills/improve-skill/lib/impact.py` provides `dependency_footprint(target_files, dependencies)` → `ImpactReport` (target's dependents + dependencies) — read-only impact awareness for the self-improvement loop; stdlib-only (decoupled from `lib.codemap` to avoid a `lib` package-name collision). **Deferred:** symbol-level call-graph (function→function) — lean-ctx's graph DB is class-only with no usable edges (`lib/codemap/SPIKE_FINDINGS.md`); a true call-graph exceeds the adopted tooling. Module-import graph delivers the Pillar-5 dependency-map need. No new ADR, no page-type, no schema change. Tests: codemap 28, improve-skill 175+1skip; `claude plugin validate --strict` ✔.
- **H1 — `/ren:doctor` +CONTEXT & TOKEN ECONOMICS +WIKI HEALTH (7→9 sections):** two new read-only report sections: **CONTEXT & TOKEN ECONOMICS** (`check-context.sh`) counts MCP servers, enabled plugins, and framework skills; flags token-heavy `CLAUDE.md` files (>200 lines); lints skill-size (SKILL.md >500 lines or missing name/description/version frontmatter); warns when `permissions.defaultMode` is `bypassPermissions` or `acceptEdits`. **WIKI HEALTH** (`check-wiki-health.sh`) reports dead links (`[[wikilinks]]` + relative `.md` links), stale pages (frontmatter `updated:` >90 days), token-heavy pages (>500 lines), and an aggregate health score. Both scripts are strictly side-effect-free. +2 hermetic shell test files (context 12/12, wiki-health 8/8; full doctor suite 8/8); `eval.json` reconciled to nine sections; `claude plugin validate --strict` ✔. Scope cut (intentional, documented): stable-ID-rehydration flag + MCP-vs-CLI audit deferred (speculative static analysis); network-tier audits already covered by ROUTINES.
- **C5b — self-improvement loop completion:** the eval loop now scores real skills (skill-runs execute from the plugin-active worktree root); `--eval-runs N` measures true skill-run variance; unit-tested + reviewed. Still EXPERIMENTAL — the live supervised proof is deferred (needs ≥3 clean runs; ADR-036).
- **`/ren:improve-skill` eval backend wired (C5a, ADR-036):** the Karpathy loop now runs against a real LLM-judge backend — `run_evals()` scores binary assertions via the own judge path. The loop runs when `claude` + a credential are present; exits cleanly via `requires_configured_backend` (now meaning *backend unavailable*) when not. `--eval-runs N` flag added (default 1; majority-binarized scoring when N>1). **Autonomy is still earned:** `--autonomous` requires `--max-iterations` + `--max-budget-usd`; EXPERIMENTAL banner stays until ≥3 logged clean supervised runs (ADR-036).
- **`/ren:code-map` (C2, ADR-035):** code-map context layer — adopts the lean-ctx CLI (per-file `read -m signatures`) to generate a regenerable symbol→line-range digest; cache stored under plugin-data, never in the wiki or user's repo; staleness detection with STALE banner; load-on-demand only (never in wake-up injection per ADR-008). Ingest Stage 6 seeds the map when lean-ctx is available (graceful-degrade). ADR-035 filed; ADR-002/008 amended; `/ren:doctor` CODE-MAP check added.
- **Cadence-as-glue (C4, ADR-034):** `routine-spec` wiki page-type; `/ren:routine-init` (scaffolds a lean Cloud-Routine repo + writes the routine-spec page); `/ren:cadence` (decision-matrix router over /loop · Cron · /goal · Cloud Routines); `/ren:recall --routine` (reads a routine's state.md/run-log.md); `/ren:doctor` ROUTINES audits (network-tier + quota headroom); wake-up hook "Live automations" section.
- **`/ren:ingest-project` (C1, ADR-032):** brownfield onboarding — ingest an existing project into your wiki. A read-only scanner reads the repo (stack, docs, git history) and the skill drafts a populated ADR-014 sub-wiki, previews it once, and writes additively on approval. Never modifies the project's own files.

**Context — wiki + wake-up**
- `lib/sf_paths.py` — the framework's path/handle/schema single source of truth (extracted so it outlives the cut feed; the **F1** fix). 3-tier `wiki_path()` resolves `SF_WIKI_ROOT` → `CLAUDE_PLUGIN_OPTION_WIKIROOT` → `framework_root()/wiki`, so the advertised `wikiRoot` plugin option is honored on its own.
- `/ren:wake-up` — SessionStart hook (ADR-008) composing the wake-up context (master wiki index + current project + last `/ren:wrap` pointer + recent master log). Pure, cache-preserving wiki injection.
- Per-builder hierarchical wiki + `wiki-skeleton/` templates (`identity.md`, master `index.md` + `log.md`, project sub-wiki taxonomy).

**Connections — distribution, updates, permissions**
- `ren-os` private Claude Code marketplace (ADR-019): friends install via `/plugin marketplace add hazarsozer/ren-os` + `/plugin install ren@ren-os`. `ren-os-rc` RC channel (opt-in via `userConfig.rcChannel`).
- `.claude-plugin/{marketplace,plugin}.json` manifests at the repo root (one-repo layout, `source: "./"`).
- `/ren:doctor` — environment + plugin + schema + framework-update + backup verification (ADR-025 + ADR-027).
- `/ren:doctor --permissions` — read-only permission audit ("keys on your ring"): MCP servers (name + transport + tool-key counts), `allow`/`deny`/`ask` tally, broad-grant flags, enabled plugins + hooks. Framing: **keys ≠ instructions**. Never prints secret/env/token values.
- `/ren:update` — opt-in framework upgrade with snapshot, migration chain, per-page verify, diff-review, post-update verification (ADR-019 + ADR-027). Flags: `--rc`, `--to <ver>`, `--dry-run`, `--auto`, `--restore-snapshot`. `gh` is a soft requirement, used by `/ren:doctor`'s update check.

**Capabilities — onboarding + the `/ren:*` skills**
- `/ren:install` — 7-stage onboarding: env check → required plugins → conditional plugins → identity bootstrap (`/ren:interview`) → wiki bootstrap → `/ren:doctor` verification → first-session walkthrough.
- `/ren:interview` — AI-driven identity-bootstrap interview (~17–18 questions across 5 sections); keeps a `handle:` field (a personal short-name).
- `/ren:bootstrap-project <name>` — instantiates a project sub-wiki from the per-builder skeleton.
- Companions: `/ren:note "..."` (pin for `/ren:wrap`), `/ren:recall "..."` (wiki query without page loads).
- `/ren:backup` (ADR-026) — git-remote primary + tarball fallback. Flags: `--setup <remote>`, `--tarball`, `--status`.
- **Schema-versioning machinery** (`skills/wiki-migration/`, ADR-027): `schemas.json` registers **15 page-types** (identity, master-index, project-index, licenses, project-main, project-state, project-roadmap, project-requirements, project-context, research, decision, pattern, log-entry, project-log-entry, skill); `schemas.schema.json` + `verify.schema.json` validators; `MIGRATION_PATTERN.md` + `migrations/_template/`; snapshot retention (latest 3, `userConfig.snapshotRetain`, at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/`); predicate vocabulary v1.

**Cadence — consolidation, improvement, insight**
- `/ren:wrap` — session-end consolidation: reads the session log + `/ren:note` pins, gates on a conservative **deterministic** signal classifier (the **F2** fix; EXPERIMENTAL, bike-method) that biases hard to `none`, never raises, lets pins dominate, and creates artifacts only for `decision`/`pattern`. **Wiki-only** (no cross-user write). The LLM classifier path ships as future-upgrade primitives.
- `/ren:improve-skill` — Karpathy auto-research loop with `eval.json` scoring + safety primitives. Its default path **fails fast honestly** with exit reason `requires_configured_backend` (EXPERIMENTAL) instead of crashing on an unconfigured eval backend (the other half of **F2**).
- `/ren:insights` — read-only skill that mines your local Claude Code session history (`~/.claude/projects/*.jsonl` + `~/.claude/session-data/*.tmp`) for what's working / what's slowing you down (`--days N`, `--project <name>`). No writes, no network.

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

### Changed
- **Rebranded to RenOS** (from 仁 *rén*, humaneness) — command namespace `/sf:` → `/ren:`, plugin `name: sf → ren`, repo/marketplace `ren-os` (install `ren@ren-os`). Skill dirs unchanged. See ADR-033. No version bump — pre-first-republish, so `ren` / `/ren:` is the first public command surface anyone sees.
- **Foundation merged** — the v1.0 remediation Phases 1–4 (Python correctness, doc/contract drift, security/privacy, and the `/sf:` namespace-defect fix) landed on the dev branch (`9555a2d`); 454+ tests green, `claude plugin validate --strict` ✔.

### Security
- `/ren:doctor --permissions` and `/ren:insights` are strictly read-only (no writes, no network) and **never print secret / env / token / header values** — verified by hermetic tests (a seeded fake token is asserted absent from output).
- `scripts/publish.sh` snapshots only tracked files via `git ls-files` and a guard that fails on `__pycache__` / `.pytest_cache` / `*.pyc` / `wiki/` (the **F5** fix), so caches and the private wiki never reach the published snapshot.
- License mix surfaced in `LICENSES.md`; friends explicitly informed of Context Mode's ELv2 SaaS restriction.

### Schema
- All **15 page-types** start at schema version 1, supported_from 1, no migrations. Future MINOR/MAJOR releases will add migrations here. (The `feed-entry` page-type was removed pre-ship with the Activity Feed — RETIRED, not migrated, per ADR-031 + ADR-027.)
