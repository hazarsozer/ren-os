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
version: 0.7.2
license: MIT

framework_version: "0.7.2"
schema_version: 1
type: skill
execution_tier: worker

contract:
  required_outputs:
    - "One Proposal queued: ADD (or UPDATE) projects/<slug>/map.md, populated from real repo facts"
    - "projects/<slug>/schema.md queued first (type: project-schema) — the project's own taxonomy/conventions, drafted before any knowledge page"
    - "Any distilled durable pages queued under projects/<slug>/knowledge/ (type: project-knowledge; nested paths allowed, every subdirectory with a hub named after the folder, <topic>/<topic>.md), in the same batch, before the map"
    - "The first-session artifact text shown to the user verbatim"
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

Bringing an existing repo's context into the wiki, in one visible artifact. `scan_repo` mines the repo for facts (never writes, never touches the project); the live session turns those facts into `knowledge` (compact facts) and `pointers` (topic → wiki-path#anchor, rendered as `[topic](wiki-path#anchor)`; external `repo:` references keep the arrow form); `ingest` assembles the frozen L2 schema from that and queues it, then hands back the exact text to show the friend.

## When to use this skill

- Friend invokes `/ren:ingest-project [path]` (path defaults to cwd) against a project with real code, a README, or git history
- Friend says: "bring this existing project into the wiki", "set up memory for this codebase I already have"

## When NOT to use this skill

- Brand-new, empty project → `/ren:bootstrap-project <slug>` instead (empty map, no scan)
- Friend wants to re-scan without changing anything → still this skill; `ingest` proposes an `UPDATE` and the queue surfaces a `supersedes` conflict against the prior map for a human to reconcile, it never silently clobbers

## Behavior

