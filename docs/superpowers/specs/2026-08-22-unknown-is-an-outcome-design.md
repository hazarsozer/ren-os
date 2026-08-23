# Unknown is an outcome — reporting surfaces must be able to say "I could not look"

A function that returns `[]` for *nothing found* and `[]` for *I could not
look* has destroyed the difference at the point where it was still known.
When something renders that value to the friend as a finding, the friend is
told the system is healthy on the strength of a check that never ran.

This spec gives the small, closed set of surfaces that report findings a way
to say "unknown", fixes the four that cannot, and adds the one check whose
absence was proven live today.

Scope is deliberately small: one registry, one enforcement test, four
surface fixes, one new check. It changes no wiki content and no user-facing
default behavior.

## 1. Evidence (why now)

All measurements taken 2026-08-22 against `worktree-unknown-is-an-outcome`
at `ea3919c` (v0.8.4), on the live machine.

### 1.1 The shape, at its worst

`skills/wiki-health/lib.sweep()` called against a wiki root that is not a
directory returns this:

```python
{"dangling_pointers": [], "contradiction_pairs": [], "duplicate_pairs": [],
 "numeric_drift_pairs": [], "orphan_pages": [], "unlinked_knowledge_pages": [],
 "stale_facts": {"stale": [], "unverifiable": [], "corrections_queued": 0}, ...}
```

Every key present, every finding empty. `render_report` prints a clean bill
of health for a wiki that does not exist. Nothing in the returned structure
distinguishes this from a genuinely healthy wiki.

### 1.2 Doctor is not the problem — doctor is the reference

Doctor's `CheckResult` carries `status: "ok" | "warn" | "info" | "skip" |
"error"`. `skip` is exactly the "I could not look" channel this spec is
about, and doctor already uses it correctly.

Probe: all 26 `check_*` functions run twice, once with `CLAUDE_PLUGIN_ROOT`
set and once with it removed.

| Result | Count |
|---|---|
| Checks run | 26 |
| Changed status when the plugin root was removed | 1 |
| …and it changed to | `skip` — "plugin cache root unresolvable" |
| Checks that falsely reported `ok` while blinded | **0** |

Doctor needs no changes. It is the model the other surfaces are measured
against.

### 1.3 Detecting the shape generically does not work

An AST probe over every `.py` outside `tests/`, `migrations/`, `archive/`,
looking for a top-level guard clause returning a falsy literal from a
function that can also return that literal normally:

| Population | Count |
|---|---|
| Any top-level guard returning a falsy literal | 230 |
| …whose condition mentions resolution/availability | 58 |

Most of the 58 are correct. `_read_small()` returning `''` for a non-file
and `list_existing_tarballs()` returning `[]` when no backup dir exists are
both right — their values are consumed as data, not rendered as assertions
about the world.

This confirms the deferral recorded in
`2026-08-22-fail-open-declared-design.md` §7 ("a rule here would fire on
hundreds of legitimate sites"). **Definition-site detection is abandoned.**

### 1.4 The discriminator is the consumption site

`gc_stale_envs()` returning `[]` is a false statement; `list_existing_tarballs()`
returning `[]` is not. The difference is not in the function — it is that
something renders the first one to the friend as a finding.

`skills/update/SKILL.md` closing steps: *"returns the removed version list;
report it if non-empty, **silent otherwise**."* The blind case and the
healthy case take the same branch, by written instruction.

That narrows the population from 230 to a list short enough to enumerate.

### 1.5 The registry cannot be auto-derived (prototype, negative result)

Before choosing a hand-maintained registry, a parser was prototyped to
derive the surface list from SKILL.md prose — find reporting instructions
("report the returned…", "surface…", "show the friend"), extract co-located
backticked identifiers, resolve them against each skill's `lib`.

Scored against the eight surfaces identified by hand:

| Metric | Result |
|---|---|
| Recall | **4 of 8** |
| Found | `gc_stale_envs`, `rewarm_interpreter`, `watch`, `sweep` |
| Missed | `changelog_digest`, `rerender_all_project_claude_md`, `write_global_claude_md`, **all of doctor** |
| Spurious hits | ~5 of 12 (`stamp_wiki`, `accept` — these perform work, they do not report findings) |

Two structural failures, neither fixable by tuning:

1. **Doctor was missed entirely** — the reference implementation. Its
   SKILL.md discusses `ok`/`warn`/`skip`/`info` as prose and never names a
   check function beside a reporting verb.
2. **Three of five update surfaces were invisible** because they live in
   `lib/adapter/claude_md.py`, not `skills/update/lib/`. Widening
   resolution repo-wide trades the recall gap for a precision collapse.

Tuning further would fit the parser to the eight known examples, which
predicts nothing about the ninth. **The registry is explicit.** §7 states
the resulting limitation rather than concealing it.

### 1.6 Three ledger claims, checked

This spec's four candidate sites came from ledger prose. Checking them
against the code changed the scope materially:

| Ledger claim | Verdict |
|---|---|
| `cache_env_hygiene` "silently no-ops without `CLAUDE_PLUGIN_ROOT`, reporting absence-of-problem" | **False.** Returns `skip` — "plugin cache root unresolvable". Correct today. |
| `gc_stale_envs` same | **Half.** The function is deliberately correct (refuses to delete what it cannot confirm). Its *return type* cannot carry that distinction. |
| "No check reads the global CLAUDE.md block's version pins" | **True.** `check_global_drift` covers page typing under `global/`, never the doctrine index. |

Two of three descriptions were wrong. A spec built from the prose alone
would have specified fixes for two non-defects. See §8.

## 2. The rule

> Any function whose result is rendered to the friend as a finding MUST be
> able to express three outcomes: **found**, **not-found**, and **unknown**.

"Unknown" means the check could not run — an unresolvable root, a missing
registry, an unreadable source. It is not an error (nothing crashed) and it
is not health (nothing was verified).

Doctor satisfies this today via `CheckResult.status == "skip"`. The rule
generalizes doctor's existing design; it does not invent one.

## 3. Part A — the registry

New module `lib/reporting.py`:

```python
@dataclass(frozen=True)
class Unknown:
    """Returned in place of a result when the check could not run."""
    reason: str
