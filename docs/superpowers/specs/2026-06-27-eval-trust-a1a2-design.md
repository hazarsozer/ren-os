# A1+A2 — Locked Scorer + Cross-Model Critic (Anti-Goodhart Eval Trust) — Design Spec

> **Status:** Approved design (2026-06-27). Brainstormed via `superpowers:brainstorming`; the three
> trust-model calls (scorer-lock depth, critic placement, critic model) locked with the maintainer
> via the H2 AskUserQuestion pattern (see §2). This spec is the input to a `superpowers:writing-plans`
> pass and the contract for the subsequent TDD build.
>
> **Roadmap slice:** A1+A2 — item 2 of the parked video-ingest menu
> (`docs/superpowers/specs/2026-06-21-video-ingest-improvements.md` §Theme A, recommended build order #2).
> A3+A4 (item 1) shipped 2026-06-27 (`6775d06`). This is the high-value anti-Goodhart pair.
> **Amends:** ADR-036 (Bike-Method / Earned Autonomy) — a **second** 2026-06-27 amendment (the first was A3+A4).
> **Foundational ADRs:** ADR-036 (earned autonomy; the loop this hardens), ADR-012 (Two-Layer
> Self-Improvement), ADR-011 (Skill Schema / `eval.json` — the rubric A1 locks), ADR-031 (Solo-First —
> no speculative trust-tracker), ADR-003 (No-Daemon).

---

## 1. Purpose

The Karpathy loop (`/ren:improve-skill`) can score a skill, propose a change, re-score, and keep/revert.
But its **trust model has two holes** that A1+A2 close — the work the 2026-06-27 session ledger flagged
as "deserving its own deliberate ADR-036 amendment" because it changes *how much the loop can be trusted
to modify itself*.

1. **The loop can silently game itself (A1).** `apply_proposed_change()` (`lib/__init__.py:467`) runs
   `git apply` on whatever diff the proposer returns, with **no path allowlist**. The proposer prompt
   asks for "SKILL.md or a references/ file," but nothing enforces it — a diff that edits
   `eval/eval.json` (delete a failing assertion → `total` drops → score "rises") would be applied and
   kept. Textbook *optimize-the-score-not-the-goal*. Compounding it: the proposer is an agentic
   `claude --print` subprocess with default tools, so it can also **read** `eval/eval.json` off disk.

2. **A "success" rests on one model (A2).** Every assertion is judged by a single model
   (`JUDGE_MODEL = "haiku"`, `lib/eval_runner.py:300`). One model's blind spots can wave a bad output
   through, and an auto-merge ships on that single opinion.

A1 makes the rubric **immutable from the loop's perspective**. A2 lets an auto-shipped success carry an
**independent cross-vendor second opinion**. Together — a locked rubric judged by a *different* model —
they are the strong anti-Goodhart pair, and they make autonomy *more earnable*, which is the whole
governable-self-improvement thesis (ADR-036).

Both follow the A3/A4 discipline: **the default scoring path stays byte-for-byte unchanged.** A1's
edit-lock is always-on but behavior-preserving (no legitimate run targets `eval/`); A2 is opt-in
(`--critic-model`, default `None`).

---

## 2. Locked decisions (maintainer, 2026-06-27)

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| 1 | **A1 isolation depth** | **Edit-lock only.** Mechanically forbid applied diffs from touching `eval/**`; leave the proposer's read access as-is. | Kills the real tamper vector (editing the rubric) surgically. Assertions ARE the spec here (no held-out set), so read-isolation buys little for real cost (proposer sandbox + lost intent context). |
| 2 | **A2 critic placement** | **Final gate before merge.** Critic runs only after `ALL_ASSERTIONS_PASS`, before squash-merge. | One extra eval pass, only on success, only when opted in → bounded cost (respects ADR-036's "cost is the gate"). Guards the boundary that matters (merge), per the source framing ("ship only if both agree"). |
| 3 | **A2 critic model** | **Codex (cross-vendor) recommended; any Claude model supported via the same flag.** Gemini explicitly excluded (maintainer: "Gemini CLI is not supported anymore"). | Codex (`codex-cli 0.139.0`, on PATH) gives genuine OpenAI-vs-Anthropic diversity — correlated-blind-spot coverage a same-vendor model can't. `--critic-model claude-opus-*` remains a no-external-dep fallback. |
| 4 | **Edit-lock always-on vs opt-in** | **Always-on** (it's a safety invariant), but behavior-preserving for legitimate runs. | No flag; nobody should be able to opt *out* of "the improver can't edit its own rubric." |
| 5 | **Critic dispute handling** | **Flag for human review, never destroy work.** Disagreement blocks the *auto-merge*, keeps the branch, reports disputed assertions. | Conservative + honest: a second opinion withholds a ship, it doesn't manufacture or discard one. |
| 6 | **Critic backend absent** | **Graceful skip + explicit notice** (`shipped WITHOUT cross-model confirmation`). | Never a hard dependency; mirrors A4's missing-reference handling and the framework's degrade-honestly doctrine. Never silently reports as if confirmed. |

---

## 3. Architecture — two choke points, one new adapter

Both features land at existing seams; the skill-run path is untouched (the skill always runs under
`claude` — only the *judge* can switch vendors).

| Unit | Path | Status | Responsibility |
|------|------|--------|----------------|
| **edit-lock guard** | `lib/__init__.py` → `apply_proposed_change()` + a new `lib/scorer_lock.py` helper | **NEW + AMEND** | Parse the proposed diff's target paths; reject if any touches the skill's `eval/` or escapes the skill dir. Raises `ScorerTamperError`. |
| **orchestrator** | `lib/__init__.py` → `improve_skill()` | **AMEND** | Catch `ScorerTamperError` on the proposer/apply path like `ProposerError` (skip iteration, count toward the 3-consecutive cap). Add the **final critic gate** before `squash_merge_on_success` (`:432`). |
| **judge threading** | `lib/eval_runner.py` → `judge_assertion`, `run_evals` | **AMEND (additive)** | Separate the **judge** runner/model from the **skill** runner. Add `judge_model` (default `JUDGE_MODEL`) + `judge_runner` (default `run_print`). Default call sites unchanged. |
| **codex adapter** | `lib/codex_cli.py` | **NEW** | The single place that shells `codex exec` (non-interactive). Returns the same typed shape as `claude_cli.ClaudeRun` (`output_text`, `usage`, `is_error`, `timed_out`). Mockable like `claude_cli`. |
| **judge router** | `lib/eval_runner.py` → `select_judge(model)` | **NEW** | Map a model name → `(judge_runner, normalized_model)`. Codex/OpenAI-shaped (`codex`, `gpt*`, `o1`/`o3*`) → codex adapter; everything else → `run_print`. Detects an absent backend (`shutil.which` / import failure) and signals `CriticBackendUnavailable`. |
| **types** | `lib/types.py` → `ImproveSkillArgs` | **AMEND (additive)** | Add `critic_model: str | None = None`. Frozen-dataclass default → backward-compatible with all existing tests. |
| **CLI parse** | `skills/improve-skill/SKILL.md` arg-parsing contract | **AMEND** | `--critic-model MODEL` → `ImproveSkillArgs.critic_model`. |

The two engines (`claude`, `codex`) sit behind `claude_cli.py` / `codex_cli.py`; unit tests mock those wrappers.

---

## 4. A1 — Locked scorer (edit-lock)

**Invariant:** the improver can never modify the artifact that grades it.

**Enforcement point:** `apply_proposed_change()` — the single choke through which *every* applied diff
passes. A new pure helper `scorer_lock.diff_targets_locked_path(unified_diff, target_file, skill_name)`
returns the offending path (or `None`):

- Parse the unified diff's path headers (`diff --git a/… b/…`, `--- a/…`, `+++ b/…`) **and** consider the
  declared `change.target_file`. (Both: `target_file` is advisory; `git apply` uses the diff headers, so
  we check what will actually be written.)
- A path is **locked** if, resolved relative to `skills/<skill_name>/`, it (a) lies under `eval/`, or
  (b) escapes the skill directory (`..`, absolute paths, or a different skill).
- `apply_proposed_change()` calls the helper first; on a hit it raises `ScorerTamperError(path)` **before**
  any `git apply` — nothing is written, nothing is committed.

**Orchestrator handling:** `improve_skill()` wraps the apply in the same `try` that already catches
`ProposerError` (`lib/__init__.py:319-335`). A `ScorerTamperError` is treated identically: log
`rejected: proposed change targeted the locked scorer (<path>)`, skip the iteration, increment
`consecutive_proposer_errors`. A proposer that keeps clawing at `eval/` therefore exits cleanly via the
existing 3-consecutive cap (`NO_IMPROVEMENT_POSSIBLE`) instead of looping or tampering.

**Always-on, behavior-preserving:** no flag. Legitimate runs (SKILL.md / `references/**` diffs) are
unaffected; only the malicious/buggy path changes.

**Read access unchanged** (decision #1): the proposer still receives only opaque failing-IDs (`test-1:0`),
not assertion text, and we do **not** sandbox its filesystem.

---

## 5. A2 — Cross-model critic (final gate, opt-in)

**Trigger:** `args.critic_model is not None` **and** the loop reached `ExitReason.ALL_ASSERTIONS_PASS`.
Placed in `improve_skill()` immediately before the `squash_merge_on_success` branch (`:427-438`).

**Flow:**
1. Resolve the judge via `select_judge(args.critic_model)` → `(judge_runner, model)`.
   - Backend absent (`codex` not on PATH, adapter import fails) → **graceful skip**: proceed to the
     normal squash-merge, but stamp the disposition `squash-merged (critic <model> unavailable — shipped
     WITHOUT cross-model confirmation)`. Never blocks, never silently "confirms."
2. Run **one** independent confirmation pass: `run_evals(skill, judge_model=model, judge_runner=judge_runner,
   eval_runs=1, skills_root=…)`. The skill re-runs under `claude` (always); only the **judge** is the critic
   model. This is an end-to-end second opinion, not a re-grade of the primary transcript.
3. **Agreement contract:**
   - `critic_result.all_pass` → squash-merge; disposition `squash-merged (critic <model> confirmed)`.
   - Critic disputes ≥1 assertion → **do not auto-merge**; keep the branch; disposition
     `kept (critic-flagged — <model> disputed <ids>)`; surface the disputed `failing_assertion_ids` in the
     result so the human can adjudicate.
4. **`--keep-branch` interaction:** when the user already opted out of auto-merge, the critic still runs
   (if `critic_model` set) and its agree/dispute verdict is *reported*, but disposition stays `kept` — the
   critic only ever *blocks an auto-merge*, it does not force one.

**Adapter routing (`select_judge`):**
- `codex` / `gpt*` / `o1*` / `o3*` → `codex_cli.run_exec(prompt, model=…, timeout_seconds=…)`.
- anything else → `claude_cli.run_print(prompt, bare=False, model=…)` (e.g. `claude-opus-4-8`).

**Codex adapter (`lib/codex_cli.py`):** shells `codex exec` in non-interactive mode (exact flags confirmed
at implementation time against `codex-cli 0.139.0` — mirrors `claude_cli.run_print`'s shape), parses
`TRUE`/`FALSE` from stdout, returns a `ClaudeRun`-shaped struct. **Known gap (documented, not solved
here):** codex may not report token usage in the Anthropic shape, so its critic pass contributes
`ApiUsage(0,0)` to the budget tracker — acceptable because the critic is a single bounded final pass, not
an in-loop cost. Noted in the ADR amendment.

**Cost:** zero on the default path (`critic_model is None`). When set: exactly one extra `eval_runs=1`
pass, only on an otherwise-successful run.

---

## 6. ADR-036 — second 2026-06-27 amendment (trust-model shift)

A new amendment section appended to `wiki/decisions/036-bike-method-earned-autonomy.md`:

- **A1 — locked scorer as a first-class invariant.** The rubric (`eval/**`) is immutable from the loop's
  perspective; the improver optimizes the *asset*, never the *scorer*. Enforced mechanically at the apply
  choke point (not a prompt request). This is the anti-Goodhart guarantee the earned-autonomy posture
  implicitly assumed but did not enforce.
- **A2 — cross-model critic as a final-gate trust check.** An auto-shipped success may carry an independent
  cross-vendor confirmation; disagreement downgrades to human review. Opt-in; default path unchanged.
- **Relationship to §3 (EXPERIMENTAL banner):** these *strengthen* the evidence a supervised run produces
  (a tamper-proof score + an optional second-model agreement) but do **not** change the downgrade rule —
  banner removal stays a manual maintainer decision after ≥3 clean runs (ADR-031 solo-first: still no
  trust-tracker code).
- **Documented gap:** codex critic token-usage not budgeted (see §5).

---

## 7. Testing (TDD, mocked — no live model calls)

Run `skills/improve-skill/lib/tests/` as its **own** pytest call (basename-collision gotcha with
`lib/codemap/tests/`).

**A1 / scorer-lock:**
- diff targeting `eval/eval.json` → `ScorerTamperError` (via header parse).
- `target_file` = `eval/…` but diff body benign → still rejected (advisory-field check).
- diff escaping the skill dir (`../other-skill/…`, absolute path) → rejected.
- legitimate `SKILL.md` and `references/foo.md` diffs → **allowed** (no false positives).
- orchestrator: a `ScorerTamperError` increments `consecutive_proposer_errors`; 3 in a row →
  `NO_IMPROVEMENT_POSSIBLE`, no commit, no tampered `eval/`.

**A2 / critic gate (inject a fake critic eval-runner):**
- critic agrees (all-pass) → squash-merge; disposition notes `critic … confirmed`.
- critic disputes → branch kept; disposition `critic-flagged`; disputed ids surfaced.
- backend unavailable (fake raises `CriticBackendUnavailable`) → squash-merge proceeds with the
  `WITHOUT cross-model confirmation` notice.
- `critic_model is None` → **no** critic call; result identical to today (regression guard on the default path).
- `--keep-branch` + critic dispute → disposition stays `kept`, verdict reported.

**Threading / adapter:**
- `judge_model` / `judge_runner` default to Haiku / `run_print` → existing `run_evals` tests unchanged.
- `select_judge`: `codex`/`gpt*`/`o*` → codex runner; `claude-*`/other → `run_print`.
- `codex_cli.run_exec` TRUE/FALSE parse + timeout/error → mocked subprocess (like `claude_cli`).

Target: keep improve-skill's suite green and growing (baseline 190+1skip at `6775d06`).

---

## 8. Wiring / docs

- `skills/improve-skill/SKILL.md` — document `--critic-model` (opt-in, default single-judge), the
  always-on edit-lock invariant, final-gate semantics, and graceful degradation.
- `CHANGELOG.md` `[Unreleased]` — A1 (locked scorer) + A2 (cross-model critic) bullets.
- `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md` — A-theme note: A1+A2 built.
- `docs/superpowers/specs/2026-06-21-video-ingest-improvements.md` — recommended-order item 2 → BUILT.
- `wiki/log.md` — one dated 2026-06-27 entry (chronological invariant; append-only).

---

## 9. Non-goals (explicit)

- **No read-isolation / proposer sandbox** (decision #1).
- **No in-loop per-assertion critic** — final gate only (decision #2).
- **No Gemini** (maintainer-excluded).
- **No trust-tracker / auto-promotion** — banner downgrade stays manual (ADR-036 §3 / ADR-031).
- **No codex budget accounting** — documented gap, not solved here (§5).
- **No change to the skill-run path** — the skill under test always runs under `claude`.

---

## 10. Build order / slice

Slice branch `feat/eval-trust-a1a2` off `feat/project-ingest`; `--no-ff` merge back. Suggested TDD order:

1. `scorer_lock.py` + `ScorerTamperError` (pure, fast) → wire into `apply_proposed_change` → orchestrator catch. **A1 complete + green.**
2. `judge_model`/`judge_runner` threading through `judge_assertion`/`run_evals` (additive, default-preserving).
3. `codex_cli.run_exec` + `select_judge` router (mocked).
4. `ImproveSkillArgs.critic_model` + the final critic gate in `improve_skill` + dispositions. **A2 complete + green.**
5. Wiring (§8) + ADR amendment (§6).

Each step keeps the suite green before the next. A1 is independently shippable if A2 needs to spill.
