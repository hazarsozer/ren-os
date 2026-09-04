# The graph is the hierarchy — link convention, write-time fan-out, graph-aware lint and recall (0.8.7)

- **Date:** 2026-09-04
- **Status:** draft, awaiting Hazar's review
- **Builds on:** `docs/decisions/2026-09-04-taxonomy-depth-cap.md` (depth 2 is
  a shelf, hierarchy is links), `docs/superpowers/specs/2026-08-31-concept-tree-routing-design.md`
  (0.8.5 concept routing), `docs/superpowers/specs/2026-08-12-orphan-detection-design.md`
  (inbound-link orphan rule).
- **Source pattern:** Karpathy, *llm-wiki* (gist 442a6bf5, April 2026).

## 1. Problem

Measured against Karpathy's pattern, RenOS matches or exceeds it on the raw
layer, the schema document, index and log, lint breadth, and Obsidian
rendering. It falls short on three things, all the same thing seen from
three sides — **the cross-reference graph is not a first-class object**:

1. **Ingest fan-out.** His ingest "updates relevant entity and concept
   pages across the wiki," 10–15 pages per source. Ours touches the new
   page, its hub, and the schema fence. An existing page is updated only
   when the classifier picks it as the placement for one item
   (`_apply_concept_create`, `_append_facts_bullet`). Nothing ever asks
   "which other pages should now mention this?"
2. **Links as hierarchy.** Links are created in three places only: hub
   glob-backfill (`_ensure_hub`), a single `See: [[node]]` on distilled
   lessons, and whatever ingest's worker drafts. There is no convention for
   a page to name its conceptual parent or its related pages, so the depth-2
   ruling has no mechanism to carry hierarchy with.
3. **Query ignores the graph.** `skills.recall.lib.rank` scores title,
   headings, body, recency, and path kind. Inbound-link count — the signal
   Karpathy names for "which pages are hubs" — is not used anywhere. Lint
   computes inbound links (`_orphan_pages`) and throws the index away.

## 2. Goals and non-goals

Goals:

- A page-body link convention every producer emits and every consumer reads.
- Every durable write fans out to the existing pages it should touch,
  bounded, through the queue, revertible.
- Lint audits the graph (asymmetry, concepts without a page) and recall
  ranks with it.

Non-goals (explicitly rejected, per the depth-cap ruling):

- No `parent:` or `related:` frontmatter field. Links live in the body
  where Obsidian and `_orphan_pages` already see them.
- No directory nesting beyond depth 2, no per-project depth override.
- No wiki-wide migration. Existing pages gain links lazily when touched or
  when the asymmetry auto-fix runs.
- No change to wake-up ranking in this train (it calls `rank`, so it
  inherits the boost for free; anything more is a separate decision).

## 3. Link convention

Every `type: project-knowledge` and `type: lesson` page body carries, in
this order, after the H1:

```markdown
# <Title>

Parent: [[<page-stem>]]

<body…>

## Related
- [[<page-stem>]] — <one clause: why it is related>
```

Rules:

- **`Parent:` names a page, never a directory.** Default parent is the
  page's folder-note hub (`page_types._is_folder_note_hub`); the classifier
  or drafter may pick any other page in the same project when the
  conceptual parent is not the shelf the page sits on. Exactly one parent.
  A hub's parent is its parent hub; a top-level hub's parent is the
  project `map.md`. Hubs at the top of the shelf and `map.md` itself have
  no `Parent:` line.
