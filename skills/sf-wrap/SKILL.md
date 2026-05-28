---
name: sf-wrap
description: |
  Use at session end when the friend wants to consolidate what they learned and
  emit a terse Activity Feed entry. Triggers on the /sf:wrap slash command.
  Applies a high-signal-threshold: most sessions produce ZERO wiki edits (that
  is the discipline per ADR-009 — routine work doesn't pollute the wiki). When
  signal exists (decision, pattern, lesson, gotcha, stack change), updates the
  relevant ADR-014 pages with diffs shown for approval. Always rewrites the
  active project's CONTEXT.md (the next session's wake-up pointer). Always
  writes a terse session-end entry to the Activity Feed via feed.feed_write_session_end()
  unless --skip-feed or SF_SKIP_FEED=1.
version: 0.1.0
license: MIT

framework_version: 1.0.0
schema_version: 1
type: skill

contract:
  required_outputs:
    - "An updated wiki/projects/<active-project>/CONTEXT.md with the new session pointer"
    - "Zero or more diffs to wiki/projects/<active-project>/{STATE.md,ROADMAP.md,REQUIREMENTS.md,PROJECT.md} when signal threshold is met"
    - "Zero or more new pages under wiki/projects/<active-project>/{decisions,patterns,research}/ when signal is decision/pattern/research grade"
    - "One appended entry in wiki/projects/<active-project>/log.md and/or master wiki/log.md"
    - "One Activity Feed entry via feed.feed_write_session_end() (unless skip-active)"
    - "A brief summary printed to the user covering: pages touched, feed-write status, next-session pointer"
  budgets:
    turns: 10
    files_written: 15
    duration_seconds: 90
  permissions:
    read:
      - "~/.startup-framework/wiki/**"
      - "~/.startup-framework/wiki/.session-notes/**"
      - "~/.startup-framework/activity-feed/**"
      - "skills/sf-wrap/references/**"
    write:
      - "~/.startup-framework/wiki/**"
      - "~/.startup-framework/activity-feed/**"
    execute:
      - "feed.feed_write_session_end"
      - "feed.is_skip_active"
      - "feed.config.handle"
  completion_conditions:
    - "Either: signal-threshold returned 'no signal' → zero wiki edits + (if not skipped) feed entry written + CONTEXT.md still rewritten"
    - "Or: signal threshold returned 'has signal' → all proposed wiki diffs applied or explicitly rejected by user + (if not skipped) feed entry written + CONTEXT.md rewritten"
    - "User has been shown the summary line"
  output_paths:
    - "~/.startup-framework/wiki/projects/<active-project>/"
    - "~/.startup-framework/activity-feed/<handle>.log.md"

tags: [session-end, consolidate, wiki, feed, lifecycle]
related_skills: [sf-note, sf-recall, sf-bootstrap-project]
references_required:
  - "references/signal-threshold.md"
  - "references/wiki-page-mapping.md"
  - "references/feed-call.md"
references_on_demand:
  - "references/diff-approval-ui.md"
  - "references/notes-discovery.md"
---

# sf-wrap

