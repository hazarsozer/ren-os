---
title: "ADR-029: Test Against Real Contract Instances — Pattern as Doctrine"
status: accepted
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: []
affects-components: [testing, code-review, skills, contracts]
relates-to: [011-skill-schema, 028-locked-build-time-contracts]
---

# ADR-029: Test Against Real Contract Instances — Pattern as Doctrine

## Context

The 2026-05-28 multi-agent build session (4 teammates + team-lead, ~6 hours wall-clock, 60 tasks shipped) surfaced three contract-drift incidents — distinct bugs in distinct teammates' code that all shared the **same root cause**: implementation followed an in-memory model of a contract rather than the canonical written source.

Each incident's implementer had passing unit tests; each incident escaped TDD; each was caught only at integration time or in cross-team review. Three failures of the same kind in one build is a pattern, not a fluke.

The three incidents:

1. **Polymorphic-vs-split feed writer** (feed-2). Peer DM coordination between feed-2 and lifecycle-2 converged on a single-entrypoint `feed_write_entry(kind=...)` shape; team-lead arbitrated for a split (`feed_write_session_start` + `feed_write_session_end` + `feed_write_release`); implementation shipped the polymorphic shape; feed-2's 40+ unit tests validated against the wrong-from-the-start surface; onboarding-2's integration harness using `inspect.signature` against the imported real symbol caught the mismatch at integration time and pointed at the contract doc.

2. **eval.json schema fork** (lifecycle-2). `/sf:improve-skill`'s `_validate_eval_file` enforced `test_cases[].assertions[].binary` (object form); ADR-011 specifies `tests[].binary_assertions: list[str]` (string form); every framework-shipped skill outside lifecycle's modules used the ADR-011 shape; `/sf:improve-skill` was therefore **unusable** on every other framework skill. Lifecycle-2 also had the same wrong shape in their own `skills/sf-wrap/eval/eval.json`, so their internal tests passed (validator and fixture validated each other). Caught in onboarding-2's cross-team REVIEW.md pass.

3. **Timeout-units routing slip** (team-lead). Distribution-2 initially flagged "timeout in ms" as a finding; team-lead routed it to lifecycle-2 without verifying against the JSON Schema first; lifecycle-2 pushed back with verbatim `json.schemastore.org/claude-code-settings.json` evidence ("Optional timeout in seconds"); team-lead retracted. Demonstrated the pattern applies to **triage discipline**, not just authoring.

Without a wiki-indexed doctrine ADR, the antidote pattern lives only in `docs/PATTERNS/test-against-real-contract-instances.md` (which is non-obvious from the wiki index) + per-skill `learnings.md` files (per-team only). Future contributors and future build sessions would need to re-derive the lesson.

## Decision

### Core: validate against canonical contract instances, not in-memory models

When implementing a validator, parser, consumer, or any code that depends on the shape of an existing contract, **open the canonical source, quote verbatim, then proceed**. When triaging a finding from one peer to another, **verify against the canonical source before routing**.

Three complementary failure-catching layers — none sufficient alone — together cover the failure modes observed:

#### Layer 1: Signature drift tests via `inspect.signature` against real symbols

Catches **contract-shape changes** (added/removed/renamed parameters).

Pattern (executable form per `docs/PATTERNS/test-against-real-contract-instances.md`):

```python
import inspect
from feed import feed_write_session_end

def test_feed_write_session_end_signature_drift():
    sig = inspect.signature(feed_write_session_end)
    params = set(sig.parameters)
    expected = {"handle", "project", "task_brief", "files_touched",
                "schema_version", "skip", "timestamp"}
    missing = expected - params
    extra = params - expected
    assert not missing, f"lost param(s): {missing}; sig now: {list(params)}"
    assert not extra, f"unexpected param(s): {extra}; sig now: {list(params)}"
```

Worked example: this exact technique caught incident (1) when onboarding-2's integration harness imported the real `feed.feed_write_session_end` and discovered the polymorphic-shape implementation diverged from the locked spec.

#### Layer 2: Cross-team code review pass