1. Resolve the repo path (default cwd) and a project slug (kebab-case, from the repo's manifest name or directory name — caller's choice of derivation).
2. Call `importlib.import_module("skills.ingest-project.lib").scan_repo(repo_root)` — read-only facts: detected languages/package managers/frameworks, entry points, doc inventory, git history summary, size signals. Never writes to the project, never raises on a non-project path (see the carried `scan.py`'s own contract).
3. **Draft the project wiki from the facts — in a worker subagent when possible** (`execution_tier: worker`): the facts JSON is self-contained, so spawn a cheap worker-model subagent (worker-class or classifier-class) with the facts and the drafting spec below, and take its output back. Parse its returned JSON with `lib.adapter.worker.parse_worker_json` — it tolerates a ```json fence or leading prose despite raw-JSON-only instructions, and raises `WorkerOutputError` (carrying the raw text) if the output still isn't valid JSON. Fall back to drafting inline only when subagents aren't available.

   **The drafting model is Andrej Karpathy's LLM Wiki pattern** — every future ingest session should hold these principles:
   > Three layers: **raw sources, write-once by convention** (`projects/<slug>/raw/`) / **LLM-maintained wiki pages dense with cross-references** (`knowledge/`) / **a SCHEMA document defining structure + conventions** (`schema.md`). Ingest touches many pages and maintains cross-refs; lint (wiki-health) finds contradictions, stale claims, and orphans; `index.md` + `log.md` are navigation aids. "The wiki is a persistent, compounding artifact — the cross-references are already there." The human curates sources; **the LLM's job is everything else.**

   Draft in this order (each stage feeds the next):
   1. **Propose the taxonomy** from what the repo/domain actually contains — which `knowledge/` subdirectories exist and what belongs in each (e.g. a game project: `knowledge/entities/characters/`, `knowledge/mechanics/`; a web app: `knowledge/api/`, `knowledge/infra/`). Depth is project-determined; don't force flat, don't force deep.
   2. **Write `projects/<slug>/schema.md` FIRST** (`type: project-schema`, `schema_version: 1`, `project: <slug>`) — the project's own wiki conventions: the taxonomy tree, naming conventions, what `raw/` holds. Bootstrap may have stamped a template stub; ingest's draft is a normal `UPDATE` over it. Future sessions read `schema.md` and follow it; evolving it later is a normal wiki write.
   3. **Hub pages**: every `knowledge/` subdirectory gets a hub named after the folder (`<topic>/<topic>.md`) (`type: project-knowledge` — no new type — with `hub: true` in frontmatter) that summarizes and links its children.
   4. **Leaf pages** at their nested paths (`knowledge/<dir>/<topic>.md`, any depth), frontmatter `type: project-knowledge`, `schema_version: 1`, `project: <slug>`. **Cross-reference sibling pages** — link related leaves to each other, not just up to the hub.
   5. **The map points at hubs** (and top-level `knowledge/*.md` pages), never deep leaves — the map stays a compact index; hubs carry the fan-out.

   Write every page through the same door as the map (`lib.memory.queue.propose_and_apply` with `producer="ingest"`, `writer="llm-auto"`, `op="ADD"`), in the SAME batch as the map, BEFORE calling `ingest` — so the map's pointers can name real, already-written pages and carry their real `write_id`s. What the worker returns:
   - `knowledge: list[str]` — compact, general facts worth remembering (e.g. "Python project using FastAPI + PostgreSQL", "138 commits since 2025-03")
   - `schema_page: dict` — `{"body": "<markdown>"}` for `projects/<slug>/schema.md`, drafted before any knowledge page
   - `knowledge_pages: list[dict]` — hubs + leaves, each `{"name": "<relative path under knowledge/>", "body": "<markdown>"}` (e.g. `"mechanics/mechanics.md"`, `"mechanics/combat.md"`)
   - `pointers: list[dict]` — `{"topic": ..., "path": ..., "anchor": ..., "write_id": ...}` entries indexing the HUB and top-level pages just written (`"path": "projects/<slug>/knowledge/<dir>/<dir>.md"`, `write_id` from the queue entry).
   - `projects/<slug>/raw/` is for the friend's source material (write-once by convention — nothing enforces it — and human-curated); ingest doesn't populate it, but pointers may target existing files there.
   - **Pointer existence rule (founder ruling, issue #20): every pointer must target something that exists.** Either (a) an in-wiki page that already exists or is being created in this same batch, or (b) an external repository reference written `repo:<name>:<path>` (e.g. `repo:flux:src/main.rs`) — those are skipped by the dangling-pointer checks because they are not resolvable in-wiki. **Never invent a future filename.** A pointer at a page nobody has written is a dangling pointer, not a placeholder; `write_id: None` (`unstamped`) is only for a real page that has not been through the queue, never a licence to name a file that does not exist.
   - Do NOT draft project-specific pages into root-level `decisions/` · `patterns/` · `research/`. Those are the instruction plane — general practice only, promotion-gated for every producer (`docs/decisions/2026-08-01-global-tier-promotion-gate.md`); a write there holds pending instead of applying. Project-specific durable knowledge goes under `projects/<slug>/knowledge/`.
4. Call `importlib.import_module("skills.ingest-project.lib").ingest(project_slug, knowledge, pointers, session)` — assembles the L2 map and proposes it through the data-plane door (`producer="ingest"`, `writer="llm-auto"` (trust class `"foreign"`) — scan-derived content is LLM-shaped, so it's quarantine-marked; the write auto-applies immediately since a project map is a non-global page, per the v2.2 pivot), and returns `{"qid": ..., "write_id": ..., "artifact": ...}`.
5. **Pass `repo_root=` to `ingest()`** (the path resolved in step 1) so the repo gets wired to its memory — two side-cars run after the map is applied (issues #15 + #19), both best-effort and neither able to break the ingest:
   - `<repo_root>/CLAUDE.md` gets the thin RenOS pointer block via `lib.adapter.claude_md.write_project_claude_md(repo_root, project_slug)` — same additive `ren:` marker-block contract `bootstrap-project` uses: content outside the markers is byte-for-byte preserved, re-ingest is idempotent, torn markers are a `"conflict"` that touches nothing. The result string comes back as `result["claude_md"]` (`None` when `repo_root` is omitted, `"error"` if a side-car failed).
   - the repo-path↔slug pair is recorded in `state_dir()/projects.json` via `ren_paths.record_project_repo` — `ren_paths.detect_project` consults that mapping BEFORE dir-name matching, so a checkout directory named differently from the manifest-derived slug (`~/Dev/genshin-calculator-dev` vs. slug `genshin-calculator`) still gets its memory injected at wake-up. Without it such a clone is silently orphaned forever; `/ren:doctor`'s `check_orphaned_projects` warns about exactly that state.
6. **Show the friend `artifact` verbatim.** This is the first-session artifact (exit criterion 6's "wow moment") — it always starts with the exact sentence `"I set up your project memory — here's what I captured:"` followed by the full map body, then a closing line confirming the map is already saved and one-step revertible (mentions `write_id`, not an approval command).
7. **Offer to release the map from quarantine.** The map just written is `writer="llm-auto"`, so it's quarantine-marked (step 4) — and per RenOS 0.4.1 trust hardening, a quarantined L2 map is held out of `wake-up`'s context injection until a human reviews it, unlike L1 which stays injected regardless. After showing the artifact, ask the friend whether it looks right; if they confirm, call `importlib.import_module("skills.wiki-health.lib").release_page("projects/<slug>/map.md", session)` — the existing human-act exit from quarantine — and tell them the map is now released and will be pulled into future wake-ups. If they don't confirm (or say nothing), leave it quarantined; it's still saved and revertible, just held out of context until released later.

## Why `writer="llm-auto"` (and bootstrap's is `"human"`)

The knowledge/pointers here are synthesized from raw scan facts by the live session — an LLM inference, however deterministic-feeling. Per spec §3.10, LLM-authored content is data-not-instruction until a human reviews it; `lib.memory.queue.apply` quarantine-marks any `writer="llm-auto"` ADD/UPDATE automatically. `bootstrap-project`'s empty map has no such content (nothing was inferred), so it stays `writer="human"`.

## What this skill does NOT do

- Modify anything in the scanned project during the scan. `scan_repo` is read-only, full stop — see `scan.py`'s own INVARIANTS block. The single write into the repo is step 5's additive `CLAUDE.md` marker block (only when `repo_root` is passed); nothing outside those markers is ever touched.
- Draft the knowledge/pointers itself. That synthesis is the live session's job (it has the facts JSON and the framework's judgment); this skill's `lib` only assembles and queues what it's given.
- Ask a human to approve the map before it's saved. Per the v2.2 data-plane pivot, a project map is a non-global page — it auto-applies immediately (quarantine-marked, since scan-derived content is LLM-shaped) and is one-step revertible, not queued pending for a human diff.
- Port the old ADR-014 7-file taxonomy. That's dead for 0.2; the L2 map is the whole per-project artifact now.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Path isn't a project (no manifest/git/README) | `scan_repo` still returns a complete facts dict with `looks_like_project: false` | Session decides whether to proceed with a thin map or ask the friend to confirm |
| A map already exists for this slug | `ingest` proposes `UPDATE`; queue attaches a `supersedes` conflict against the prior map, then auto-applies (supersedes never holds auto-apply — lineage is recorded in the journal) | "Updating projects/<slug>/map.md — this supersedes the existing map (<write_id>)." |
| Pointer references a page never written through the queue | Renders `(unstamped)` in the Decision map, not a crash — but see the pointer existence rule: the target page must still EXIST, or `/ren:doctor`+`/ren:wiki-health` report it dangling | (visible in the rendered map itself) |
| A `knowledge/<topic>.md` page already exists for that topic | The queue proposes an `UPDATE` and surfaces a `supersedes` conflict, same as the map — never a silent clobber | "Updating projects/<slug>/knowledge/<topic>.md — supersedes (<write_id>)." |

## References

- `skills/ingest-project/lib/scan.py` (carried from donor `skills/ingest-project/scripts/scan.py`) — the read-only scanner
- Task 4.4 (`skills/bootstrap-project/lib`) — the empty-map sibling skill
- Spec §3.1 L2 + §3.8 A-10 — the pointer-map schema and the first-session artifact requirement
- Task 2.1 (`lib/memory/queue.py`) — the single write-queue this skill's only write path
- `docs/decisions/2026-08-01-project-knowledge-subtree.md` (issue #20) — the `projects/<slug>/knowledge/` subtree, the pointer existence rule, and the wake-up trust decision
- `docs/decisions/2026-08-01-hierarchical-project-wiki.md` (issue #20 amendment) — schema.md, nested knowledge/ with hubs, raw/, and the Karpathy LLM-wiki drafting order above
- `migrations/project-knowledge-1/` — relocates pre-0.6.2 flat project pages into `knowledge/`
- Task 2.2 (`lib/memory/semantics.py`) — the supersedes/contradicts/duplicate conflict detection this skill's UPDATE path surfaces
