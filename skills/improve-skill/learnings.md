---
title: "sf-improve-skill learnings (per-skill feedback log)"
type: skill-learnings
parent_skill: sf-improve-skill
version: 0.1.0
date: 2026-05-28
---

# sf-improve-skill — learnings

Per ADR-011's optional pattern: this file accumulates lessons learned during the skill's evolution. The `/sf:improve-skill` loop (ADR-012) appends here when it discovers patterns. Friends running `/sf:improve-skill` normally don't see this file unless something surfaces a related issue.

> **For the team-wide discussion of the "validate against real contract instances" pattern**, see `docs/PATTERNS/test-against-real-contract-instances.md` (authored by onboarding-2 from the originating learnings here). The pattern doc is the **formulated discipline**; this learnings file carries the originating bug context (war story) and other per-skill notes.

## Open log

### 2026-05-29 — sf-improve-skill's own `eval/` is intentionally empty for V1 (eval deferred)

`skills/sf-improve-skill/eval/` ships **empty on purpose**. This skill improves *other* skills via the Karpathy loop, and every framework-shipped skill it operates on has a real, ADR-011-conformant `eval.json` (sf-install, sf-interview, sf-bootstrap-project, sf-wrap, sf-backup, sf-note, sf-recall — all pinned in `lib/tests/test_preflight.py::CANONICAL_EVAL_FIXTURES`). So the **capability works**; only *self-application* (improve-skill improving itself) is deferred.

**Why deferred, not faked (per ADR-012 + team-lead 2026-05-29):** a meta-skill's eval would have to make binary assertions about whether improve-skill *itself* got better — and a trivial/hand-wavy eval.json is **worse than none** for the one skill whose entire job is rigor. False confidence in the rigor tool is a worse failure than an honest, documented gap.

**Candidate assertions considered (and why they don't clear the bar yet):** the genuinely *binary, deterministic* properties of improve-skill — preflight refuses on missing/malformed eval; `--autonomous` requires `--max-iterations` + `--max-budget-usd`; dirty tree refused; non-improving iteration reverts; loop never exceeds `--max-iterations` — are **already covered by unit tests** in `lib/tests/test_preflight.py`. An `eval.json` re-asserting them is redundant scaffolding. The genuinely *new* thing an eval would test is the **end-to-end loop quality** (did the LLM's edit actually improve the body?), which is non-deterministic and not cleanly binary — exactly the thing that's hard to assert WELL. Until there's a deterministic, non-trivial behavioral assertion that the unit tests don't already cover, the eval stays deferred.

**Revisit trigger:** if a future change introduces loop behavior that is (a) binary, (b) deterministic, and (c) not already unit-tested, author `eval/eval.json` then and add it to `CANONICAL_EVAL_FIXTURES`. See `eval/README.md` for the in-tree marker and ADR-012 for the loop design.

### 2026-05-28 — Validate against real contract instances, not assumed shapes (load-bearing)

**Context.** First ship of `_validate_eval_file` (in `lib/preflight.py`) drifted entirely from ADR-011's canonical eval.json schema:

| Field | I assumed | ADR-011 actually specifies |
|---|---|---|
| Top-level key | `test_cases` | `tests` |
| Per-test assertions key | `assertions` | `binary_assertions` |
| Assertion items | objects with `binary: true` field | unambiguous string statements |

**Impact**: had this shipped, `/sf:improve-skill` would have rejected EVERY framework-shipped skill (sf-install, sf-interview, sf-bootstrap-project, sf-wrap) on pre-flight gate 2 — the loop would never run on any of our own skills. **The most-used skill across the framework would have been unusable on the most-shipped skills.**

**How it was caught**: onboarding-2's `REVIEW.md` cross-team review pass. Their `inspect.signature`-against-real-symbols pattern + their contract-drift tests caught this exact class of bug before. (Earlier the same week, the same root cause produced the polymorphic-vs-split-feed-writer drift.)

**Root cause (one sentence)**: I wrote the validator against my in-memory model of what ADR-011 should say, instead of opening ADR-011 and reading what it actually says.

**The fix**: rewrote `_validate_eval_file` to use the canonical `tests` / `binary_assertions` / string-items shape. Added `TestCanonicalEvalFixtureConformance` — a parametrized pinning test that loads every framework-shipped eval.json (originally 4: sf-install, sf-interview, sf-bootstrap-project, sf-wrap; expanded to 7 on 2026-05-29 per review §M3 to add sf-backup, sf-note, sf-recall) and asserts the validator accepts them. If the validator drifts again, ALL fixtures fail simultaneously, fire-alarm style.

