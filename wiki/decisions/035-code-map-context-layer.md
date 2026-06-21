---
title: "ADR-035: Code-Map Context Layer"
status: accepted
date: 2026-06-17
sunset-review: 2027-06-17
references-pages: [lean-ctx, nate-herk-economics-and-permissions, context-mode]
affects-components: [codemap, doctor, ingest-project, install]
relates-to: [002-token-efficiency-stack, 008-wake-up-hook, 032-project-ingest, 003-no-daemon-rule]
---

# ADR-035: Code-Map Context Layer

> C2 roadmap slice — the code-map is a regenerable symbol → file:line-range digest that lets the agent
> read a compact index and pull only the line ranges it needs, rather than reading whole files. Primary
> sources: `lib/codemap/SPIKE_FINDINGS.md` and
> `docs/superpowers/specs/2026-06-17-c2-code-map-design.md`. Amends ADR-002 and ADR-008.

## Context

Context window quality degrades hierarchically as a session grows: raw file reads are expensive and
compress badly. A project with dozens of source files forces the agent to either read files
speculatively (token-expensive, noisy) or navigate blind (risky). The gap the code-map closes: the
agent reads a compact symbol→line-range index first, then fetches only the spans it needs.

Two secondary concerns shaped the scope:

1. **Staleness risk.** A line-number map that no longer reflects the code is worse than no map — the
   agent reads the wrong lines with false confidence. Detection and surfacing of staleness is therefore
   a first-class concern, not an afterthought.

2. **C5 dependency-map path.** The code-map is designed to be the natural foundation for a future
   call-graph / dependency-map layer (C5). Keeping the `Symbol` contract extensible now avoids a
   ground-up rethink later.

**Constraint from ADR-008:** the code-map must never be injected into the wake-up context; it is
load-on-demand only, to preserve the 3–5K SessionStart budget.

**Constraint from ADR-003 + ADR-032 (C1 read-only discipline):** the engine must leave the scanned
project byte-identical — no index or cache dropped into the user's repo.

## Decision

### 1. Engine — lean-ctx CLI (per-file `read -m signatures`)

**lean-ctx (v3.8.x, `cargo install lean-ctx`)** is adopted as the code-map engine, used exclusively
as a **CLI tool**. The spike (see `lib/codemap/SPIKE_FINDINGS.md`) confirmed the viable command
surface.

