# C5a — Self-Improvement Loop Made Real — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the two stubbed LLM layers of `/ren:improve-skill` (eval-runner + change-proposer) behind their existing injected-callable seams, so the Karpathy loop runs end-to-end and demonstrably improves a real skill.

**Architecture:** All `claude` CLI invocation hides behind a new `lib/claude_cli.py` wrapper; the eval-runner (our own LLM-judge) and the change-proposer both call it. Every unit test mocks that one wrapper — only the Phase-0 spike and a gated live smoke touch the real binary. The orchestrator changes in two small spots (a `ProposerError` skip-path and eval-usage budget plumbing). Autonomy stays gated per the new bike-method ADR.

**Tech Stack:** Python 3.12 (stdlib + pytest only — no new runtime deps), the `claude` CLI (`--print`/`--bare`/`--output-format`), git-as-memory. Spec: `docs/superpowers/specs/2026-06-18-c5a-self-improvement-loop-design.md`.

## Global Constraints

- **Stdlib + pytest only** for `skills/improve-skill/lib/`. No new runtime dependencies. PEP 8, type annotations on all signatures, frozen dataclasses (dotfiles `python/coding-style.md`).
- **All `claude` invocation goes through `lib/claude_cli.py`.** No other module shells `claude` directly. Unit tests mock `claude_cli`; only Task 1 (spike) and Task 9 (live smoke) invoke the real binary.
- **SPIKE correction (2026-06-18, see `skills/improve-skill/lib/SPIKE_FINDINGS.md`):** `--bare` skips the credential store, so all *authenticated* calls (skill-run, judge, proposer) are **non-bare** — auth then needs no user action. Cost is controlled via `--model` (Haiku judge) + the empty-wiki sandbox + `--max-budget-usd`. The live proof (Task 9) is bounded: small-eval target skill, `--max-budget-usd ≈ $2`, `--max-iterations ≈ 3`, and it **measures + records real cost** (fall back to a lighter eval if prohibitive).
- **Spike gates the build (Task 1).** If activation can't be detected or side-effects can't be contained, STOP and return to the maintainer. Tasks 2+ use the invocation surface the spike records in `SPIKE_FINDINGS.md`.
- **Bike-method:** autonomous mode keeps requiring BOTH `--max-iterations` and `--max-budget-usd` (pre-flight, already built). The EXPERIMENTAL posture stays; no trust-tracking code is added.
- **Eval determinism:** judge runs at temperature 0; the skill-run defaults to a single run, `--eval-runs N` opts into majority-binarized scoring.
- **Read-only on the real wiki/project during eval** — eval skill-runs are env-redirected to tmp; a property test asserts byte-identity.
- **No `schemas.json` change** (no new wiki page-type). `claude plugin validate ./ --strict` must pass.
- **Commits:** conventional `<type>(scope): desc`; **NO** `Co-Authored-By`/attribution footer. **Hook gotcha:** never put the word "commit" beside a `--`double-dash flag in one bash command — keep `git commit -m` with single-dash flags only; run any `git log --oneline`/`git show --stat` as a SEPARATE command.
- **Run tests from the plugin root:** `python3 -m pytest skills/improve-skill/lib/tests/ -q`.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `skills/improve-skill/lib/SPIKE_FINDINGS.md` | Create | Spike findings + the confirmed `claude` invocation surface. |
| `skills/improve-skill/lib/claude_cli.py` | Create | The only module that shells `claude`. `ClaudeRun` dataclass + `run_print()`. |
| `skills/improve-skill/lib/sandbox.py` | Create | `eval_sandbox()` ctx-mgr: tmp CWD + `SF_WIKI_ROOT`/`CLAUDE_PLUGIN_DATA` redirection. |
| `skills/improve-skill/lib/types.py` | Modify | Add `EvalResult.usage`; add `ProposerError`; add `ImproveSkillArgs.eval_runs`. |
| `skills/improve-skill/lib/eval_runner.py` | Modify | Real `run_evals()` body + `judge_assertion()`. (Pure helpers untouched.) |
| `skills/improve-skill/lib/__init__.py` | Modify | Real `_default_change_proposer()`; `ProposerError` skip-path; eval-usage budget plumbing; thread `--eval-runs`/`skills_root` into the default eval-runner. |
| `skills/improve-skill/eval/eval.json` | Create | Minimal self-eval (activation + refusal assertions). |
| `skills/improve-skill/references/eval-runner.md` | Modify | Flip the V1 decision path-1 → path-2. |
| `skills/improve-skill/references/model-pricing.json` | Modify | Ensure a Haiku price row exists (judge cost). |
| `skills/improve-skill/SKILL.md` | Modify | Banner update; document `--eval-runs`. |
| `skills/improve-skill/learnings.md` | Modify | Note the backend wiring + spike findings pointer. |
| `wiki/decisions/036-bike-method-earned-autonomy.md` | Create | ADR-036. |
| `wiki/decisions/012-two-layer-self-improvement.md` | Modify | Amendment: backend wired (path 2); earned-autonomy → ADR-036. |
| `README.md`, `CHANGELOG.md`, `wiki/index.md`, `wiki/log.md`, roadmap | Modify | Wire-up; roadmap C5 row → C5a DONE (C5b remaining). |
| `skills/improve-skill/lib/tests/test_claude_cli.py` | Create | Wrapper tests (mock `subprocess.run`). |
| `skills/improve-skill/lib/tests/test_sandbox.py` | Create | Sandbox env + teardown + real-wiki-untouched tests. |
| `skills/improve-skill/lib/tests/test_eval_runner.py` | Modify | Real `run_evals` tests (mock `claude_cli`). |
| `skills/improve-skill/lib/tests/test_orchestrator.py` | Modify | Full-loop tests (mock wrapper); proposer + budget. |

---

## Task 1: Phase-0 spike — verify the headless `claude` surface (GATE)

This is an exploratory spike, **not** TDD. It runs the real `claude` binary, records findings, and decides go/no-go. The findings file is the source of truth Tasks 2+ read for exact flags.

**Files:**
- Create: `skills/improve-skill/lib/SPIKE_FINDINGS.md`

