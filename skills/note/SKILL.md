---
name: note
description: |
  Use when the friend wants to pin something mid-session for the eventual
  /sf:wrap to consider promoting to the wiki. Triggers on the /sf:note
  slash command followed by free-text. Cheap (single file append); useful
  when the friend knows "this is worth remembering" but doesn't want to
  break flow with a full wrap. Per ADR-009: companion to /sf:wrap, not
  a wrap itself.
version: 0.1.0
license: MIT

framework_version: "1.0.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "One new bullet appended to wiki/.session-notes/<session-id>.md (or unsessioned-notes.md if no session-id)"
    - "Confirmation line printed to user including the file path"
  budgets:
    turns: 2
    files_written: 1
    duration_seconds: 5
  permissions:
    read:
      - "~/.startup-framework/wiki/.session-notes/**"
    write:
      - "~/.startup-framework/wiki/.session-notes/**"
    execute: []
  completion_conditions:
    - "Target file exists after the run"
    - "The user's text appears verbatim (with timestamp) at the end of the file"
  output_paths:
    - "~/.startup-framework/wiki/.session-notes/"

tags: [companion, mid-session, note, wiki, lifecycle]
related_skills: [sf-wrap, sf-recall]
references_required: []
references_on_demand: []
---

# sf-note

Mid-session pin. The friend says "this is worth remembering for `/sf:wrap`." Skill appends the text as a timestamped bullet to a per-session file. `/sf:wrap` reads this file at session end (per its SKILL.md step 1) and may promote individual pins to the wiki if they meet the high-signal threshold.

## When to use this skill

- Friend invokes `/sf:note <text>` (canonical trigger; everything after the command name is the text)
- Friend says: "pin this", "save that for later", "remember <X>", "note for the wrap" — confirm the text once, then run

## When NOT to use this skill

- Friend wants to consolidate the whole session now → `/sf:wrap`, not `/sf:note`
- Friend wants to look up existing notes → `/sf:recall <query>`
- Empty text after `/sf:note` → refuse with a brief prompt ("What should I pin?")

## Behavior

1. Resolve target file path:
   - Prefer `~/.startup-framework/wiki/.session-notes/<session-id>.md` if a session id is available (from CC's hook-input payload during the running session)
   - Fallback to `~/.startup-framework/wiki/.session-notes/unsessioned-notes.md` if no session id can be resolved
   - Create the parent directory if it doesn't exist (`.session-notes/`)
   - Create the file with a one-line header (`# Session notes — <session-id>` or `# Unsessioned notes`) if it doesn't exist yet
2. Append one bullet:
   ```
   - [<ISO-8601 UTC timestamp>] <user-provided text>
   ```
3. Confirm to user with the file path written: `Pinned to ~/.startup-framework/wiki/.session-notes/<file>.md`

## What this skill does NOT do

- Promote anything to the wiki proper. That's `/sf:wrap`'s job (with high-signal threshold filter).
- Edit existing notes. Each invocation is append-only.
- Sync to any remote. The notes file is local; if the friend wants their wiki backed up they use `/sf:backup`.
- Write outside `wiki/.session-notes/`. The skill is scoped to that one directory.
- Apply any privacy filter to the text. Per ADR-021, format constraint is the privacy mechanism — but ADR-021 applies to the **Activity Feed** terse format, not to local-only session notes. Notes are local; the friend writes whatever helps them remember.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Empty text argument | Refuse, prompt for text | "What should I pin? Usage: /sf:note <text>" |
| Notes directory unwritable | Surface error | "Couldn't write to <path>. Check permissions." |
| Session-id resolution fails | Fall back to unsessioned-notes.md | "Pinned to unsessioned-notes.md (no active session detected)" |

## References

- ADR-009 (Consolidate via /wrap) — defines this skill as a companion
- ADR-014 (Project Sub-Wiki Taxonomy) — `wiki/.session-notes/` lives at master-wiki level (cross-session), not project-level
- `skills/sf-wrap/SKILL.md` § "Step 1. Gather inputs" — consumes these notes