**Correction from the spec's original assumption:** the spec assumed a `lean-ctx map <path> --format
json` subcommand. **That command does not exist.** The real mechanism is per-file invocation:

```bash
lean-ctx read <file> -m signatures
```

This produces text output (stdout) listing each symbol with kind, visibility, name, params, return
type, and a `@Lstart-Lend` range. The adapter walks the enumerated source files and invokes
`lean-ctx read <file> -m signatures` once per file, parsing each line with a deterministic regex
into the `Symbol` model.

**Why CLI, not lean-ctx's MCP server or `lean-ctx serve`:**
- Per `wiki/research/nate-herk-economics-and-permissions.md`, CLI-over-MCP saves ~60–70% tokens
  (MCP tools inject their entire tool schema into every message; a shell call does not).
- Running `lean-ctx serve` would be a daemon — explicitly forbidden by ADR-003.

**No native JSON output.** `--json` is accepted but silently ignored for read modes. Text parsing
via regex is the only path; it is deterministic and fully validated against a real fixture.

### 2. Architecture — engine-agnostic core behind the `Symbol` contract

```
lib/codemap/
├── __init__.py          # public API: generate(), is_stale(), render_digest()
├── models.py            # Symbol dataclass + CodeMap + StaleReport
├── sources.py           # shared source-file enumerator (all *.py globs); also used by staleness
├── adapter_leanctx.py   # ONLY lean-ctx-aware unit — shells lean-ctx, parses text, returns Symbol[]
├── digest.py            # render_digest() → markdown
├── staleness.py         # is_stale(): per-file hash comparison
└── tests/               # unit tests with mocked-binary fixtures
```

The adapter is the **only lean-ctx-aware unit**. Swapping engines (e.g. to universal-ctags) requires
touching `adapter_leanctx.py` only — the core, skill, and staleness logic are engine-blind.

A shared `lib/codemap/sources.py` enumerates source files; it is used both by the adapter (which
files to scan) and by staleness (which files to hash). Single source of truth prevents drift between
"files scanned" and "files tracked for staleness."

`scan.py` (C1's ingest scanner) is **not modified**. The code-map is a separate standing capability;
coupling a cache-writing concern to `scan.py`'s stdlib-only, writes-nothing invariants would violate C1's design.

### 3. Storage — regenerable cache under `${CLAUDE_PLUGIN_DATA}`

```
${CLAUDE_PLUGIN_DATA}/code-maps/<handle>/<project>.md   # symbol digest (markdown)
${CLAUDE_PLUGIN_DATA}/code-maps/<handle>/<project>.json # sidecar: per-file content hashes
```

**Never** in the version-controlled wiki (no git-churn from line-number changes).
**Never** in the user's project tree (read-only discipline from ADR-032).

The cache is trivially regenerable; it is not backed up.

lean-ctx itself writes only to `~/.local/share/lean-ctx/` (XDG data dir) — verified byte-identical
on the project tree during the spike (`READ-ONLY: OK`).

### 4. Staleness + trust-but-verify discipline

`is_stale()` recomputes per-file content hashes (via `sources.py`) and diffs against the sidecar.
Any hash drift, added file, or deleted file produces a `StaleReport`.

A stale map opens with a banner:

```
⚠ STALE — N files changed since <commit/timestamp>; regenerate with /ren:code-map --refresh
```

The map is **never silently trusted**. The digest header documents the read discipline: treat any
cited line range as a *hint* and verify the symbol is actually there before relying on it. A map
that lies about line numbers is worse than none.

**Refresh:** manual `/ren:code-map --refresh`. Auto/git-hook/cadence refresh is deferred to C5.

### 5. `/ren:code-map` skill

`skills/code-map/` provides the `/ren:code-map` entrypoint. Responsibilities:

- `generate` (default): run the adapter, write digest + sidecar, print summary + cache path.
- `--refresh`: regenerate unconditionally.
- Staleness report on read (surfaces the banner and changed-file list).
- Imports `lib.codemap` via the same `sys.path` convention `scan.py` uses for `lib.sf_paths`.

### 6. Ingest seeding — graceful Stage-6 hand-off

After `/ren:ingest-project` completes, Stage 6 attempts to seed the code-map when lean-ctx is
available. When lean-ctx is absent, Stage 6 emits a one-line install suggestion and continues. This
is **additive only** — no write gate, no change to `scan.py`.

### 7. Install path + `/ren:doctor` + graceful-degrade

lean-ctx is a Rust binary. Install:

```bash
cargo install lean-ctx
```

`/ren:doctor` reports a `CODE-MAP` line: lean-ctx present/absent + version. All code-map paths
graceful-degrade when the binary is absent: `/ren:code-map` reports cleanly, ingest Stage 6 skips,
no crash, no partial cache file.

### 8. Load-on-demand — never in wake-up (ADR-008 amendment)

The code-map is loaded only when the agent explicitly needs to navigate code. It is not part of the
SessionStart injection. A single pointer line in the project wiki context is permitted (e.g., "Code
map: `/ren:code-map`"); the digest content is not injected. See ADR-008 amendment.

## Consequences

**Easier:**
- **Cheap navigation.** Agent reads a compact index (typically < 20K tokens for a medium project),
  pulls only needed spans — significantly fewer tokens than reading all source files.
- **C5-ready.** The `Symbol` model and `sources.py` enumerator are designed to be extended with
  reference/call-graph data when C5 builds the dependency-map layer.
- **Read-only / safe.** The scanned project is byte-identical after generation (property-tested).
  No risk of lean-ctx contaminating the user's repo.
- **Governable staleness.** The STALE banner and hash sidecar make degradation visible; the agent
  never navigates with outdated line numbers silently.
- **Swappable engine.** The adapter boundary means universal-ctags (or any other tool) can replace
  lean-ctx without touching the core, skill, or tests.

**Harder:**
- **External Rust binary dependency + install friction.** `cargo install lean-ctx` requires a Rust
  toolchain. Adds a step to the install path; surfaced in `/ren:doctor`.
- **Per-file invocation cost on large repos.** Invoking `lean-ctx read` N times (once per source
  file) is I/O-serial. For very large projects this can be slow. Mitigated by graceful-degrade
  (the map is optional, never blocking) and the future C5 path may batch differently.
- **lean-ctx is young and fast-moving.** The project was ~4 months old at adoption (v3.8.8, daily
  releases). CLI surface stability is not guaranteed. A version pin + the ctags escape hatch (below)
  keeps the stack un-stranded.
- **Text-parse adapter, not JSON.** `lean-ctx read -m signatures` emits text; no native JSON output.
  The regex is deterministic and validated, but any upstream format change breaks parsing.

## Alternatives considered

### A) universal-ctags (the named escape hatch)

**Shape:** `ctags --output-format=json --fields=+ne -R <path>` produces per-symbol JSON with
name/kind/file/line/end. Stable, ubiquitous, available in most distros.

**Why not chosen for v1:** symbol → start-line only (end-line is present only with `--fields=+e` and
only for some languages/kinds); coarser than lean-ctx's signatures mode. The agent can find a symbol
but can't confidently bound its extent. lean-ctx's `@Lstart-Lend` range for every symbol is
materially better for the "pull only what you need" goal.

**Named escape hatch:** if lean-ctx becomes unmaintained or its CLI surface breaks, the adapter
reverts to universal-ctags behind the same `Symbol` interface. See Sunset triggers below.

### B) tree-sitter via pip

**Shape:** `pip install tree-sitter` + language grammars; parse ASTs directly in Python for precise
start/end ranges across all supported languages.

**Why not chosen:** breaks the plugin's no-install model for the user's project. `pip install` into
the user's environment is an intrusive side effect. lean-ctx bundles its own tree-sitter runtime
as a Rust binary; one binary vs. a pip dependency + grammar downloads.

### C) Python `ast` stdlib (zero-dep)

**Shape:** `import ast; ast.parse(...)` — zero external dependency, Python-only.

**Why not chosen:** Python-only (lean-ctx supports 21 languages via tree-sitter). Conflicts with the
"adopt, don't hand-roll" principle when a purpose-built tool already exists. Would require per-language
implementations for JS/TS/Go etc. as the user's projects diversify.

## Sunset triggers

- **lean-ctx unmaintained or its CLI surface breaks** → revert to universal-ctags behind the same
  `Symbol` adapter (no changes to core, skill, or staleness logic).
- **lean-ctx's knowledge-graph memory proves materially better than claude-mem for the friend group's
  actual usage** → re-evaluate ADR-002's lean-ctx-as-memory-layer question (a distinct decision;
  see ADR-002 amendment). That evaluation does not affect this ADR's code-map decision.

## References

- `docs/superpowers/specs/2026-06-17-c2-code-map-design.md` — design spec (locked scope, architecture, invariants)
- `lib/codemap/SPIKE_FINDINGS.md` — spike results: real CLI surface, per-file mechanism, read-only verification
- `wiki/research/lean-ctx.md` — lean-ctx research page (62 MCP tools, tree-sitter, Apache-2.0/MIT)
- `wiki/research/nate-herk-economics-and-permissions.md` — CLI-over-MCP token savings (~60–70%)
- ADR-002 (Token-Efficiency Stack) — lean-ctx adoption narrowly scoped here; see amendment
- ADR-003 (No-Daemon Rule) — CLI-only use of lean-ctx; `lean-ctx serve` excluded
- ADR-008 (Wake-Up Hook) — code-map is load-on-demand, never in SessionStart injection; see amendment
- ADR-032 (Project Ingest) — read-only-project discipline inherited by the code-map

---

## Amendment — 2026-06-21 (C5c: dependency-map realized)

The "C5-ready" consequence noted above (§ Consequences → Easier) is realized in C5c.

**What shipped:**
- The dependency-map layer is implemented as a **stdlib-`ast` module-level import graph** in
  `lib/codemap/deps.py` — engine-agnostic, zero external dependencies, read-only, never raises.
  This is deliberately **not** the lean-ctx graph DB (see finding below).
- `CodeMap.dependencies` persists the graph in the existing cache sidecar (backward-compatible;
  no schema migration required).
- `core.load_fresh()` provides on-demand auto-refresh when the cache is stale — no daemon, no
  wake-up injection (ADR-008 preserved).

**lean-ctx graph DB finding (recorded, not adopted):**
The C5c spike (`lib/codemap/SPIKE_FINDINGS.md`) confirmed that lean-ctx's knowledge-graph layer
is **class-only** — it exposes class→member and class→class relationships but has no
function→function call edges. A true symbol-level call-graph cannot be built on the current
lean-ctx graph DB.

**Symbol-level call-graph: explicitly deferred.**
Function→function call-graph analysis would require a different tool (e.g., a custom
tree-sitter pass, pycallgraph, or a dedicated Python call-graph library). This exceeds
the scope of the adopted tooling and is not blocked by this ADR — it is a future layer if
the need is demonstrated. The module-import graph delivers the Pillar-5 dependency-map
need as scoped.

**Self-improvement impact surface:**
`skills/improve-skill/lib/impact.py` (`dependency_footprint` → `ImpactReport`) consumes the
dependency graph for read-only impact awareness in the Karpathy loop. It is stdlib-only and
decoupled from `lib.codemap` to avoid a `lib` package-name collision. This is additive only —
no change to the code-map's engine, storage, or staleness logic.

This amendment is additive. ADR-035's status, engine choice, storage architecture, staleness
discipline, and all other decisions remain unchanged.