**Prerequisite:** `claude --version` returns a version; a credential is available (logged-in CLI or `ANTHROPIC_API_KEY`). If not, STOP — record "spike blocked: no runnable `claude`" and return to maintainer.

- [ ] **Step 1: Probe — does a skill run + produce parseable JSON?**

Run (pick a low-side-effect skill, e.g. `recall`):
```bash
mkdir -p /tmp/c5a-spike/wiki /tmp/c5a-spike/data
SF_WIKI_ROOT=/tmp/c5a-spike/wiki CLAUDE_PLUGIN_DATA=/tmp/c5a-spike/data \
  claude --print --output-format json "Use the recall skill to find notes about onboarding" \
  > /tmp/c5a-spike/run.json 2>/tmp/c5a-spike/run.err; echo "exit=$?"
```
Record in `SPIKE_FINDINGS.md`: the exit code, the JSON top-level keys, where the assistant text lives (e.g. `.result`), and where token usage lives (e.g. `.usage`).

- [ ] **Step 2: Probe — is skill activation detectable?**

Run the same prompt with the event stream:
```bash
SF_WIKI_ROOT=/tmp/c5a-spike/wiki CLAUDE_PLUGIN_DATA=/tmp/c5a-spike/data \
  claude --print --output-format stream-json --verbose "Use the recall skill to find notes about onboarding" \
  > /tmp/c5a-spike/stream.jsonl 2>&1; echo "exit=$?"
```
Inspect for a Skill/tool-use event naming the activated skill. Record: the exact event shape that proves "skill `<name>` activated" (or "NOT detectable" → see gate).

- [ ] **Step 3: Probe — are side-effects contained?**

After Steps 1–2, confirm the real repo is untouched and writes (if any) landed under `/tmp/c5a-spike`:
```bash
git -C "$(git rev-parse --show-toplevel)" status --porcelain | head
find /tmp/c5a-spike -type f | head
```
Record whether the skill honored `SF_WIKI_ROOT`/`CLAUDE_PLUGIN_DATA`. Repeat with one wiki-writing skill if available.

- [ ] **Step 4: Probe — proposer JSON path.**

```bash
claude --bare --print --output-format json \
  "Output exactly this JSON and nothing else: {\"target_file\":\"SKILL.md\",\"unified_diff\":\"\",\"summary\":\"x\",\"rationale\":\"y\"}" \
  > /tmp/c5a-spike/proposer.json 2>&1; echo "exit=$?"
```
Record: is the assistant's JSON reliably extractable from the result field?

- [ ] **Step 5: Write `SPIKE_FINDINGS.md` + decide go/no-go.**

Record, in this structure: the confirmed `run_print` invocation for (a) a skill-run with activation detection and (b) a bare judge/proposer call; the JSON paths for text/usage; the activation-event shape; the side-effect-containment result; and a **GO / NO-GO** line.

**GATE:** If Step 2 shows activation is **not** detectable, or Step 3 shows side-effects are **not** containable by env-redirection → **STOP. Do not proceed.** Report to the maintainer with the finding (options: defer trigger/non-trigger assertions; or use a tmp git-clone sandbox).

- [ ] **Step 6: Commit**

```bash
git add skills/improve-skill/lib/SPIKE_FINDINGS.md
git commit -m "spike(c5a): verify headless claude surface for eval-runner + proposer"
```

---

## Task 2: `claude_cli.py` — the subprocess wrapper

**Files:**
- Create: `skills/improve-skill/lib/claude_cli.py`
- Test: `skills/improve-skill/lib/tests/test_claude_cli.py`

**Interfaces:**
- Consumes: `types.ApiUsage`; the invocation surface from `SPIKE_FINDINGS.md`.
- Produces: `ClaudeRun(output_text: str, usage: ApiUsage, activated: tuple[str, ...], raw: str, timed_out: bool=False)`; `run_print(prompt: str, *, bare: bool, model: str | None = None, detect_activation: bool = False, max_budget_usd: float | None = None, timeout_seconds: int = 300, cwd: Path | None = None, env: dict | None = None) -> ClaudeRun`.

- [ ] **Step 1: Write the failing test** (`test_claude_cli.py`)

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from ..claude_cli import ClaudeRun, run_print
from ..types import ApiUsage


def _fake_completed(stdout: str, returncode: int = 0):
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr="")


def test_run_print_parses_text_and_usage(monkeypatch):
    payload = json.dumps({
        "result": "hello world",
        "usage": {"input_tokens": 10, "output_tokens": 4},
    })
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(payload))
    run = run_print("hi", bare=True, timeout_seconds=30)
    assert isinstance(run, ClaudeRun)
    assert run.output_text == "hello world"
    assert run.usage == ApiUsage(input_tokens=10, output_tokens=4)
    assert run.timed_out is False


