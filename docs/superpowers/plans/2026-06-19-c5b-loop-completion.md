# C5b — Self-Improvement Loop Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the C5a self-improvement loop able to score a *real* skill end-to-end (it currently cannot — nested `claude` from the `/tmp` eval sandbox loads no plugin skills), fix `--eval-runs > 1` to measure true skill-run variance, and prove it with one bounded supervised run logged to the ADR-036 gate.

**Architecture:** Run each nested skill-run from the **plugin-active worktree root** (so the worktree's *edited* skill loads and the eval scores the iteration's changes), while keeping wiki/plugin-data **writes** redirected to a throwaway tmp tree (the existing `eval_sandbox` env-redirect, unchanged). Then fix `run_evals` so `--eval-runs N` judges each of the N skill-runs' *own* output (real variance) instead of re-judging `runs[0]` N times. Finally, run one bounded, interactive supervised proof and log it.

**Tech Stack:** Python 3 (stdlib only — `subprocess`, `tempfile`, `pathlib`, `json`, `contextlib`, `dataclasses`); `pytest`; the `claude` CLI invoked **non-bare** via `lib/claude_cli.py`.

## Global Constraints

Every task's requirements implicitly include this section.

- **Scope is loop-completion ONLY.** Items in scope: (1) skill-loading unblock, (2) `--eval-runs > 1` variance, (3) one supervised proof run. **Out of scope (deferred to C5c):** dependency/call-graph layer, auto/cadence code-map refresh. Do not touch `lib/codemap/`.
- **Branch / base:** cut the worktree branch `feat/c5b-loop-completion` off the **post-C5a base `0ac023e`** (current `feat/project-ingest` HEAD), **NOT** `origin/main`. Worktree: `.claude/worktrees/c5b-loop-completion` (create via `superpowers:using-git-worktrees`).
- **Python style:** PEP 8; type annotations on all signatures; frozen dataclasses for new data types (immutability default); `black` / `isort` / `ruff` clean. Match the surrounding file's existing idioms.
- **Nested `claude` is always non-bare.** `--bare` skips the credential store → "Not logged in" (SPIKE_FINDINGS.md §2). Never pass `bare=True` for an authenticated call.
- **Test invocation (established repo gate):** `python3 -m pytest skills/improve-skill/lib/tests/ -q`. Do not introduce a new runner. Baseline before this slice: **167 passed, 1 skipped**.
- **Full slice gate (all must pass before PR):**
  - `python3 -m pytest skills/improve-skill/lib/tests/ -q` (green; +new tests, still 1 skip = the gated live smoke)
  - `claude plugin validate ./ --strict`
  - schema CI-parity: `python3 -c "import json,jsonschema; jsonschema.validate(json.load(open('skills/wiki-migration/schemas.json')), json.load(open('skills/wiki-migration/schemas.schema.json')))"` (this slice changes NO schema — parity must still hold)
- **Commits:** conventional `<type>(c5b): <desc>`; **NO `Co-Authored-By` / attribution footer.** Keep `git commit -m` to single-dash flags; never put a `--double-dash` token or the word "commit" + `--` in the same bash command (the `block-no-verify` hook false-positives). Run `git show --stat` / `gh pr create --base …` as **separate** commands.
- **SDD artifacts** (ledger, task briefs, reports, spike drivers) live in `.git/worktrees/c5b-loop-completion/sdd/` (untracked git-metadata; add `sdd/` to `.git/info/exclude`). From a worktree, `.git` is a *file* — use the resolved gitdir path, not `<worktree>/.git/...`.
- **Do NOT `git worktree remove`** the harness-owned worktree (C1/C2/C5a lesson) — leave it on disk for PR iteration.
- **Cost discipline:** real `claude` calls are non-trivial (~$0.36+/non-bare call + sub-agent fan-out; SPIKE_FINDINGS.md §3). Only Task 0 (spike) and Task 3 (proof) spend real money; both are bounded and user-gated. Tasks 1–2 are pure unit tests (mocked runner — zero spend).

---

## File Structure

