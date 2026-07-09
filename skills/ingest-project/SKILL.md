---
name: ingest-project
description: |
  Use when the friend wants to bring an EXISTING project (real code/git
  history) into their wiki as an L2 pointer-map. Triggers on the
  /ren:ingest-project slash command (optional [path]). A read-only scanner
  mines the repo for facts; the live session drafts compact knowledge +
  pointers from those facts; this skill assembles and queues the map, then
  shows the friend the first-session artifact — the visible proof memory was
  captured (spec §3.8 A-10). For a brand-new project with nothing to scan,
  use /ren:bootstrap-project instead.
version: 0.3.1
license: MIT

framework_version: "0.3.1"
schema_version: 1
type: skill
execution_tier: worker

contract:
  required_outputs:
    - "One Proposal queued: ADD (or UPDATE) projects/<slug>/map.md, populated from real repo facts"
    - "The first-session artifact text shown to the user verbatim"
    - "RenOS pointer block present in <project-path>/CLAUDE.md (markers only — content outside them untouched)"
  budgets:
    turns: 4
    files_written: 0
    duration_seconds: 60
  permissions:
    read:
      - "<project-path>/**"
      - "~/.renos/wiki/**"
    write:
      - "<project-path>/CLAUDE.md"
    execute: []
  completion_conditions:
    - "A QueueEntry exists at state_dir()/queue/<qid>.json with status=applied, writer=llm-auto"
    - "The artifact text starts with the exact FIRST_SESSION_LEAD sentence"
  output_paths: []

tags: [onboarding, project, l2-map, ingest, queue, scan]
related_skills: [bootstrap-project, recall, wrap]
references_required: []
references_on_demand: []
---

# ingest-project

Bringing an existing repo's context into the wiki, in one visible artifact. `scan_repo` mines the repo for facts (never writes, never touches the project); the live session turns those facts into `knowledge` (compact facts) and `pointers` (topic → wiki-path#anchor); `ingest` assembles the frozen L2 schema from that and queues it, then hands back the exact text to show the friend.

## When to use this skill

- Friend invokes `/ren:ingest-project [path]` (path defaults to cwd) against a project with real code, a README, or git history
- Friend says: "bring this existing project into the wiki", "set up memory for this codebase I already have"

## When NOT to use this skill

- Brand-new, empty project → `/ren:bootstrap-project <slug>` instead (empty map, no scan)
- Friend wants to re-scan without changing anything → still this skill; `ingest` proposes an `UPDATE` and the queue surfaces a `supersedes` conflict against the prior map for a human to reconcile, it never silently clobbers

## Behavior

1. Resolve the repo path (default cwd) and a project slug (kebab-case, from the repo's manifest name or directory name — caller's choice of derivation).
2. Call `skills.ingest-project.lib.scan_repo(repo_root)` — read-only facts: detected languages/package managers/frameworks, entry points, doc inventory, git history summary, size signals. Never writes to the project, never raises on a non-project path (see the carried `scan.py`'s own contract).
3. **Draft knowledge + pointers from the facts — in a worker subagent when possible** (`execution_tier: worker`): the facts JSON is self-contained, so spawn a cheap worker-model subagent (Sonnet/Haiku-class) with the facts and the drafting spec below, and take its output back. Parse its returned JSON with `lib.adapter.worker.parse_worker_json` — it tolerates a ```json fence or leading prose despite raw-JSON-only instructions, and raises `WorkerOutputError` (carrying the raw text) if the output still isn't valid JSON. Fall back to drafting inline only when subagents aren't available. What gets drafted either way:
   - `knowledge: list[str]` — compact, general facts worth remembering (e.g. "Python project using FastAPI + PostgreSQL", "138 commits since 2025-03")
   - `pointers: list[dict]` — `{"topic": ..., "path": ..., "anchor": ..., "write_id": None}` entries pointing at wiki pages worth cross-referencing (decisions, patterns, research) — `write_id` is `None` until that target page has actually been through the write-queue (renders as `unstamped`)
4. Call `skills.ingest-project.lib.ingest(project_slug, knowledge, pointers, session)` — assembles the L2 map and proposes it through the data-plane door (`producer="promotion"`, `writer="llm-auto"` — scan-derived content is LLM-shaped, so it's quarantine-marked; the write auto-applies immediately since a project map is a non-global page, per the v2.2 pivot), and returns `{"qid": ..., "write_id": ..., "artifact": ...}`.
5. Call `lib.adapter.claude_md.write_project_claude_md(repo_root, project_slug)` — stamps the thin RenOS pointer block (managed `ren:` markers) into `<repo_root>/CLAUDE.md`: a pointer to the project's L2 map plus the recall-doctrine reminder, deferring everything else to the global tier. ONLY the marker block is ever touched; on `"conflict"` (torn markers), tell the friend which file to fix and continue — never force it.
6. **Show the friend `artifact` verbatim.** This is the first-session artifact (exit criterion 6's "wow moment") — it always starts with the exact sentence `"I set up your project memory — here's what I captured:"` followed by the full map body, then a closing line confirming the map is already saved and one-step revertible (mentions `write_id`, not an approval command).

## Why `writer="llm-auto"` (and bootstrap's is `"human"`)

The knowledge/pointers here are synthesized from raw scan facts by the live session — an LLM inference, however deterministic-feeling. Per spec §3.10, LLM-authored content is data-not-instruction until a human reviews it; `lib.memory.queue.apply` quarantine-marks any `writer="llm-auto"` ADD/UPDATE automatically. `bootstrap-project`'s empty map has no such content (nothing was inferred), so it stays `writer="human"`.

## What this skill does NOT do

- Modify anything in the scanned project beyond the `CLAUDE.md` marker block (step 5). `scan_repo` itself is read-only, full stop — see `scan.py`'s own INVARIANTS block.
- Draft the knowledge/pointers itself. That synthesis is the live session's job (it has the facts JSON and the framework's judgment); this skill's `lib` only assembles and queues what it's given.
- Ask a human to approve the map before it's saved. Per the v2.2 data-plane pivot, a project map is a non-global page — it auto-applies immediately (quarantine-marked, since scan-derived content is LLM-shaped) and is one-step revertible, not queued pending for a human diff.
- Port the old ADR-014 7-file taxonomy. That's dead for 0.2; the L2 map is the whole per-project artifact now.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Path isn't a project (no manifest/git/README) | `scan_repo` still returns a complete facts dict with `looks_like_project: false` | Session decides whether to proceed with a thin map or ask the friend to confirm |
| A map already exists for this slug | `ingest` proposes `UPDATE`; queue attaches a `supersedes` conflict against the prior map, then auto-applies (supersedes never holds auto-apply — lineage is recorded in the journal) | "Updating projects/<slug>/map.md — this supersedes the existing map (<write_id>)." |
| Pointer references a page never written through the queue | Renders `(unstamped)` in the Decision map, not a crash | (visible in the rendered map itself) |

## References

- `skills/ingest-project/lib/scan.py` (carried from donor `skills/ingest-project/scripts/scan.py`) — the read-only scanner
- Task 4.4 (`skills/bootstrap-project/lib`) — the empty-map sibling skill
- Spec §3.1 L2 + §3.8 A-10 — the pointer-map schema and the first-session artifact requirement
- Task 2.1 (`lib/memory/queue.py`) — the single write-queue this skill's only write path
- Task 2.2 (`lib/memory/semantics.py`) — the supersedes/contradicts/duplicate conflict detection this skill's UPDATE path surfaces
