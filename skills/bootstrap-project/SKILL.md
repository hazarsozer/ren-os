---
name: bootstrap-project
description: |
  Use when the friend wants to start a brand-new project's memory — nothing
  to scan yet, just a name. Triggers on the /ren:bootstrap-project slash
  command. Stamps the shared wiki skeleton (additive) and queues an empty L2
  pointer-map for the project. For an EXISTING repo with real code/git
  history, use /ren:ingest-project instead.
version: 0.3.3
license: MIT

framework_version: "0.3.3"
schema_version: 1
type: skill
execution_tier: deterministic

contract:
  required_outputs:
    - "Any missing shared wiki dirs/files stamped (additive, never overwrite)"
    - "One Proposal queued: ADD (or UPDATE) projects/<slug>/map.md, an empty L2 map"
    - "Confirmation line printed to user including the queue id"
  budgets:
    turns: 2
    files_written: 0
    duration_seconds: 15
  permissions:
    read:
      - "~/.renos/wiki/**"
      - "wiki-skeleton/**"
    write: []
    execute: []
  completion_conditions:
    - "A QueueEntry exists at state_dir()/queue/<qid>.json with status=pending, op=ADD or UPDATE, page=projects/<slug>/map.md"
  output_paths: []

tags: [onboarding, project, l2-map, bootstrap, queue]
related_skills: [ingest-project, install, interview]
references_required: []
references_on_demand: []
---

# bootstrap-project

The fresh-project half of the L2 pair. `/ren:ingest-project` scans an existing repo for facts; this skill is for a project with nothing to scan yet — just a name and an empty map to grow into.

## When to use this skill

- Friend invokes `/ren:bootstrap-project <slug>` for a new project with no existing code/history
- Friend says: "start tracking a new project called X", "set up memory for my new idea"

## When NOT to use this skill

- The project already has real code/git history to mine → `/ren:ingest-project [path]` instead (it produces a POPULATED map, not an empty one)
- The friend wants to look something up, not create a project → `/ren:recall`

## Behavior

1. Resolve `project_slug` (kebab-case) and the active `session` id.
2. Call `skills.bootstrap-project.lib.bootstrap(project_slug, session)`:
   - Stamps the shared skeleton (`lib/skeleton.py` against `wiki-skeleton/manifest.yaml`'s `master` profile) into the wiki root — additive only; an already-onboarded wiki is untouched.
   - Assembles an empty L2 map (`skills.ingest-project.lib.assemble_l2` — same frozen schema `ingest` uses, just with empty `knowledge`/`pointers` and a single "project bootstrapped" log line) and proposes it (`ADD` if the map doesn't exist yet, `UPDATE` if it does) at `lib.memory.queue`.
   - Always `producer="promotion"`, `writer="human"` — a human directly asked for this, so it's never quarantined on apply.
3. If the project already has a repo directory on disk, call `lib.adapter.claude_md.write_project_claude_md(repo_root, project_slug)` — stamps the thin RenOS pointer block (managed `ren:` markers, only the block is ever touched) into `<repo_root>/CLAUDE.md`. No repo yet → skip; `/ren:ingest-project` stamps it later.
4. Confirm to the user: `Queued <qid> — bootstrapped projects/<slug>/map.md`.

## Why this reuses `ingest-project`'s `assemble_l2`

Both skills produce the SAME frozen L2 schema (`type: l2-map`, Knowledge / Decision map / Log sections) — bootstrap just starts it empty. Rendering logic lives once in `skills/ingest-project/lib`, reached here via `importlib.import_module("skills.ingest-project.lib")` (the hyphenated directory name isn't a valid Python identifier segment, so a plain dotted `import` statement can't reach it — `importlib.import_module` resolves the string path without that restriction).

## What this skill does NOT do

- Scan anything. There's no repo to scan yet — that's `/ren:ingest-project`'s job.
- Write to the wiki directly. Both the skeleton stamp (additive-only, idempotent) and the map proposal go through their respective owning mechanisms (`lib/skeleton.py`, `lib.memory.queue`) — this skill orchestrates, it doesn't write.
- Populate the Knowledge or Decision map sections. They start empty; `/ren:ingest-project`, `/ren:pin`, or `/ren:wrap` fill them in over time.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| No slug given | Refuse, prompt for a name | "What should this project be called? Usage: /ren:bootstrap-project <slug>" |
| A map already exists for this slug | Proposes `UPDATE` (queued, not silently skipped) | "projects/<slug>/map.md already exists — queued an update instead." |
| Skeleton stamp finds existing user files | Skipped, reported, nothing overwritten | (silent per-file; only new entries are queued) |

## References

- Task 4.4 (`skills/ingest-project/lib/__init__.py`) — `assemble_l2`, the shared L2 renderer
- Task 0.3 (`lib/skeleton.py`, `wiki-skeleton/manifest.yaml`) — the additive skeleton stamp
- Task 2.1 (`lib/memory/queue.py`) — the single write-queue this skill's only write path
- Spec §3.1 L2 — the pointer-map definition