| File | Create/Modify | Responsibility |
| --- | --- | --- |
| `skills/improve-skill/lib/SPIKE_FINDINGS.md` | Modify (append) | Task 0 records the skill-loading spike outcome (authoritative over this plan if it contradicts). |
| `skills/improve-skill/lib/sandbox.py` | Modify | `eval_sandbox(skill_cwd=...)` yields a plugin-active CWD while still redirecting writes to tmp. |
| `skills/improve-skill/lib/eval_runner.py` | Modify | `run_evals` passes the plugin-active worktree root as the skill-run CWD; `--eval-runs N` judges each run's own output. |
| `skills/improve-skill/lib/tests/test_sandbox.py` | Modify | New tests for the `skill_cwd` param (isolation property preserved). |
| `skills/improve-skill/lib/tests/test_eval_runner.py` | Modify | New tests: skill-run CWD is the plugin root; variance judged per-run. |
| `skills/improve-skill/learnings.md` | Modify | Flip the `--eval-runs>1` "known limitation" note to RESOLVED; append the supervised-run log entry. |
| `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md` | Modify | Relabel C5b → loop-completion (DONE); add C5c (dep/call-graph + auto-refresh, Not started). |
| `CHANGELOG.md` · `wiki/log.md` · `wiki/index.md` | Modify | Wire-up per the established per-slice pattern. |

No new modules, no new dataclasses, no schema changes. `ImproveSkillArgs.eval_runs` already exists (`types.py:52`); `eval_sandbox` and `run_evals` already exist.

---

## Task 0: Spike — confirm the worktree's *edited* skill loads from a plugin-active CWD

> **SUPERSEDED 2026-06-19 — folded into Task 3 (Step 1b).** The automated nested-`claude` spike was sandbox-denied (the same nested-`claude` friction prior sessions logged). Per maintainer decision, Tasks 1–2 build on the C5a live-proof's confirmed evidence that worktree skills load, and the remaining *edited-version* question moves to **Task 3 Step 1b**, run interactively where nested `claude` works cleanly. This section is retained for context; do **not** execute it as a standalone task.

**Why first:** the C5a live-proof established that plugin skills load from a plugin-active CWD but **NOT** from the empty `/tmp` sandbox (SPIKE_FINDINGS.md §"Live proof outcome"). The remaining unknown that gates the whole design: does a nested `claude` run from the **worktree root** load the *worktree's own edited* skill, or an installed copy elsewhere? If the worktree copy loads → Tasks 1–2 as written. If only an installed copy loads → STOP and re-plan Tasks 1–2 for an install/symlink mechanism.

**Files:**
- Modify (append): `skills/improve-skill/lib/SPIKE_FINDINGS.md`
- Spike driver (untracked): `.git/worktrees/c5b-loop-completion/sdd/spike_skill_loading.sh` (or run probes inline)

**This task spends real money** (~3 non-bare calls, ≈$1). Bounded, user-gated.

- [ ] **Step 1: Probe A — plugin skills load from the worktree CWD with the eval env-redirect.**

From the worktree root, run (non-bare, stream-json so activation is visible), with writes redirected exactly as the sandbox does:

```bash
TMP=$(mktemp -d) ; mkdir -p "$TMP/wiki" "$TMP/plugin-data"
env -C "$(pwd)" SF_WIKI_ROOT="$TMP/wiki" CLAUDE_PLUGIN_DATA="$TMP/plugin-data" \
  claude --print --output-format stream-json --verbose \
  "Use the recall skill to show me recent context." > "$TMP/probeA.jsonl" 2>&1
grep -o '"name":"Skill"[^}]*"skill":"[^"]*"' "$TMP/probeA.jsonl" | head
```

Expected: at least one `Skill` tool_use naming a framework skill (e.g. `recall`). Record the exact event shape seen.

- [ ] **Step 2: Probe C (decisive) — a worktree-ONLY skill activates.**

Create a throwaway skill that exists *only* in this worktree (not installed anywhere), then check it activates from the worktree CWD:

