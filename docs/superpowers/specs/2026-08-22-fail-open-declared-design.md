# Fail-open must declare itself — enforcing the `BLE001` reason convention

A broad `except` that returns a clean value is indistinguishable, in source,
from a deliberate fail-open. This spec makes the difference machine-readable
by enforcing a convention the repo already keeps at 88%, and closes the two
sites where the ambiguity is a real defect.

Scope is deliberately small: one audit test, seven mechanical marks, two
fixes. It ships nothing to an installed instance.

## 1. Evidence (why now)

The 0.8.3 wrap opened nine ledger items in one session. Three of them
describe the same bug — a check that cannot tell "no problem" from "I could
not check". That repetition, not any single item, is what this spec targets.

Measurements taken 2026-08-22 against `main` at 041d97d:

| Question | Answer |
|---|---|
| ren-os lifetime ledger close rate | 27 of 41 = 66% (highest of five projects) |
| Median time-to-close | 2 days; 22 of 25 closed within 4 days |
| Items ever closed after 6 days | 2 |
| Fix commits shipping tests (last 40) | 35 = 88% |
| Broad `except` handlers in shippable dirs | 75 |
| …carrying a written reason | 66 = 88% |
| …marked `# noqa: BLE001` with no reason | 6 |
| …not marked at all | 3 |

Two claims follow, and one commonly-assumed claim does not.

**There are no regressions.** Every defect site opened on 2026-08-22 was
dated against git history. `.ren/` guard absent since 2026-07-06; doctrine
loader quiet-skip since 2026-07-06; the uv fallback since 2026-07-17
(`2fb4eb1`, itself a fix). Nothing that worked stopped working. The
hypothesis "our fixes break other things" is not supported.

**The convention is unenforced, not unwritten.** `pyproject.toml` has no
`[tool.ruff]` section and CI runs no ruff step, yet 66 handlers carry
hand-written `# noqa: BLE001 - <reason>` comments. The comment is being used
as documentation for a linter that never runs.

**The 12% is a discovery queue.** All five unreasoned markers in
`skills/wrap/lib/__init__.py` arrived in a single commit — `5084b5d`
`feat(wrap): run the #54 link duties in wrap_session` (2026-08-12). One
commit, one lapse, five latent ledger items. A gate would have caught them
the day they were written; instead they surface one per review session,
which is the "every session something else shows up" experience.

## 2. Part A — the convention

The convention is the existing one. No new marker is introduced.

    except Exception:  # noqa: BLE001 - fail closed: no evidence, no correction
        return None

**Rule.** Every broad exception handler in a shippable directory carries a
`# noqa: BLE001` comment on the `except` line with a non-empty reason after
the code.

"Broad" means the handler catches `Exception`, catches `BaseException`, or
is bare. Handlers catching a named exception (`OSError` and friends) are out
of scope: the exception name is itself the declaration.

**Three dispositions** are available at any flagged site:

1. **Mark it** — the clean return is a correct answer for this condition.
   Write the reason.
2. **Fix it** — the clean return conceals a failure. Make the two cases
   distinguishable: log a warning, return a tri-state, or let it raise.
3. **Narrow it** — replace `except Exception` with the exception actually
   expected. The site leaves scope by becoming self-documenting.

### 2.1 The rule is broader than the bug shape, deliberately

The defect shape is narrower than the rule: a broad handler whose clean
*return value* conceals a failure. Of 43 clean-return handlers, only 6 catch
broadly; the other 37 catch named exceptions and are deliberate by
construction.

The rule nonetheless covers all 75 broad handlers regardless of return
shape. This costs more, not less: nine violations against the wider rule
versus two against a return-shape-restricted one. It is chosen anyway,
because the narrower rule misses the worst defect in the sweep.

