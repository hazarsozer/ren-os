---
name: insights
description: |
  Use when the solo builder wants a read-only retrospective on how their
  recent Claude Code sessions actually went — what's working, what keeps
  hindering them, and the quick wins worth taking. Triggers on the
  /sf:insights slash command (optional --days N, default 30; optional
  --project <name>). A collector script mines LOCAL session history
  (~/.claude transcripts + save-session summaries) and emits facts;
  the LLM synthesizes the narrative. Strictly read-only: no writes,
  no network. Per ADR-031 (solo-first) this is the Cadence-layer
  reflection surface.
version: 0.1.0
license: MIT

framework_version: "1.0.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "A user-facing report with four sections: Usage at a Glance, What's Working, What's Hindering, Quick Wins"
    - "Every claim grounded in / cited to the collected session facts (no invented data)"
  budgets:
    turns: 2
    files_written: 0
    duration_seconds: 30
  permissions:
    read:
      - "~/.claude/projects/**"
      - "~/.claude/session-data/**"
    write: []
    execute:
      - "scripts/collect.py"
  completion_conditions:
    - "Skill produced a four-section report (possibly noting an empty window)"
    - "No file anywhere on disk was created, modified, or deleted by the run"
  output_paths: []

tags: [insights, retrospective, read-only, cadence, sessions, lifecycle]
related_skills: [sf-wrap, sf-recall, sf-doctor]
references_required:
  - "references/synthesis-prompt.md"
references_on_demand: []
---

# sf-insights

Read-only session retrospective. The solo builder asks "how have my last few weeks of building actually gone?" — sf-insights mines the **local** Claude Code session history, extracts per-session facts (project, tools used, topics, error/retry signals), and hands the LLM a bounded, cited fact-block to turn into a four-section narrative.

Solo-first (ADR-031): this is the **Cadence** layer's reflection surface. It mines only local on-disk history; it never phones home and never writes anything.

## When to use this skill

- Builder invokes `/sf:insights` (optionally `/sf:insights --days 14` or `/sf:insights --project sidecar`)
- Builder says: "how have my sessions been going", "what's slowing me down lately", "review my last month of building", "where am I losing time" — confirm scope once, then run

## When NOT to use this skill

- Builder wants to consolidate the *current* session into the wiki → `/sf:wrap`
- Builder wants to look up a specific past decision → `/sf:recall <query>`
- Builder wants to verify the install / permissions → `/sf:doctor`
- Builder wants insights about a remote or shared history → out of scope; this skill is local-only and read-only

## Flags

| Flag | Effect |
|---|---|
| (none) | Mine the last **30 days** of local sessions across all projects |
| `--days N` | Change the look-back window to N days (filters source files by mtime) |
| `--project <name>` | Restrict to sessions whose project (cwd basename) matches `<name>` (case-insensitive substring) |
| `--claude-dir <path>` | Override the `~/.claude` base (mainly for testing; defaults to `$CLAUDE_CONFIG_DIR` or `~/.claude`) |

## How it works

1. Run the collector (read-only, no network):
   ```
   python3 scripts/collect.py --days <N> [--project <name>]
   ```
   It walks **two** local sources, filtering each by file mtime within the window:
   - `~/.claude/projects/<encoded-cwd>/*.jsonl` — rich heterogeneous transcripts (the real signal). Parsed **line-by-line; malformed lines are skipped**, never fatal.
   - `~/.claude/session-data/*.tmp` — narrative `save-session` summaries (sparse, user-dependent).
   It emits a structured `=== SF-INSIGHTS COLLECTED DATA (v1) ===` block on **stdout only**.
2. Read `references/synthesis-prompt.md` and follow it: turn the collected facts into the four-section report. **Bound every claim to the data**; if the window is empty, say so plainly rather than inventing trends.
3. Print the report to the user. Do not write it anywhere.

## The four sections (synthesis output)

| Section | Owns |
|---|---|
| `## Usage at a Glance` | The factual base: sessions, projects, top tools, error counts — straight from the collector |
| `## What's Working` | Patterns the data supports as effective (well-used tools, low-friction projects) |
| `## What's Hindering` | Friction the data shows (error/retry hotspots, churny tools, stalled projects) |
| `## Quick Wins` | Small, concrete, data-grounded next actions |

## What this skill explicitly DOES NOT do

- Write, create, or delete **any** file — not the wiki, not a report, not a cache. Strictly read-only (the collector opens files read-only only).
- Make any network call. No marketplace fetch, no telemetry, nothing leaves the machine.
- Load full transcripts into the LLM context. The collector returns bounded counts + short snippets, never raw session bodies.
- Echo secrets. The collector reads transcripts for tool/topic signal, not to surface credentials; it summarizes, it does not dump.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| `~/.claude/projects` and `~/.claude/session-data` both absent | Treat as empty window | "No local sessions found in the last N days." (still renders four sections) |
| A transcript file has malformed JSON lines | Skip those lines; keep the valid ones | (no user-visible change) |
| A single file is unreadable mid-walk | Skip it; continue | (no user-visible change) |
| Empty window (no files within `--days`) | Emit `sessions_found: 0`; LLM notes the empty window | "No sessions in the window; widen with --days." |

## Implementation note

V1 implementation in `skills/sf-insights/scripts/collect.py`:
- Pure-stdlib, streaming, read-only collector (no third-party deps, no writes, no network).
- mtime-based window filter applied **before** opening any file (cheap `stat` first).
- Bounded accumulation (counters + capped snippet lists) so memory stays flat regardless of transcript size.
- `collect()` returns a frozen `CollectedData`; `render()` produces the stdout block — both unit-testable against a temp `HOME`.

v2 path: when richer session telemetry lands, the collector's extractors widen; the stdout contract (the `=== SF-INSIGHTS COLLECTED DATA (v1) ===` block) stays stable so the synthesis prompt is unaffected.

## References

- ADR-013 (Slash Command Namespacing) — `/sf:insights` uses the `/sf:` prefix
- ADR-031 (Solo-First Pivot) — defines this as the Cadence-layer reflection surface
- `references/synthesis-prompt.md` — the bounded, cited, four-section synthesis contract