```bash
mkdir -p skills/_spike_probe
cat > skills/_spike_probe/SKILL.md <<'EOF'
---
name: _spike_probe
description: Spike probe — activate when the user says the exact phrase "zorptangle the frobnitz".
---
Reply with the single word: PROBE_OK.
EOF
env -C "$(pwd)" SF_WIKI_ROOT="$TMP/wiki" CLAUDE_PLUGIN_DATA="$TMP/plugin-data" \
  claude --print --output-format stream-json --verbose \
  "zorptangle the frobnitz" > "$TMP/probeC.jsonl" 2>&1
grep -c "_spike_probe" "$TMP/probeC.jsonl"
```

Expected (GO): `_spike_probe` appears as an activated `Skill` (the worktree's own new skill loaded). If it does NOT activate but Probe A's recall did, the loader is reading an installed copy, not the worktree → **NO-GO**.

- [ ] **Step 3: Clean up the throwaway skill + tmp.**

```bash
rm -rf skills/_spike_probe "$TMP"
git status --short   # MUST show clean (no _spike_probe left behind)
```

- [ ] **Step 4: Record findings in SPIKE_FINDINGS.md.**

Append a section `## Skill-loading fix spike (C5b, 2026-06-19)` with: the Probe A/C commands, their outcomes, the **GO/NO-GO verdict**, the chosen CWD (the worktree root), the measured per-call cost, and — if NO-GO — the required alternative (install/symlink the worktree as the active plugin for the eval). This file is authoritative over Tasks 1–2 if it contradicts them.

- [ ] **Step 5: Gate.**

GO ⇒ proceed to Task 1 as written. NO-GO ⇒ stop; re-plan Tasks 1–2 around the install/symlink mechanism the spike identified, then resume. Commit the SPIKE_FINDINGS.md update:

```bash
git add skills/improve-skill/lib/SPIKE_FINDINGS.md
git commit -m "docs(c5b): spike — worktree skill-loading verdict for eval sandbox"
```

---

## Task 1: Skill-loading unblock — run skill-runs from the plugin-active worktree root

**Files:**
- Modify: `skills/improve-skill/lib/sandbox.py` (the `eval_sandbox` ctx-mgr)
- Modify: `skills/improve-skill/lib/eval_runner.py:427` (derive plugin root) and the two skill-run call sites (`_run_skill` ~438-447, non-trigger loop ~483-492)
- Test: `skills/improve-skill/lib/tests/test_sandbox.py`, `skills/improve-skill/lib/tests/test_eval_runner.py`

**Interfaces:**
- Produces: `eval_sandbox(skill_cwd: Path | None = None)` — when `skill_cwd` is given, `SandboxEnv.cwd` is `skill_cwd` (a plugin-active dir); when `None`, `cwd` is the tmp root (unchanged legacy behavior). `wiki_root`/`plugin_data` remain tmp dirs in both cases; **teardown only ever removes the tmp root, never `skill_cwd`.**
- Consumes (in `run_evals`): `skill_cwd = Path(skills_root).resolve().parent` (the repo/worktree root, parent of `skills/`).

### Cycle A — `eval_sandbox` accepts `skill_cwd`

- [ ] **Step 1: Write the failing tests** (append to `test_sandbox.py`):

```python
def test_sandbox_uses_skill_cwd_when_given(tmp_path: Path):
    plugin_root = tmp_path / "repo"
    plugin_root.mkdir()
    with eval_sandbox(skill_cwd=plugin_root) as sb:
        assert sb.cwd == plugin_root              # runs from the plugin-active dir
        assert Path(sb.wiki_root).is_dir()         # writes still redirected to tmp
        assert sb.env["SF_WIKI_ROOT"] == str(sb.wiki_root)
        tmp_wiki = sb.wiki_root
    assert not Path(tmp_wiki).exists()             # tmp torn down
    assert plugin_root.exists()                    # plugin dir NEVER torn down


def test_sandbox_defaults_to_tmp_cwd_when_no_skill_cwd():
    with eval_sandbox() as sb:
        assert sb.cwd == sb.wiki_root.parent        # legacy: cwd is the tmp root
```

- [ ] **Step 2: Run to verify they fail.**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_sandbox.py -q`
Expected: FAIL — `eval_sandbox()` takes no `skill_cwd` argument (TypeError).

- [ ] **Step 3: Implement** — replace the `eval_sandbox` body in `sandbox.py`:

```python
@contextmanager
def eval_sandbox(skill_cwd: Path | None = None):
    """Run a skill with wiki/plugin-data WRITES redirected to a throwaway tmp tree.

    `skill_cwd`, when given, is the working directory handed to the subprocess
    (the plugin-active worktree root, so the worktree's own skills load and the
    eval scores the iteration's edits). When None, the cwd is the tmp root —
    the legacy isolated behavior. Teardown removes ONLY the tmp root; the
    skill_cwd (the real repo) is never touched.
    """
    root = Path(tempfile.mkdtemp(prefix="ren-c5a-eval-"))
    wiki_root = root / "wiki"
    plugin_data = root / "plugin-data"
    wiki_root.mkdir(parents=True)
    plugin_data.mkdir(parents=True)
    env = dict(os.environ)
    env["SF_WIKI_ROOT"] = str(wiki_root)
    env["CLAUDE_PLUGIN_DATA"] = str(plugin_data)
    cwd = skill_cwd if skill_cwd is not None else root
    try:
        yield SandboxEnv(env=env, cwd=cwd, wiki_root=wiki_root, plugin_data=plugin_data)
    finally:
        shutil.rmtree(root, ignore_errors=True)
```

- [ ] **Step 4: Run to verify pass** (including the pre-existing isolation tests, which must still pass):

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_sandbox.py -q`
Expected: PASS (all sandbox tests).

- [ ] **Step 5: Commit.**

```bash
git add skills/improve-skill/lib/sandbox.py skills/improve-skill/lib/tests/test_sandbox.py
git commit -m "feat(c5b): eval_sandbox accepts plugin-active skill_cwd"
```

### Cycle B — `run_evals` runs the skill from the plugin root

- [ ] **Step 6: Write the failing test** (append to `test_eval_runner.py`, in `TestRunEvalsBackend`):

```python
    def test_run_evals_runs_skill_from_plugin_root_cwd(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}])
        seen = {}

        def recording_runner(prompt, *, bare, model=None, detect_activation=False,
                             max_budget_usd=None, timeout_seconds=300, cwd=None, env=None):
            if detect_activation:                       # a skill-run
                seen["cwd"] = cwd
                return ClaudeRun("DONE", ApiUsage(20, 5), activated=("wrap",))
            return ClaudeRun("TRUE", ApiUsage(8, 1))    # a judge call

        run_evals("wrap", skills_root=skills_root, _runner=recording_runner)
        # plugin-active CWD = the repo/worktree root = parent of skills/
        assert Path(seen["cwd"]).resolve() == tmp_path.resolve()
```

- [ ] **Step 7: Run to verify it fails.**

Run: `python3 -m pytest "skills/improve-skill/lib/tests/test_eval_runner.py::TestRunEvalsBackend::test_run_evals_runs_skill_from_plugin_root_cwd" -q`
Expected: FAIL — `seen["cwd"]` is a tmp sandbox dir, not `tmp_path`.

- [ ] **Step 8: Implement** in `eval_runner.py`. After the `root = Path(skills_root)...` line (currently line 427), add the plugin-root derivation; then pass `skill_cwd` into both `eval_sandbox()` call sites.

Add right after `root = Path(skills_root) if skills_root else Path("skills")`:

```python
    # Plugin-active CWD: the worktree root (parent of skills/) so the nested
    # `claude` loads the worktree's own — possibly mid-iteration-edited — skill.
    # Writes stay redirected to the sandbox tmp tree (eval_sandbox env), so the
    # real wiki/plugin-data are untouched. (C5b skill-loading fix; SPIKE_FINDINGS.)
    plugin_root = root.resolve().parent
```

Change `_run_skill` (the inner helper) to:

```python
    def _run_skill(prompt: str):
        with eval_sandbox(skill_cwd=plugin_root) as sb:
            return runner(
                prompt,
                bare=False,
                detect_activation=True,
                timeout_seconds=timeout_seconds,
                cwd=sb.cwd,
                env=sb.env,
            )
```

Change the non-trigger loop's sandbox call the same way:

```python
    for nt in spec.non_triggers:
        with eval_sandbox(skill_cwd=plugin_root) as sb:
            r = runner(
                nt.prompt,
                bare=False,
                detect_activation=True,
                timeout_seconds=timeout_seconds,
                cwd=sb.cwd,
                env=sb.env,
            )
```

- [ ] **Step 9: Run to verify pass + no regressions** in the eval-runner suite:

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_eval_runner.py -q`
Expected: PASS (new test + all existing `TestRunEvalsBackend` tests; the injected fakes accept/ignore `cwd`).

- [ ] **Step 10: Commit.**

```bash
git add skills/improve-skill/lib/eval_runner.py skills/improve-skill/lib/tests/test_eval_runner.py
git commit -m "feat(c5b): run skill-runs from plugin-active worktree root so real skills load"
```

---

## Task 2: `--eval-runs > 1` judges each run's own output (true skill-run variance)

**Problem (confirmed, learnings.md:44-46):** `run_evals` does N skill-runs but then sets `output = runs[0].output_text` and judges *that one output* N times — fake variance (judge noise only, at temp-0 near-deterministic), while paying for N skill-runs.

**Fix:** judge each of the N skill-runs' own `output_text` once; majority across the N runs. Same judge-call count (N per assertion), now real variance.

**Files:**
- Modify: `skills/improve-skill/lib/eval_runner.py` (the binary-assertion judging block, currently lines 471-481)
- Test: `skills/improve-skill/lib/tests/test_eval_runner.py`

- [ ] **Step 1: Write the failing tests** (append to `test_eval_runner.py`). First add a varying fake near `_FakeRunner`:

```python
class _VaryingRunner:
    """Skill-runs return successive `outputs`; judge returns TRUE iff the judged
    output contains 'GOOD'. Lets a test distinguish 'judge each run' from the old
    'judge runs[0] only'."""
    def __init__(self, outputs, activated=("wrap",)):
        self.outputs = list(outputs)
        self.activated = activated
        self._i = 0

    def __call__(self, prompt, *, bare, model=None, detect_activation=False,
                 max_budget_usd=None, timeout_seconds=300, cwd=None, env=None):
        if detect_activation:                       # a skill-run
            out = self.outputs[self._i]
            self._i += 1
            return ClaudeRun(out, ApiUsage(20, 5), activated=self.activated)
        return ClaudeRun("TRUE" if "GOOD" in prompt else "FALSE", ApiUsage(8, 1))
```

Then the two distinguishing tests (in `TestRunEvalsBackend`):

```python
    def test_eval_runs_judges_each_run_not_just_first(self, tmp_path):
        # runs[0]='BAD' DISAGREES with the GOOD majority. Old code (judge runs[0]
        # x3) -> [F,F,F] -> FAIL. New code (judge each run) -> [F,T,T] -> PASS.
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["output is acceptable"]}])
        fake = _VaryingRunner(outputs=["BAD", "GOOD", "GOOD"])
        res = run_evals("wrap", skills_root=skills_root, _runner=fake, eval_runs=3)
        assert res.total == 1 and res.passed == 1 and res.score == 1.0

    def test_eval_runs_majority_fail_when_runs_disagree(self, tmp_path):
        # runs[0]='GOOD' but majority is BAD. Old -> [T,T,T] PASS; new -> [T,F,F] FAIL.
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["output is acceptable"]}])
        fake = _VaryingRunner(outputs=["GOOD", "BAD", "BAD"])
        res = run_evals("wrap", skills_root=skills_root, _runner=fake, eval_runs=3)
        assert res.passed == 0 and res.failing_assertion_ids == ("t1:0",)
