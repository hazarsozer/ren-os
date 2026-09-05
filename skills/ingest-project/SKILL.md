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
version: 0.8.7
license: MIT

framework_version: "0.8.7"
schema_version: 1
type: skill
execution_tier: worker

contract:
  required_outputs:
    - "One Proposal queued: ADD (or UPDATE) projects/<slug>/map.md, populated from real repo facts"
    - "projects/<slug>/schema.md queued first (type: project-schema) — the project's own taxonomy/conventions, drafted before any knowledge page, and shown to the friend in chat for a yes before the first write"
    - "One hub page per taxonomy branch queued under projects/<slug>/knowledge/ (type: hub, hub: true, <branch>/<branch>.md), after schema.md and before the map — ingest() queues these itself from schema_page/hub_pages"
    - "Any additional distilled leaf pages queued under projects/<slug>/knowledge/ (type: project-knowledge; nested paths allowed, every subdirectory with a hub named after the folder, <topic>/<topic>.md) — the map never points at leaves, only hubs, so these may queue after the map"
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

Bringing an existing repo's context into the wiki, in one visible artifact — in Karpathy order (spec 2026-08-31 §6): taxonomy first. `scan_repo` mines the repo for facts (never writes, never touches the project); the live session drafts a `schema.md` taxonomy tree and **shows it to the friend in chat for a yes** before anything is written (the one human gate); it then turns the facts into `knowledge` (compact facts), `hub_pages` (one folder-note per branch), and `pointers` (topic → wiki-path#anchor, rendered as `[topic](wiki-path#anchor)`; external `repo:` references keep the arrow form); `ingest` validates the taxonomy, assembles the frozen L2 schema pointing at the hubs, and queues schema.md + hubs + map, then hands back the exact text to show the friend.

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
   1. **Propose the taxonomy** from what the repo/domain actually contains — which `knowledge/` subdirectories exist and what belongs in each (e.g. a game project: `knowledge/entities/characters/`, `knowledge/mechanics/`; a web app: `knowledge/api/`, `knowledge/infra/`). Depth is project-determined; don't force flat, don't force deep — up to the 2-levels-below-`knowledge/` cap (`lib.memory.taxonomy.MAX_DEPTH`, permanent per `docs/decisions/2026-09-04-taxonomy-depth-cap.md`: hierarchy deeper than that is carried by parent/child links inside pages, so leaf pages link their conceptual parent, not just their hub).
   2. **Show the friend the proposed tree in chat and wait for a yes** — render the branches with a one-line "what belongs here" description each, and ask them to confirm before any write happens. **This is the one human gate in ingest** (spec §6): the initial taxonomy shapes everything drafted after it, so it's reviewed once, up front, as a ~10-line tree — not later as a pile of restructure suggestions. If they want changes, revise and re-show; nothing is queued until they confirm.
   3. **Draft `schema_page`** — the full markdown body for `projects/<slug>/schema.md` (`type: project-schema`, `schema_version: 1`, `project: <slug>`): the confirmed taxonomy as a ```taxonomy fence (parseable by `lib.memory.taxonomy.parse_taxonomy`) plus the per-branch prose descriptions. This is passed to `ingest()` as the `schema_page` string — do NOT queue it directly; `ingest()` validates and queues it.
   4. **Draft `hub_pages`** — one folder-note per branch, `{"<branch>": "<markdown>", ...}` (`type: hub`, `hub: true` in frontmatter — the shipped folder-note convention, `_ensure_hub`/`page_types.py` rule 2) that summarizes and will link its children. Also passed to `ingest()`, not queued directly.
   5. **Leaf pages** for the strongest scan facts, at their nested paths (`knowledge/<dir>/<topic>.md`, any depth), frontmatter `type: project-knowledge`, `schema_version: 1`, `project: <slug>`. **Cross-reference sibling pages and their hub** — link related leaves to each other, not just up to the hub. Bounded (the existing ingest cap). Every leaf body MUST carry, after its H1: a `Parent: [[<stem>]]` line naming its hub (or the concept page that is its real conceptual parent), and a `## Related` section with at least one sibling bullet in the form `- [[<stem>]] — <one clause saying why>`. Hubs are the shelf, not a chain: a hub directly under `knowledge/` is the top of the shelf and carries NO `Parent:` line, and neither does the project `map.md`. Only a NESTED hub carries one, `Parent: [[<parent-hub-stem>]]`. Leaves always carry a `Parent:` line. Pass these to `ingest()` as `leaf_pages` (step 5 below); do NOT queue them yourself with `propose_and_apply`. `ingest()` queues them after the hubs, so the hub a leaf names as `Parent:` is already on disk. The map never points at leaves (only hubs and top-level `knowledge/*.md` pages), so this ordering costs nothing.

   What the worker returns: `knowledge: list[str]` (compact, general facts, e.g. "Python project using FastAPI + PostgreSQL", "138 commits since 2025-03"), `schema_page: str` (the drafted markdown body from step 3), `hub_pages: dict[str, str]` (branch → markdown body, step 4), `leaf_pages: list[dict]` (`{"name": "<relative path under knowledge/>", "body": "<markdown>"}`, step 5), and `pointers: list[dict]` (`{"topic": ..., "path": ..., "anchor": ..., "write_id": ...}`) for any additional top-level `knowledge/*.md` pointer the session wrote directly and wants in the map (hub pointers are added automatically by `ingest()` — see step 4 below).
   - `projects/<slug>/raw/` is for the friend's source material (write-once by convention — nothing enforces it — and human-curated); ingest doesn't populate it, but pointers may target existing files there.
   - **Pointer existence rule (founder ruling, issue #20): every pointer must target something that exists.** Either (a) an in-wiki page that already exists or is being created in this same batch, or (b) an external repository reference written `repo:<name>:<path>` (e.g. `repo:flux:src/main.rs`) — those are skipped by the dangling-pointer checks because they are not resolvable in-wiki. **Never invent a future filename.** A pointer at a page nobody has written is a dangling pointer, not a placeholder; `write_id: None` (`unstamped`) is only for a real page that has not been through the queue, never a licence to name a file that does not exist.
   - Do NOT draft project-specific pages into root-level `decisions/` · `patterns/` · `research/`. Those are the instruction plane — general practice only, promotion-gated for every producer (`docs/decisions/2026-08-01-global-tier-promotion-gate.md`); a write there holds pending instead of applying. Project-specific durable knowledge goes under `projects/<slug>/knowledge/`.
4. Call `importlib.import_module("skills.ingest-project.lib").ingest(project_slug, knowledge, pointers, session, schema_page=schema_page, hub_pages=hub_pages, leaf_pages=leaf_pages)` — validates `schema_page` with `lib.memory.taxonomy.parse_taxonomy` first: an unparseable/missing taxonomy fence (`TaxonomyError`) refuses the whole schema/hub write group (no partial tree — nothing is queued for `schema.md` or any hub) and falls back to the existing map-only behavior, reporting why in `result["taxonomy_error"]`. On a valid taxonomy, queues `schema.md`, then each hub page (`projects/<slug>/knowledge/<branch>/<branch>.md`), then the L2 map — in that order, all through the data-plane door (`producer="ingest"`, `writer="llm-auto"` (trust class `"foreign"`) — scan-derived content is LLM-shaped, so it's quarantine-marked; every write auto-applies immediately since these are non-global pages, per the v2.2 pivot). `ingest()` adds one Decision-map pointer per hub automatically (`- [architecture](projects/<slug>/knowledge/architecture/architecture.md)` style, carrying the hub's real `write_id`) — don't hand-build those pointer entries yourself. Returns `{"qid": ..., "write_id": ..., "artifact": ..., "taxonomy_error": ..., "schema_write_id": ..., "hub_write_ids": ..., "link_errors": ...}`. Omitting `schema_page`/`hub_pages` entirely (e.g. re-ingesting a project whose taxonomy is already stable) is a legacy call — behaves exactly as before this section existed.
5. **Pass the drafted leaf pages to `ingest()` as `leaf_pages`** — a list of `{"name": "<relative path under knowledge/>", "body": "<markdown>"}`. Every leaf body MUST carry, after its H1: a `Parent: [[<stem>]]` line naming its hub (or the concept page that is its real conceptual parent), and a `## Related` section with at least one sibling bullet in the form `- [[<stem>]] — <one clause saying why>`. Hubs are the shelf, not a chain: a hub directly under `knowledge/` is the top of the shelf and carries NO `Parent:` line, and neither does the project `map.md`. Only a NESTED hub carries one, `Parent: [[<parent-hub-stem>]]`. Leaves always carry a `Parent:` line. `ingest()` validates each leaf with `lib.memory.links.parse_page_links` and reports failures in `result["link_errors"]`; the leaf is queued either way — missing links are lint's job to find, not a reason to lose knowledge. Do NOT queue leaves yourself with `propose_and_apply`.
6. **Pass `repo_root=` to `ingest()`** (the path resolved in step 1) so the repo gets wired to its memory — two side-cars run after the map is applied (issues #15 + #19), both best-effort and neither able to break the ingest:
   - `<repo_root>/CLAUDE.md` gets the thin RenOS pointer block via `lib.adapter.claude_md.write_project_claude_md(repo_root, project_slug)` — same additive `ren:` marker-block contract `bootstrap-project` uses: content outside the markers is byte-for-byte preserved, re-ingest is idempotent, torn markers are a `"conflict"` that touches nothing. The result string comes back as `result["claude_md"]` (`None` when `repo_root` is omitted, `"error"` if a side-car failed).
   - the repo-path↔slug pair is recorded in `state_dir()/projects.json` via `ren_paths.record_project_repo` — `ren_paths.detect_project` consults that mapping BEFORE dir-name matching, so a checkout directory named differently from the manifest-derived slug (`~/Dev/genshin-calculator-dev` vs. slug `genshin-calculator`) still gets its memory injected at wake-up. Without it such a clone is silently orphaned forever; `/ren:doctor`'s `check_orphaned_projects` warns about exactly that state.
7. **Show the friend `artifact` verbatim.** This is the first-session artifact (exit criterion 6's "wow moment") — it always starts with the exact sentence `"I set up your project memory — here's what I captured:"` followed by the full map body, then a closing line confirming the map is already saved and one-step revertible (mentions `write_id`, not an approval command).
8. **Offer to release the map from quarantine.** The map just written is `writer="llm-auto"`, so it's quarantine-marked (step 4) — and per RenOS 0.4.1 trust hardening, a quarantined L2 map is held out of `wake-up`'s context injection until a human reviews it, unlike L1 which stays injected regardless. After showing the artifact, ask the friend whether it looks right; if they confirm, call `importlib.import_module("skills.wiki-health.lib").release_page("projects/<slug>/map.md", session)` — the existing human-act exit from quarantine — and tell them the map is now released and will be pulled into future wake-ups. If they don't confirm (or say nothing), leave it quarantined; it's still saved and revertible, just held out of context until released later.

## Why `writer="llm-auto"` (and bootstrap's is `"human"`)

The knowledge/pointers here are synthesized from raw scan facts by the live session — an LLM inference, however deterministic-feeling. Per spec §3.10, LLM-authored content is data-not-instruction until a human reviews it; `lib.memory.queue.apply` quarantine-marks any `writer="llm-auto"` ADD/UPDATE automatically. `bootstrap-project`'s empty map has no such content (nothing was inferred), so it stays `writer="human"`.

## What this skill does NOT do

- Modify anything in the scanned project during the scan. `scan_repo` is read-only, full stop — see `scan.py`'s own INVARIANTS block. The single write into the repo is step 6's additive `CLAUDE.md` marker block (only when `repo_root` is passed); nothing outside those markers is ever touched.
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
| `schema_page` doesn't parse (`TaxonomyError` — no/broken `` ```taxonomy `` fence) | `ingest` refuses the whole schema/hub write group — no partial tree — and falls back to the existing map-only behavior; the fact is still saved | `result["taxonomy_error"]` carries the reason; `schema_write_id`/`hub_write_ids` come back empty |
| A drafted leaf has no `Parent:` or no `## Related` sibling | reported, leaf still written | `result["link_errors"]`, and `/ren:wiki-health`'s `asymmetric_links`/`orphan_pages` next sweep |

## References

- `skills/ingest-project/lib/scan.py` (carried from donor `skills/ingest-project/scripts/scan.py`) — the read-only scanner
- Task 4.4 (`skills/bootstrap-project/lib`) — the empty-map sibling skill
- Spec §3.1 L2 + §3.8 A-10 — the pointer-map schema and the first-session artifact requirement
- Task 2.1 (`lib/memory/queue.py`) — the single write-queue this skill's only write path
- `docs/decisions/2026-08-01-project-knowledge-subtree.md` (issue #20) — the `projects/<slug>/knowledge/` subtree, the pointer existence rule, and the wake-up trust decision
- `docs/decisions/2026-08-01-hierarchical-project-wiki.md` (issue #20 amendment) — schema.md, nested knowledge/ with hubs, raw/, and the Karpathy LLM-wiki drafting order above
- `migrations/project-knowledge-1/` — relocates pre-0.6.2 flat project pages into `knowledge/`
- Task 2.2 (`lib/memory/semantics.py`) — the supersedes/contradicts/duplicate conflict detection this skill's UPDATE path surfaces
- `docs/superpowers/specs/2026-08-31-concept-tree-routing-design.md` §3 + §6 — the `` ```taxonomy `` fence contract (`lib/memory/taxonomy.py`) and the Karpathy-order drafting flow this section implements (Task 6)
