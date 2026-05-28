# Test Against Real Contract Instances, Not Assumed Shapes

**Pattern:** when your code consumes a contract defined elsewhere (peer module, ADR-specified schema, vendor API), test it against an actual shipped instance of that contract — not an idealized shape you remembered.

**Why this matters:** two contract drifts this week (one polymorphic vs split, one schema fork) both came from the same root cause — code passed its own tests because its tests encoded the same assumption the code did. Only a cross-team review pass surfaced the gap. The pattern below catches both classes at PR time instead of integration time.

---

## The two worked examples

### Example 1: feed writer — polymorphic vs split

**Convergence state (pre-arbitration):** sf-feed had drafted one polymorphic writer:

```python
# WHAT FEED-2 INITIALLY SHIPPED
def feed_write_entry(
    *,
    handle: str,
    kind: Literal["start", "end", "release"],
    project: str | None = None,
    summary: str = "",
    files_touched: list[str] | None = None,
    cwd: str | None = None,
    continuation_hint: str | None = None,
    schema_version: int = 1,
    skip: bool = False,
    timestamp: datetime | None = None,
) -> FeedWriteResult:
    if kind == "start": ...
    elif kind == "end": ...
    elif kind == "release": ...
    else: raise FormatViolation("unknown-kind", ...)
```

**Lifecycle's consumer encoded:**

```python
# Lifecycle's /sf:wrap call site (mid-flight)
from feed import feed_write_session_end  # ← assumed split shape
feed_write_session_end(handle=..., project=..., task_brief=..., files_touched=[...])
```

Lifecycle's tests passed against `feed_write_session_end_fake` — which had the split shape too. Feed's tests passed against `feed_write_entry` — which had the polymorphic shape. Both passed; integration would have failed.

**Team-lead arbitrated:** ship the split (one function per kind, no `kind` arg, no runtime branch). Feed moved the polymorphic engine to `_write_entry_dispatch` (private) and exposed three split functions. Lifecycle's assumption was right; feed's draft was wrong.

**Why neither side's tests caught it:** each side tested against fakes that mirrored its own assumption. Neither imported the OTHER side's real symbol and compared shapes.

### Example 2: eval.json schema fork

**ADR-011 § "eval.json schema" specifies:**

```json
{
  "name": "<skill-name>",
  "tests": [
    { "id": "test-1", "binary_assertions": ["assertion as string"] }
  ]
}
```

**Lifecycle's `_validate_eval_file` enforced (before the fix):**

```python
# skills/sf-improve-skill/lib/preflight.py:163-184 BEFORE
test_cases = data.get("test_cases")
if not isinstance(test_cases, list) or not test_cases:
    raise PreFlightError(f"{eval_path} must contain a non-empty 'test_cases' array per ADR-011 schema.")

total_assertions = 0
for case in test_cases:
    assertions = case.get("assertions") or []
    for assertion in assertions:
        if not assertion.get("binary"):
            raise PreFlightError(f"... assertion {assertion.get('id', '<unnamed>')} is not binary ...")
        total_assertions += 1
```

That validator expected `test_cases` + `assertions` + objects with `binary: true` field. ADR-011 specifies `tests` + `binary_assertions` as a list of strings. Different camp entirely.

**What shipped (after the fix):**

```python
# AFTER
tests = data.get("tests")
if not isinstance(tests, list) or not tests:
    raise PreFlightError(f"{eval_path} must contain a non-empty 'tests' array per ADR-011 schema.")

total_assertions = 0
for test in tests:
    assertions = test.get("binary_assertions") or []
    if not isinstance(assertions, list):
        raise PreFlightError(f"{eval_path}: each test must have a 'binary_assertions' list.")
    for assertion in assertions:
        if not isinstance(assertion, str):
            raise PreFlightError(
                f"{eval_path}: binary_assertions items must be strings per ADR-011. "
                "Objects with 'binary: true' belong to a different (non-shipped) schema."
            )
    total_assertions += len(assertions)
```

**Why lifecycle's own tests didn't catch it:** their `skills/sf-wrap/eval/eval.json` used the same wrong-camp shape (`test_cases` + `assertions` + objects). Their validator and their fixture were internally consistent — both reflecting the same assumption. Their suite was green. Onboarding's eval files (and feed's, and distribution's) were all in the ADR-011 camp; running preflight on any of them would have failed at gate 2.

