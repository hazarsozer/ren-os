# C2 — Code-Map Context Layer — Design Spec

> **Status:** Approved design (2026-06-17). Brainstormed via `superpowers:brainstorming`; four
> foundational decisions locked with the maintainer (see §2). This spec is the input to a
> `superpowers:writing-plans` pass and the contract for the subsequent `subagent-driven-development`
> build (the C1/C4 recipe).
>
> **Roadmap slice:** C2 (Pillar 6) in `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`.
> **Input spec (why/what):** `docs/superpowers/specs/2026-06-08-nate-herk-ingest-positioning-design.md` §6.
> **Builds on:** C1 (`ingest-project`, ADR-032) — shares the read-only-project discipline, not the scanner.

---

## 1. Purpose

A regenerable **symbol → file:line-range** markdown digest (a "code-map") so the agent reads a compact
index and pulls only the line ranges it needs, instead of reading whole files. Token economy — the
spec's "context gets worse hierarchically" concern. Built as a **standing capability** the builder
refreshes on demand; designed so C5 (self-improvement) can later extend it into the dependency-map.

The discipline that makes it safe: **a digest that lies about line numbers is worse than none** — so
staleness is detected and surfaced, never silently trusted.

---

## 2. Locked scope decisions (maintainer, 2026-06-17)

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| 1 | **Shape** | **Standing map + manual refresh.** Reusable module + `/ren:code-map` generate/refresh + staleness flag + trust-but-verify read discipline + load-on-demand. | Auto/cadence-driven refresh is **deferred to C5**. No daemon (ADR-003). |
| 2 | **Engine** | **Adopt lean-ctx as a version-pinned CLI** (its `map`/`signatures`/`lines:N-M` modes; tree-sitter across 21 languages; Apache-2.0/MIT). **Not** its MCP server, **not** `lean-ctx serve`. | New external-binary dependency → install path + `/ren:doctor` check + graceful-degrade. Amends ADR-002. |
| 3 | **Storage** | **Regenerable cache under `${CLAUDE_PLUGIN_DATA}`** (the existing `wiki-snapshots/` convention), **not** in the version-controlled wiki. | No git-churn from line-number changes; not backed up (regenerable); never in the wake-up injection (ADR-008). |
| 4 | **Nav-maps** | **Defer** the per-subfolder wiki-navigation `CLAUDE.md` maps (Pillar 6's secondary bullet) to a later wiki-structure slice. | Keeps C2 one subsystem; honors the roadmap's one-plan-per-subsystem rule. |

---

## 3. Architecture

### 3.1 `scan.py` is NOT modified (refinement of decision 1's wording)

`scan.py` (C1's ingest scanner) holds three invariants: **writes nothing** (emits facts JSON to stdout),
**stdlib-only**, **one-shot**. A standing, lean-ctx-backed, cache-writing code-map violates all three.
So the code-map is a **separate capability**, and the reusable extraction logic lives in the shared
top-level `lib/` (alongside `sf_paths.py`) — exactly where cross-skill code belongs.

> The roadmap's phrase "built into C1's `scan.py`" predates C1 shipping. We honor its *intent* (the
> code-map shares the ingest project-reading lineage and seeds at ingest time) without coupling the
> pure scanner to a standing-cache concern.

### 3.2 Units

| Unit | Path | Responsibility | Depends on |
|------|------|----------------|------------|
| `codemap` package | `lib/codemap/` | Engine-agnostic core: `generate(project_root) -> CodeMap`, `is_stale(map, project_root) -> StaleReport`, `render_digest(map) -> str`. Split into small focused files (adapter / digest / staleness) per the <800-line rule. | lean-ctx adapter, `lib.sf_paths` |
| lean-ctx adapter | `lib/codemap/adapter_leanctx.py` | Shell the pinned `lean-ctx` CLI → normalized `Symbol{name, kind, file, start_line, end_line, signature}`; the only lean-ctx-aware unit. | `lean-ctx` binary |
| `/ren:code-map` skill | `skills/code-map/` (`SKILL.md` + `scripts/` entrypoint + `eval/` + `learnings.md`) | Orchestration: generate / `--refresh` / staleness report / hand-off. Imports `lib.codemap` via the same `sys.path` + `from lib.codemap` convention `scan.py` uses for `lib.sf_paths`. | `lib.codemap` |
| ingest seeding | `skills/ingest-project/SKILL.md` Stage 6 | After ingest, **runs** code-map seeding when lean-ctx is available; graceful-degrade to a one-line install+run suggestion when absent. Additive to Stage 6's existing hand-off; adds no write gate (the cache is outside both wiki and project). Does **not** touch `scan.py`. | `/ren:code-map` |
| doctor check | `skills/doctor/scripts/check-code-map.sh` | `lean-ctx` present? version? → a "CODE-MAP" line/section. Mirrors C4's `check-routines.sh`. | — |

The **engine sits behind the adapter interface**, so a different engine can be substituted without
touching `lib/codemap`'s core or the skill.

---

## 4. The lean-ctx adapter — Phase-0 spike + escape hatch

lean-ctx is **not installed** here and was only a *research candidate* (ADR-002 "Option E"), so its
**headless CLI surface is unverified** (the research page emphasizes its 62 *MCP* tools). The
implementation plan therefore **opens with a validation spike** that must confirm, against the real
binary:

1. lean-ctx can emit a **project-wide symbol map via CLI** (not only via MCP), parseable into the
   `Symbol` shape above (name, kind, file, start/end line, signature).
2. Generation **writes nothing into the scanned project** — no `.lean-ctx/` (or similar) index dropped
   in the repo. If lean-ctx insists on a cache, it must be redirectable to `${CLAUDE_PLUGIN_DATA}`.

**If the spike fails on either count, STOP and return to the maintainer with the finding.**
universal-ctags is the documented escape-hatch engine (same adapter interface, symbol→start-line
granularity). **Do not silently switch engines.**

---

## 5. Storage & data flow

- **New `sf_paths` helper** (e.g. `code_map_cache_dir()`) resolving `CLAUDE_PLUGIN_DATA` with the same
  fallback the shell scripts already use: `${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/ren-ren-os}`.
  Path: `<plugin-data>/code-maps/<handle>/<project>.md` (handle via `sf_paths.handle()`).
- **Not** under the wiki (`wiki_path()`), **not** under `framework_root()/cache` — consistent with
  where `wiki-snapshots/` already live.
- **Generation flow:** `/ren:code-map [path] [--refresh]` → adapter runs lean-ctx on the project →
  normalize to `Symbol[]` → `render_digest` writes the markdown map (header below) → print a summary
  + the cache path.
- **Digest format (markdown):** a header block + per-file sections listing each symbol with kind,
  `Lstart–Lend`, and signature. Header records: source project path, generation timestamp, the git
  commit the map was built at (if a repo), and **per-file content hashes** (for staleness).

---

## 6. Staleness + trust-but-verify

- **Detection:** `is_stale()` recomputes per-file content hashes and compares to the header; any drift
  (or new/deleted files) → a `StaleReport` naming the changed files.
- **Surfacing:** a stale map opens with a banner —
  `⚠ STALE — N files changed since <commit/timestamp>; regenerate with /ren:code-map --refresh` — so
  it is **never silently trusted**. `/ren:doctor` also reports staleness for the current project.
- **Refresh:** manual `/ren:code-map --refresh` regenerates. (Auto/git-hook/cadence refresh → C5.)
- **Read discipline (documented in `SKILL.md` + the digest header):** treat a cited line range as a
  *hint*; verify the symbol is actually there before relying on it. The map accelerates navigation; it
  is not authority.

---

## 7. Two load-bearing invariants

1. **Read-only on the user's project** (inherited from C1/ADR-032). Code-map generation must leave the
   scanned project **byte-identical** — the lean-ctx adapter redirects any tool cache to
   `${CLAUDE_PLUGIN_DATA}`. A **property test asserts byte-identity** of the project before/after.
2. **Load-on-demand, never in wake-up** (ADR-008 amendment). The code-map is read only when the agent
   explicitly needs to navigate code — never part of the 3–5K SessionStart injection. A single
   *pointer* line in the project wiki (e.g. CONTEXT.md: "Code-map: run `/ren:code-map`") is permitted;
   the map *content* is not injected.

---

## 8. ADRs

- **New — ADR-035: Code-Map Context Layer.** Records: engine = lean-ctx CLI (with the `serve`/MCP
  exclusion and the CLI-over-MCP rationale — 60–70% fewer tokens, per
  `wiki/research/nate-herk-economics-and-permissions.md`); storage = `${CLAUDE_PLUGIN_DATA}` cache;
  staleness + trust-but-verify discipline; load-on-demand; the `scan.py`-untouched architecture;
  ctags as the named alternative. Mirrors ADR-032 (C1) / ADR-034 (C4). Must include "Alternatives
  considered" (ctags, tree-sitter-pip, stdlib-ast — the rejected map-engine options).
- **Amend ADR-002 (Token-Efficiency Stack).** Adopt lean-ctx **narrowly** — its AST/code-map capability
  only — explicitly distinct from the still-open question of replacing claude-mem for memory (that
  remains ADR-002's existing sunset trigger). Record the new burden: a Rust binary in the install path,
  commitment to lean-ctx's CLI surface, and a young/fast-moving project → **version pin + a sunset
  trigger** ("lean-ctx unmaintained or CLI breaks → revert to ctags").
- **Amend ADR-008 (Wake-Up Hook).** The code-map is load-on-demand from `${CLAUDE_PLUGIN_DATA}`, never
  in the wake-up injection; a one-line wiki pointer is allowed.
- **No `schemas.json` change.** The code-map is a cache file, **not** a wiki page-type — so, like C1, the
  schema-conformance gate is untouched.

---

## 9. Scope boundaries

**In scope (this slice):**
- `lib/codemap/` (engine-agnostic core + lean-ctx adapter + digest + staleness), with `lib/codemap/tests/`.
- `skills/code-map/` → `/ren:code-map` (generate / `--refresh` / staleness report) + `eval/eval.json` + fixtures + `learnings.md`.
- New `sf_paths` cache-dir helper.
- `skills/doctor/scripts/check-code-map.sh` + doctor wiring (lean-ctx availability/version).
- Ingest Stage-6 seeding hand-off (graceful-degrade).
- ADR-035 + ADR-002/ADR-008 amendments.
- Wire-up: README, CHANGELOG, `wiki/index.md`, `wiki/log.md`, roadmap C2 row → DONE.

**Out of scope (deferred, named):**
- **Auto / git-hook / cadence-driven refresh** → C5.
- **Dependency / reference / call graph** ("which artifact references which code") → C5. C2 emits
  symbol→location now and keeps the `Symbol`/digest format **extensible** to references, but does **not**
  build the call-graph speculatively (YAGNI).
- **Per-subfolder wiki-navigation `CLAUDE.md` maps** → later wiki-structure slice.
- **claude-mem replacement by lean-ctx's knowledge graph** → stays open in ADR-002.

---

## 10. Testing & eval (mirrors C1)

- **Unit tests** for `lib/codemap` with lean-ctx **mocked via a recorded-output fixture** (CI has no
  binary): normalization, digest rendering, staleness detection (hash drift / added / deleted files).
- **Read-only-project property test:** the scanned project tree is byte-identical after `generate()`.
- **Graceful-degrade tests:** lean-ctx absent → `/ren:code-map` reports cleanly and ingest seeding
  skips, with **no crash and no partial cache file**.
- **`eval/eval.json`** (ADR-011, binary assertions) + a Python-project fixture: a code-map is produced
  at the cache path with correct symbol→line-range entries drawn from the fixture (not invented), the
  project is unmodified, and a stale map surfaces the banner.
- **Per-module run:** `( cd <plugin-root> && python3 -m pytest lib/codemap/tests/ -q )`.
- **CI parity unchanged:** no `schemas.json` touch; `claude plugin validate ./ --strict` must pass.

---

## 11. Risks & open questions

- **lean-ctx headless CLI viability** — the central unknown → §4 Phase-0 spike gates the whole build.
- **lean-ctx writing into the project** — would break the C1 invariant → §7.1 property test + adapter
  cache redirection.
- **lean-ctx longevity** (4-month-old project, daily releases) → version pin + ADR-002 sunset trigger
  + the ctags escape hatch keeps us un-stranded.
- **Binary absence in CI / cloud routines** — everything stays optional via graceful-degrade; the
  capability is a bonus, never a hard dependency. (Relevant when C5 later runs in cloud routines.)
- **Plugin-data wipe on reinstall** — acceptable: the cache is trivially regenerable.

---

## 12. Implementation sequencing hint (for `writing-plans`)

1. **Phase 0 — lean-ctx spike** (gate; may bounce back to the maintainer).
2. `sf_paths` cache-dir helper (+ tests).
3. `lib/codemap` core + adapter + digest + staleness (TDD; mocked-binary fixtures).
4. `skills/code-map/` SKILL + entrypoint + eval + fixtures + learnings.
5. doctor `check-code-map.sh` + wiring.
6. ingest Stage-6 seeding hand-off.
7. ADR-035 + ADR-002/008 amendments.
8. Wire-up (README/CHANGELOG/wiki/roadmap) + full gate (pytest, `plugin validate --strict`, schema CI-parity).