def test_run_print_timeout_sets_flag(monkeypatch):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)
    monkeypatch.setattr(subprocess, "run", _raise)
    run = run_print("hi", bare=True, timeout_seconds=1)
    assert run.timed_out is True
    assert run.output_text == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_claude_cli.py -q`
Expected: FAIL (`ModuleNotFoundError: ...claude_cli`).

- [ ] **Step 3: Write minimal implementation** (`claude_cli.py`)

```python
"""The single module that shells the `claude` CLI. All other modules mock this.

Invocation surface confirmed by the Phase-0 spike (see SPIKE_FINDINGS.md). If the
spike recorded different flags/JSON paths than the defaults below, update this file
to match and note it in SPIKE_FINDINGS.md.

SPIKE 2026-06-18: `--bare` does NOT authenticate (it skips the credential store) — every
authenticated call must be non-bare. `bare=True` is retained only for unauthenticated/local use.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .types import ApiUsage


@dataclass(frozen=True)
class ClaudeRun:
    output_text: str
    usage: ApiUsage
    activated: tuple[str, ...] = ()
    raw: str = ""
    timed_out: bool = False
    is_error: bool = False   # SPIKE: claude JSON carries is_error; treat True as a failed run


def _usage_from(obj: dict) -> ApiUsage:
    u = obj.get("usage") or {}
    return ApiUsage(
        input_tokens=int(u.get("input_tokens", 0)),
        output_tokens=int(u.get("output_tokens", 0)),
        cache_read_input_tokens=int(u.get("cache_read_input_tokens", 0)),
        cache_creation_input_tokens=int(u.get("cache_creation_input_tokens", 0)),
    )


def _activated_from_stream(raw: str) -> tuple[str, ...]:
    """Parse a stream-json transcript for Skill activation events.
    Event shape confirmed by the spike (SPIKE_FINDINGS.md §activation)."""
    names: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Spike-confirmed shape: a tool_use event for the Skill tool carries the skill name.
        if ev.get("type") == "tool_use" and ev.get("name") == "Skill":
            skill = (ev.get("input") or {}).get("name") or (ev.get("input") or {}).get("skill")
            if skill:
                names.append(str(skill))
    return tuple(names)


def run_print(
    prompt: str,
    *,
    bare: bool,
    model: str | None = None,
    detect_activation: bool = False,
    max_budget_usd: float | None = None,
    timeout_seconds: int = 300,
    cwd: Path | None = None,
    env: dict | None = None,
) -> ClaudeRun:
    cmd = ["claude", "--print"]
    if bare:
        cmd.append("--bare")
    cmd += ["--output-format", "stream-json", "--verbose"] if detect_activation else ["--output-format", "json"]
    if model:
        cmd += ["--model", model]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", f"{max_budget_usd:.4f}"]
    cmd.append(prompt)

    try:
        proc = subprocess.run(
            cmd, input=None, text=True, capture_output=True,
            timeout=timeout_seconds, cwd=cwd, env=env,
        )
    except subprocess.TimeoutExpired:
        return ClaudeRun(output_text="", usage=ApiUsage(0, 0), raw="", timed_out=True)

    raw = proc.stdout or ""
    if detect_activation:
        # stream-json: the final result event carries text + usage; events carry activation.
        text, usage = _last_result(raw)
        return ClaudeRun(output_text=text, usage=usage, activated=_activated_from_stream(raw), raw=raw)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return ClaudeRun(output_text=raw.strip(), usage=ApiUsage(0, 0), raw=raw)
    return ClaudeRun(output_text=str(obj.get("result", "")).strip(), usage=_usage_from(obj),
                     raw=raw, is_error=bool(obj.get("is_error", False)))


def _last_result(raw: str) -> tuple[str, ApiUsage]:
    text, usage = "", ApiUsage(0, 0)
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            text = str(ev.get("result", text))
            usage = _usage_from(ev)
    return text, usage
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_claude_cli.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add skills/improve-skill/lib/claude_cli.py skills/improve-skill/lib/tests/test_claude_cli.py
git commit -m "feat(c5a): claude_cli subprocess wrapper (ClaudeRun + run_print)"
```

---

## Task 3: `types.py` additions — `EvalResult.usage`, `ProposerError`, `eval_runs`

**Files:**
- Modify: `skills/improve-skill/lib/types.py`
- Test: `skills/improve-skill/lib/tests/test_eval_runner.py` (one new assertion in `TestEmptyEvalResult`)

**Interfaces:**
- Produces: `EvalResult.usage: ApiUsage` (default `ApiUsage(0,0)`); `class ProposerError(Exception)`; `ImproveSkillArgs.eval_runs: int = 1`.

- [ ] **Step 1: Write the failing test** (append to `test_eval_runner.py`)

```python
def test_eval_result_has_default_usage():
    from ..types import ApiUsage
    r = empty_eval_result()
    assert r.usage == ApiUsage(0, 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_eval_runner.py -k usage -q`
Expected: FAIL (`AttributeError: 'EvalResult' object has no attribute 'usage'`).

- [ ] **Step 3: Implement the additions** (`types.py`)

In `EvalResult`, add as the last field:
```python
    usage: "ApiUsage" = field(default_factory=lambda: ApiUsage(0, 0))
```
(Add to `ImproveSkillArgs`: `eval_runs: int = 1`.) After `PreFlightError`, add:
```python
class ProposerError(Exception):
    """Raised by the change-proposer when claude returns no parseable change.
    The orchestrator treats it as a skipped iteration, not a fatal stop."""
```
`ApiUsage` and `field` are already imported in `types.py`.

- [ ] **Step 4: Run to verify it passes (+ no regressions)**

Run: `python3 -m pytest skills/improve-skill/lib/tests/ -q`
Expected: PASS (145 — the 144 baseline + 1 new). `empty_eval_result` keyword-only construction is unaffected (new field is defaulted).

- [ ] **Step 5: Commit**

```bash
git add skills/improve-skill/lib/types.py skills/improve-skill/lib/tests/test_eval_runner.py
git commit -m "feat(c5a): EvalResult.usage + ProposerError + eval_runs arg"
```

---

## Task 4: `sandbox.py` — env-redirected eval sandbox

**Files:**
- Create: `skills/improve-skill/lib/sandbox.py`
- Test: `skills/improve-skill/lib/tests/test_sandbox.py`

**Interfaces:**
- Produces: `eval_sandbox() -> ContextManager[SandboxEnv]` where `SandboxEnv(env: dict, cwd: Path, wiki_root: Path, plugin_data: Path)`. On exit, the tmp tree is removed and `os.environ` is restored.

- [ ] **Step 1: Write the failing test** (`test_sandbox.py`)

```python
from __future__ import annotations

import os
from pathlib import Path

from ..sandbox import eval_sandbox


def test_sandbox_redirects_and_restores():
    before = dict(os.environ)
    with eval_sandbox() as sb:
        assert Path(sb.wiki_root).is_dir()
        assert sb.env["SF_WIKI_ROOT"] == str(sb.wiki_root)
        assert sb.env["CLAUDE_PLUGIN_DATA"] == str(sb.plugin_data)
        tmp = sb.wiki_root
    assert not Path(tmp).exists()           # torn down
    assert dict(os.environ) == before        # process env untouched


def test_sandbox_env_is_a_copy_not_global_mutation():
    with eval_sandbox() as sb:
        assert "SF_WIKI_ROOT" not in os.environ or os.environ.get("SF_WIKI_ROOT") != sb.env["SF_WIKI_ROOT"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_sandbox.py -q`
Expected: FAIL (`ModuleNotFoundError: ...sandbox`).

- [ ] **Step 3: Implement** (`sandbox.py`)

```python
"""Eval sandbox: run a skill with wiki/plugin-data writes redirected to a tmp tree,
so the real wiki/project is left byte-identical. We build an env COPY (passed to the
subprocess) rather than mutating os.environ — keeps the orchestrator process clean."""
from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxEnv:
    env: dict
    cwd: Path
    wiki_root: Path
    plugin_data: Path


@contextmanager
def eval_sandbox():
    root = Path(tempfile.mkdtemp(prefix="ren-c5a-eval-"))
    wiki_root = root / "wiki"
    plugin_data = root / "plugin-data"
    wiki_root.mkdir(parents=True)
    plugin_data.mkdir(parents=True)
    env = dict(os.environ)
    env["SF_WIKI_ROOT"] = str(wiki_root)
    env["CLAUDE_PLUGIN_DATA"] = str(plugin_data)
    try:
        yield SandboxEnv(env=env, cwd=root, wiki_root=wiki_root, plugin_data=plugin_data)
    finally:
        shutil.rmtree(root, ignore_errors=True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_sandbox.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add skills/improve-skill/lib/sandbox.py skills/improve-skill/lib/tests/test_sandbox.py
git commit -m "feat(c5a): eval sandbox (env-redirected tmp wiki/plugin-data)"
```

---

## Task 5: `run_evals()` real body + `judge_assertion()`

**Files:**
- Modify: `skills/improve-skill/lib/eval_runner.py`
- Test: `skills/improve-skill/lib/tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `claude_cli.run_print`, `sandbox.eval_sandbox`, the pure helpers (`load_eval_spec`, `filter_tests_by_ids`, `compute_total_assertions`, `make_failing_assertion_id`, `empty_eval_result`), `EvalResult`, `ApiUsage`.
- Produces: `judge_assertion(output_text: str, assertion: str, *, timeout_seconds: int = 120, _runner=None) -> tuple[bool, ApiUsage]`; real `run_evals(skill_name, *, eval_subset_ids=None, timeout_seconds=300, cwd=None, eval_runs=1, skills_root=None, _runner=None) -> EvalResult`. `_runner` defaults to `claude_cli.run_print`; tests inject a fake. Backend-absent → raises the existing `EvalBackendNotConfiguredError`.

- [ ] **Step 1: Write the failing tests** (append a `TestRunEvalsBackend` class to `test_eval_runner.py`)

```python
from ..claude_cli import ClaudeRun
from ..types import ApiUsage


class _FakeRunner:
    """Mimics claude_cli.run_print. Maps a prompt-substring -> ClaudeRun."""
    def __init__(self, skill_text="DONE", activated=("wrap",), judge_true=True):
        self.skill_text, self.activated, self.judge_true = skill_text, activated, judge_true
        self.calls = []

    def __call__(self, prompt, *, bare, model=None, detect_activation=False,
                 max_budget_usd=None, timeout_seconds=300, cwd=None, env=None):
        self.calls.append({"prompt": prompt, "bare": bare, "detect_activation": detect_activation})
        if detect_activation:  # a skill-run
            return ClaudeRun(self.skill_text, ApiUsage(20, 5), activated=self.activated)
        # a judge call: answer TRUE/FALSE
        return ClaudeRun("TRUE" if self.judge_true else "FALSE", ApiUsage(8, 1))


def _write_eval(tmp_path, name, tests, non_triggers=None):
    d = tmp_path / "skills" / name / "eval"
    d.mkdir(parents=True)
    import json as _j
    (d / "eval.json").write_text(_j.dumps({"name": name, "tests": tests, "non_triggers": non_triggers or []}))
    return tmp_path / "skills"


class TestRunEvalsBackend:
    def test_all_pass_when_judge_true_and_activated(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a", "b"], "trigger_test": True}])
        fake = _FakeRunner(activated=("wrap",), judge_true=True)
        res = run_evals("wrap", skills_root=skills_root, _runner=fake)
        assert res.total == 3          # 2 assertions + 1 trigger-activation
        assert res.passed == 3
        assert res.score == 1.0
        assert res.usage.output_tokens > 0   # usage aggregated

    def test_failing_assertion_recorded(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}])
        fake = _FakeRunner(judge_true=False)
        res = run_evals("wrap", skills_root=skills_root, _runner=fake)
        assert res.score == 0.0
        assert res.failing_assertion_ids == ("t1:0",)

    def test_non_trigger_fails_when_skill_activates(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}],
            non_triggers=[{"id": "nt1", "prompt": "off-topic"}])
        fake = _FakeRunner(activated=("wrap",), judge_true=True)  # wrongly activates on the non-trigger too
        res = run_evals("wrap", skills_root=skills_root, _runner=fake)
        # 1 assertion (pass) + 1 non-trigger (fail: it activated) = 1/2
        assert res.total == 2 and res.passed == 1

    def test_timeout_scores_zero(self, tmp_path):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}])
        def timed_out_runner(prompt, *, detect_activation=False, **k):
            return ClaudeRun("", ApiUsage(0, 0), timed_out=True)
        res = run_evals("wrap", skills_root=skills_root, _runner=timed_out_runner)
        assert res.score == 0.0

    def test_backend_absent_raises(self, tmp_path, monkeypatch):
        skills_root = _write_eval(tmp_path, "wrap",
            [{"id": "t1", "prompt": "p", "binary_assertions": ["a"]}])
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)  # no claude on PATH
        with pytest.raises(EvalBackendNotConfiguredError):
            run_evals("wrap", skills_root=skills_root)  # default runner, no binary
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_eval_runner.py -k RunEvalsBackend -q`
Expected: FAIL (`run_evals` still raises `EvalBackendNotConfiguredError` unconditionally / no `_runner` kwarg).

- [ ] **Step 3: Implement** — replace the `run_evals` stub body and add `judge_assertion` (`eval_runner.py`)

Add imports at top: `import shutil`, `from .types import ApiUsage`, and lazy imports of `claude_cli`/`sandbox` inside the function (avoid import cycles). Replace the `raise EvalBackendNotConfiguredError(...)` body of `run_evals` with:

```python
JUDGE_MODEL = "haiku"


def _judge_prompt(output_text: str, assertion: str) -> str:
    return (
        "Given the following skill output, is the statement TRUE or FALSE?\n"
        "Reply with exactly TRUE or FALSE and nothing else.\n\n"
        f"--- OUTPUT ---\n{output_text}\n--- END OUTPUT ---\n\n"
        f"STATEMENT: {assertion}"
    )


def judge_assertion(output_text, assertion, *, timeout_seconds=120, _runner=None):
    from .claude_cli import run_print
    runner = _runner or run_print
    run = runner(_judge_prompt(output_text, assertion), bare=False, model=JUDGE_MODEL,
                 timeout_seconds=timeout_seconds)  # SPIKE: non-bare — --bare skips auth
    verdict = run.output_text.strip().upper().startswith("TRUE")
    return verdict, run.usage


def _add(a: ApiUsage, b: ApiUsage) -> ApiUsage:
    return ApiUsage(a.input_tokens + b.input_tokens, a.output_tokens + b.output_tokens,
                    a.cache_read_input_tokens + b.cache_read_input_tokens,
                    a.cache_creation_input_tokens + b.cache_creation_input_tokens)


def run_evals(skill_name, *, eval_subset_ids=None, timeout_seconds=300, cwd=None,
              eval_runs=1, skills_root=None, _runner=None):
    from pathlib import Path as _Path
    from .claude_cli import run_print
    from .sandbox import eval_sandbox

    runner = _runner
    if runner is None:
        if shutil.which("claude") is None:
            raise EvalBackendNotConfiguredError(
                "`claude` not on PATH — eval backend unavailable (EXPERIMENTAL). "
                "Install/login to Claude Code, or inject a runner."
            )
        runner = run_print

    root = _Path(skills_root) if skills_root else _Path("skills")
    spec = load_eval_spec(root / skill_name)
    spec = filter_tests_by_ids(spec, eval_subset_ids)
    total = compute_total_assertions(spec)
    if total == 0:
        return empty_eval_result("no tests after subset filter")

    passed = 0
    failing: list[str] = []
    usage = ApiUsage(0, 0)

    def _run_skill(prompt):
        with eval_sandbox() as sb:
            return runner(prompt, bare=False, detect_activation=True,
                          timeout_seconds=timeout_seconds, cwd=sb.cwd, env=sb.env)

    for test in spec.tests:
        runs = [_run_skill(test.prompt) for _ in range(max(1, eval_runs))]
        for r in runs:
            usage = _add(usage, r.usage)
        if any(r.timed_out for r in runs):
            # treat a timed-out test as all-fail for its assertions (+ trigger)
            for i in range(len(test.binary_assertions)):
                failing.append(make_failing_assertion_id(test.id, i))
            continue
        activated = _majority(r.activated and (skill_name in r.activated) for r in runs)
        if test.trigger_test:
            passed += 1 if activated else 0
        output = runs[0].output_text
        for i, assertion in enumerate(test.binary_assertions):
            votes = []
            for _ in range(max(1, eval_runs)):
                ok, ju = judge_assertion(output, assertion, _runner=runner)
                usage = _add(usage, ju)
                votes.append(ok)
            if _majority(votes):
                passed += 1
            else:
                failing.append(make_failing_assertion_id(test.id, i))

    for nt in spec.non_triggers:
        with eval_sandbox() as sb:
            r = runner(nt.prompt, bare=False, detect_activation=True,
                       timeout_seconds=timeout_seconds, cwd=sb.cwd, env=sb.env)
        usage = _add(usage, r.usage)
        if skill_name not in r.activated:   # correct: it did NOT activate
            passed += 1

    return EvalResult(score=passed / total, passed=passed, total=total,
                      failing_assertion_ids=tuple(failing), raw_output="", usage=usage)


def _majority(votes) -> bool:
    votes = list(votes)
    if not votes:
        return False
    return sum(1 for v in votes if v) * 2 > len(votes)
```

(Keep `EvalBackendNotConfiguredError` and the existing pure helpers exactly as-is — they remain the composable primitives. Delete only the old unconditional `raise` body of `run_evals`.)

- [ ] **Step 4: Run to verify the new + existing tests pass**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_eval_runner.py -q`
Expected: PASS. The old `TestRunEvalsRequiresBackend` tests (which call `run_evals("sf-wrap")` with no skill dir + real PATH) may now hit the no-binary path — **update them**: in environments with `claude` absent they still raise `EvalBackendNotConfiguredError` (keep), but assert via `monkeypatch.setattr(shutil, "which", lambda _: None)` so the test is deterministic regardless of host. Adjust those four tests accordingly in this step.

- [ ] **Step 5: Commit**

```bash
git add skills/improve-skill/lib/eval_runner.py skills/improve-skill/lib/tests/test_eval_runner.py
git commit -m "feat(c5a): real run_evals (own LLM-judge) + judge_assertion"
```

---

## Task 6: `_default_change_proposer()` real body

**Files:**
- Modify: `skills/improve-skill/lib/__init__.py`
- Test: `skills/improve-skill/lib/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `claude_cli.run_print`, `EvalSpec`, `BudgetState`, `ProposedChange`, `ApiUsage`, `ProposerError`.
- Produces: real `_default_change_proposer(spec, failing_ids, budget, *, _runner=None) -> tuple[ProposedChange, ApiUsage, int]`; raises `ProposerError` on unparseable output.

- [ ] **Step 1: Write the failing tests** (append `TestProposer` to `test_orchestrator.py`)

```python
import json
from ..claude_cli import ClaudeRun
from ..eval_runner import EvalSpec, EvalTest
from ..types import ApiUsage, BudgetState, ProposedChange, ProposerError
from .. import _default_change_proposer


def _spec():
    return EvalSpec(name="wrap", tests=(EvalTest(id="t1", prompt="p", binary_assertions=("a",)),))


def test_proposer_parses_change():
    payload = json.dumps({"target_file": "SKILL.md", "unified_diff": "--- a\n+++ b\n",
                          "summary": "clarify step", "rationale": "why"})
    fake = lambda prompt, **k: ClaudeRun(payload, ApiUsage(100, 50))
    change, usage, turns = _default_change_proposer(_spec(), ("t1:0",),
                                                    BudgetState(max_budget_usd=5.0), _runner=fake)
    assert isinstance(change, ProposedChange)
    assert change.target_file == "SKILL.md"
    assert usage.output_tokens == 50 and turns == 1


def test_proposer_raises_on_garbage():
    fake = lambda prompt, **k: ClaudeRun("I cannot help with that.", ApiUsage(10, 3))
    with pytest.raises(ProposerError):
        _default_change_proposer(_spec(), ("t1:0",), BudgetState(max_budget_usd=5.0), _runner=fake)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_orchestrator.py -k Proposer -q`
Expected: FAIL (`_default_change_proposer` raises `NotImplementedError`).

- [ ] **Step 3: Implement** — replace the `_default_change_proposer` body (`__init__.py`)

Add `from .types import ProposerError` to the types import block and `import json`. Replace the stub:

```python
def _proposer_prompt(spec, failing_ids):
    return (
        f"You are improving the skill '{spec.name}'. Its eval binary-assertions that are "
        f"FAILING (as <test-id>:<index>): {list(failing_ids)}.\n"
        "Propose ONE change to SKILL.md or a references/ file that fixes at least one of "
        "these WITHOUT regressing the others. Output ONLY JSON with keys: "
        '{"target_file","unified_diff","summary","rationale"}.'
    )


def _default_change_proposer(spec, failing_ids, budget, *, _runner=None):
    from .claude_cli import run_print
    from .types import ApiUsage, ProposedChange, ProposerError
    runner = _runner or run_print
    run = runner(_proposer_prompt(spec, failing_ids), bare=False,
                 max_budget_usd=budget.remaining_usd)  # SPIKE: non-bare — --bare skips auth
    text = run.output_text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ProposerError(f"No JSON object in proposer output: {text[:160]!r}")
    try:
        data = json.loads(text[start:end + 1])
        change = ProposedChange(
            target_file=str(data["target_file"]),
            unified_diff=str(data["unified_diff"]),
            summary=str(data.get("summary", "proposed change")),
            rationale=str(data.get("rationale", "")),
        )
    except (json.JSONDecodeError, KeyError) as exc:
        raise ProposerError(f"Malformed proposer JSON: {exc}") from exc
    return change, run.usage, 1
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_orchestrator.py -k Proposer -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add skills/improve-skill/lib/__init__.py skills/improve-skill/lib/tests/test_orchestrator.py
git commit -m "feat(c5a): real change-proposer (claude --bare --print JSON)"
```

---

## Task 7: Orchestrator wiring — `ProposerError` skip + eval-usage budget + `--eval-runs`

**Files:**
- Modify: `skills/improve-skill/lib/__init__.py`
- Test: `skills/improve-skill/lib/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `advance_budget`, `EvalResult.usage`, `ProposerError`, `ImproveSkillArgs.eval_runs`.
- Produces: full loop that (a) treats `ProposerError` as a skipped iteration (continue, capped at 3 consecutive), (b) advances the budget from each `EvalResult.usage`, (c) threads `args.eval_runs` + `skills_root` into the default eval-runner.

- [ ] **Step 1: Write the failing test** (append to `test_orchestrator.py`)

```python
from ..types import EvalResult, ImproveSkillArgs


def test_loop_improves_fixture_skill_end_to_end(tmp_path, monkeypatch):
    # eval-runner: first call 0.5, after a change 1.0
    scores = iter([EvalResult(0.5, 1, 2, ("t1:0",), usage=ApiUsage(30, 10)),
                   EvalResult(1.0, 2, 2, (), usage=ApiUsage(30, 10))])
    fake_eval = lambda name, ids: next(scores)
    fake_prop = lambda spec, failing, budget: (
        ProposedChange("SKILL.md", "--- a\n+++ b\n", "fix", "why"), ApiUsage(100, 40), 1)
    # stub git mechanics + apply via monkeypatch to avoid real git in this unit test
    monkeypatch.setattr("skills.improve_skill.lib.create_improve_branch", lambda *a, **k: "improve/wrap/ts")
    monkeypatch.setattr("skills.improve_skill.lib.commit_iteration", lambda *a, **k: "deadbeef")
    monkeypatch.setattr("skills.improve_skill.lib.apply_proposed_change", lambda *a, **k: None)
    monkeypatch.setattr("skills.improve_skill.lib.amend_iteration_metadata", lambda *a, **k: None)
    monkeypatch.setattr("skills.improve_skill.lib.squash_merge_on_success", lambda *a, **k: "cafef00d")
    monkeypatch.setattr("skills.improve_skill.lib.pre_flight_check", lambda *a, **k: None)
    monkeypatch.setattr("skills.improve_skill.lib.load_eval_spec",
                        lambda d: EvalSpec(name="wrap", tests=(EvalTest("t1", "p", ("a", "b")),)))
    args = ImproveSkillArgs(skill_name="wrap", max_iterations=3, max_budget_usd=5.0)
    res = improve_skill(args, eval_runner=fake_eval, change_proposer=fake_prop, cwd=tmp_path)
    assert res.exit_reason.value == "all_assertions_pass"
    assert res.total_usd_spent > 0          # budget advanced from proposer AND eval usage
```

(Note: align the monkeypatch module path with the package's import name — `skills.improve_skill.lib` if `sys.path`/`conftest` aliases the dashed dir, else the dotted form used by the existing `test_orchestrator.py`. Match the existing tests' import style in this file.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_orchestrator.py -k end_to_end -q`
Expected: FAIL (budget not advanced from eval usage yet, or eval-runs/skills_root closure missing).

- [ ] **Step 3: Implement the three changes** (`__init__.py`)

(a) After the baseline eval and after each re-eval, advance the budget from the result's usage:
```python
        budget = advance_budget(budget, new_result.usage if new_result else ApiUsage(0, 0),
                                model=table.default_model, table=table, turns_used=0)
```
Insert an equivalent advance for the baseline (initialize `budget` before the baseline eval, or fold baseline usage in right after branch/budget setup — pick the smaller diff; the baseline eval happens once).

(b) Replace the bare `except NotImplementedError:` around the proposer call with handling for both:
```python
        try:
            proposed, usage, turns_used = proposer(spec, last_failing_ids, budget)
            consecutive_proposer_errors = 0
        except NotImplementedError:
            exit_reason = ExitReason.NO_IMPROVEMENT_POSSIBLE
            break
        except ProposerError:
            consecutive_proposer_errors += 1
            if consecutive_proposer_errors >= 3:
                exit_reason = ExitReason.NO_IMPROVEMENT_POSSIBLE
                break
            continue   # skip this iteration; try a different angle
```
(Initialize `consecutive_proposer_errors = 0` before the loop; import `ProposerError`.)

(c) Thread `--eval-runs` + `skills_root` into the default eval-runner:
```python
    runner = eval_runner or (lambda s, ids: _default_eval_runner(
        s, ids, eval_runs=args.eval_runs, skills_root=skills_root_resolved))
```
and update `_default_eval_runner(skill_name, subset_ids, *, eval_runs=1, skills_root=None)` to forward both to `run_evals`.

- [ ] **Step 4: Run to verify pass (+ full suite green)**

Run: `python3 -m pytest skills/improve-skill/lib/tests/ -q`
Expected: PASS (all — baseline 144 + Task-3/5/6/7 additions). The existing exit-reason matrix tests stay green.

- [ ] **Step 5: Commit**

```bash
git add skills/improve-skill/lib/__init__.py skills/improve-skill/lib/tests/test_orchestrator.py
git commit -m "feat(c5a): orchestrator wiring — ProposerError skip + eval-usage budget + eval-runs"
```

---

## Task 8: Minimal `improve-skill/eval/eval.json` + conformance

**Files:**
- Create: `skills/improve-skill/eval/eval.json`
- Modify: `skills/improve-skill/lib/tests/test_eval_runner.py` (add to `CANONICAL_SKILL_DIRS`)

- [ ] **Step 1: Write the eval.json** (activation + refusal only — no recursive loop-run assertions)

```json
{
  "name": "improve-skill",
  "_status": "minimal — activation + refusal assertions only (C5a). Loop-behavioral assertions deferred (recursive).",
  "tests": [
    {
      "id": "activates-on-improve-request",
      "prompt": "/ren:improve-skill wrap",
      "binary_assertions": [
        "The response begins the improve-skill pre-flight or names the wrap skill as the target."
      ],
      "trigger_test": true
    },
    {
      "id": "refuses-missing-skill",
      "prompt": "/ren:improve-skill this-skill-does-not-exist",
      "binary_assertions": [
        "The response refuses because the target skill does not exist.",
        "The response does NOT create a git branch."
      ],
      "trigger_test": true
    }
  ],
  "non_triggers": [
    { "id": "plain-question", "prompt": "What time is it in Istanbul?", "expected_outcome": "skill_not_activated" }
  ]
}
```

- [ ] **Step 2: Add it to the canonical conformance set** (`test_eval_runner.py`)

Append `REPO_ROOT / "skills" / "improve-skill"` to `CANONICAL_SKILL_DIRS`.

- [ ] **Step 3: Run conformance**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_eval_runner.py -k Canonical -q`
Expected: PASS — the new eval.json loads cleanly and reports a positive assertion total.

- [ ] **Step 4: Commit**

```bash
git add skills/improve-skill/eval/eval.json skills/improve-skill/lib/tests/test_eval_runner.py
git commit -m "feat(c5a): minimal eval.json for improve-skill (dogfood + ADR-011 conformance)"
```

---

## Task 9: Isolation property test + gated live smoke

**Files:**
- Test: `skills/improve-skill/lib/tests/test_sandbox.py` (isolation property)
- Create: `skills/improve-skill/lib/tests/test_live_smoke.py` (gated; skipped without `claude` + key)

- [ ] **Step 1: Isolation property test** (append to `test_sandbox.py`)

```python
def test_real_wiki_untouched_when_skill_writes_in_sandbox(tmp_path, monkeypatch):
    """A runner that 'writes' must only write under the sandbox env, never the real wiki."""
    real_wiki = tmp_path / "REAL_WIKI"
    real_wiki.mkdir()
    (real_wiki / "keep.md").write_text("original")
    monkeypatch.setenv("SF_WIKI_ROOT", str(real_wiki))
    from ..sandbox import eval_sandbox
    with eval_sandbox() as sb:
        # simulate a skill writing to the redirected wiki
        (Path(sb.env["SF_WIKI_ROOT"]) / "scratch.md").write_text("sandboxed")
    assert (real_wiki / "keep.md").read_text() == "original"
    assert list(real_wiki.iterdir()) == [real_wiki / "keep.md"]   # nothing leaked in
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_sandbox.py -q`
Expected: PASS.

- [ ] **Step 3: Gated live smoke** (`test_live_smoke.py`)

```python
"""Live smoke — needs the real `claude` binary + a credential. Skipped in CI.
Proves run_evals scores ONE real skill end-to-end."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from ..eval_runner import run_evals