**Same root cause as Example 1:** code's tests proved code works against code's assumptions. Nobody tested code against the contract's actual shipped instances.

---

## The three techniques

### Technique 1: `inspect.signature` drift tests against real symbols

Import the peer's real symbol. Compare its signature to the fake's. Fail on mismatch.

```python
# skills/sf-install/tests/integration/test_contract_drift.py
import inspect
from integration.fakes.feed_fake import FeedFake

def test_feed_detect_repo_state_signature_drift() -> None:
    import feed
    real_sig = inspect.signature(feed.feed_detect_repo_state)
    fake_sig = inspect.signature(FeedFake.feed_detect_repo_state)

    fake_params = [p.name for p in fake_sig.parameters.values() if p.name != "self"]
    real_params = [p.name for p in real_sig.parameters.values()]
    assert fake_params == real_params, (
        f"feed_detect_repo_state signature drift: fake={fake_params}, real={real_params}"
    )
```

When the peer renames a parameter, adds a positional arg, or drops a keyword arg, this test fails at PR-time with a clear `signature drift` message naming both shapes.

**Used in this codebase:** `skills/sf-install/tests/integration/test_contract_drift.py` has 9 such tests against `feed/`. All 7 active ones passed after feed-2's refactor — proving the contract held across the split-shape transition.

### Technique 2: parametrized fixtures across all peer instances

