# Design: `sf-ingest-project` — Brownfield Project Ingest

**Date:** 2026-05-31
**Status:** Approved (brainstorming complete; ready for implementation plan)
**Author:** Hazar (with Claude)
**Branch:** `feat/project-ingest`
**Related ADRs:** amends ADR-015 (onboarding), reconciles with ADR-017 (per-friend wiki scope / "wiki starts empty"), builds on ADR-014 (project sub-wiki taxonomy), ADR-013 (slash-command namespacing), ADR-027 (schema versioning), ADR-031 (solo-first pivot). New ADR-032 to be filed during implementation.

---

## 1. Problem

The framework's onboarding is **additive, forward-only, and manual**. A founder who already has mature projects in `~/Dev/` gets:

- `/sf:install` Stage 5 stamps only an **empty** master skeleton — it never scans real projects.
- The wake-up hook's `detect_project()` returns a project **only if `wiki/projects/<X>/` already exists** — so opening an un-bootstrapped project dir surfaces nothing and offers no nudge.
- `/sf:bootstrap-project <name>` is **manual + per-project** and seeds **empty placeholders** — no importer reads README, ADRs, git history, or existing docs.

**Net:** non-destructive (their code is never touched), but the wiki starts empty with zero backfill. A founder with N mature projects gets an empty wiki + N manual, empty bootstraps. This is a real adoption gap.

## 2. Goal

A user-invoked skill that turns an **existing** project directory into a first-class framework citizen — on par with a freshly bootstrapped project, but with its pages **populated from what's actually in the repo**. The user goes into an old project, invokes one skill, and gets a populated ADR-014 sub-wiki plus master-wiki registration.

### Success criteria

1. Running `/sf:ingest-project` in an existing project produces a complete ADR-014 sub-wiki whose pages reflect the real project (purpose, stack, state, timeline) — not empty placeholders.
2. The user's project files are **never modified** (read-only on the project).
3. Nothing is written without **one explicit approval** (honors ADR-017 "no silent writes").
4. Re-running is **idempotent** — additive-only, never overwrites existing sub-wiki pages.
5. Low-evidence pages get **honest placeholders**, never invented content.

## 3. Non-goals (v1)

- **Wake-up discovery nudge** (`detect_project()` → "this project isn't in your wiki; run `/sf:ingest-project`"). Natural follow-on; flagged, not built.
- **Bulk scan** of all `~/Dev` projects (`--scan` to list + multi-select). Follow-on.
- **Re-ingest / refresh-on-drift** (detecting the project changed since last ingest and updating STATE/log). Follow-on; v1 re-run is additive-fill only.
- **Global pattern extraction** into master `patterns/` and **identity enrichment**. Deliberately excluded — see §6 (Registration-only footprint).
- **Writing into the user's project dir** (e.g. dropping a `.sf-project` marker). Read-only on the project, always.

## 4. Key decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| **Skill shape** | Separate new skill `sf-ingest-project` | Keeps `sf-bootstrap-project` as the fast greenfield stamp; ingest owns the heavier brownfield extraction. Single responsibility each. |
| **Write posture** | Extract → preview → **one** approval | Honors ADR-017 "no silent writes" without per-file nagging. AI does the drafting; user approves once. |
| **Extraction depth (default)** | Standard: docs + tree + code skim + git log | Fills PROJECT/STATE/CONTEXT well; ROADMAP/REQUIREMENTS lightly. Bounded cost. `--depth light|deep` available. |
| **Global footprint** | Registration only | Master wiki gets just the project registration (1 index line + 1 log line), same as bootstrap. All extracted knowledge lives in the sub-wiki. Keeps the global layer clean and per-project-isolated. |
| **Engine** | B: read-only Python scanner + LLM interpretation | Mechanical, unit-testable scanner core (matches `sf-insights`/`sf-wrap`); LLM interprets bounded facts, not a raw repo dump; write step reuses the tested template-loader. |

## 5. Architecture

`/sf:ingest-project [path] [--depth standard|light|deep] [--name <kebab>]` — default path = cwd.

A 4-stage pipeline:

```
1. SCAN  (read-only Python: scripts/scan.py)
   → emits a structured facts JSON on stdout (the stable scanner↔LLM interface)
   → touches NOTHING in the project; writes NOTHING

2. INTERPRET  (LLM, main thread; optional subagent code-skim for big repos)
   → consumes facts JSON; drafts all 7 ADR-014 pages in memory
   → maps git history → backfilled log.md timeline
   → per-page confidence; thin evidence → labeled placeholder, never invents

3. PREVIEW  (one gate)
   → prints a manifest: target sub-wiki path, every page w/ ~line count + confidence,
     the 2 master-wiki additions, and a short content sample
   → asks ONE approval. User can approve / edit / abort.

4. WRITE  (additive-only; reuses the template-loader's write *discipline*)
   → writes wiki/projects/<name>/** from the LLM drafts, additive-only
   → appends the 2 master-wiki registration lines
   → appends an init entry to the project log.md
```

**Why this shape:** the scanner is mechanical and unit-testable; the LLM only interprets bounded facts; the write step reuses the *existing, tested* additive-write discipline instead of forking write logic; the single gate satisfies ADR-017.

**Reuses (not rebuilt):**
- `lib/sf_paths.py` — `wiki_path()`, `handle()`, `framework_version()`.
- `skills/sf-bootstrap-project/references/template-loader.md` — its **write discipline**: `copy_if_missing` semantics, additive-diff detection for an existing sub-wiki, and the master-`index.md`/`log.md` append pattern. **Note:** the loader's normal flow copies *static templates* with placeholder substitution; ingest's page source is **LLM-drafted full content**, so the placeholder-substitution step is bypassed (pages arrive already complete). The plan decides the exact mechanism (e.g. drafts staged to a temp dir then run through the loader with no bindings, vs. a thin shared additive-write helper) — but ingest MUST NOT route drafted content through placeholder substitution, and MUST NOT fork the additive/no-overwrite logic.
- ADR-014 taxonomy page set (PROJECT / REQUIREMENTS / ROADMAP / STATE / CONTEXT / index / log + research/decisions/patterns dirs).

**Hard boundaries:**
- **Read-only on the user's project** — the scanner never writes into the project dir; the skill only ever writes under `wiki/projects/<name>/` + the 2 master lines.
- **Idempotent / never overwrites** — if `wiki/projects/<name>/` exists, drop to the template-loader's additive-diff mode (fill only missing pages).
- **No invention** — low-confidence pages get an honest placeholder (`_TBD — scanner found no <X>; fill in._`), mirroring the framework's honesty stance (cf. the F2b honest `sf-improve`).

## 6. The facts contract (`scripts/scan.py` → JSON)

The stable interface between the mechanical scanner and the LLM interpreter:

```jsonc
{
  "schema_version": 1, "scanned_path": "...", "looks_like_project": true,
  "name_candidates": { "dir": "myapp", "manifest": "my-app", "chosen": "my-app" },
  "stack":   { "languages":[{"name":"Python","evidence":"pyproject.toml","confidence":"high"}],
               "package_managers":["uv"], "frameworks":["fastapi"], "manifests":[...] },
  "tree_digest":  { "depth_cap":4, "entry_count":312, "truncated":false, "top_dirs":[...], "notable_files":[...] },
  "entry_points": ["src/main.py"],
  "doc_inventory":[{"path":"README.md","kind":"readme","bytes":4210},{"path":"docs/adr/0001.md","kind":"adr"}],
  "git": { "is_repo":true, "first_commit":"2025-01-03", "last_commit":"2026-05-20", "commit_count":487,
           "tags":[{"name":"v1.0","date":"..."}], "timeline":[{"period":"2025-01","count":40,"notable":[...]}],
           "recent":[{"date":"2026-05-20","subject":"..."}], "branch":"main", "dirty":false },
  "size_signals": { "file_count":312, "loc_estimate":18400, "recommend_subagents":false },
  "warnings": ["no README.md found"]
}
```

## 7. Facts → ADR-014 page mapping (the LLM's job)

Thin evidence → honest placeholder, never invented.

| Page | Drawn from |
|---|---|
| `PROJECT.md` | name, stack, README purpose/users, doc links |
| `REQUIREMENTS.md` | README features + code skim (often light → placeholder) |
| `ROADMAP.md` | git **tags** as milestones + any ROADMAP/TODO docs; "we are here" = branch/recent |
| `STATE.md` | git **recent** (active work), branch, dirty flag |
| `CONTEXT.md` | latest commit cluster / WIP / branch name |
| `index.md` | catalog of written pages |
| `log.md` | git **timeline** clustered into terse one-line entries (capped ~20) + init entry |