```

- [ ] **Step 2: Run to verify they fail.**

Run: `python3 -m pytest "skills/improve-skill/lib/tests/test_eval_runner.py::TestRunEvalsBackend::test_eval_runs_judges_each_run_not_just_first" "skills/improve-skill/lib/tests/test_eval_runner.py::TestRunEvalsBackend::test_eval_runs_majority_fail_when_runs_disagree" -q`
Expected: FAIL — the first errors (old code judges `runs[0]='BAD'` → fails) and/or the second passes-when-it-should-fail, because only `runs[0]` is judged.

- [ ] **Step 3: Implement** — in `eval_runner.py`, replace the block that begins `output = runs[0].output_text` (currently lines 471-481) with:

```python
        # Judge each run's OWN output once, majority across the N runs (true
        # skill-run variance). NOT runs[0] re-judged N times. (C5b variance fix.)
        for i, assertion in enumerate(test.binary_assertions):
            votes = []
            for r in runs:
                ok, ju = judge_assertion(r.output_text, assertion, _runner=runner)
                usage = _add(usage, ju)
                votes.append(ok)
            if _majority(votes):
                passed += 1
            else:
                failing.append(make_failing_assertion_id(test.id, i))
```

(The standalone `output = runs[0].output_text` line is removed — `output` is no longer used.)

- [ ] **Step 4: Run to verify pass + no regressions.**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_eval_runner.py -q`
Expected: PASS. Note `test_all_pass_when_judge_true_and_activated` (eval_runs default 1) still passes — with one run, `for r in runs` judges `runs[0]` exactly once, identical to before.