Catches **semantic intent / contract gaps** (the implementation works against the implementer's assumptions, but the assumptions are wrong).

Pattern: a senior peer reads the implementation against the ADR-cited contract (not against the implementer's documentation). REVIEW.md is the canonical worked example — onboarding-2's review of feed-2's, distribution-2's, and lifecycle-2's scopes surfaced 9 findings (1 critical + 1 high + 4 medium + 3 low) that no single teammate's tests would catch.

Worked example: incident (2) — lifecycle-2's `/sf:improve-skill` was internally consistent and 100% test-green, but the eval.json shape was wrong per ADR-011. Only a reviewer reading ADR-011 verbatim alongside the implementation could surface this.

#### Layer 3: Invariant assertion tests

Catches **silent data loss in otherwise-correct flows** (the algorithm "works" but quietly violates a load-bearing invariant the contract requires).

Pattern: after writing behavior tests ("function returns X for input Y"), add invariant assertions ("function NEVER violates condition Z"). Examples that landed during this build:

- `test_truncate_preserves_at_least_one_entry_per_friend` (feed F4) — truncation algorithm was correct on aggregate but silently dropped friends with single entries, violating the per-friend-coverage invariant
- `test_diverged_remote_refuses_force_push` (lifecycle backup) — backup never force-pushes; the test pins the negative
- `test_check_auth_does_not_include_show_token_flag` (feed F1) — security invariant against the existence of a dangerous flag in argv
- `test_read_only_no_modifications` (lifecycle /sf:recall) — sha256-invariant check that the function does not mutate disk state

Worked example: incident (1)'s F4 medium finding — feed-2's truncation tests verified output sizes and total counts, but no test verified the per-friend coverage invariant that motivated the architecture. The cross-team review surfaced it; the invariant test now pins it.

### Triage discipline (the load-bearing extension)

The discipline applies to **routing** as well as authoring. When a peer reports a finding, before forwarding to another peer:

1. Open the canonical source
2. Quote verbatim
3. Verify the finding matches the canonical source
4. Only then route

Triage failures are harder to mechanize (no executable artifact), so the enforcement mechanism is **habit, not assertion**. The pattern doc names this explicitly in its v1.2 "the discipline applies to triage" section.

Worked example: incident (3) — team-lead propagated distribution-2's pre-correction finding without checking the JSON Schema. The downstream teammate (lifecycle-2) had to catch + retract it. The cost is small (one extra schema-citation step before each route); the alternative is contributors acting on incorrect routed findings.

### When NOT to apply this pattern

Per the pattern doc:

- **Single-author code with no contract surface** — the discipline targets multi-author coordination; trivial scripts don't need it.
- **Doc-generated-from-code** — when the implementation IS the canonical source, drift against it is impossible.
- **Throwaway scripts** — discipline cost > expected lifetime benefit.
- **Peer hasn't stabilized** — drift tests against an actively-changing contract become noise; wait until the contract locks.

Mechanizing the discipline where it doesn't earn its keep is its own anti-pattern.

## Consequences

**Easier:**
- New skills + modules adopting the pattern get drift detection for free.
- Future cross-team coordination has a named doctrine to reference.
- The three incidents become teaching artifacts, not just history.

**Harder:**
- Every implementer touching a contract surface has one additional discipline step (open canonical source, quote verbatim).
- Every routing step has an additional verification gate.

**Now impossible:**
- Silent contract drift between peer modules that have integration tests using `inspect.signature` against real symbols.
- Treating "tests pass" as sufficient evidence that a contract is honored (the assumption-gap layer requires review, and the invariant-gap layer requires explicit invariant assertions).

**Sunset review trigger conditions:**
- A future build session demonstrates the pattern doesn't catch a fourth contract drift class → reframe.
- Tooling emerges (CC builtin, IDE plugin) that mechanizes Layer 2 (semantic gap review) such that human review becomes optional → revisit.
- Project grows past N teammates where Layer 2 review cost exceeds drift cost → reframe with batched-review cadence.

## Alternatives considered

### A) Leave the pattern at `docs/PATTERNS/` without a wiki-indexed ADR

**Why rejected**: `docs/PATTERNS/` is discoverable by code search but not by the wiki's `index.md` entry point. Future contributors using the wiki as the canonical source-of-design wouldn't see it. Doctrine needs ADR-level visibility.

### B) Capture the pattern only in per-skill `learnings.md` files

**Why rejected**: `learnings.md` are per-skill institutional record. The pattern is cross-cutting — applies to authoring across all skills, to review across all peers, to triage by the team-lead. Pattern-level scope deserves an ADR.

### C) Skip the ADR, rely on the executable pattern doc

**Why rejected**: The pattern doc captures the *how*; the ADR captures the *why* (three drift incidents + their root cause + the sunset triggers). Both layers needed for durable institutional memory.

### D) Embed the pattern lessons inside ADR-011 (skill schema) as amendments

**Why rejected**: The pattern applies to many surfaces (eval.json shape per ADR-011, but also feed API shape per ADR-028, but also any future contract). Embedding in ADR-011 would mis-scope. A standalone doctrine ADR is the right shape.

## References

- `docs/PATTERNS/test-against-real-contract-instances.md` — the executable form (≤300 lines) with three techniques, four "when NOT to apply" guards, worked examples, and the triage-discipline extension
- `REVIEW.md` — the canonical worked example for Layer 2 (cross-team review); 9 findings with severity + ADR-citation + suggested-fix + pinning-recommendation per finding
- `wiki/decisions/028-locked-build-time-contracts.md` — § 4 (feed split) is the worked example for incident (1); the three incidents are summarized there for posterity
- `wiki/log.md` 2026-05-28 entries — chronological dispositions of each incident
- `skills/sf-improve-skill/learnings.md` — lifecycle-2's per-skill learning entry on the eval.json fork; the "validate against real contract instances" framing originated here
- `skills/sf-install/tests/integration/test_contract_drift.py` — onboarding-2's drift-pin implementation using `inspect.signature`; the executable form of Layer 1
- `wiki/decisions/011-skill-schema.md` — the canonical contract for eval.json (the source-of-truth incident (2) drifted from)
- `feed/tests/` — feed-2's "expected absence" pattern (Layer 3) worked examples: `test_check_auth_does_not_include_show_token_flag` (F1), `test_truncate_preserves_at_least_one_entry_per_friend` (F4)
