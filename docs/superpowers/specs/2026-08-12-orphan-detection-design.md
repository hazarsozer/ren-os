# Wiki-wide orphan detection (#55) — design

**Date:** 2026-08-12 · **Issue:** [#55](https://github.com/hazarsozer/ren-os/issues/55) · **Target version:** 0.7.0 (after #53, #54; last of the trio)

## Problem

`unlinked_knowledge_pages` audits only `projects/<slug>/knowledge/`
subdirectories. The dogfood sweep said "none" while 40 pages sat orphaned —
top-level project pages, study's standalone pages, every pre-#54 L1. The
graph tiers #53/#54 connect need an auditor that sees the whole wiki.

## Decisions already made (with Hazar)

- Exemptions encoded, not implied: `raw/` and `archive/` only. `l1/` is NOT
  exempt — session pages must be reachable from `log.md` or their project
  hub (#54 makes new ones reachable; this check finds the old ones).
- Primary targets: the wiki root tier and `projects/<slug>/` knowledge
  directories — durable knowledge must be connected.
- Orphans are judgment-shaped → suggestions store (fingerprint-deduped),
  never auto-fixed. The existing knowledge-tree checks stay as the
  mechanical tier.

## New sweep finding: `orphan_pages`

### Candidates

Every `*.md` under `wiki_root`, EXCLUDING:
- `.ren/` (machine state) and any dot-directory
- `projects/<slug>/raw/` (immutable sources — `ren_paths.in_project_raw`,
  canonical, never re-implemented locally) and `archive/` /
  `projects/<slug>/archive/` (exact depth: `archive/` at the wiki root or
  directly under a project — NOT an `archive`/`raw` dir at arbitrary depth,
  e.g. `projects/x/knowledge/raw/notes.md` is a candidate, not exempt)
- quarantined pages (`lib.memory.quarantine.is_quarantined`) — unreviewed
  content is not a placement candidate; it surfaces via the Quarantined
  section and the release flow instead. A quarantined page still
  contributes links/mentions to the corpus, like any other exempt page.
- designed entry points: `index.md`, `log.md`, `identity.md` (wiki roots)
- `LICENSES.md` (repo hygiene page, not knowledge)

### Incoming-link corpus (one pass over ALL pages, including exempt ones —
an exempt page can still legitimately link a candidate)

A candidate is LINKED when any of:
1. A markdown link target resolves to it — resolved BOTH relative to the
   linking file's directory AND wiki-root-relative (both conventions
   legitimately coexist post-#53; `#anchor` fragments stripped).
2. A legacy arrow pointer (via `lib.pointer.parse_pointer_line`, arrow form)
   resolves to it (root-relative, per the L2 convention).
3. Forgiving name-mention fallback: its FILENAME appears word-bounded
   (reuse the exact `name_re` pattern from `_knowledge_tree_findings`)
   anywhere in the corpus — EXCEPT for files named `index.md`, which are
   never matched by mention (a dozen hubs share the name; only resolved
   paths count for them).

Self-links don't count (a page linking itself stays an orphan).

### Surfacing

- `sweep()` result gains `"orphan_pages": [<wiki-relative paths>]`;
  degraded empty-findings path includes the key as `[]`.
- `render_report` gains `## Orphan pages (no incoming links)` — path list,
  `- none` when clean.
- New helper `record_orphan_suggestions(orphans: list[str], session: str)
  -> int` — records one suggestion per orphan via `lib.suggestions.record`
  with fingerprint `orphan:<page>` (exact-dedup against ledger + pending is
  the store's built-in behavior), returns how many were newly recorded.
  The wiki-health SKILL.md instructs the live session to call it after
  showing the report. `sweep()` itself stays read-only.

## Non-goals

- No auto-repair; no change to `unlinked_knowledge_pages` /
  `hubless_knowledge_dirs` (they remain the mechanical-repair tier; the
  mention-fallback keeps the two checks from contradicting each other).
- No incremental-lint integration (sweep-scope audit).
- No backfill of the dogfood wiki here — the first post-release sweep IS
  the discovery pass.

## Testing

Temp-wiki fixtures: orphan L1 flags; L1 linked from log.md does not;
map-Sessions link counts; raw/archive/entry-point exemptions; relative and
root-relative link resolution both count; arrow-pointer resolution counts;
name-mention saves a prose-referenced page; `index.md` never mention-saved
but path-link-saved; self-link doesn't save; `record_orphan_suggestions`
dedups across two calls; degraded no-wiki path carries the key.