- [ ] **Step 5: Update the `run_evals` docstring** for `eval_runs` (currently `eval_runner.py:398`) to read:

```python
        eval_runs: Number of skill-runs per test; each run's own output is judged
            and the per-assertion verdict is a majority across the N runs.
```

- [ ] **Step 6: Commit.**

```bash
git add skills/improve-skill/lib/eval_runner.py skills/improve-skill/lib/tests/test_eval_runner.py
git commit -m "fix(c5b): eval-runs>1 judges each skill-run output, not runs[0] N times"
```

---

## Task 3: Supervised proof run + ADR-036 log entry

**Goal:** prove the loop scores a *real* skill end-to-end and record the first of the ≥3 clean supervised runs the ADR-036 downgrade gate requires. **This task spends real money** (~$1–2, bounded by the budget cap) and is **interactive / user-gated** (ADR-036 §1 interactive default). It runs AFTER Tasks 1–2 are merged into the worktree branch and the unit suite is green.

**Files:**
- Modify: `skills/improve-skill/learnings.md` (the "Supervised run log (ADR-036 downgrade gate)" section, currently line 40)

- [ ] **Step 1: Pick the cheapest meaningful target skill** — the shipped skill with the fewest total assertions:

```bash
python3 - <<'EOF'
from pathlib import Path
from skills.improve_skill.lib.eval_runner import load_eval_spec, compute_total_assertions
root = Path("skills")
rows = []
for d in sorted(root.iterdir()):
    f = d / "eval" / "eval.json"
    if f.is_file():
        try:
            rows.append((compute_total_assertions(load_eval_spec(d)), d.name))
        except Exception as e:
            rows.append((-1, f"{d.name} (load error: {e})"))
for n, name in sorted(rows):
    print(f"{n:>3}  {name}")
EOF
```