**The pattern (for the team)**:

> **When implementing against a contract, always validate against a real instance of the contract, not your in-memory model of what the contract should be.**

Concrete techniques that make this load-bearing:

1. **Open the canonical doc + read the schema verbatim** before writing the validator. Don't reconstruct from memory. ADR text is the source of truth; your recollection is not.
2. **Load real-shipped fixtures into your tests.** If your validator passes synthetic test data but rejects every peer's actual file, your validator is wrong. The fixtures are the ground truth.
3. **Parametrize across multiple peer fixtures.** Single-fixture tests catch single-source drift; multi-fixture tests catch validator drift because the failure mode is "every peer's file fails simultaneously."
4. **Where applicable, use `inspect.signature` (or equivalent introspection) against the imported real symbol.** Onboarding-2 catches API drift with this; we should too where contracts are Python-callable.

**Process discipline added going forward**:

- Before authoring any validator / parser / consumer of an existing data shape: `grep -nE "schema|format|frontmatter" <canonical-ADR>.md` and READ the relevant section. Quote it verbatim in a code comment.
- Include at least one real shipped instance of the contract in the test suite. If none exist yet (first implementation), document that and add the test when the first real instance lands.
- When discovering drift between your validator and the contract, the validator is wrong unless the contract has changed. Default action: fix the validator.

**Two contract drifts this week with the same root cause**: this one (eval.json schema) and the polymorphic-vs-split feed writer. Both shipped through peer review; both required a coordination intervention. The principle above is the antidote.

### 2026-05-28 — Reader/writer API asymmetry (from /sf:recall integration)

Pattern discovered while integrating with feed-2's API in /sf:recall. Documented here because it generalizes beyond the feed module.

**The asymmetry**: paired read/write APIs against a stateful backend (git, database, distributed file) typically WANT different failure modes:

| Surface | Failure semantic | Rationale |
|---|---|---|
| **Read** (e.g., `feed_read_tail`, `grep_wiki`) | Return empty on missing backend; only specific config errors raise | Reads are inherently safe to attempt; the worst outcome is "no results found." Forcing the caller to wrap every read in try/except for a "no data yet" state pollutes call sites without earning any safety. |
| **Write** (e.g., `feed_write_session_end`, `commit_pending_changes`) | Explicit failure result (FeedWriteResult, BackupResult) WITH specific error categories | Writes have side effects; the caller MUST know whether the write happened and why-not. Categorical errors (e.g., `not-bootstrapped` vs `non-fast-forward`) drive distinct UX branches. |

**Why this matters for `/sf:improve-skill`**: the eval_runner integration has a similar shape coming. `run_evals()` is logically a "read" (it queries the skill's current state against tests) but it ALSO writes (test fixtures may produce side effects, eval logs, etc.). When the run_evals execution layer lands, the API should:
- Return EvalResult with `score=0.0, raw_output=<error>` for runtime failures (asymmetric-read-style: don't raise; let the loop continue with a revert)
- Raise PreFlightError for setup failures (asymmetric-write-style: stop the loop entirely)

**Cross-reference**: feed-2's contract explicitly designed this asymmetry; mirroring it across our own lib code is good API consistency. The feed-2 surface is documented in `feed/README.md`; the wake-up hook (when it lands) will follow the same pattern (read first, never raises on missing; write later, surfaces explicit `FeedWriteResult.violation`).

### 2026-05-28 — Initial design notes (lifecycle-2)

- The Karpathy loop's "one change per iteration + revert on score drop" discipline is the load-bearing safety. Flags (`--max-iterations`, `--max-budget-usd`, shadow turn count) are bounds. Discipline is correctness.
- `--max-turns` does NOT exist as a CC CLI flag in CC 2.1.154. See `references/cc-flag-watch.md` for the watch + ADR-012 amendment for the correction trail.
- Inner sub-runs use `--bare --print --max-budget-usd $REMAINING` so CC enforces dollar cap at the sub-run level; our shadow tracker handles the outer loop's accumulation.
- Budget tracking uses `references/model-pricing.json` (per-plugin-version bumps). Stale-pricing nag in /sf:doctor when `valid_as_of` > 60 days old.
- Git as memory: branch `improve/<skill>/<timestamp>`, one commit per iteration with metadata in commit body, revert via `git reset --hard HEAD~1`, squash-merge only on full success.
