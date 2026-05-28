---
name: sf-recall
description: |
  Use when the friend wants to look up something the wiki should know — a
  past decision, pattern, lesson, or recent friend activity — WITHOUT
  loading more wiki context into the session. Triggers on /sf:recall
  <query>. Read-only: greps the wiki for matches; optionally surfaces a
  short tail of recent feed entries from other friends. Companion to
  /sf:wrap (the consolidate) and /sf:note (the pin).
version: 0.1.0
license: MIT

framework_version: "1.0.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "A list of zero-or-more wiki hits (paths + snippets) ranked by relevance"
    - "If feed is bootstrapped: zero-or-more recent feed entries from other friends, rendered as single-line bullets via feed.format_entry_one_line"
    - "User-facing summary listing both surfaces"
  budgets:
    turns: 2
    files_written: 0
    duration_seconds: 10
  permissions:
    read:
      - "~/.startup-framework/wiki/**"
      - "~/.startup-framework/activity-feed/**"
    write: []
    execute:
      - "feed.feed_read_tail"
      - "feed.format_entry_one_line"
      - "feed.config.handle"
  completion_conditions:
    - "Skill produced output (possibly empty if no matches anywhere)"
    - "No file under wiki/ was modified by the run"
    - "If feed unavailable (identity not configured, schema mismatch): silent degradation, NO error surfaced (per ADR-009 + plan §5)"
  output_paths: []

tags: [companion, mid-session, search, wiki, lifecycle, read-only]
related_skills: [sf-wrap, sf-note, sf-catch-up]
references_required:
  - "references/grep-strategy.md"
references_on_demand: []
---

# sf-recall

Read-only wiki search + optional friend-activity tail. The friend asks "what did we decide about X" or "what does pattern Y look like" — sf-recall greps their local wiki and returns top matches with snippets, plus a short tail of recent activity from other friends (if the Activity Feed is bootstrapped).

## When to use this skill

- Friend invokes `/sf:recall <query>` (canonical trigger; everything after the command name is the query)
- Friend says: "what do we know about X", "did we decide on Y", "recall <topic>", "remind me about <pattern>" — confirm the query once, then run

## When NOT to use this skill

- Friend wants cross-friend session history specifically → `/sf:catch-up <project>` is the right surface (feed-2's skill; covers what others have been working on across a project)
- Friend wants to pin something for later → `/sf:note <text>` (not a search)
- Empty query after `/sf:recall` → refuse with usage hint
- Friend wants to modify the wiki → that's `/sf:wrap`'s domain; this skill is strictly read-only

## Behavior

1. Validate query is non-empty (after whitespace strip). If empty, refuse with usage hint.
2. Walk `~/.startup-framework/wiki/**/*.md` (excluding hidden dirs like `.git/`, but INCLUDING `wiki/.session-notes/` since pins are part of recallable context).
3. For each file:
   - Tokenize the query into lowercase words
   - Score the file based on `references/grep-strategy.md` heuristic (title hits, body hits, file recency, file kind)
   - If at least one token hits: extract a snippet (matching line + 2 lines context)
4. Rank hits descending by score; truncate to top N (default 10).
5. Attempt feed tail:
   - Resolve friend's own handle via `feed.config.handle()`
   - If success: call `feed_read_tail(n=3, exclude_handle=own_handle)` and render each entry via `format_entry_one_line()`
   - If `HandleNotConfiguredError` or `SchemaVersionMismatchError`: silently set feed_hits = [] (no diagnostics; the friend asked for recall, not status)
6. Compose user-facing output:
   ```
   ## Wiki matches for "<query>"
   - <path1>:<line>: <snippet>
   - <path2>:<line>: <snippet>
   ...
   
   ## Recent feed activity
   <format_entry_one_line bullets>
   ```
7. If both surfaces are empty: explicit "No matches" message.

## What this skill explicitly DOES NOT do

- Modify any file under `~/.startup-framework/wiki/` or anywhere else. Strictly read-only.
- Call `feed.feed_write_*` — no writes to the Activity Feed.
- Surface feed-availability diagnostics to the user. If feed-side is unavailable, silently render only the wiki section. `/sf:doctor` is the right surface for "feed status."
- Load full file contents into the LLM context. Returns snippets only (max ~3 lines per hit).

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Empty query | Refuse, prompt for query | "What should I search for? Usage: /sf:recall <query>" |
| Wiki root missing | Treat as zero hits; still attempt feed tail | "No wiki matches for '<query>'" |
| Single file unreadable mid-walk | Skip the file; log to stderr; continue | (no user-visible change) |
| `HandleNotConfiguredError` | Silent feed-empty | Only wiki matches shown |
| `SchemaVersionMismatchError` | Silent feed-empty | Only wiki matches shown |
| feed unavailable for any other reason | Silent feed-empty | Only wiki matches shown |
| Both wiki + feed empty | Explicit no-results message | "No matches for '<query>' in wiki or recent feed activity." |

## Implementation note

V1 implementation in `skills/sf-recall/lib/`:
- `lib/types.py` — `RecallHit`, `RecallResult` dataclasses (frozen)
- `lib/grep.py` — pure-logic wiki-grep + scoring + snippet extraction
- `lib/__init__.py` — public `recall(query, *, wiki_root, n_feed_entries)` orchestrator

The feed-integration layer is the only LLM/IPC-touching part. The wiki-grep layer is pure filesystem + Python — fully unit-testable against tmpdir fixtures.

v2 swap-in path: when qmd adoption triggers per ADR-005, `lib/grep.py` becomes `lib/qmd_search.py`; the public API stays. Same shape as ADR-008's wake-up `wake_up_context()` abstraction.

## References

- ADR-005 (Wiki Retrieval Evolution) — defines the v1 grep → v2 qmd transition
- ADR-009 (Consolidate via /wrap) §"Optional but recommended companion commands" — names this skill
- `references/grep-strategy.md` — the scoring heuristic + snippet extraction logic
- feed-2's API: `feed_read_tail`, `format_entry_one_line`, `feed.config.{handle, HandleNotConfiguredError, SchemaVersionMismatchError}`
