---
name: recall
description: |
  Use when the friend wants to look up something the wiki should know — a
  past decision, pattern, or lesson — WITHOUT loading more wiki context
  into the session. Triggers on /ren:recall <query>. Read-only: greps the
  local wiki for matches and returns ranked snippets. Companion to
  /ren:wrap (the consolidate) and /ren:note (the pin).
version: 0.1.0
license: MIT

framework_version: "1.0.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "A list of zero-or-more wiki hits (paths + snippets) ranked by relevance"
    - "User-facing summary of the matches"
  budgets:
    turns: 2
    files_written: 0
    duration_seconds: 10
  permissions:
    read:
      - "~/.startup-framework/wiki/**"
      - "<routine-repo>/state.md"
      - "<routine-repo>/run-log.md"
    write: []
    execute: []
  completion_conditions:
    - "Skill produced output (possibly empty if no matches)"
    - "No file under wiki/ was modified by the run"
  output_paths: []

tags: [companion, mid-session, search, wiki, lifecycle, read-only]
related_skills: [wrap, note]
references_required:
  - "references/grep-strategy.md"
references_on_demand: []
---

# recall

Read-only wiki search. The friend asks "what did we decide about X" or "what does pattern Y look like" — /ren:recall greps their local wiki and returns top matches with snippets.

Solo-first (ADR-031): recall searches the local wiki only. The former cross-friend feed-activity tail was removed with the Activity Feed module.

## When to use this skill

- Friend invokes `/ren:recall <query>` (canonical trigger; everything after the command name is the query)
- Friend says: "what do we know about X", "did we decide on Y", "recall <topic>", "remind me about <pattern>" — confirm the query once, then run
- Friend invokes `/ren:recall --instincts <query>` to restrict results to the hot-tier `instincts.md` pages (C3a) — "what did I learn about X", "any don't-repeats on Y"

## When NOT to use this skill

- Friend wants to pin something for later → `/ren:note <text>` (not a search)
- Empty query after `/ren:recall` → refuse with usage hint
- Friend wants to modify the wiki → that's `/ren:wrap`'s domain; this skill is strictly read-only

## Behavior

1. Validate query is non-empty (after whitespace strip). If empty, refuse with usage hint.
2. Walk `~/.startup-framework/wiki/**/*.md` (excluding hidden dirs like `.git/`, but INCLUDING `wiki/.session-notes/` since pins are part of recallable context).
3. For each file:
   - Tokenize the query into lowercase words
   - Score the file based on `references/grep-strategy.md` heuristic (title hits, body hits, file recency, file kind)
   - If at least one token hits: extract a snippet (matching line + 2 lines context)
4. Rank hits descending by score; truncate to top N (default 10).
5. Compose user-facing output:
   ```
   ## Wiki matches for "<query>"
   - <path1>:<line>: <snippet>
   - <path2>:<line>: <snippet>
   ...
   ```
6. If there are no matches: explicit "No matches" message.

## What this skill explicitly DOES NOT do

- Modify any file under `~/.startup-framework/wiki/` or anywhere else. Strictly read-only.
- Load full file contents into the LLM context. Returns snippets only (max ~3 lines per hit).

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Empty query | Refuse, prompt for query | "What should I search for? Usage: /ren:recall <query>" |
| Wiki root missing | Treat as zero hits | "No wiki matches for '<query>'" |
| Single file unreadable mid-walk | Skip the file; log to stderr; continue | (no user-visible change) |
| No matches | Explicit no-results message | "No matches for '<query>' in the wiki." |

## Implementation note

V1 implementation in `skills/recall/lib/__init__.py`:
- `RecallHit`, `RecallResult` dataclasses (frozen)
- pure-logic wiki-grep + scoring + snippet extraction
- public `recall(query, *, wiki_root, n_hits)` orchestrator

The wiki-grep layer is pure filesystem + Python — fully unit-testable against tmpdir fixtures.

v2 swap-in path: when qmd adoption triggers per ADR-005, the grep core becomes a qmd search; the public API stays. Same shape as ADR-008's wake-up `wake_up_context()` abstraction.

## References

- ADR-005 (Wiki Retrieval Evolution) — defines the v1 grep → v2 qmd transition
- ADR-009 (Consolidate via /wrap) §"Optional but recommended companion commands" — names this skill
- `references/grep-strategy.md` — the scoring heuristic + snippet extraction logic

## Filtering to instincts (`--instincts`, C3a)

When invoked as `/ren:recall --instincts <query>`, recall runs the normal grep but keeps only pages whose frontmatter declares `type: instincts` (the hot-tier `instincts.md` at master + project levels). Same ranking, same read-only contract — just scoped to durable instincts. Backed by `recall(query, *, wiki_root, instincts_only=True)` / `grep_wiki(..., instincts_only=True)`; instincts pages are already in the default search too (this only narrows). See ADR-037 + `docs/superpowers/specs/2026-06-28-c3a-instincts-design.md`.

## Reading routine state (`--routine <path>`)

When invoked as `/ren:recall --routine <repo-path>` (no query), recall switches to **state-read mode** instead of grep: it reads that routine repo's `state.md` (full) and `run-log.md` (last 10 entries) via `read_routine_state()` and prints the cross-run memory trail. This is the call a Cloud Routine makes at run start (ADR-034) so a stateless run knows what prior runs did. Read-only, like the grep path. If neither file exists, it reports "no prior state" and exits cleanly.
