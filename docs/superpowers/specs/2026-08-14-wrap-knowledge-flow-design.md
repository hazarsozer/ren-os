# Wrap knowledge-flow — doctrine-first fix for the frozen KB

**Date:** 2026-08-14
**Issues:** #60 (doctrine-first slice), #57 (fix), #39 (fix)
**Status:** approved in brainstorm 2026-08-14 (Hazar); spec review waived by Hazar

## Problem

Wrap is the sole session→knowledge producer, and its durable-item loop can
only `ADD` to global `lessons/<slug>.md` (`skills/wrap/lib/__init__.py:797`).
Consequences:

- Knowledge subtrees are frozen — no producer ever *updates* an existing
  knowledge page, so session learnings die in quarantined L1s (#60).
- The #54 D4 auto-pointer duty (weave new durable pages into the project
  map) is implemented and tested but unreachable: durables never land in
  project scope (#57).
- Facts that age (framework version, release counts) are re-injected by
  wake-up every session with authority and nothing revisits them (#39).

## Decision record (brainstorm outcomes)

1. **Doctrine-first, distiller later.** This train does NOT build the #60
   wiki-distiller. It ships the cheaper step — wrap may UPDATE existing
   knowledge pages — plus the #57 and #39 fixes, specs the distiller's
   interface (§6), and instruments outcomes so the follow-up decision is
   made on data.
2. **#57 placement: project-scoped + lessons hub** (issue option (c)).
3. **#39 freshness: volatile-facts marker + wiki-health sweep** (the
   general mechanism; no update-flow grep in this train).
4. **Update bound: session-surfaced pages only; trust-user targets held.**
   Wrap may update only pages this session mechanically surfaced (wake-up
   injection + `/ren:recall` fetches, both already logged). Updates whose
   target is `trust: user` are never auto-applied — they route to the
   suggestions store.
5. **Mechanism: approach A — extend the existing `gate` classifier**
   (one classification call per item, plus one merge call for
   update-action items only; no second placement pass; no
   breadcrumbs-only deferral).

## 1. Wrap durable loop: scope / action / target

The `gate(item, llm_call)` classifier's structured output grows from
`{verdict, reason}` to:

```
{verdict, reason, scope: "project"|"global", action: "create"|"update",
 target_page: <path>|null}
```

- `target_page` is required when `action == "update"` and MUST be a member
  of the **eligibility set**; it is null for creates.
- **Eligibility set** = pages surfaced to this session: wake-up's
  `wakeup_surface` records ∪ recall's `l3_fetch` records, same-session,
  read from the instrumentation logs. Assembled in code
  (`_eligible_update_targets(session)`), passed to the classifier prompt,
  and re-checked in code after the call — a returned target outside the
  set is treated as malformed output.
- **Fail-closed unchanged:** malformed or uncertain output gates the item
  out, counted in the existing classifier-event stream.
- The write path stops hardcoding `op="ADD"` / `lessons/`:
  - `action=update` → `Proposal(op="UPDATE", page=target_page, ...)`. The
    gate's schema carries no page body, so update items make ONE
    additional `llm_call` (merge call): input = target page body + the
    durable item; output = the full merged body, changing only the
    relevant section, never touching frontmatter (the door stamps
    provenance itself). A malformed merge result (empty, or frontmatter
    tampered) gates the item out — same fail-closed rule.
  - `action=create` → placement per §2.
- **Trust-user hold:** before applying an UPDATE, wrap reads the target's
  `ren_trust`. `user` → the proposal is routed to the suggestions store
  (kind `wrap-update`, payload = proposal + evidence) instead of
  `propose_and_apply`. All other trust classes → normal
  `propose_and_apply` (revertible, per-write snapshot as today).
- Producer stays `wrap`, writer stays `llm-auto`.

## 2. Placement of durable creates (#57)

- **Project in scope:**
  `projects/<slug>/knowledge/lessons/<slug>.md`, with a folder-note hub
  `projects/<slug>/knowledge/lessons/lessons.md` (0.7.2 hub convention:
  `hub: true`, named after its directory) created on first use. Because
  the page is project-scoped, the existing #54 D4 duty auto-pointers it
  into the project map's Decision map — no new code, the dormant duty
  just becomes reachable.
- **No project in scope:** global `lessons/<slug>.md` as today, plus a new
  folder-note hub `lessons/lessons.md` listing every lesson page. Hub
  creation backfills links to all pre-existing `lessons/*.md` pages
  once (idempotent — re-running adds nothing). Hub appends run as an
  isolated link duty (#54 pattern): failure warns, never fails the wrap.
- **No migration** of existing global lessons into projects — that needs
  per-page ownership judgment; distiller-era work (§7).
- Durability bar for creates is unchanged — same gate, same bias toward
  NOT durable (spec §3.1).

## 3. Volatile-facts markers + freshness sweep (#39)

- **Marker syntax** (inline HTML comment, invisible in Obsidian):
  `<!-- ren-volatile: <kind> -->` placed at the end of the sentence
  carrying the aging fact.
- **Kind registry** (shipped in `lib/`, extensible):
  - `framework-version` — ground truth: installed plugin version
    (`pyproject.toml` / plugin cache version).
  - `release-count` — ground truth: `git tag` count in the ren-os repo.
  - Kinds without a registered checker are valid markers but are only
    inventoried, never auto-corrected.
- **Sweep:** `/ren:wiki-health` gains a `stale_facts` check: scan durable
  pages for markers, run each kind's checker, and where the sentence
  disagrees with ground truth, queue a correction through the write queue
  (producer `wiki-health`, writer `routine` — never quarantines
  human-owned pages). Trust-user targets route to suggestions (§1 rule).
  Warn-not-block throughout; unreachable ground truth (no repo, unreadable
  pyproject) skips that kind with a warning, queues nothing.
- **Seeding:** the known stale spots (ren-os map release count,
  `identity.md` `framework_version`) get markers stamped in this train's
  one-time repair session; ingest/wrap page templates document the
  convention. No wiki-wide guessing pass.

## 4. Instrumentation (the measurement that decides #60)

Wrap's result summary and the collect stream record, per session:
durable items seen / created (project vs global) / updated / gated-out /
held-for-suggestion / refused. After a few weeks of dogfood: if updates
flow and `knowledge/` moves again, the distiller shrinks or dies; if
creates still starve, #60 reopens with data.

## 5. Error handling

All reuse wrap's "never fail the close-out" posture:

- Malformed/uncertain classifier output → item gated out (existing).
- Target outside eligibility set → malformed: gated out + logged.
- Target page gone at apply time → write-door lease check fails; recorded
  as held/refused; no crash.
- Hub append / D4 pointer failure → warn, wrap completes (#54 pattern).
- Freshness checker missing ground truth → skip kind with warning.

## 6. Distiller interface stub (for the follow-up train — NOT built now)

- **Input:** L1 narratives since a stored watermark — including
  quarantined ones, read-only, pre-escaped via
  `lib.memory.quarantine.escape_untrusted` — plus wrap's applied/held
  write records.
- **Engine:** the same classifier schema as §1, batched across sessions;
  eligibility set widened to pages surfaced in the L1s' sessions.
- **Output:** proposals through the single write door, producer
  `distiller`, same trust-user hold rule.
- **Cadence + model class:** deferred to the follow-up brainstorm,
  informed by §4's measurements and the agent-orchestration doctrine.

## 7. Out of scope

- Distiller implementation (#60 proper).
- Migrating existing global `lessons/` pages into projects.
- Quarantine-exit fixes #46/#51/#52 (separate bounded fix-train).
- Marker kinds without mechanical checkers (inventory-only is the
  ceiling this train).
- Any change to wrap's L1 / log / ledger / overview / Sessions duties.
- Update-flow version-grep refresh path (superseded by the marker sweep
  unless #39 reopens).

## 8. Testing

- **Classifier evals** (`skills/wrap/eval_cases.json`, the load-bearing
  suite): update-to-surfaced-page; create-project-scoped;
  create-global-fallback; hallucinated target (must gate out);
  trust-user target (must hold); uncertain verdict (must gate out);
  merge-call cases (clean section merge; frontmatter-tampering output
  must gate out).
- **Unit tests:** eligibility-set assembly from wakeup/recall logs;
  placement selection; hub backfill idempotence; marker parsing; both
  checkers against fixture repos; trust-user suggestion routing; §5
  failure modes.
- **Live proof (train close-out):** dogfood wrap on the design session —
  expect ≥1 project-scoped durable under
  `projects/ren-os/knowledge/lessons/` with a D4 pointer in the map;
  seeded markers verified by a `/ren:wiki-health` run.