End-of-session consolidate. The partner to the wake-up hook (ADR-008): wake-up reads what `/sf:wrap` writes. Per ADR-009 this is a **user-invoked slash command**, NEVER a Stop hook (Ralph collision + claude-mem SessionEnd ordering + the discipline that most sessions are routine and shouldn't pollute the wiki).

## When to use this skill

- Friend invokes `/sf:wrap` (the canonical trigger)
- Friend invokes `/sf:wrap --skip-feed` to consolidate locally without pushing to the Activity Feed (sensitive session per ADR-021)
- Friend says any of: "wrap up", "consolidate this", "let's save the learnings", "I'm done for the day" — confirm intent with them once, then run

## When NOT to use this skill

- Mid-session "save my progress" — the friend wants `/sf:note <text>` for that, not a full wrap
- Routine debugging session with no genuine signal — STILL invoke /sf:wrap if the friend asked, but expect ZERO wiki edits and only the feed entry to be written. **Do not invent signal to justify wiki writes.** Per ADR-009: "would I want this loaded next session by default? If no, it doesn't go in."
- Throwaway exploration sessions — invoke with `--skip-feed` if the friend prefers no Activity Feed trace

## The 7-step pipeline

### Step 1. Gather inputs (read-only)

Sources:
- The session's transcript (Claude Code's record; reachable via the `transcript_path` hook-input field if invoked from a hook, or via `~/.claude/projects/<slug>/*.jsonl` otherwise)
- Any `/sf:note` pins for this session at `~/.startup-framework/wiki/.session-notes/<session-id>.md` (if no session-id available, also check `unsessioned-notes.md`)
- The cwd → determines the active project (or `None` if not in a `~/Dev/<X>/` dir)
- The current state of relevant wiki pages: `wiki/projects/<active>/STATE.md`, `CONTEXT.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `PROJECT.md`, `log.md`, `index.md`

**Token discipline**: don't load PROJECT.md / REQUIREMENTS.md / ROADMAP.md unless the signal classifier (Step 2) signals they may need updates. Lazy-load on demand. Always load CONTEXT.md (you must rewrite it).

### Step 2. Apply the signal threshold classifier

See `references/signal-threshold.md` for the full criteria. The classifier returns ONE of:

- `none` → no signal; no wiki updates
- `decision` → a real architectural/scope decision was made; needs a new file in `decisions/` and a STATE.md update
- `pattern` → a reusable pattern was discovered; needs a new file in `patterns/`
- `lesson` → a non-obvious learning ("gotcha"); usually goes to STATE.md notes or learnings.md per the related skill
- `stack_change` → tech-stack shift; needs STATE.md + maybe REQUIREMENTS.md update
- `milestone` → roadmap milestone completed; needs ROADMAP.md update
- `purpose_shift` → very rare; project's purpose/scope changed; needs PROJECT.md update

Multi-label is allowed (e.g., a session can have `decision` + `lesson`). When in doubt, prefer `none`. The wiki is sacred; the default is to not touch it.

### Step 3. Compose the diff plan

Use `references/wiki-page-mapping.md` to translate signal-label(s) → list of `(file_path, proposed_diff)` pairs. Diffs are unified-format text (compatible with `git apply --check` for verification).

**CONTEXT.md is always in the diff plan** (the session pointer is rewritten every wrap). Other pages only if signal warrants.

### Step 4. Show diffs for user approval

For each proposed diff, show the user:
- The target file path
- The proposed diff (with syntax highlighting if the host renders markdown nicely)
- Y/N/E[dit]/A[ll-yes] options

`--autonomous` flag (rare; not in V1) would skip this and apply all. **V1 default: ALWAYS prompt.**

### Step 5. Apply approved diffs atomically

Use `git restore` checkpoint before any wiki write. If any single approved diff fails to apply cleanly:
1. Roll back ALL wiki writes from this wrap (`git restore wiki/`)
2. Surface the would-have-been diffs to the user with the failure cause
3. Skip Step 6 + Step 7 (don't write the feed if the wiki write failed; consistency matters)
4. Tell the user how to retry

Append the one-line entry to `wiki/projects/<active>/log.md` AND to the master `wiki/log.md`. The chronological-invariant per ADR-004 must be preserved.

### Step 6. Compose the terse Activity Feed payload

Validate ourselves before calling the feed (defense in depth per the lifecycle ↔ feed-2 contract):
- `summary` ≤ 300 chars (locked by team-lead spec)
- `files_touched` list ≤ 8 displayed
- No triple-backtick fences in `summary`
- No multi-line `summary` (no `\n` chars allowed)
- No `Error:` / `Traceback` / `<` / `>` outside the header
- NO secret-pattern scanning (ADR-021: format constraint IS the privacy mechanism; we don't reinvent AgentShield)

Compute `skip` flag:
```python
skip, reason = feed.is_skip_active(wrap_flag=args.skip_feed)
```

Then call:
```python
result = feed.feed_write_session_end(
    handle=feed.config.handle(),
    project=active_project_or_None,
    task_brief=composed_summary,  # ≤300 chars
    files_touched=touched_files_list,
    schema_version=1,
    skip=skip,
)
```

### Step 7. Handle the feed result + close out

Possible outcomes from `feed.feed_write_session_end()`:
- `success=True, pushed=True` → "✓ feed entry pushed"
- `success=True, pushed=False, queued=True` → "⚠ feed entry queued locally; next session-start will push"
- `success=True, pushed=False, queued=False, error=None` → skip was active → "(feed skipped: \<reason\>)"
- `success=False, violation=<reason>` → format violation; re-prompt the LLM ONCE to recompose `summary`; on second failure abandon feed write but keep wiki updates intact (per team-lead's locked spec)
- `success=False, error=<other>` → log error, keep wiki updates, surface a retry hint

Print the final summary to user:
```
/sf:wrap complete.
  Wiki: <N> pages updated (or "no signal; CONTEXT.md refreshed only")
  Feed: <status>
  Next-session pointer (CONTEXT.md): "<first 100 chars>..."
