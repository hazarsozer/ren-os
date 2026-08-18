# Knowledge flows train — live gate wiring + wiki-distiller (#60)

**Date:** 2026-08-18
**Status:** Approved design (brainstorm 2026-08-18, post-0.7.9)
**Decides:** GitHub #60 (wiki-distiller), the wrap durable-gate `no_llm` defect,
the scope-`None` fail_closed bug, and the wrap extraction-starvation gap.

## 1. Evidence (why now)

The #60 decision page (`projects/ren-os/knowledge/architecture/
wiki-distiller-doctrine-first.md`) deferred the distiller to a measurement
window: build it only "if session learnings keep dying in quarantined L1s."
The window's data (wiki `.ren/metrics/2026-08.jsonl`):

- **9 wraps, 2026-08-14 → 2026-08-18: seen=11, gated_out=11, created=0,
  updated=0, suggested=0, held=0.** Nothing landed.
- The three largest sessions (pre-handoff train, both 0.7.9 train sessions)
  wrapped with **seen=0** — no candidates extracted at all.
- `classifier_event` shows nearly every gated-out item died to **`no_llm`**:
  the deterministic fail-closed fallback ran because no `llm_call` was wired,
  and that path can never promote. Killed items include textbook durable
  learnings: the release-process lesson (bump_version), the #63 entry-path
  decision, the secret-literals lesson, the TFlow parser finding, the Hazar
  learning-profile note.
- One genuine `fail_closed` parse bug: verdict `durable` with scope `None`
  → silently discarded (2026-08-14, signal-dashboard deploy item).
- Structural cause of `no_llm`: `llm_call` is a Python callable, but the wrap
  skill drives `wrap_session()` through a one-shot `uv run python` invocation
  — no LLM is reachable inside that process. This reproduces the donor 0.1
  finding verbatim: "an LLM prompt/parse path was built but never wired in,
  while a deterministic heuristic quietly did all the real work."
- Meta-evidence (2026-08-17): the #60 decision itself lived only in an issue
  comment + spec file; `/ren:recall` missed it when asked.

**Ruling on the confound:** the measurement criterion is met on its face but
confounded — learnings died because the pipeline was broken, not because the
doctrine-first step was fairly tried. Decision (Hazar, 2026-08-18): fix the
wiring AND build the distiller in one train; the distiller's first run
re-mines the dead backlog.

## 2. Part A — live-wrap gate wiring

### 2.1 Classifier subagent

When `/ren:wrap` has extracted ≥1 candidate durable item, the live session
spawns **one** classifier-class subagent (batched — one spawn regardless of
item count, per agent-economics doctrine). The subagent receives:

- `lib/classifier.py`'s exact `CLASSIFIER_PROMPT` per item (one shared prompt
  discipline for all producers — see §3.3),
- the session's eligibility set (wake-up injections + `/ren:recall` fetches,
  verified on disk) so `update` verdicts can name a legal `target_page`.

It returns strict verdict JSON, one decision per item.

### 2.2 Verdicts as data

`wrap_session()` gains a `verdicts=` parameter: pre-computed decisions keyed
by item **index** (positional, matching `durable_items` order — never by item
text, which can duplicate). Validation reuses the exact shape discipline `classify_llm` applies
to an LLM response (`VALID_VERDICTS`, scope/action/target checks). A
malformed verdict falls back to deterministic **for that item only**, with a
`classifier_event` logged. `llm_call` stays supported unchanged — `verdicts`
is the transport that works from a one-shot `uv run`.

### 2.3 Die loudly, not silently

Two fail-path changes, both preserving "never auto-write on uncertainty":

- **Scope-`None` bug:** a `durable` verdict with invalid/missing placement is
  no longer silently gated out — it lands in the suggestions store as a held
  item ("classifier said durable but couldn't place it") for Hazar to place.
- **Spawn failure:** if the classifier subagent cannot be spawned or returns
  garbage wholesale, all candidates route to the suggestions store rather
  than dying to the deterministic fallback.

Fail-closed keeps meaning "don't auto-write"; it stops meaning "discard
unheard."

### 2.4 Extraction floor

Wrap SKILL step 2 gains concrete extraction triggers: recorded rulings,
closed issues, releases cut, decisions made in chat. "When in doubt, extract
fewer" stays for judgment calls, but a session with commits/closures that
wraps with `seen=0` must log a one-line reason.

## 3. Part B — the wiki-distiller (#60)

Built to spec §6 of `2026-08-14-wrap-knowledge-flow-design.md` (interface
stub), with the cadence + model class that section deferred.

### 3.1 Shape

- New agent **`ren:ren-distiller`** (worker-class).
- Thin skill **`/ren:distill`** that drives it on demand.
- A **weekly v3 routine-spec** (schema per `/ren:routine-init`): schedule
  weekly; exit criterion = watermark caught up or write cap hit; failure
  handler = log + watermark untouched; capability allowlist = read wiki,
  write only via the queue.

### 3.2 Input

L1 narratives newer than a stored watermark
(`wiki/.ren/state/distiller-watermark.json`, holding the last processed L1's
write ts), **including quarantined ones** — read-only, pre-escaped via
`lib.memory.quarantine.escape_untrusted` — plus wrap's applied/held write
records (journal) for those sessions, so the distiller never re-proposes
what already landed.

### 3.3 Engine

The worker agent mines each L1 for candidate durable items (this gives the
`seen=0` starvation a second chance: it reads the narrative, not the live
session's memory) and drafts CREATE/UPDATE content. Per-item durable
verdicts go through **classifier-class** calls using the same shared prompt
as Part A — one classifier discipline, two producers. UPDATE eligibility is
widened per spec §6: pages surfaced in the L1s' own sessions (from the
surface log).

Model routing (model-classes doctrine): judgment work (reading, extraction,
drafting, merge content) at worker tier; scoring (verdicts) at classifier
tier; no orchestrator-class seat.

### 3.4 Output

Proposals through the single write door, `producer="distiller"`, same
trust-user hold rule as wrap (updates to `ren_trust: "user"` pages are never
auto-applied — suggestions store). UPDATEs go through the existing strict
`merge.py` path; every write is revertible and quarantine-stamped as usual.

**Per-run cap: 10 writes.** The remainder stays behind the watermark for the
next run, and the cap event is logged — no silent truncation.

### 3.5 First run — backlog rescue (acceptance test)

Watermark seeded at **2026-08-03** (first recorded `no_llm` kill). Run
on-demand via `/ren:distill` with Hazar watching. Acceptance: it must
recover the known-dead learnings by name — the release-process lesson, the
#63 entry-path decision, the secret-literals lesson, the TFlow parser
finding. May take multiple capped runs to drain.

## 4. Part C — instrumentation, exit criteria, testing

### 4.1 Instrumentation

- `durable_outcome` events gain a **`producer`** field (`wrap` | `distiller`)
  so the two paths measure separately.
- New **`distiller_run`** event: sessions read, candidates extracted,
  verdicts by outcome, writes applied/capped, watermark before/after.
- `classifier_event` unchanged, but post-train, `no_llm` on a wrap that had
  candidates is a defect signal — `/ren:metric-watch` adds it to its watch
  list.

### 4.2 Exit criteria (0.8 measurement window)

1. `no_llm` ≈ 0 on wraps that had candidates.
2. `created + updated + suggested > 0` over the window — knowledge
   demonstrably flows again.
3. The backlog-rescue run recovers the named dead learnings (§3.5).
4. The #60 question inverts: the next review asks whether the distiller
   should **shrink to a backlog/audit tool**. If live wraps carry the flow
   and weekly distiller runs keep finding nothing new, demotion is the
   recorded **success** condition, not a failure.

### 4.3 Error handling

- Distiller failures never advance the watermark — re-run safe; idempotent
  by construction (the write door plus the journal records it reads dedupe
  re-proposals).
- Wrap subagent spawn failure → candidates to suggestions (§2.3).
- All writes revertible; quarantine rules unchanged.

### 4.4 Testing

TDD throughout:

- Unit: verdict-shape validation including the scope-`None` repro; watermark
  advance/hold semantics; the 10-write cap and carry-over; UPDATE
  eligibility widening.
- Integration: fixture-L1 dry-run of the distiller end to end.
- Live acceptance: the §3.5 backlog rescue.

## 5. Out of scope

- Any change to the quarantine model, trust taxonomy, or write-door
  semantics beyond the `producer="distiller"` value.
- Consolidation of judged semantic findings (0.5.3 territory).
- Auto-promotion into instruction-plane `global/` pages — trust-user hold
  rule unchanged.
- Rewriting `classify_llm` / `llm_call`: the callable path stays as-is.