pytestmark = pytest.mark.skipif(
    shutil.which("claude") is None or not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")),
    reason="live smoke needs the claude binary + a credential",
)


def test_run_evals_scores_a_real_skill():
    root = Path("skills")
    target = "recall"     # spike-confirmed low-side-effect target
    res = run_evals(target, skills_root=root, eval_runs=1)
    assert 0.0 <= res.score <= 1.0
    assert res.total > 0
    assert res.usage.output_tokens > 0
```

- [ ] **Step 4: Run (will SKIP in CI / no key; RUN locally if a key is present)**

Run: `python3 -m pytest skills/improve-skill/lib/tests/test_live_smoke.py -q`
Expected: SKIPPED (no key) or PASS (key present — record the real score in the run summary / `learnings.md`).

- [ ] **Step 5: Commit**

```bash
git add skills/improve-skill/lib/tests/test_sandbox.py skills/improve-skill/lib/tests/test_live_smoke.py
git commit -m "test(c5a): isolation property + gated live smoke"
```

---

## Task 10: ADR-036 + ADR-012 amendment + references + pricing

**Files:**
- Create: `wiki/decisions/036-bike-method-earned-autonomy.md`
- Modify: `wiki/decisions/012-two-layer-self-improvement.md`
- Modify: `skills/improve-skill/references/eval-runner.md`
- Modify: `skills/improve-skill/references/model-pricing.json`

- [ ] **Step 1: Write ADR-036** following the ADR template (frontmatter: title, status accepted, date 2026-06-18, sunset-review 2027-06-18, references-pages incl. `nate-herk-ai-os`, relates-to `[012, 031, 009, 003]`). Body: Context (the backend is now real → autonomy must be governed), Decision (interactive default; `--autonomous` keeps the two ceilings; EXPERIMENTAL until ≥3 logged clean supervised runs; **no trust-tracking code** — the only code gate is the pre-flight ceiling check; manual maintainer downgrade), Consequences, Alternatives rejected (ship-autonomous-now; never-autonomous), References. Copy the §9 content of the design spec verbatim where applicable.

- [ ] **Step 2: Amend ADR-012** — add an `amendments:` entry dated 2026-06-18: the Layer-2 eval backend is now WIRED via the own LLM-judge path (path 2), chosen over Skill-Creator adoption; earned-autonomy posture deferred to ADR-036. Add `036` to `relates-to` if present.

- [ ] **Step 3: Flip `eval-runner.md`** — in the "Integration with Skill Creator" section, change the "V1 decision: start with path 1 (adopt)" to "**V1 decision (revised 2026-06-18, C5a): path 2 — our own LLM-judge.** Rationale: no dependency on Skill Creator's internal script surface; direct budget integration; we own eval.json's schema." Keep the `run_evals` contract section.

- [ ] **Step 4: Ensure a Haiku price row** in `model-pricing.json` (add `claude-haiku-4-5` input/output per-MTok if absent, matching the file's existing shape).

- [ ] **Step 5: Validate + commit**

Run: `claude plugin validate ./ --strict`
Expected: ✔ (no schema change; ADRs are plain wiki pages).
```bash
git add wiki/decisions/036-bike-method-earned-autonomy.md wiki/decisions/012-two-layer-self-improvement.md skills/improve-skill/references/eval-runner.md skills/improve-skill/references/model-pricing.json
git commit -m "docs(c5a): ADR-036 bike-method; amend ADR-012; flip eval-runner to own-judge"
```

---

## Task 11: SKILL.md banner/flags + learnings + wire-up + full gate

**Files:**
- Modify: `skills/improve-skill/SKILL.md`, `skills/improve-skill/learnings.md`
- Modify: `README.md`, `CHANGELOG.md`, `wiki/index.md`, `wiki/log.md`, `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`

- [ ] **Step 1: Update SKILL.md** — reword the EXPERIMENTAL banner from "the eval backend is **not yet wired** … exits `requires_configured_backend`" to: "the eval backend is **wired (own LLM-judge)**; the loop runs when `claude` + a credential are present, else it exits cleanly via `requires_configured_backend` (now meaning *backend unavailable*). **Autonomy is still earned** per ADR-036 — `--autonomous` requires the two ceilings; EXPERIMENTAL until supervised runs prove it." Add `--eval-runs N` to the optional-flags table (default 1; majority-binarized scoring when >1).

- [ ] **Step 2: Update learnings.md** — add: the spike's key finding (the confirmed `claude` activation-detection surface), and a placeholder line for logging supervised runs toward the ADR-036 downgrade gate.

- [ ] **Step 3: Wire-up** — README skills section (improve-skill now functional, note EXPERIMENTAL/earned-autonomy); CHANGELOG entry; `wiki/index.md` (improve-skill summary shift); `wiki/log.md` (append a C5a milestone entry, chronological); roadmap C5 row → **C5a ✅ DONE 2026-06-18** with **C5b (dep/call-graph + auto-refresh) remaining**.

- [ ] **Step 4: Full gate**

Run (from plugin root):
```bash
python3 -m pytest skills/improve-skill/lib/tests/ -q
```
Then, as a SEPARATE command (avoid the hook gotcha):
```bash
claude plugin validate ./ --strict
```
Then schema CI-parity (unchanged):
```bash
python3 -c "import json,jsonschema; jsonschema.validate(json.load(open('skills/wiki-migration/schemas.json')), json.load(open('skills/wiki-migration/schemas.schema.json')))"
```
Expected: all green; no `schemas.json` change.

- [ ] **Step 5: Commit**

```bash
git add skills/improve-skill/SKILL.md skills/improve-skill/learnings.md README.md CHANGELOG.md wiki/index.md wiki/log.md docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md
git commit -m "docs(c5a): SKILL banner/flags, wire-up, roadmap C5a done"
```

---

## Self-Review (run against the spec)

**Spec coverage:** §3 units → Tasks 2,4,5,6 + types(3); §4.1 eval flow → Task 5; §4.2 proposer → Task 6; §5 spike → Task 1; §6 isolation → Tasks 4,9; §7 budget → Tasks 3,7; §8 determinism → Task 5 (`eval_runs`/`_majority`) + SKILL flag (Task 11); §9/§11 ADRs → Task 10; §12 self-eval → Task 8; §13 tests → Tasks 2,4,5,6,7,8,9; §14 graceful-degrade → Task 5 (no-binary raise); §15 sequencing → task order. No gaps.

**Placeholder scan:** spike-dependent flags are explicitly routed through `SPIKE_FINDINGS.md` (Task 1) and the wrapper notes the surface may be corrected — this is the C2 spike pattern, not a placeholder. All test/impl steps carry real code.

**Type consistency:** `ClaudeRun`/`run_print` (Task 2) signatures match every call site (Tasks 5,6); `EvalResult.usage` (Task 3) consumed in Tasks 5,7; `ProposerError` defined in Task 3, raised in Task 6, caught in Task 7; `_majority`, `_add`, `judge_assertion`, `_default_change_proposer`, `_default_eval_runner` names consistent across tasks; `eval_runs` flows args(3)→orchestrator(7)→run_evals(5).
