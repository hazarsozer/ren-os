---
name: note
description: |
  Use when the friend wants to pin something mid-session for the eventual
  /ren:wrap to consider promoting to the wiki. Triggers on the /ren:note
  slash command followed by free-text. Cheap (single file append); useful
  when the friend knows "this is worth remembering" but doesn't want to
  break flow with a full wrap. Per ADR-009: companion to /ren:wrap, not
  a wrap itself.
version: 0.1.0
license: MIT

framework_version: "1.0.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "Default mode: one new bullet appended to wiki/.session-notes/<session-id>.md (or unsessioned-notes.md if no session-id)"
    - "Instinct mode (--instinct <kind>): one typed bullet appended to the routed instincts.md (project sub-wiki by default; master wiki on --global or when no project is resolvable)"
    - "Confirmation line printed to user including the file path (and scope, in instinct mode)"
  budgets:
    turns: 2
    files_written: 1
    duration_seconds: 5
  permissions:
    read:
      - "~/.startup-framework/wiki/.session-notes/**"
      - "~/.startup-framework/wiki/instincts.md"
      - "~/.startup-framework/wiki/projects/**/instincts.md"
    write:
      - "~/.startup-framework/wiki/.session-notes/**"
      - "~/.startup-framework/wiki/instincts.md"
      - "~/.startup-framework/wiki/projects/**/instincts.md"
    execute: []
  completion_conditions:
    - "Target file exists after the run"
    - "The user's text appears verbatim (with timestamp) at the end of the file"
  output_paths:
    - "~/.startup-framework/wiki/.session-notes/"
    - "~/.startup-framework/wiki/instincts.md"
    - "~/.startup-framework/wiki/projects/<project>/instincts.md"

tags: [companion, mid-session, note, wiki, lifecycle]
related_skills: [wrap, recall]
references_required: []
references_on_demand: []
---

# note

Mid-session pin. The friend says "this is worth remembering for `/ren:wrap`." Skill appends the text as a timestamped bullet to a per-session file. `/ren:wrap` reads this file at session end (per its SKILL.md step 1) and may promote individual pins to the wiki if they meet the high-signal threshold.

## When to use this skill

- Friend invokes `/ren:note <text>` (canonical trigger; everything after the command name is the text)
- Friend says: "pin this", "save that for later", "remember <X>", "note for the wrap" — confirm the text once, then run
- Friend invokes `/ren:note --instinct <kind> <text>` (kind ∈ worked | avoid | dont-repeat) to capture a durable **instinct** into the hot-tier `instincts.md` (C3a). Add `--global` to route to the master wiki instead of the current project. Friend phrasings: "remember this lesson", "don't let me repeat X", "that worked, keep it".

## When NOT to use this skill

- Friend wants to consolidate the whole session now → `/ren:wrap`, not `/ren:note`
- Friend wants to look up existing notes → `/ren:recall <query>`
- Empty text after `/ren:note` → refuse with a brief prompt ("What should I pin?")

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

### Instinct mode (`--instinct <kind>`, C3a hot tier)

When the invocation carries `--instinct <kind>` (optionally `--global`), route to the durable instincts tier instead of session-notes:

1. Validate `<kind>` ∈ `worked | avoid | dont-repeat`; reject otherwise with the valid set.
2. Resolve scope: **project by default** → `wiki/projects/<project>/instincts.md` (resolve the current project the same way `/ren:wrap` and `/ren:recall` do). `--global`, or **no resolvable project**, → master `wiki/instincts.md` (announce the fallback).
3. Create the file from the page-type template (frontmatter `type: instincts`, `schema_version: 1`, `scope`) on first write; append a typed bullet otherwise: `- **[<kind>]** YYYY-MM-DD — <text>`.
4. Confirm with the resolved path **and** scope: `Captured [<kind>] instinct → <path> (<scope>)`.

The pure logic lives in `lib/__init__.py` (`pin_instinct`, `resolve_instinct_path`, `instinct_scope`); pass the resolved `wiki_root`, `project_slug`, and `framework_version` (via `lib.sf_paths`).

## What this skill does NOT do

- Promote anything to the wiki proper. That's `/ren:wrap`'s job (with high-signal threshold filter).
- Edit existing notes. Each invocation is append-only.
- Sync to any remote. The notes file is local; if the friend wants their wiki backed up they use `/ren:backup`.
- Write outside its declared paths. Default mode writes only `wiki/.session-notes/`; `--instinct` mode writes only the routed `instincts.md` (project sub-wiki or master). Nothing else.
- Promote, dedup, or consolidate instincts. Capture is append-only; the governed hot→curated sweep is a separate future slice (C3b), proposal-diff-gated per ADR-031.
- Apply any privacy filter to the text. Per ADR-021, format constraint is the privacy mechanism — but ADR-021 applies to the **Activity Feed** terse format, not to local-only session notes. Notes are local; the friend writes whatever helps them remember.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Empty text argument | Refuse, prompt for text | "What should I pin? Usage: /ren:note <text>" |
| Notes directory unwritable | Surface error | "Couldn't write to <path>. Check permissions." |
| Session-id resolution fails | Fall back to unsessioned-notes.md | "Pinned to unsessioned-notes.md (no active session detected)" |
| `--instinct` with an invalid kind | Refuse; nothing written | "Invalid kind. Use one of: worked, avoid, dont-repeat" |
| `--instinct` with no resolvable project | Route to master `wiki/instincts.md` | "Captured to global instincts (no project detected)" |

## References

- ADR-009 (Consolidate via /wrap) — defines this skill as a companion
- ADR-014 (Project Sub-Wiki Taxonomy) — `wiki/.session-notes/` lives at master-wiki level (cross-session), not project-level
- ADR-037 (Compounding Memory Model) — the instincts hot tier this skill captures into (C3a)
- `docs/superpowers/specs/2026-06-28-c3a-instincts-design.md` — C3a design spec
- `skills/wrap/SKILL.md` § "Step 1. Gather inputs" — consumes these notes