**Global footprint (registration only):** master `wiki/index.md` gets one line under `## Projects`; master `wiki/log.md` gets one init line. Identical footprint to `sf-bootstrap-project`. No master `patterns/` writes, no `identity.md` edits.

## 8. Read-safety & bounds (load-bearing per the privacy stance)

- **Skip dirs:** `.git, node_modules, .venv, venv, __pycache__, dist, build, target, vendor, .next, coverage, .idea, .pytest_cache`.
- **Never read:** `.env*, *.pem, *.key, id_rsa, credentials*, *.sqlite`, anything `.gitignore`d (best-effort), files > 256 KB.
- **Secret hygiene:** scanner emits *facts*, not raw file dumps; the LLM is instructed not to copy secret-looking strings into pages; an eval asserts `.env` content never reaches the facts JSON or any page.
- **Caps:** tree depth ≤ 4 / ≤ 500 entries · git summarized (`--since` ~2y) · code skim ≤ 20 files × ≤ 200 lines.

## 9. Edge cases & refusals

- **Wiki not installed** → refuse → recommend `/sf:install`.
- **Path missing / not a dir** → refuse with a clear message.
- **`looks_like_project: false`** → warn + confirm ("doesn't look like a project — ingest anyway?").
- **Sub-wiki already exists** → template-loader **additive-diff** (fill only missing pages, never overwrite).
- **Not a git repo** → proceed; `log.md` gets the init entry only; timeline skipped + noted in a warning.
- **Ingesting the framework's own dev repo** → soft warn (avoid self-ingest confusion).
- **Polyglot repo** → list all detected stacks.
- **Huge repo** (`recommend_subagents: true`) → fan out code-skim subagents, or suggest `--depth light`.
- **Invalid `--name`** (not kebab-case `^[a-z][a-z0-9-]*$`) → re-prompt (same contract as bootstrap).
- **No `handle` configured** (identity.md missing) → fall back to `handle = "unknown"` with a warning suggesting `/sf:interview` (same fallback as bootstrap).

## 10. Testing

Per-module: `( cd skills/sf-ingest-project && python3 -m pytest tests/ -q )` (root pytest collides on duplicate `lib.tests.*` — pre-existing; do not "fix").

- **Scanner unit tests** vs fixture repos: python / js / polyglot / no-git / empty / tagged.
- **Read-only property:** hash the project tree before+after a scan → byte-identical.
- **Idempotency:** 2nd run → additive-diff, zero overwrites.
- **No-invention:** low-evidence fixture → output has placeholder markers, not fabricated features.
- **Secret-skip:** fixture `.env` with `FAKE_SECRET` → assert it never appears anywhere in facts or pages.
- **`eval/eval.json`** binary assertions (matches sibling skills): 7 pages present · 2 registration lines · additive on re-run · project dir unchanged · `schema_version` stamped.

## 11. Framework integration

- **Location:** `skills/sf-ingest-project/`
  - `SKILL.md` (with a `contract:` block like `sf-bootstrap-project`)
  - `scripts/scan.py`
  - `references/{extraction-spec,page-mapping}.md`
  - `eval/eval.json` + `eval/fixtures/`
  - `tests/`
- **Command:** `/sf:ingest-project` (ADR-013 namespacing).
- **Manifests:** register the new skill + command in the plugin manifest and the marketplace manifest.
- **ADR-032 (project ingest):** amends ADR-015 (onboarding gains a brownfield path); reconciles with ADR-017 — "wiki starts empty" still holds, because ingest fills the **user's own project knowledge** on explicit invocation + approval; it never injects framework content.

## 12. Open items for the implementation plan

- Exact stack-detection rules table (manifest → language/PM/framework mapping) lives in `references/extraction-spec.md`.
- Exact git-timeline clustering algorithm (monthly buckets vs. tag-anchored) — decide in plan; default monthly with tag annotations.
- Whether `--depth deep` ingests existing ADRs/design docs into `decisions/` + `research/` as copies or as summaries — default summaries (avoid duplicating large files into the wiki).
- Subagent fan-out threshold tuning (`recommend_subagents` heuristic) — start at file_count > 800 or loc_estimate > 50k.