- **`## Related` is a flat list of wikilinks**, one per line, each with a
  reason clause. Order is insertion order. The section is created on first
  need and never removed when empty (an empty section is a visible "nothing
  linked yet", same spirit as the empty taxonomy fence).
- **Wikilink form, `[[stem]]`**, resolved by basename exactly as
  `skills/wiki-health/lib/lint.py::_resolves` already does. Markdown links
  stay the L2-map and hub-list form; this train does not convert them.
- **Parsing is tolerant.** `lib.memory.links.parse_page_links(text)` returns
  `PageLinks(parent: str | None, related: list[(stem, reason)],
  other: list[stem])` — `other` is every wikilink or resolvable markdown link
  elsewhere in the body. A page with no `Parent:` line parses to
  `parent=None`, never an error. Reading one link is not a behaviour change.

## 4. The link index — `lib/memory/links.py`

One module builds the graph, three consumers read it.

```python
@dataclass(frozen=True)
class LinkIndex:
    outbound: dict[str, set[str]]   # rel posix path -> resolved rel paths
    inbound:  dict[str, set[str]]
    parent:   dict[str, str | None]
    related:  dict[str, list[tuple[str, str]]]

def build_link_index(wiki_root: Path, *, project: str | None = None) -> LinkIndex
def parse_page_links(text: str) -> PageLinks
def render_related(items: list[tuple[str, str]]) -> str
def upsert_related(text: str, stem: str, reason: str) -> str     # idempotent
def upsert_parent(text: str, stem: str) -> str                   # idempotent
```

- Walk and exemptions are `_orphan_pages`'s: every page contributes links;
  dot-dirs skipped; `raw/`, `archive/`, and quarantined pages are in the
  corpus but not candidates. `_orphan_pages` is refactored to consume
  `build_link_index` so there is one resolver, not two. Its findings must be
  byte-identical on the existing fixtures (regression test).
- `project=` narrows the walk to `projects/<slug>/` plus the root files
  that link into it; fan-out and recall use this, lint uses the whole wiki.
- Cost: one pass, regex only, no LLM. On the 400-page dogfood wiki this is
  the same walk lint already pays.

## 5. Write-time fan-out — `lib/memory/fanout.py`

Called after every durable create or accretion that lands under
`projects/<slug>/knowledge/`: wrap's `_apply_concept_create` and
`_durable_create_page`, distill's landing path, and `seed_tree`. Ingest's
worker is told to draft `Parent:`/`## Related` itself (§7) and does not call
fan-out — the draft already touches many pages.

```python
FANOUT_CANDIDATES = 8   # pages the classifier sees
FANOUT_CAP = 5          # edits per landed item

def fan_out(item: LandedItem, project: str, session: str, llm_call, *,
            cap: int = FANOUT_CAP) -> FanoutResult
```

Steps:

1. **Candidates.** Rank the project's knowledge pages against the item's
   title + text with `skills.recall.lib._score_content` (title, headings,
   body overlap — the recall scorer, not a new one). Exclude: the item's own
   page, hubs, `lessons/lessons.md`, quarantined pages, pages already in the
   item's `## Related`. Take the top `FANOUT_CANDIDATES`.
2. **Classify.** One classifier-class LLM call (same `llm_call` shape as the
   wrap classifier; `lib.adapter.worker.parse_worker_json` on the way back)
   with the item and the candidates' first 40 lines each. Verdict per
   candidate: `{"page": stem, "edge": "relate" | "fact" | "none",
   "reason": <clause>, "fact": <one bullet, only when edge == "fact">}`.
   Any parse failure or missing field → the whole fan-out is `unknown`,
   reported, no edits (fail-closed, same as every other classifier in
   RenOS).
3. **Apply, capped.** For the first `cap` non-`none` verdicts, in verdict
   order:
   - `relate`: `upsert_related` on BOTH pages (the item gains
     `[[candidate]] — reason`, the candidate gains `[[item]] — reason`).
     Two proposals, one per page, `op="UPDATE"`.
   - `fact`: the candidate gets `_append_facts_bullet(fact)` (existing
     helper; creates `## Facts` if absent) AND the `relate` edge above.
     The 40-bullet split suggestion fires exactly as it does today.
   - A candidate whose `ren_trust` is `"user"` is never edited: the edit
     becomes a suggestion (`lib.suggestions`, kind `fanout-edit`), same
     hold as the human-owned `schema.md` splice in 0.8.5.
4. **Queue.** Every edit is `propose_and_apply(producer=<caller's producer>,
   writer="llm-auto", reason="fanout: <item write_id>")`. A `contradicts`
   hold stays held; a `supersedes` conflict records lineage and applies,
   as today.
5. **Metric.** One `fanout_event` per landed item:
   `{item, candidates, verdicts: {relate, fact, none}, applied, held,
   unknown_reason}`. `metric-watch` gains a "fan-out silent" signal: items
   landed with zero candidates over a week means the scorer or the walk is
   broken, not that nothing was related.

Budget: a session that lands 3 durable items pays at most 3 small
classifier calls and 15 queued writes. Distill's `WRITE_CAP` counts fan-out
edits, so a capped distill run lands fewer items rather than more writes.

## 6. Graph-aware lint — `skills/wiki-health`

Two new finding keys, both built on `LinkIndex`:

- **`asymmetric_links`** — page A lists B under `## Related` and B's
  `## Related` does not list A. Mechanically safe fix: add the reverse
  bullet with reason `"(reverse of [[A]])"`. The `ren-wiki-lint` agent
  auto-applies this class through the queue like its other safe fixes;
  the sweep report lists them. Human-owned pages (`ren_trust: "user"`) are
  reported, never edited.
- **`unpaged_concepts`** — a taxonomy node from `schema.md` with no content
  page (hub only, the "legacy hand-seeded node" case 0.8.5 special-cases),
  OR a `[[stem]]` that at least three distinct pages link and that resolves
  to nothing. Reported as a suggestion, never auto-created: minting a page
  is model work.

`orphan_pages` keeps its contract and now reads the shared index (§4).

## 7. Producers emit the convention

- **wrap** — `_durable_create_page` and `_apply_concept_create` render
  `Parent:` (the placement node's content page, else the hub) and an empty
  `## Related`, then call `fan_out`.
- **distill** — the same, on both the normal landing path and `seed_tree`.
  Seed-tree's existing `See: [[node]]` line becomes the `Parent:` line;
  nothing else there changes in this train (existing-node accretion stays
  the follow-up it already is — fan-out's `fact` edge delivers the same
  outcome one item at a time, which is the honest way to find out whether
  the bulk path is still needed).
- **ingest-project** — the worker drafting spec (SKILL.md step 3) requires
  `Parent:` on every leaf and hub, and a `## Related` with at least one
  sibling on every leaf. `ingest()` validates with `parse_page_links`
  before queuing; a leaf with no `Parent:` is a drafting error reported in
  `result["link_errors"]`, and the leaf is still written (missing links are
  lint's job to find, not a reason to lose knowledge).

## 8. Recall

`rank` multiplies the existing score by `1 + 0.1 * min(inbound, 5)` where
`inbound` comes from `LinkIndex.inbound` for the page. Hubs are excluded
from the boost (their inbound count is structural, not earned), same
exclusion the 0.8.5 concept-tree boost uses. The retrieval-eval fixture
gains two cases: a well-linked page outranks a fresh unlinked twin; a hub
does not.

`rank`'s signature is unchanged; the index is built once per call and
memoised on `wiki_root` mtime, so wake-up's single call pays one walk.

## 9. Failure modes

| Failure | Behaviour | Visible as |
|---|---|---|
| Classifier output unparseable | no edits, `unknown_reason` set | wrap close-out line "fan-out unknown: …"; `fanout_event` |
| Zero candidates | no LLM call, event recorded | metric-watch "fan-out silent" after 7 days |
| Candidate is human-owned | suggestion, not edit | `/ren:suggestions` |
| Reverse edit contradicts | held, forward edit applied | queue hold, as today |
| Link index cannot walk (I/O) | `Unknown(reason)`; fan-out and boost skip, lint reports | doctor/wiki-health line |

Every path is "reported, never guessed" per `lib/reporting.py`.

## 10. Testing

- `lib/memory/links.py`: parse round-trips, idempotent upserts, index on a
  fixture wiki with known edges, `_orphan_pages` byte-identical before/after
  the refactor.
- `lib/memory/fanout.py`: candidate exclusions; verdict application with a
  fake `llm_call`; cap honoured; human-owned → suggestion; unparseable →
  unknown with zero writes; `fanout_event` shape.
- wiki-health: `asymmetric_links` finds and fixes; never edits user pages;
  `unpaged_concepts` on a fixture taxonomy.
- recall: boost cases in the retrieval fixture; hub excluded; signature
  unchanged (the eval harness's `ranker_fn` contract).
- Producers: wrap/distill/seed-tree create pages carrying `Parent:` and
  `## Related`; ingest validation reports `link_errors` without dropping the
  leaf.
- One end-to-end: land a concept in a fixture project, assert the item page,
  two related pages, and the event.

## 11. Rollout

No migration. First `/ren:wiki-health` after update reports asymmetric
links (expected: many, one-way hub links are not `## Related` so they do not
count) and unpaged concepts. Dogfood: the study project's ingest-draft
(paused this session) is the first producer run under the new drafting
spec; its first `/ren:wrap` is the first fan-out.

## 12. Open questions for review

1. Should `fact` edges be allowed onto `lessons/` pages, or only onto
   concept-node content pages? Draft says concept pages only; lessons are
   episodic and accrete badly.
2. `FANOUT_CAP = 5` vs Karpathy's 10–15 touches: deliberately low for the
   first release, raise once `fanout_event` shows the classifier's `relate`
   precision. Agree?