```

A surface signals blindness by returning `Unknown(reason=...)` in place of
its normal result type. Callers test with `isinstance(result, Unknown)`.

`REPORTING_SURFACES` in the same module is the closed list, each entry
naming the module path, the function, and the SKILL.md section that
instructs a session to report it:

| Surface | Today | After |
|---|---|---|
| `skills.wiki_health.lib.sweep` | all-clear dict | `Unknown("wiki root is not a directory: <path>")` |
| `skills.update.lib.gc_stale_envs` | `[]` | `Unknown("plugin cache root unresolvable")` |
| `skills.update.lib.rerender_all_project_claude_md` | `{}` | `Unknown("project registry missing or unreadable")` |
| `skills.update.lib.changelog_digest` | `""` | `Unknown("changelog missing")` / `Unknown("changelog unparseable")` |

`Unknown` is deliberately not a subclass of `list`/`dict`/`str`. A caller
that forgets to handle it fails loudly at the first attribute access rather
than rendering it as empty — the failure mode this spec exists to remove
must not be reintroduced by the fix.

### 3.1 Why `rerender_all_project_claude_md` is on the list

`ren_paths.load_project_registry()` documents returning `{}` when the file
is "missing, unreadable, or malformed". `rerender_all_project_claude_md`
iterates that mapping, so `{}` means either *no project carries an
instructions.md* (benign — the observed case on this machine today) or *the
registry could not be read*. Both render identically.

### 3.2 In-repo callers must handle `Unknown`

Because `Unknown` is not a subclass of the type it replaces, every in-repo
consumer of a changed surface is part of this work — a missed one raises at
the first attribute access, which is the intended failure mode but must not
be discovered by a friend.

| Surface | Consumers to update |
|---|---|
| `sweep` | `skills/wiki-health/lib.render_report` (renders the report); `skills/wrap/lib._run_wiki_health_sweep` → `harvest_suggestions` (wrap close-out) |
| `gc_stale_envs`, `rerender_all_project_claude_md`, `changelog_digest` | no in-repo callers — invoked by the live session per `skills/update/SKILL.md` closing steps, so the SKILL.md instruction is the only consumer |

`render_report` renders `Unknown` as a single line naming the reason, in
place of the findings body. That is the whole user-facing fix for `sweep`.

Wrap is **not** a second reporting surface, and an earlier draft of this
section was wrong to treat it as one. `skills/wrap/SKILL.md` step 5 states
that `harvest_suggestions`'s return value is never rendered: *"nothing in
the end screen below depends on its return value."* Wrap's obligation is
therefore only to not crash — `_run_wiki_health_sweep` propagates the
`Unknown`, and `harvest_suggestions` skips the `wiki_health_critical` leg,
exactly as it already does when the sweep raises. No warnings channel is
added, because nothing would read it.

### 3.3 What is NOT on the list

- **Doctor's `check_*`** — already correct (§1.2). Reference, not target.
- **`rewarm_interpreter`, `write_global_claude_md`** — already carry a
  `status` field that can express the blind case.
- **`metric-watch.watch`** — checked and excluded. Its blind paths fail
  *loud*: `_git_remote_configured` returns `False` on `OSError`, which
  produces a `backup-unconfigured` finding rather than a false all-clear.
  Alarming on blindness is an acceptable answer to this rule.
- **The 230 / 58 definition-site population** (§1.3). Out of scope by
  evidence, not by omission.

## 4. Part B — enforcement

New `tests/audit/test_unknown_is_an_outcome.py`:

1. **Every registered surface can return `Unknown`.** For each entry, assert
   a code path constructs `Unknown` — AST-walk the function for an
   `Unknown(...)` call. Fails when a surface is registered but never signals
   blindness.
2. **Every registered surface is exercised blind.** Each entry names a
   pytest fixture that induces its blind condition (a `tmp_path` that does
   not exist, a removed env var) and asserts the return `isinstance` of
   `Unknown`. This is the load-bearing test — (1) alone can be satisfied by
   dead code.
3. **Registry entries resolve.** Every module path and function name in
   `REPORTING_SURFACES` imports and exists — the registry cannot rot into
   naming functions that were renamed or deleted.

(3) is what a hand-maintained registry *can* be protected against. What it
cannot be protected against is a genuinely new surface never being added;
see §7.

## 5. Part C — the missing check

`skills/doctor/lib/check_doctrine_index_pins`:

The global CLAUDE.md managed block's doctrine index holds absolute paths
pinned to the running plugin version
(`.../cache/ren-os/ren/<version>/doctrine/*.md`). A version bump leaves
every one naming the previous version — live only until that cache dir is
GC'd, then dead links in a file injected into every session.

Observed live today: after v0.8.4 installed, the block still pinned
`0.8.3` until `write_global_claude_md()` was called by hand. Nothing would
have reported it.

The check reads the block, extracts pinned versions, compares against
`ren_paths.framework_version()`:

- pins match → `ok`
- pins name another version → `warn`, naming both
- block absent, torn markers, or unreadable → `skip` with the reason
  (this check obeys §2 like everything else)

## 6. Testing

Every surface this spec changes already has a dedicated test file. New tests
go in the existing file for that surface; only the audit file is new.

| File | Status | Asserts |
|---|---|---|
| `tests/audit/test_unknown_is_an_outcome.py` | **new** | `test_surfaces_can_signal` — each registered surface constructs `Unknown`; `test_surfaces_signal_when_blind` — each returns `Unknown` under its induced blind condition; `test_registry_resolves` — every entry imports |
| `tests/skills/wiki_health/test_sweep.py` | exists | absent wiki root returns `Unknown`, not the §1.1 all-clear dict |
| `tests/skills/update/test_gc_stale_envs.py` | exists | unresolvable cache root returns `Unknown`, not `[]` |
| `tests/skills/update/test_global_rerender.py` | exists | unreadable project registry returns `Unknown`, not `{}` |
| `tests/skills/update/test_changelog_digest.py` | exists | missing vs unparseable carry distinct reasons |
| `tests/skills/doctor/test_doctor.py` | exists | `check_doctrine_index_pins`: ok / warn-on-drift / skip-when-unreadable |

Each SKILL.md whose closing steps report a changed surface gets its
instruction updated to say what to print for `Unknown` — the fix is not
complete while the docs still tell a session to stay silent.

## 7. What this does not do

- **It does not guarantee new surfaces get registered.** The registry is
  hand-maintained. §1.5 records the prototype that tried to derive it and
  why it failed. A newly added reporting surface that nobody registers is
  caught by code review, not by a gate. This is the known edge of this
  design, stated rather than concealed.
- **It does not touch the 230-site definition-shape population** (§1.3),
  nor the guard-clause item deferred by the fail-open spec §7. That item
  stays open.
- **It does not change doctor**, beyond adding one check.
- **It does not address the unenforced-handoff class** — `accept()`'s three
  handoff kinds (`orphan_page`, `review_lint_finding`, `place_durable_item`)
  record a promise as a completion with no receiving end and no retry. That
  is a real and distinct defect class; it stays on the ledger with a date.
- **It ships no wiki content changes** and alters no default behavior a
  friend would notice, except that a blinded check now says so.

## 8. Process finding

Three ledger claims were checked against code before being specified
(§1.6); two were wrong. Separately, the day's release work established that
the ledger's stale-`.venv` root-cause item names one site
(`hooks/wake-up/ren-wake-up.py`) when there are two — `warm_environment` in
`skills/install/lib` has the same missing `UV_PROJECT_ENVIRONMENT`, and
0.8.3 wired `rewarm_interpreter` to call it on *every* update. The
prescribed "one line in `child_env`" fix would not have stopped the warn
regenerating.

Four ledger descriptions checked in one day; three materially wrong. The
ledger is reliable as an *index of where to look* and unreliable as a
*specification of what is wrong*. Every item should be re-derived from code
before it becomes work.

This is itself an instance of the class this spec addresses: a ledger line
reports a finding with no channel for "this description has not been
verified against the code since it was written."