When a contract describes a class of artifacts (every skill's `eval.json`, every wiki page's frontmatter, every plugin's `plugin.json`), test the validator against every shipped instance.

```python
# skills/sf-improve-skill/lib/tests/test_preflight.py (lifecycle-2)
CANONICAL_EVAL_FIXTURES = [
    "skills/sf-install/eval/eval.json",
    "skills/sf-interview/eval/eval.json",
    "skills/sf-bootstrap-project/eval/eval.json",
    "skills/sf-wrap/eval/eval.json",
]

@pytest.mark.parametrize("fixture_path", CANONICAL_EVAL_FIXTURES)
def test_preflight_accepts_canonical_eval(fixture_path: str) -> None:
    skill_root = Path(fixture_path).parent.parent
    args = make_args(skill_name=skill_root.name)
    pre_flight_check(args, skills_root=skill_root.parent)  # must not raise
```

When ADR-011 amends the schema or a new skill ships an eval.json with a slightly-different shape, every fixture fails simultaneously — bright fire alarm, not an ambiguous regression.

**Maintenance burden:** when a new skill ships an eval.json, append its path to `CANONICAL_EVAL_FIXTURES`. One line, instant pin extension.

### Technique 3: doc-citation-in-test-name

Name the test after the doc it pins. When the test fails, the reader knows exactly which authority to consult:

```python
def test_preflight_accepts_adr011_eval_shape() -> None:
    """Pin per ADR-011 § 'eval.json schema (compatible with Skill Creator's run_eval.py)'.

    The shape: top-level 'tests' array; items have 'id', 'prompt', and
    'binary_assertions' (list of strings). NOT 'test_cases' + 'assertions' +
    objects-with-binary-field — that was a fork that shipped and was caught
    by REVIEW.md finding L1.
    """
    ...
```

The test name + docstring make the contract authority searchable. A future contributor renaming the schema in ADR-011 grep's for `adr011` and finds every pin.

---

## The non-obvious insight: tests AND review, not one or the other

**Each piece passes against its own assumptions:**

- Feed's polymorphic writer passed feed's own tests (which used `feed_write_entry`).
- Lifecycle's `_validate_eval_file` passed lifecycle's own tests (which used `test_cases` fixtures).
- Onboarding's install simulator passed onboarding's own tests (which used onboarding's `FeedFake`).

**Each side was internally consistent.** Each side's test suite was green. Neither side imported the OTHER side's real symbol or shipped fixture.

**Only a cross-team review pass surfaces the assumption-doc gap.** When a reviewer reads both the ADR's verbatim schema and the implementation's enforced schema, they see the gap. No suite did. No single-perspective process can — by construction, single-perspective tests reproduce the perspective's own assumptions.

**Both layers are load-bearing:**

| Layer | Catches |
|---|---|
| Single-perspective tests | implementation bugs against its own intent |
| Cross-team review | drift between intent and contract |
| Cross-team **signature-drift tests** (Technique 1) | the gap automatically at PR-time |
| Cross-team **canonical fixture tests** (Technique 2) | the gap automatically across all instances |

Once review surfaces a drift, codify the catch as Technique 1 or 2. Review caught the bug; the test prevents the recurrence. Don't rely on review alone — reviewers context-switch; tests don't.

---

## The discipline applies to triage, not just authoring

The root failure is **in-memory model substitution** — believing your recollection of a contract instead of consulting the canonical source. That substitution can happen at any process step, not just when writing code. Both classes fail the same way and fix the same way:

| Phase | Failure mode | Fix |
|---|---|---|
| **Authoring** (writing a validator / parser / consumer) | Substituting your in-memory model of the contract for the actual canonical source | Open the canonical doc, read the schema verbatim, quote it in a comment alongside the code |
| **Triage** (routing a finding from one peer to another) | Substituting the peer's stated interpretation for the canonical source | Before forwarding, open the canonical doc yourself; verify the finding's claim against the verbatim text; only forward if the canonical source confirms |

The week of 2026-05-28 produced one instance of each:

- **Authoring failure:** the eval.json schema drift (REVIEW.md finding L1). Code's tests reflected code's assumption; only review-against-ADR-011 caught the gap. Documented in the worked examples above.
- **Triage failure:** a routing chain hopped a peer's now-retracted timeout-unit claim without anyone re-reading the canonical doc. Team-lead caught it themselves on the readback. Same substitution; different process step.

Both fixes reduce to: **verbatim-quote the canonical source before any downstream step depends on the interpretation.** Authoring: quote it next to the code. Triage: quote it in the forwarding message.

Tests can't catch triage failures (no executable artifact to assert against), but the discipline still applies — the canonical-source-quoting habit is the antidote at both ends. When you find yourself paraphrasing a contract while routing a finding, that's the moment to stop and open the canonical doc.

---

## When NOT to apply this pattern

Guard against overgeneralizing. Skip the techniques when:

- **The code has no peer-consumed contract surface.** A private helper inside one module, with no docstring claim about an external schema, has nothing to drift against. Don't add `inspect.signature` tests for internal-only functions.
- **The contract is single-author and the doc is the code.** When the ADR-style doc is generated from the code (e.g. JSON schema generated from a Pydantic model), the doc-to-code drift is impossible by construction. Don't pin against a generated doc.
- **The code is throwaway** (script that runs once, fixture generator for a single test, exploratory notebook). Pin against contracts only when both sides expect long-term coexistence.
- **The peer hasn't shipped a stable API yet.** When the peer is mid-design and the signature is changing weekly, drift tests fire on every peer commit. Wait for the peer to lock — then add the pin. Until then, document the assumption with a `TODO(peer-2):` comment so the future-you knows where the assumption lives.

The pattern is for **established cross-team contracts**: locked signatures, ADR-specified schemas, vendor APIs the framework depends on long-term. Not for every function call.

---

## Cross-references

- `REVIEW.md` § findings F1, L1 — the worked examples written up at finding-shape
- `skills/sf-improve-skill/learnings.md` (lifecycle-2) — the team-wide formulation in the originating module
- `skills/sf-install/tests/integration/test_contract_drift.py` — 9 active feed-contract drift pins; the implementation reference for Technique 1
- ADR-011 § "eval.json schema" — the canonical source the eval fork-fix points at
- `feed/writer.py` header docstring — feed-2's own articulation of why the split shape survived as the public surface and the polymorphic engine became private

---

## Revision history

- v1 (2026-05-28) — initial draft. Two worked examples (split-vs-polymorphic; eval.json fork). Three techniques. The non-obvious insight that tests and review are complementary load-bearing layers, not interchangeable.
- v1.1 (2026-05-28) — added "The discipline applies to triage, not just authoring" section. Generalizes the underlying root cause (in-memory model substitution) from authoring to any process step that depends on a contract interpretation. Proposed by lifecycle-2; endorsed by team-lead; same root cause that produced the eval.json fork also produced an unrelated triage hop the same week.