```

## What `/sf:wrap` explicitly DOES NOT do

- Run automatically. Invoked by the user only.
- Block session exit. After it completes, the session can continue or end.
- Compete with claude-mem's SessionEnd capture (different layer; per ADR-002 + ADR-009).
- Modify CLAUDE.md (that's `/revise-claude-md`'s job per the claude-md-management plugin; see ADR-009 §"Coexistence with `/revise-claude-md`").
- Edit settings.json or any system-prompt-cached layer (per ADR-008 discipline).
- Promote routine debugging or coding to the wiki. The high-signal threshold is the discipline.

## Failure-degradation modes (per lifecycle plan §5)

| Failure | Behavior | User-visible |
|---|---|---|
| Session transcript unreadable | Abort cleanly | "No session log found; nothing to wrap" |
| High-signal classifier returns nothing | Zero wiki edits; STILL write feed entry (timestamp + project + files) | "No wiki changes; feed entry written" |
| Wiki write mid-batch fails | `git restore wiki/` rollback; show would-have-been diff; defer feed | Retry instructions |
| Feed push conflict | Feed retries; on N=3 failures returns `queued=True`; wrap surfaces it | "feed push deferred; will retry next session" |
| Feed auth/network failure | Same as conflict | Same |
| `--skip-feed` or `SF_SKIP_FEED=1` | Wiki writes only; no feed call | "feed skipped: \<reason\>" |
| Format violation in summary | One LLM re-prompt; on second failure abandon feed, keep wiki | "feed entry rejected (format); wiki saved" |

## Implementation note

V1 implementation lives in `skills/sf-wrap/lib/`. Imports `feed.*` from the `feed/` module. During development, `feed.feed_write_session_end_fake` + `feed.is_skip_active` (real impl) from feed-2's stub branch are used; the imports swap to real impls when feed/ Task #19 lands.

The signal-threshold classifier is implemented in `references/signal-threshold.md` as a structured prompt the LLM evaluates against the session transcript. See that doc for the exact criteria.

## References

- ADR-004 (Wiki Design Hierarchical) — directory shape we write
- ADR-008 (Wake-Up Hook) — the partner; CONTEXT.md is the handoff artifact
- ADR-009 (Consolidate via /wrap) — this skill's design rationale + non-Stop-hook decision
- ADR-014 (Project Sub-Wiki Taxonomy) — page mapping for diff plans
- ADR-018 (Activity Feed) — feed entry format
- ADR-021 (Privacy Boundaries) — terse-format constraint IS the privacy mechanism
- `references/signal-threshold.md` — the classifier criteria
- `references/wiki-page-mapping.md` — signal-label → diff-plan mapping
- `references/feed-call.md` — feed contract usage details