Choose the skill with the smallest positive total (do **not** pick `improve-skill` itself — self-application is deferred per learnings.md). Record the chosen `<skill>`.

- [ ] **Step 1b: Edited-version check (the folded Task-0 spike).** Confirm the loop will score the *worktree's* skill (with iteration edits), not an installed/stale copy. Run interactively (your terminal, `!`-prefix), bounded:

  1. Append one line to `skills/<skill>/SKILL.md` instructing the skill to end its reply with the exact token `WTLOAD_OK_8842`.
  2. From the worktree root, trigger it once:
     `T=$(mktemp -d); mkdir -p "$T/w" "$T/p"; env -C "$PWD" SF_WIKI_ROOT="$T/w" CLAUDE_PLUGIN_DATA="$T/p" timeout 240 claude --print --output-format stream-json --verbose --max-budget-usd 1.00 "<prompt that triggers <skill>>" 2>&1 | grep -c WTLOAD_OK_8842; rm -rf "$T"`
  3. `git checkout -- skills/<skill>/SKILL.md` to revert the marker.
  4. **Result ≥ 1 → the worktree's edited skill loads; the C5b premise holds — proceed.** `0` → the loader is using an installed/stale copy: STOP and re-plan Task 1 cycle B around an install/symlink mechanism before the loop is correct.

- [ ] **Step 2: Run the bounded, interactive proof** from the worktree root:

