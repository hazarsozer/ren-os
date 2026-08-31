# Concept-tree routing — durable knowledge lands in the taxonomy, not the notebook

Date: 2026-08-31
Status: draft, pending friend review
Supersedes nothing; implements the deferred half of
`2026-08-14-wrap-knowledge-flow-design.md` §7 ("distiller-era work") and makes
`docs/decisions/2026-08-01-hierarchical-project-wiki.md` operational.

## 1. Problem

The founder decision of 2026-08-01 describes a Karpathy LLM-wiki: a
project-declared taxonomy in `projects/<slug>/schema.md`, an arbitrary-depth
`knowledge/` tree with a folder-note hub in every directory, and a SCHEMA
document the model reads **on every write**. What ships instead:

- `_durable_create_page` (`skills/wrap/lib/__init__.py:652-657`) has exactly
  two destinations, both a flat `lessons/` directory. It takes no path input.
- The wrap classifier is structurally forbidden from proposing a path for a
  create (`classifier.py:189-191` — `target_page` must be null).
- `skills/wrap/SKILL.md:120` instructs the model to place pages per the
  taxonomy — an instruction the API it must call cannot carry out.
- The distiller reuses the same function; ingest writes only `map.md`; the
  concept tree exists solely where humans built it by hand.

Net effect (the friend's report, verified against source): studying a large
codebase produces a pile of episodic side-notes
(`in-<project>-first-eight-words-of-a-sentence.md`), not a connected,
hierarchical knowledge base about the system.

The purpose ruling for this design: the wiki is **agent-first** — a
persistent, hierarchical, efficient memory layer per Karpathy — with human
legibility as a welcome side effect, not the optimization target. Placement
may therefore be aggressive and automatic; success is judged by retrieval
usefulness and tree growth, not prose polish.

## 2. Decisions taken (with the friend, 2026-08-31)

1. **Purpose**: agent-first memory layer (option a/c).
2. **Taxonomy governance — hybrid (option c)**: the agent may *add* branches,
   leaves, and hubs automatically (data-plane, revertible). *Restructuring* —
   rename, merge, move, delete of existing branches — routes to the
   suggestions store for explicit approval. This mirrors the existing
   two-plane instinct: additive ≈ data plane, restructure ≈ instruction plane.
3. **Two-way routing (option b)**: durable items are classified
   `concept` (structural knowledge about the system → taxonomy) or `lesson`
   (episodic learning about how we work → `lessons/`, unchanged). Not
   everything is conceptual; nothing gets forgotten for failing to be.
4. **Ingest drafts the taxonomy; backfill exists but is manually triggered**
   (a distiller mode, capped, revertible).
5. **Placement mechanism — one call (option A)**: extend the existing wrap
   classifier schema rather than adding a second LLM call or a mechanical
   ranker. Rationale: follows the exact pattern by which `target_page` was
   added (08-14 spec); one call per item; code re-validates everything; a
   mechanical ranker is predicted to die on measurement the way
   prose-derived registries did (4/8 recall, recorded negative result).

## 3. The taxonomy contract (`schema.md`)

`schema.md` stays a normal wiki page (trust-user editable) but gains one
machine-readable region:

    ```taxonomy
    architecture/
      memory-plane/
      instrumentation/
    governance/
    ingestion/
    ```

- **Parser**: new module `lib/memory/taxonomy.py` — parse the fenced
  `taxonomy` block (indentation tree, slug-per-segment), validate (depth cap
  = 2 below `knowledge/` by default, overridable per project in the block
  header later if ever needed — YAGNI for now), diff two trees, classify a
  diff as `additive` (only added paths) vs `restructuring` (anything removed
  or renamed).
- **Prose stays prose**: each branch should carry a one-line "what belongs
  here" description in the surrounding markdown. The classifier prompt gets
  both the tree and these lines — the descriptions are what make placement
  accurate.
- **Blindness is Unknown, not a guess**: no `schema.md`, no parseable
  taxonomy block, or an unreadable file → concept routing for that project is
  `Unknown` per the reporting convention (`lib/reporting.py`). Wrap falls
  back to `lessons/` for every item and the wrap report says so explicitly
  ("concept routing blind: no taxonomy"). Register the wrap surface's
  blindness note in `REPORTING_SURFACES` accordingly.
- Agent edits to `schema.md` go through the write queue like any page.
  Additive taxonomy edits auto-apply; restructuring edits become suggestions.

## 4. Wrap-time routing

### Classifier schema

Output grows to `{verdict, reason, scope, action, target_page, kind,
placement, title}`:

- `kind: "concept" | "lesson"` — required when durable.
- `placement` — taxonomy path (e.g. `architecture/memory-plane`). Required
  when `kind == "concept"` and `action == "create"`; must be null otherwise.
  Valid values: an existing node, or an existing node plus **at most one new
  leaf segment** (the additive rule, enforced in code).
- `title` — required when the placement introduces a new leaf: a 2–4 word
  concept name, slug-checked mechanically. Lessons keep `_slugify`-from-prose.

Prompt additions: the parsed taxonomy tree + per-branch descriptions for the
in-scope project. Guidance text: "a fact about how the studied system is
built or connected is a concept; a fact about how we work, what failed, or
what to avoid is a lesson; when in doubt, lesson" — bias preserves the
existing "bias toward NOT durable / not concept" discipline.

### Fail-closed extensions

Mechanical rejection (not repair) when: `kind` missing/invalid; `placement`
present but not resolvable under the additive rule; `placement` on a lesson
or an update; new-leaf without a valid `title`. A rejected concept item
**falls back to a lesson create** (the fact is kept — routing failed, not
durability) and increments a `placement_rejected` metric so a noisy
classifier is visible.

### Create path

`_durable_create_page` gains an optional validated `placement` argument
(resolved `knowledge/<path>/` target). New-leaf creation is one queued write
group: page + folder-note hub + parent-hub link line + `schema.md` taxonomy
line. All additive, all auto-apply, all revertible as a unit if the journal
supports grouped writes; otherwise as ordered individual writes with the page
last (so a partial failure leaves structure without an orphan page, which
wiki-health already detects).

### Update path

A concept item whose placement resolves to an **existing** node becomes
`action: update` against that node's page — appended fact bullet — reusing
the existing update machinery. The eligibility-set rule for updates is
extended: taxonomy nodes of the in-scope project are always eligible update
targets (they are enumerable and validated, so the original
prompt-injection rationale for the eligibility set is preserved).

**Concepts accrete; lessons multiply.** This is the central behavior change.

## 5. Concept pages

- Page type: **`project-knowledge`**, unchanged — `page_types.py` rule 5
  already types every non-hub, non-lesson page under a project `knowledge/`
  tree as `project-knowledge`, and existing hand-built concept pages carry
  it. No new type is introduced; concept-ness is shape + location.
  (Amended from the draft's `type: concept` during plan grounding: a
  parallel type for identical positions would fork `derive_type`.)
- Shape: frontmatter; one-line definition; `## Facts` bullet list, each
  bullet a standalone fact with `[[links]]` to related nodes; optional
  `## See also`. Rendered for retrieval first: rank()'s heading/title
  matching works on the node name and definition line.
- `rank()` path-kind multipliers gain a `concept` boost comparable to
  `decisions/`/`patterns/` so the tree pays off at wake-up and recall time.
- **Split rule**: wrap never splits a page. When a concept page exceeds
  ~40 fact bullets, wrap raises a suggestion proposing a split
  (restructuring by definition). Threshold is a named constant, not config.
- Hubs: generalize `_ensure_lessons_hub` → `_ensure_hub`, and call it from
  the distiller too (closing the exploration-found gap where distiller
  writes never maintained hubs). L2 `map.md` points at hubs and top-level
  concept pages only, never deep leaves (08-01 decision, unchanged).

## 6. Ingest drafts the taxonomy

`/ren:ingest-project` upgraded to the Karpathy order:

1. Scan (existing read-only miner, unchanged).
2. Live session drafts the taxonomy block + per-branch descriptions into
   `schema.md` **and shows the friend the proposed tree in chat before the
   first write** — the one human gate in ingest, because the initial
   taxonomy shapes everything after it and is cheap to review once (a
   10-line tree) and expensive to review as 30 restructure suggestions
   later.
3. Create branch dirs + hubs (queued writes).
4. Draft initial concept pages for the strongest scan facts (bounded — the
   ingest cap already exists).
5. `map.md` assembled pointing at hubs (extend `assemble_l2`'s pointer
   section; schema unchanged, `schema_version` stays 2 — pointers are
   already free-form lines).

`/ren:bootstrap-project` (nothing to scan) stamps an empty taxonomy block in
the `schema.md` stub so wrap's routing is defined-but-empty rather than
blind, and the first sessions grow the tree additively.

## 7. Backfill: seeding the tree from existing lessons

New distiller mode: `/ren:distill --seed-tree <project>`.

- Manually triggered only; never part of scheduled distillation.
- Reads existing `knowledge/lessons/*.md` for the project; runs each through
  the same extended classifier (so lesson-vs-concept judgment and placement
  validation are one code path, not a fork).
- Conceptual content is written to the tree; the **source lesson stays in
  place**, gaining a `See: [[<concept-node>]]` line — history is annotated,
  never deleted.
- Capped by the existing `WRITE_CAP` per run; re-runnable until the backlog
  is drained (watermark per lesson page, mirroring the distiller's existing
  watermark pattern). Every write revertible as usual.

## 8. Instrumentation & success criteria

Counters via the existing `collect.record` substrate:

- `durable_kind{concept|lesson}` per wrap — is the concept share nonzero?
  (If ~0%, the classifier bias is too conservative or the taxonomy prose is
  too thin — both diagnosable.)
- `placement_rejected` — classifier noise.
- `concept_update_vs_create` — are concepts accreting (healthy) or leafing
  endlessly (taxonomy too flat)?
- Wiki-health already audits `hubless_knowledge_dirs` /
  `unlinked_knowledge_pages`; add `orphan_concept_pages` (concept page not
  linked from its hub) if not already covered by `unlinked_knowledge_pages`
  (verify during implementation; do not duplicate).

Success, measured after real use on the friend's job-codebase project: the
tree exists and grows across sessions; recall/wake-up surface concept nodes
for system questions; lessons keep only genuinely episodic content.

## 9. Out of scope

- Retrieval overhaul — only the `concept` path-kind multiplier (§5).
- Automatic splitting/merging of concept pages (suggestion-gated, §5).
- Any global-tier (cross-project) taxonomy — `lessons/` at global tier is
  unchanged.
- Migrating global lessons into projects (still deferred, 08-14 §7).
- Graphify/code-map integration.
- Changing lesson naming (`_slugify` first-8-words) — cosmetic, separate.

## 10. Failure-degradation summary

| Failure | Behavior | Visible where |
|---|---|---|
| No/unparseable taxonomy | All items → lessons; routing reported blind (Unknown) | wrap report |
| Classifier emits invalid placement | Item kept as lesson; `placement_rejected` counter | metrics, wrap report |
| Partial new-leaf write group | Structure without page, or page pending; wiki-health flags orphans | wiki-health |
| Restructure needed but only additive allowed | Suggestion raised; item placed at best existing node meanwhile | /ren:suggestions |
| Backfill interrupted | Watermark resumes; no lesson ever deleted | distill report |
