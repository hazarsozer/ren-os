# Automated quarantine screening — design spec

**Date:** 2026-08-03
**Status:** approved (brainstorm gate passed; this document is the approved spec)
**Owner:** hazarsozer
**Origin:** 0.6.5 post-upgrade verification session — 43 quarantined pages, growing,
with `release_page` (one page, one human sentence each) as the only exit.

## Problem

Quarantine correctly keeps unreviewed LLM-written pages out of injection and
drafting channels, but the only exit is a per-page human act. In practice the
backlog only grows, so the friend's own ingested project knowledge — the
majority of the quarantined population — stays unsearchable indefinitely.
Ingestion loses its meaning if the ingested data can never be recalled.

## Decision record

Three decisions fixed during brainstorming (2026-08-03):

1. **Release gate:** a page auto-releases only when the deterministic scanner
   (`detect_instruction_shaped`) finds zero hits **and** an LLM judge, above
   `JUDGE_MIN_CONFIDENCE`, verdicts it data-only. Either objecting → suggestions
   store.
2. **Scope:** only `ren_trust: "model"` pages at data-plane paths are eligible
   for auto-release. Foreign-stamped pages and instruction-plane targets
   (`global/`, `decisions/`, `patterns/`, `research/`) always route to the
   suggestions store — never auto-released.
3. **Trigger:** the screen runs inside the ren-wiki-lint agent at `/ren:wrap`
   close-out (after its incremental lint pass), and wake-up's nudge line
   reports the quarantine backlog. No new agent, skill, or cadence surface.

**Doctrine amendment (spec §3.10):** this introduces a bounded *machine* exit
from quarantine alongside the human-only `release_page`. The bound is the
scope + gate above; everything outside it keeps the human gate unchanged.

## Architecture

Two new engine functions in `skills/wiki-health/lib/`, forming a two-phase
protocol (amended from a single `llm_call`-taking function during planning:
the ren-wiki-lint agent invokes the engine via a one-shot subprocess — the
same seam as `run_incremental_lint` — so a Python callable cannot cross the
process boundary):

```
run_quarantine_screen(session: str, cap: int = 20) -> dict
    # Phase 1: filter + deterministic scan. Routes ineligible and
    # scanner-hit pages to the suggestions store immediately; returns
    # `candidates`: [{page, prompt}] — one ready-built judge prompt per
    # clean eligible page.

apply_quarantine_verdicts(session: str, verdicts: dict[str, dict]) -> dict
    # Phase 2: strict-parses the agent's per-page verdicts, re-checks
    # eligibility + scan (state may have changed), then releases or
    # routes to suggestions. Invalid verdicts fail closed (page stays
    # quarantined).
```

The agent judges each `candidates[*].prompt` with its own reasoning (the
framework itself never makes LLM calls) and passes the verdict objects back
to phase 2.

### Eligibility filter

Worklist = `quarantine.quarantined_rel_pages(wiki_root)` minus:

- pages whose frontmatter `ren_trust` ≠ `"model"` — unstamped or malformed
  frontmatter counts as ineligible (fail closed);
- instruction-plane paths: `global/`, `decisions/`, `patterns/`, `research/`
  (the same list `propose_and_apply` holds for human approval);