```
/ren:improve-skill <skill> --max-iterations 1 --max-budget-usd 2
```

(Interactive — NOT `--autonomous`. The single iteration + $2 cap bound the spend.)

- [ ] **Step 3: Verify the unblock actually worked.** The run is a valid proof iff **all** hold:
  - exit reason is **NOT** `requires_configured_backend` (the backend ran);
  - the baseline `EvalResult.total > 0` and the score came from a **real activated skill-run** (the target skill appeared as an activated `Skill` — confirm in the run's transcript/output);
  - the loop behaved sanely (kept on improve/neutral, reverted on score drop, no crash).

  If exit was `requires_configured_backend` or `total == 0`, the skill-loading fix did NOT take effect → STOP, return to Task 0/1 (re-check the plugin-active CWD against the spike finding). Do not log a failed run as clean.

- [ ] **Step 4: Log the run** — replace the placeholder line in `learnings.md` (currently line 40):

```
_No runs yet. Log entries here; remove EXPERIMENTAL banner after ≥3 clean runs._
```

with the first entry (fill the real values; keep the gate reminder):

```
- **2026-06-19 — `<skill>`** · iterations: `<n>` · score: `<before>` → `<after>` · reverts: `<r>` · ~cost: `$<usd>` · clean: yes (C5b skill-loading proof — eval scored a real activated skill-run).

_Run 1 of ≥3. Remove the EXPERIMENTAL banner (SKILL.md, ADR-036 §3) only after ≥3 clean runs._
```

- [ ] **Step 5: Commit.**

```bash
git add skills/improve-skill/learnings.md
git commit -m "docs(c5b): log first supervised proof run (ADR-036 gate, 1 of 3)"
```

---

## Task 4: Wire-up — roadmap relabel, learnings, CHANGELOG, wiki

Done last, after the proof confirms the slice works, so every "DONE" is honest.

**Files:** `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`, `skills/improve-skill/learnings.md`, `CHANGELOG.md`, `wiki/log.md`, `wiki/index.md`.

- [ ] **Step 1: Roadmap — relabel C5b and add C5c.** In `…/2026-06-11-agentic-os-rebuild-roadmap.md`, replace the C5b table row:

Old:
```
| **C5b** | Self-improvement — dep/call-graph + auto-refresh | P5 | extend `sf-improve-skill` | C5a | — | Not started |
```
New (two rows):
```
| **C5b** | Self-improvement — loop completion (skill-loading fix + eval-run variance + supervised proof) | P5 | extend `sf-improve-skill` | C5a | — | ✅ **DONE 2026-06-19** — eval sandbox runs skill-runs from the plugin-active worktree root (real skills load); `--eval-runs N` judges each run's own output; 1st supervised proof logged (ADR-036 gate); plan `docs/superpowers/plans/2026-06-19-c5b-loop-completion.md` |
| **C5c** | Self-improvement — dep/call-graph + auto-refresh | P6 | extend `sf-improve-skill` + `lib/codemap/` | C5b, C2 | — | Not started |
```

- [ ] **Step 2: Roadmap — fix the C5a note.** Replace (currently line 63):

Old:
```
  **C5b (dep/call-graph + auto-refresh) remains.** Gate: pytest green; `plugin validate --strict` ✔; schema CI ✔.
```
New:
```
  **C5b (loop completion: skill-loading fix + eval-run variance + supervised proof) followed; C5c (dep/call-graph + auto-refresh) remains.** Gate: pytest green; `plugin validate --strict` ✔; schema CI ✔.
```

- [ ] **Step 3: Roadmap — extend the critical-path diagram.** Replace (currently line 139):

Old:
```
  └──► C1 ──► C2 ──► C5a ──► C5b (populated brain → code-map → self-improvement backend → dep/call-graph)
```
New:
```
  └──► C1 ──► C2 ──► C5a ──► C5b ──► C5c (populated brain → code-map → self-improvement backend → loop completion → dep/call-graph)
```

- [ ] **Step 4: learnings.md — flip the limitation note to RESOLVED.** Replace the block (currently lines 44-46):

Old:
```
### 2026-06-18 — Known limitation: `--eval-runs > 1` measures judge variance, not skill-run variance

`--eval-runs > 1` re-runs the LLM judge N times against the same `runs[0].output_text` (the first skill invocation's output), so majority voting reduces judge variance only — a C5b follow-up is needed to re-run the skill itself N times and judge each run independently for true skill-run variance measurement; the default `--eval-runs 1` is unaffected.
```
New:
```
### 2026-06-18 — RESOLVED in C5b: `--eval-runs > 1` now measures true skill-run variance

Originally `--eval-runs > 1` re-ran the LLM judge N times against the same `runs[0].output_text`, so majority voting reduced judge variance only. **Fixed in C5b (2026-06-19):** `run_evals` now judges each of the N skill-runs' own output once and takes the majority across runs — real skill-run variance. The default `--eval-runs 1` is unchanged.
```

- [ ] **Step 5: CHANGELOG.md** — add one line under the current unreleased/top section:

```
- **C5b — self-improvement loop completion:** the eval loop now scores real skills (skill-runs execute from the plugin-active worktree root); `--eval-runs N` measures true skill-run variance; first supervised proof logged. Still EXPERIMENTAL until ≥3 clean runs (ADR-036).
```

- [ ] **Step 6: wiki/log.md** — append (chronological invariant — newest at the established end; do not rewrite prior days) an entry dated 2026-06-19 recording C5b loop-completion DONE, mirroring the C5a entry's style (slice, branch, what shipped, gate). **Step 7: wiki/index.md** — update the `improve-skill` summary only if its one-line description shifted (it now scores real skills end-to-end); otherwise leave unchanged.

- [ ] **Step 8: Full slice gate + commit.**

```bash
python3 -m pytest skills/improve-skill/lib/tests/ -q
claude plugin validate ./ --strict
python3 -c "import json,jsonschema; jsonschema.validate(json.load(open('skills/wiki-migration/schemas.json')), json.load(open('skills/wiki-migration/schemas.schema.json')))"
```
Expected: pytest green (≈172 passed, 1 skipped); validate ✔; schema parity ✔. Then:

```bash
git add docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md skills/improve-skill/learnings.md CHANGELOG.md wiki/log.md wiki/index.md
git commit -m "docs(c5b): wire-up — roadmap relabel C5b->loop-completion + add C5c; learnings; changelog; wiki"
```

---

## Self-Review

**1. Spec coverage** (the three in-scope items + deferral):
- Skill-loading unblock → Task 0 (spike) + Task 1 (sandbox `skill_cwd` + `run_evals` plugin-root CWD). ✓
- `--eval-runs > 1` variance → Task 2. ✓
- Supervised proof + ADR-036 log → Task 3. ✓
- Deferral of dep/call-graph + auto-refresh → Task 4 creates the C5c row; Global Constraints forbid touching `lib/codemap/`. ✓

**2. Placeholder scan:** code steps carry full code; doc steps carry verbatim old→new blocks for the strings confirmed in-repo (roadmap, learnings, SKILL banner left intentionally unchanged). `<skill>`/`<n>`/`<usd>` in Task 3 are runtime-measured values, not plan placeholders — they cannot be known before the run, and the surrounding format is fully specified. CHANGELOG/wiki append-targets are described by section because their current top content isn't pinned here; the new content is verbatim. ✓

**3. Type consistency:** `eval_sandbox(skill_cwd: Path | None=None)` → `SandboxEnv.cwd` (existing field) consumed by `run_print(cwd=...)` (existing param). `plugin_root = root.resolve().parent` is a `Path`. `judge_assertion(r.output_text, assertion, _runner=runner)` matches the existing signature (`eval_runner.py:317`). `_majority` / `_add` / `make_failing_assertion_id` unchanged. `eval_runs` is already on `ImproveSkillArgs` and `run_evals`. No signature drift. ✓

**Note on Task 0 dependency:** Tasks 1–2's code assumes the spike returns GO (worktree-CWD loads the worktree's skill). If NO-GO, Task 0 Step 5 halts and re-plans Tasks 1–2 for an install/symlink mechanism — an explicit, honest contingency, not a silent gap.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-19-c5b-loop-completion.md`.