`skills/ingest-project/lib/scan.py:74` returns the string literal `"0.8.3"`.
A return-shape rule that recognises `None`, `[]`, `{}`, `""`, `0` and `True`
does not fire on it, because a stale version literal is not a "clean" value
in any syntactic sense — it is an ordinary string that happens to be a lie.
Any return-value taxonomy precise enough to catch it would have to encode
which strings are honest, which is not a decidable property of source.

The seven sites the wider rule adds are exactly the ones a return-shape
taxonomy cannot reason about: five `except Exception as exc` handlers in
`wrap`, a `continue` in `quarantine.py`, and that literal. Handler breadth
is a syntactic property; honesty of a return value is not.

### 2.2 Why not an audit document

`tests/audit/test_destructive_write_paths.py` (issue #11 §2) pins its class
against `docs/audits/2026-07-destructive-writes.md`, and that precedent was
considered. Inline was chosen because these reasons are local and short, and
because most already exist in the adjacent docstring — a central document
would duplicate them and drift. The inline marker cannot drift from the code
it annotates.

### 2.3 Withdrawn during design

An earlier draft proposed a new `# ren-fail-open: <reason>` marker mirroring
the `ren-volatile` convention. It was withdrawn on discovering the 66
existing `BLE001` reasons. A second marker for a convention already kept at
88% would have created two idioms for one intent and a 75-site migration
instead of a nine-site one.

## 3. Part B — enforcement

**Location.** `tests/audit/test_fail_open_declared.py`, beside the
destructive-write audit. Same folder, same purpose: pin a class of dangerous
behaviour rather than an instance.

**Gate.** `.github/workflows/validate.yml` already runs the full pytest
suite on push and pull_request to `main` and `rc`. No new CI wiring, no git
hooks. The test is the gate.

**Detector: AST, not regex.** The sizing scans in §1 used regex with a
fixed-line lookahead; that is adequate for counting and too fragile to fail
a build on. The test walks `ast.ExceptHandler` nodes for exact handler
identification, and uses `tokenize` to map comments to line numbers because
comments are absent from the AST. Both are standard library; no dependency
is added.

**A handler is a violation when** it is broad (per §2) and either carries no
`BLE001` comment on its `except` line, or carries one whose text after the
code is empty.

**An empty reason is a violation.** Permitting a bare `# noqa: BLE001` would
degrade the marker into a rubber stamp within two sessions.

**Scope.** `lib/`, `hooks/`, `skills/`, `agents/` — reusing the
`SHIPPABLE_DIRS` list already defined in `tests/test_repo_hygiene.py`.
`tests/` is excluded.

**Failure output** names each offending `file:line` and restates the three
dispositions from §2, so the remedy is available without opening this spec.

### 3.1 Invariant

Zero broad exception handlers in shippable directories lack a written
reason. A new one is a failing test until someone classifies it — the same
contract the destructive-write audit uses for new write primitives.

### 3.2 Non-goal: configuring ruff

Adding `[tool.ruff]` and a CI lint step would surface findings across 247
files and is out of scope. This spec enforces one rule with one test. Should
ruff be adopted later, the `BLE001` markers already carry their reasons and
become live suppressions with no migration.

## 4. Part C — triage of the nine

Seven marks and two fixes. The marks are mechanical: in every case the
reason already exists in the adjacent docstring or comment and moves inline.

| Site | Disposition | Reason source |
|---|---|---|
| `skills/wrap/lib/__init__.py:1352` | Mark | `5084b5d` lapse; behaviour correct |
| `skills/wrap/lib/__init__.py:1371` | Mark | as above |
| `skills/wrap/lib/__init__.py:1393` | Mark | as above |
| `skills/wrap/lib/__init__.py:1422` | Mark | as above |
| `skills/wrap/lib/__init__.py:1451` | Mark | as above |
| `hooks/wake-up/wakeup/__init__.py:1176` | Mark | docstring: "any error reads as 0, wake-up must not die over a nudge" |
| `lib/memory/quarantine.py:129` | Mark | comment above: "Skip unreadable files (never raise)" |
| `skills/doctor/lib/__init__.py:806` | **Fix** | §5.1 |
| `skills/ingest-project/lib/scan.py:74` | **Fix** | §5.2 |

## 5. Part D — the two fixes

### 5.1 `doctor` cannot report its own blindness

    try:
        wiki_root_ = ren_paths.wiki_root()
    except Exception:
        return None

`_detect_project` returns `None` for "no project here", which is a correct
and expected answer. The bare handler makes `None` *also* mean
"`wiki_root()` raised", so the health checker cannot distinguish a clean
no-project state from its own failure. This is the §1 bug shape inside the
tool whose entire purpose is reporting problems.

**Fix.** The two cases must be distinguishable to the caller. The failure
path is logged at warning level and the check reports inability-to-check
rather than absence-of-problem. The exact return shape is an implementation
decision for the plan; the invariant is that a raised `wiki_root()` never
renders as a clean "no project".

### 5.2 `ingest` returns a stale version literal

    except Exception:
        return "0.8.3"

On resolver failure this reports a plausible but wrong framework version,
and the literal must be hand-bumped every release or it silently reports a
version that has not shipped for months. This is worse than silence: it is a
confident wrong answer, and it is the only site in the sweep with that
property.

This defect is **not** in the open-work ledger. It was found by the §1 sweep.

**Fix.** Remove the hardcoded literal. On resolver failure the function
reports that the version is unknown rather than inventing one. Callers that
require a version string handle the unknown case explicitly.

## 6. Testing

1. `tests/audit/test_fail_open_declared.py` passes on `main` after Part C —
   this is the acceptance signal for the migration.
2. A fixture with a bare `# noqa: BLE001`, one with no marker, and one with
   a written reason assert the detector's three outcomes. The detector is
   tested, not merely run.
3. Regression tests for §5.1 and §5.2 assert the *distinguishability*
   property, not a specific return value: a raised resolver must not render
   as a clean result.
4. `uv run pytest tests/` is green.

## 7. What this does not do

**It closes no open ledger item.** An earlier draft of this section claimed
four closures; that claim was wrong and is withdrawn.

Three of the fourteen items describe the same *shape* this spec targets — a
check reporting absence-of-problem where it means inability-to-check — but
by a different *mechanism*. `doctrine/loader.py` skips via a guard clause
(`if not root.is_dir(): return []`) and per-file stderr warnings. The
`CLAUDE_PLUGIN_ROOT` no-ops in the env-hygiene checks are guard clauses on a
missing environment variable. The global-`CLAUDE.md` version-pin gap is the
absence of any check at all. No broad exception handler is involved in any
of them, so the Part B test does not fire on them.

The wrap `NOOP_DUPLICATE` item is likewise untouched: it concerns
duplication introduced by `64a5967` (2026-08-21), a different region of
`skills/wrap/lib/__init__.py` than the `5084b5d` marks in §4.

What this spec delivers is therefore additive, not subtractive against the
ledger:

- the except-handler half of the class stops regenerating, permanently;
- two real defects are fixed, one of which (§5.2) was not previously known
  and appears in no ledger.

The guard-clause half of the class is deliberately left alone. Early returns
on unmet preconditions are pervasive and usually correct; a rule there would
fire on hundreds of legitimate sites and be suppressed within a week. If
that half is worth attacking it needs its own evidence pass and its own
spec, not an extension of this rule.

All fourteen ledger items remain open after this work.

## 8. Process finding

The ledger grows because finding is cheaper than fixing, not because work is
abandoned. Sessions close 4–7 items and open 7–12; the net is positive while
the close rate stays the highest of any project in the wiki.

The residue has a shape: items close hot or never. Nothing in ren-os has
closed after 6 days except two outliers at 13 and 14 days. Two items now
19 days old will not close by this process; they need explicit disposition
rather than another session of hoping.

This spec addresses one generator of new items — an unenforced convention.
It does not address the age cliff, which is a separate question about
whether a ledger line that survives its session should expire, escalate, or
be killed on sight.