- `l1/` pages (already covered by the wake-up L1 injection exemption; L1
  lifecycle is wrap's concern);
- `raw/` and dot-dirs (already excluded by `quarantined_rel_pages`).

Ineligible-but-quarantined pages (foreign, instruction-plane) are not silently
dropped: each gets a one-time suggestions-store entry (fingerprint-deduped) so
the friend eventually decides them.

### Two-stage gate (per eligible page)

1. **Deterministic scan** — `detect_instruction_shaped(body)`. Any hit →
   suggestion carrying the matched snippets as evidence; the page is never
   judged and never released.
2. **LLM judge** — phase 1 builds each candidate's judge prompt via a new
   `lib.memory.judge.build_data_only_prompt(text)`, which wraps the page
   content in `escape_untrusted()` (fence-breakout-proof), so the page cannot
   prompt-inject its own judge. The agent answers each prompt with strict
   JSON; phase 2 parses via `lib.memory.judge.parse_data_only_verdict`
   (mirrors `judge_pair`'s strict-parse discipline, raises `JudgeError` on
   anything malformed). Verdict contract: `data_only: bool`,
   `confidence: float`, `reason: str`. Release requires `data_only == True`
   and `confidence >= JUDGE_MIN_CONFIDENCE`. Anything else → suggestion with
   the verdict as evidence. A page whose full text exceeds the judge's
   truncation window (`JUDGE_MAX_TEXT_CHARS`) is routed to a suggestion with
   `why="too-long"` before either stage runs — the judge only ever sees the
   text's tail, so an unjudged head must never ride a tail-only verdict to
   release.

### Machine release path

New `release_page_auto(page, session, evidence)` in `skills/wiki-health/lib/`,
beside the human-only `release_page`:

- proposes the banner-stripped content through the normal queue:
  `op="UPDATE"`, `producer="retrospective"`, `writer="retrospective"`,
  `reason="quarantine-screen-release"`. (Amended during planning from
  `producer="wiki-health"` / `writer="llm-auto"`: the queue's producer
  whitelist has no wiki-health class — the human `release_page` uses
  `"retrospective"` for the same reason — and the queue banner-marks ALL
  `llm-auto` ADD/UPDATE content at the door, so an `llm-auto` release would
  re-quarantine itself. `trust_class("retrospective", …)` still derives
  `"model"`, so the released page's trust is unchanged as required.);
- completes via `approve_and_apply(qid, who="agent:quarantine-screen")` —
  the actor string is the audit handle;
- `ren_trust` untouched (stays `model`); no residual body marker — the banner
  comes off clean, auditability lives in provenance and the journal;
- a `contradicts` hold is returned as `held`, never forced.

### Suggestions entries

Kind `structured_action`, payload
`{"action": "quarantine_release", "page": <rel path>, "evidence": <scan hits | judge verdict | ineligibility reason>}`,
fingerprint `quarantine:release:<page>` — a rejected page does not reappear
every wrap. Approving in `/ren:suggestions` invokes the existing **human**
`release_page`; the machine path is never used for pages the friend decided
personally.

### Surfaces

- **ren-wiki-lint report** gains a `quarantine_screen` block:
  `released`, `suggested`, `held`, `skipped_remaining`.
- **Wake-up nudge** extends to report the quarantine backlog
  (`quarantined_rel_pages` minus `l1/`) alongside unlinted journal entries.
- **wiki-health sweep** adds a "machine-released since last sweep" count from
  the journal. Doctor gets nothing new.

## Data flow

wrap close-out → spawns ren-wiki-lint (existing seam) → incremental lint
(unchanged) → `run_quarantine_screen(session, cap=20)` (filter + scan; hard
routes → suggestions; clean pages → judge prompts) → the agent judges each
prompt with its own reasoning → `apply_quarantine_verdicts(session, verdicts)`
(strict parse → queue release **or** suggestion) → agent report → next
wake-up shows the shrunken backlog; next `/ren:suggestions` shows held pages.

**Cap:** at most `cap` (default 20) pages screened per run; the remainder is
explicitly reported in `skipped_remaining` — no silent truncation. The current
43-page backlog drains in ~2–3 wraps.

## Error handling

Fail closed, always toward "stays quarantined":

- judge exception or unparseable verdict → page skipped, counted in
  `skipped_remaining`;
- queue conflict → `held`, reported;
- unreadable page → skipped;
- crash mid-run loses nothing: there is no watermark — the worklist self-heals
  (released pages leave `quarantined_rel_pages`; rejected pages are
  fingerprint-deduped in the suggestions store).

The screen never edits page content beyond banner removal.

## Non-goals (v1)

- Editing a page to strip its instruction-shaped parts — that is a human edit
  through the normal wiki flow.
- Releasing foreign-stamped or instruction-plane pages automatically — always
  a human decision via suggestions.
- L1 lifecycle changes — the L1 injection exemption already covers continuity.
- A new shipped agent or scheduled routine — rejected during brainstorming in
  favor of extending the existing wrap-close-out hygiene seam.

## Testing

TDD per the execution doctrine; every box below lands as a failing test first.

**Unit**
- Eligibility: foreign / instruction-plane / `l1/` / unstamped / malformed
  frontmatter never pass, even with clean content.
- Scanner hit → suggestion with matched snippets; page not judged.
- Judge reject and judge low-confidence → suggestion with verdict evidence.
- Judge pass → released; provenance `who == "agent:quarantine-screen"`;
  `ren_trust` unchanged; banner gone; body otherwise byte-identical.
- Judge exception → fail-closed skip, counted in `skipped_remaining`.
- Cap honored; remainder reported.
- Fingerprint dedup: a rejected page is not re-suggested on the next run.
- Revert round-trip: undoing the machine release via provenance restores the
  banner exactly.

**Integration**
- Fixture wiki with a mixed population (clean model-trust page, injection-
  shaped page, foreign page, instruction-plane page, l1 page) + scripted fake
  `llm_call`; assert the end state page-by-page.
- A page containing its own backtick fences cannot break out of the
  `escape_untrusted` wrapper passed to the judge.

**Live smoke (post-merge)**
- Real `/ren:wrap` on the dev Mac against the 43-page backlog; verify report
  counts, wake-up backlog shrink, and suggestions entries.
