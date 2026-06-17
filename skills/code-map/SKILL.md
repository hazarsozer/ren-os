---
name: code-map
description: |
  Use when the builder wants a compact symbol→line-range index of a project so
  the agent reads less and pulls only the line ranges it needs. Triggers on
  /ren:code-map [path] --name <kebab> [--refresh]. Adopts the lean-ctx CLI;
  caches a regenerable markdown digest under the plugin-data dir (never the
  wiki). Read-only on the project. If lean-ctx is absent, degrades gracefully.
version: 0.1.0
license: MIT
framework_version: "1.0.0"
schema_version: 1
type: skill
tags: [code-map, token-economy, navigation, lean-ctx, read-only]
related_skills: [ingest-project, doctor]
references_required: []
references_on_demand: []
---

# code-map

Generates a regenerable symbol→file:line-range digest of a project.

## When to use
- Builder runs `/ren:code-map [path] --name <kebab> [--refresh]`.
- Builder says "build a code index for this project", "map the symbols", "refresh the code-map".

## Procedure
1. Resolve project path (default cwd) and `--name` (kebab; reuse the project's wiki name).
2. Run `python3 scripts/code_map.py "<path>" --name <name> [--refresh]`.
3. On generation: report the cache path + symbol count; remind the builder the map is
   load-on-demand (not auto-loaded at wake-up) and to re-run with `--refresh` after big changes.
4. If a cache already exists and `--refresh` was not passed: the script reports freshness
   (or a STALE banner). Relay it.
5. If lean-ctx is unavailable: relay the install hint; do not fail the session.

## Read discipline (load-bearing)
The digest's line ranges are **hints**. Before relying on one, verify the symbol is
actually at that range — a stale map is worse than none. Staleness is computed from a
`.json` sidecar next to the digest.

## Anti-patterns
- Never write the map into the user's project or the wiki — cache only (`${CLAUDE_PLUGIN_DATA}/code-maps/`).
- Never inject the map at wake-up; it is load-on-demand (ADR-008).
- Never invent symbols; emit only what lean-ctx reports.

## References
- `lib/codemap/` — the engine-agnostic core + lean-ctx adapter.
- ADR-035 (Code-Map Context Layer), ADR-002 (token-efficiency stack), ADR-008 (wake-up).
