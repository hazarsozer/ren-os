---
name: code-map
description: |
  Use when the friend wants a structural map of a codebase (call graphs,
  symbol index, cross-file references) — beyond what wake-up/recall already
  surface from the wiki. Triggers on /ren:code-map [build|status]. A thin
  wrapper over Graphify (pinned 0.9.x), never a second hand-rolled engine;
  gracefully absent if Graphify isn't installed.
version: 0.5.3
license: MIT

framework_version: "0.5.3"
schema_version: 1
type: skill
execution_tier: deterministic

contract:
  required_outputs:
    - "status: a CodeMapStatus report (installed/version/pinned/stale), never a crash"
    - "build: graph.json under state_dir()/derived/codemap/, plus a codemap_tokens 'build' metric"
    - "consume (internal, called by other capabilities): tokens_loaded vs tokens_baseline metric"
  budgets:
    turns: 1
    files_written: 1
    duration_seconds: 120
  permissions:
    read:
      - "<repo being mapped>/**"
    write:
      - "~/.renos/wiki/.ren/derived/codemap/**"
      - "~/.renos/wiki/.ren/metrics/**"
    execute:
      - "graphify"
  completion_conditions:
    - "status() returns without raising regardless of whether graphify is installed"
    - "build() either returns a graph.json path or raises CodeMapUnavailable with an install pointer"
  output_paths:
    - "~/.renos/wiki/.ren/derived/codemap/"
    - "~/.renos/wiki/.ren/metrics/"

tags: [companion, code-map, graphify, derived-cache, instrumentation]
related_skills: []
references_required: []
references_on_demand: ["doctrine/companions.md"]
---

# code-map

A structural map of a codebase — symbols, call graphs, cross-file references — for sessions that need more than the wiki's own knowledge. This skill is a **thin wrapper over [Graphify](https://github.com/) (pinned 0.9.x)**, not a second code-intelligence engine. Per the reuse doctrine (spec §3.2 v2.1 D-4), the framework's own hand-rolled `lib/codemap/` engine was deleted in favor of this wrapper.

## When to use this skill

- Friend invokes `/ren:code-map status` — report whether Graphify is installed, its version, whether that version is within the pinned range, and whether the derived graph exists and is fresh.
- Friend invokes `/ren:code-map build` — (re)generate the derived graph for the active repo.
- Another capability (not the friend directly) calls `skills.code_map.lib.consume()` to load the graph mid-session.

## When NOT to use this skill

- The friend wants wiki knowledge, not code structure → `/ren:recall`.
- Graphify is not installed and the friend hasn't asked to install it → report absence plainly via `status()`; do not suggest a fallback engine. There isn't one.

## Behavior

1. **status**: call `skills.code_map.lib.status(repo_root)`. Never raises — reports `installed=False` plainly when Graphify is absent, with a pointer to install it (`uv tool install graphifyy`; see `doctrine/companions.md`).
2. **build**: call `skills.code_map.lib.build(repo_root, session)`. Runs Graphify headlessly (`graphify <repo_root> --output <state_dir()/derived/codemap>`), records a `codemap_tokens` "build" metric (real byte size, not an estimate), and returns the `graph.json` path. Raises `CodeMapUnavailable` (with the install pointer) if the binary is missing, or if Graphify exits nonzero.
3. **consume** (internal use by other capabilities, not a direct user command): loads the graph and records BOTH `tokens_loaded` (the graph itself) and `tokens_baseline` (the raw source it summarizes) via `lib.instrument.estimator` — this is the chairman-ruling instrumentation: Graphify's token-savings claim must show up in these two numbers, not just be asserted. Raises `CodeMapUnavailable` if the graph is absent or stale (a source file changed since the last build) — it never rebuilds silently; the caller decides.

## Boundaries (load-bearing)

- **Derived cache, never memory.** The graph lives at `state_dir()/derived/codemap/graph.json` — entirely OUTSIDE the wiki page tree, the write-queue (Task 2.1), integrity checks (Task 2.3), and the backup-critical set (Phase 9). It is regenerable at any time from source; losing it loses nothing durable.
- **The pin (0.9.x) and why.** Graphify's API has churned across major versions; `GRAPHIFY_PIN = "0.9"` is the version prefix this wrapper is built against. `status()`'s `pinned_ok` flags drift for doctor (Phase 7) to surface — a version outside the pin is a warning, not a hard failure, but it's not silently ignored either.
- **Code-mode only, never Graphify's LLM media-extraction paths.** This wrapper only ever invokes Graphify's deterministic tree-sitter parsing. Graphify's own LLM-backed media-extraction features are never invoked from here, and stay off by default per the §3.6 data-flow statement.
- **Graphify's wiki/Obsidian export feature is FORBIDDEN here.** The wiki's SSOT stays queue-governed (Task 2.1) — nothing in this wrapper, ever, writes a wiki page. `build()` asserts its output path is under `state_dir()` in code, not just in this doc.
- **Graceful absence, no second engine.** Not installed → `status()` says so plainly and `build()`/`consume()` raise `CodeMapUnavailable` with an install pointer. There is no fallback hand-rolled engine to fall back to; that engine was deliberately deleted.
