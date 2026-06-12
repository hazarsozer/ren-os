# C4 — Cadence-as-Glue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute in an isolated worktree (superpowers:using-git-worktrees) on a focused branch `feat/c4-cadence-as-glue`.

**Goal:** Ship RenOS's cadence glue layer — a `routine-spec` wiki page-type, a `/ren:routine-init` scaffolder for lean cloud-routine repos, a `/ren:cadence` decision-matrix/router skill, plus extensions to `/ren:recall` (read routine state), `/ren:doctor` (network-tier + quota audits), and the wake-up hook (surface live automations) — all thin glue over CC-native primitives, no daemon.

**Architecture:** Per ADR-034 (cadence-as-glue), the framework adds scaffolding, conventions, write-back, and safety audits over native `/loop`/Cron/`/goal`/Cloud-Routines — never a long-running process. Cloud routines "report home" via git pull-model write-back (ADR-026). Every durable artifact lands in the governable wiki (the truth layer); the wake-up hook surfaces which automations are live.

**Tech Stack:** Python 3.12 (`dataclasses`, `pathlib`, stdlib only — no PyYAML at hook/doctor runtime; frontmatter parsed with the same hand-rolled `--- … ---` line-parser `check-schemas.sh` already uses), bash (doctor check scripts), Markdown templates (`.tmpl`). Skills follow ADR-011 (SKILL.md ≤200 lines + `contract:` block + `eval/eval.json` + per-module pytest). Namespace `/ren:` (ADR-033).

**Binding spec:** `wiki/decisions/034-cadence-as-glue.md` (§1 matrix, §2 write-back, §3 glue surface, §4 safety). Conventions: `wiki/research/nate-herk-cadence-automation.md`.

---

## Scope check (writing-plans)

C4 is **one** roadmap subsystem (cadence-as-glue), already decomposed out of the 9-subsystem spec by `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`. Its parts (page-type, scaffolder, router, recall/doctor/wake-up extensions) are interdependent pieces of one shippable capability, not independent subsystems — so **one plan** is correct. It depends only on A1 (ADR-034, filed) and F1 (merged); both are done.

**Two scope judgments made (flag for the maintainer):**
1. **`/ren:cadence` is included as a lean LLM-only skill** (the home for the decision matrix + the local-tier `/loop`/Cron/`/goal` conventions — research tension #6: "needs a matrix, not just docs"). The "wrappers" in the session next-step are realized as this router + baked-in scaffold conventions, **not** as separate reimplementations of native commands (faithful to "thin glue over native primitives").
2. **`routine-spec` is global** (`wiki/routines/<slug>.md`, surfaced at master level by the wake-up hook), because cadence is cross-project. Per-project routine pages are a clean future extension, not built here (YAGNI).

---

## File Structure

**New — `routine-spec` page-type (Task 1):**
- Modify `skills/wiki-migration/schemas.json` — register `routine-spec`.
- Modify `tests/integration/schema-conformance/conformance.py` — `REQUIRED_FIELDS_BY_TYPE` + `SCAN_TARGETS`.
- Create `skills/routine-init/templates/wiki/routine-spec.md.tmpl` — the conformant wiki-page template.
- Create `tests/integration/schema-conformance/test_routine_spec.py` — regression guard.

**New — `/ren:routine-init` skill (Tasks 2–4):**
- Create `skills/routine-init/lib/__init__.py` — `routine_init()` scaffolds repo + writes spec page.
- Create `skills/routine-init/lib/tests/{__init__.py,test_routine_init.py}`.
- Create `skills/routine-init/templates/repo/{CLAUDE.md.tmpl,ROUTINE_PROMPT.md.tmpl,state.md.tmpl,run-log.md.tmpl}`.
- Create `skills/routine-init/SKILL.md`, `skills/routine-init/eval/eval.json`, `skills/routine-init/references/lean-repo.md`, `skills/routine-init/learnings.md`.

**New — `/ren:cadence` skill (Task 5):**
- Create `skills/cadence/SKILL.md`, `skills/cadence/eval/eval.json`, `skills/cadence/references/{cadence-matrix.md,conventions.md}`, `skills/cadence/learnings.md`.

**Extensions:**
- Modify `skills/recall/lib/__init__.py` + `skills/recall/lib/tests/test_recall.py` + `skills/recall/SKILL.md` (Task 6).
- Create `skills/doctor/scripts/check-routines.sh` + `skills/doctor/scripts/tests/test_check_routines.sh`; modify `skills/doctor/SKILL.md` (Task 7).
- Modify `hooks/wake-up/wakeup/__init__.py`; create `hooks/wake-up/wakeup/tests/test_routines.py` (Task 8).

**Wiki write-back (Task 9):** `wiki/log.md`, `wiki/index.md`, `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`, `CHANGELOG.md`.

**Verification gate (Task 10).**

---

## Test conventions (per the codebase)

- Python skill lib: `( cd skills/<verb> && python3 -m pytest lib/tests -q -p no:cacheprovider )`
- Wake-up hook: `( cd hooks/wake-up && python3 -m pytest -q )`
- Doctor bash harness: `( cd skills/doctor && bash scripts/tests/<name>.sh )`
- Conformance: `python3 tests/integration/schema-conformance/conformance.py` (exit 0 = no strict blocker) and `python3 -m pytest tests/integration/schema-conformance/ -q`
- Plugin: `claude plugin validate ./ --strict`
- **Commits:** conventional subject+body; NO `Co-Authored-By` trailer; keep the literal tokens `pre-commit` / `commit-msg` / `--no-verify` out of commit messages AND bash commands (hook false-positives).

---

## Task 1: Register the `routine-spec` page-type

**Files:**
- Create: `skills/routine-init/templates/wiki/routine-spec.md.tmpl`
- Modify: `tests/integration/schema-conformance/conformance.py` (`SCAN_TARGETS` ~line 79–91; `REQUIRED_FIELDS_BY_TYPE` ~line 52–72)
- Modify: `skills/wiki-migration/schemas.json` (append a `page_types` entry)
- Test: `tests/integration/schema-conformance/test_routine_spec.py` (new)

- [ ] **Step 1: Create the conformant wiki-page template**

Create `skills/routine-init/templates/wiki/routine-spec.md.tmpl`. All placeholder-bearing frontmatter values are **quoted** so the conformance harness (which only renders a fixed placeholder set) still parses valid YAML; `{{framework_version}}` and `{{today}}` are in the harness's render set, the rest stay as literal quoted strings (key-presence is what conformance checks).

```markdown
---
title: "Routine: {{routine_name}}"
type: routine-spec
schema_version: 1
framework_version: "{{framework_version}}"
name: "{{routine_name}}"
trigger_type: "{{trigger_type}}"
linked_repo: "{{linked_repo}}"
network_tier: "{{network_tier}}"
env_secrets_ref: "{{env_secrets_ref}}"
schedule: "{{schedule}}"
expected_output: "{{expected_output}}"
failure_handler: "{{failure_handler}}"
created: "{{today}}"
updated: "{{today}}"
---

# Routine: {{routine_name}}

Documents one live cadence routine deployed via `/ren:routine-init` (ADR-034). Surfaced by the wake-up hook (every session sees which automations are live) and audited by `/ren:doctor` (network tier + quota headroom).

## What it does

{{expected_output}}

## Trigger

- **Type:** {{trigger_type}}
- **Schedule:** {{schedule}}

## Linked repo

{{linked_repo}}

## Safety

- **Network tier:** {{network_tier}} — `trusted` = Anthropic allowlist; `full` = unrestricted egress = a prompt-injection exfiltration surface (flagged by `/ren:doctor`).
- **Secrets:** {{env_secrets_ref}} — live in the cloud env, never the repo.

## Failure handling

{{failure_handler}}

## Cross-run memory

State trail lives in the linked repo's `state.md` + `run-log.md`, read at run start via `/ren:recall --routine .` (ADR-034 / ADR-026 pull-model write-back).
```

- [ ] **Step 2: Add the scan target + required-fields entry in conformance.py**

In `tests/integration/schema-conformance/conformance.py`, add the routine-init wiki-template glob to `SCAN_TARGETS` (right after the bootstrap-project line):

```python
    ("bootstrap-project templates", "skills/bootstrap-project/templates/**/*.md.tmpl", "strict"),
    ("routine-init wiki templates", "skills/routine-init/templates/wiki/**/*.md.tmpl", "strict"),
```

And add the required-fields entry to `REQUIRED_FIELDS_BY_TYPE` (right after `"licenses": set(),`):

```python
    "licenses": set(),
    # C4 cadence (ADR-034): documents one live routine; surfaced by wake-up + doctor.
    "routine-spec": {"name", "trigger_type", "linked_repo", "network_tier"},
}
```

- [ ] **Step 3: Run conformance to verify it FAILS (type not yet registered)**

Run: `python3 tests/integration/schema-conformance/conformance.py`
Expected: exit 1, a FAILURES block naming `routine-spec.md.tmpl` with reason `claims type='routine-spec' but no such page-type in registry`.

- [ ] **Step 4: Register `routine-spec` in schemas.json**

Read `skills/wiki-migration/schemas.json`. Locate the **last** entry in `page_types` (the `"skill": { … }` block). Add a comma after its closing `}` and append this entry as the new last `page_types` member:

```json
    "routine-spec": {
      "current": 1,
      "supported_from": 1,
      "deprecated_below": null,
      "path_pattern": "wiki/routines/<slug>.md",
      "description": "Documents one live cadence routine — name, trigger type, linked repo, network tier, env/secrets ref, expected output, failure handler. Written by /ren:routine-init; surfaced by the wake-up hook and audited by /ren:doctor.",
      "owner_module": "sf-cadence",
      "adr_refs": ["ADR-034", "ADR-027"],
      "migrations": []
    }
```

- [ ] **Step 5: Run conformance to verify it PASSES**

Run: `python3 tests/integration/schema-conformance/conformance.py`
Expected: exit 0; "Type coverage" shows `✅ routine-spec  1 file(s)`; `BLOCKERS (strict mode): 0` (or "All files conform.").

- [ ] **Step 6: Add a regression guard test**

Create `tests/integration/schema-conformance/test_routine_spec.py`:

```python
"""Regression guard: routine-spec is registered and its template conforms (C4 / ADR-034)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("conformance", _HERE / "conformance.py")
conformance = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conformance)


def test_routine_spec_registered():
    registry = conformance.load_registry()
    assert "routine-spec" in registry["page_types"]
    meta = registry["page_types"]["routine-spec"]
    assert meta["current"] == 1
    assert meta["supported_from"] == 1


def test_routine_spec_template_conforms():
    registry = conformance.load_registry()
    report = conformance.walk_targets(registry)
    passed = [r.path for r in report.by_status["pass"] if r.type_claimed == "routine-spec"]
    assert passed, "no conformant routine-spec template scanned (is the SCAN_TARGETS glob added?)"
    fails = [(r.path, r.detail) for r in report.by_status["fail"] if r.type_claimed == "routine-spec"]
    assert not fails, f"routine-spec conformance failures: {fails}"
```

- [ ] **Step 7: Run the guard + full conformance pytest**

Run: `python3 -m pytest tests/integration/schema-conformance/ -q`
Expected: PASS (prior 10 tests + 1 xfail unchanged; +2 new tests pass).

- [ ] **Step 8: Commit**

```bash
git add skills/wiki-migration/schemas.json tests/integration/schema-conformance/conformance.py tests/integration/schema-conformance/test_routine_spec.py skills/routine-init/templates/wiki/routine-spec.md.tmpl
git commit -m "feat(schema): register routine-spec page-type (C4/ADR-034)

Adds routine-spec to schemas.json (current:1), wires the routine-init wiki
template into the conformance SCAN_TARGETS, and adds a regression guard.
Foundation for the cadence glue layer: written by /ren:routine-init, surfaced
by the wake-up hook, audited by /ren:doctor."
```

---

## Task 2: `/ren:routine-init` lib — validation + lean-repo scaffold

**Files:**
- Create: `skills/routine-init/templates/repo/CLAUDE.md.tmpl`, `ROUTINE_PROMPT.md.tmpl`, `state.md.tmpl`, `run-log.md.tmpl`
- Create: `skills/routine-init/lib/__init__.py`
- Test: `skills/routine-init/lib/tests/__init__.py`, `skills/routine-init/lib/tests/test_routine_init.py`

- [ ] **Step 1: Create the four lean-repo templates**

Create `skills/routine-init/templates/repo/CLAUDE.md.tmpl`:

```markdown
# {{routine_name}} — cadence routine

Lean repo for the RenOS cadence routine **{{routine_name}}** (ADR-034). This repo is the *muscle*: it carries only what this one routine needs. Do not add unrelated project context — it burns run budget.

## What this routine does

{{expected_output}}

## How it runs

Each scheduled run starts a fresh, stateless Claude Code session that clones this repo, reads this CLAUDE.md, and executes `ROUTINE_PROMPT.md`. The environment is destroyed after the run.

## Secrets

{{env_secrets_ref}}

Secrets are provided by the cloud environment as environment variables. **Use them directly — do NOT search for a `.env` file.**

## Cross-run memory

- `state.md` — durable state carried between runs (read at start, updated at end).
- `run-log.md` — append-only trail of what each run did.

At run start, load the trail with `/ren:recall --routine .` before doing work.
```

Create `skills/routine-init/templates/repo/ROUTINE_PROMPT.md.tmpl`:

```markdown
# Routine prompt — {{routine_name}}

> The prompt the scheduled run executes. Skill-as-routine-prompt convention (ADR-034):
> one named /ren: skill, explicit order of operations, one pass, then exit.

## Order of operations

1. **Load memory.** Run `/ren:recall --routine .` to read `state.md` + `run-log.md` so you know what prior runs did.
2. **Do the work.** Run `/ren:{{skill}}` exactly once. {{expected_output}}
3. **Write back.** Append one entry to `run-log.md` (`## [<UTC timestamp>] <one-line summary>`) and update `state.md` if durable state changed. Then commit and push both:
   ```
   git add -A && git commit -m "routine {{routine_name}}: <summary>" && git push origin HEAD
   ```
   (Pull-model write-back per ADR-026 — the run pushes; the human pulls.)
4. **Exit.** This is a SINGLE-PASS run. Do not start a `/loop`, do not schedule additional crons, do not iterate beyond the one pass above.

## Secrets

{{env_secrets_ref}} — available as environment variables. Use directly; do NOT look for a `.env`.

## Failure handler (required — ADR-034)

If this run fails for ANY reason — an error, an unmet precondition, or an empty result where output was expected — then BEFORE exiting, send an email via the Resend MCP tool `mcp__resend__send-email`:

- **to:** {{failure_email}}
- **subject:** `Routine {{routine_name}} FAILED`
- **body:** the error message + the step it failed on.

Headless runs fail silently by default; this footer is the only way you'll hear about a broken routine.
```

Create `skills/routine-init/templates/repo/state.md.tmpl`:

```markdown
---
routine: {{routine_name}}
updated: {{today}}
---

# {{routine_name}} — state

Durable state carried between runs. Read at the start of each run, updated at the end. Keep this SHORT — it loads into every run's context.

_(empty — the first run will populate this)_
```

Create `skills/routine-init/templates/repo/run-log.md.tmpl`:

```markdown
# {{routine_name}} — run log

Append-only. Each run adds one entry at the bottom (newest last):

`## [YYYY-MM-DD HH:MM UTC] <one-line summary of what the run did>`

---

_(no runs yet)_
```

- [ ] **Step 2: Write the failing tests**

Create `skills/routine-init/lib/tests/__init__.py` (empty file).

Create `skills/routine-init/lib/tests/test_routine_init.py`:

```python
"""Tests for skills.routine-init.lib — scaffold + validation (C4 / ADR-034)."""
from __future__ import annotations

from pathlib import Path

from ..__init__ import RoutineInitResult, routine_init

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"  # skills/routine-init/templates


def _run(tmp_path: Path, **overrides) -> RoutineInitResult:
    kw = dict(
        name="daily-digest",
        dest_dir=tmp_path / "repos",
        wiki_root=tmp_path / "wiki",
        trigger_type="cron",
        linked_repo="https://github.com/u/daily-digest",
        skill="insights",
        network_tier="trusted",
        schedule="every day at 8am ET",
        expected_output="A digest of yesterday's activity.",
        env_secrets_ref="RESEND_API_KEY",
        failure_email="me@example.com",
        today="2026-06-11",
        templates_dir=TEMPLATES,
    )
    kw.update(overrides)
    return routine_init(**kw)


class TestValidation:
    def test_rejects_non_kebab_name(self, tmp_path):
        r = _run(tmp_path, name="DailyDigest")
        assert not r.success and "kebab" in r.error

    def test_rejects_bad_trigger(self, tmp_path):
        r = _run(tmp_path, trigger_type="hourly")
        assert not r.success and "trigger_type" in r.error

    def test_rejects_bad_tier(self, tmp_path):
        r = _run(tmp_path, network_tier="open")
        assert not r.success and "network_tier" in r.error

    def test_rejects_empty_skill(self, tmp_path):
        r = _run(tmp_path, skill="  ")
        assert not r.success and "skill" in r.error

    def test_refuses_existing_repo_dir(self, tmp_path):
        (tmp_path / "repos" / "daily-digest").mkdir(parents=True)
        r = _run(tmp_path)
        assert not r.success and "overwrite" in r.error


class TestScaffold:
    def test_creates_all_repo_files(self, tmp_path):
        r = _run(tmp_path)
        assert r.success, r.error
        repo = tmp_path / "repos" / "daily-digest"
        for f in ("CLAUDE.md", "ROUTINE_PROMPT.md", "state.md", "run-log.md"):
            assert (repo / f).is_file(), f"missing {f}"
        assert r.repo_dir == repo

    def test_prompt_bakes_in_conventions(self, tmp_path):
        r = _run(tmp_path)
        prompt = (tmp_path / "repos" / "daily-digest" / "ROUTINE_PROMPT.md").read_text()
        assert "mcp__resend__send-email" in prompt       # failure footer
        assert "me@example.com" in prompt                # owner email rendered
        assert "/ren:recall --routine ." in prompt       # state load
        assert "/ren:insights" in prompt                 # skill-as-prompt
        assert "SINGLE-PASS" in prompt                   # self-terminating

    def test_claude_md_env_var_sourcing(self, tmp_path):
        r = _run(tmp_path)
        claude = (tmp_path / "repos" / "daily-digest" / "CLAUDE.md").read_text()
        assert ".env" in claude and "do NOT" in claude   # explicit env-var sourcing
```

- [ ] **Step 3: Run tests to verify they FAIL**

Run: `( cd skills/routine-init && python3 -m pytest lib/tests -q -p no:cacheprovider )`
Expected: collection/import error (`ModuleNotFoundError: ..__init__` / no `lib/__init__.py`).

- [ ] **Step 4: Implement the lib (scaffold only — no spec-page write yet)**

Create `skills/routine-init/lib/__init__.py`:

```python
"""
routine-init library — internal implementation for /ren:routine-init.

Scaffolds a lean per-routine repo (ADR-034 cadence-as-glue) from templates.
Task 3 adds the routine-spec wiki-page write.

Public entry: `routine_init(name, *, dest_dir, wiki_root, trigger_type,
linked_repo, skill, ...) -> RoutineInitResult`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

FRAMEWORK_VERSION: Final[str] = "1.0.0"
VALID_TRIGGERS: Final[frozenset[str]] = frozenset({"cron", "api", "github"})
VALID_TIERS: Final[frozenset[str]] = frozenset({"trusted", "full", "custom"})
SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

REPO_TEMPLATE_FILES: Final[tuple[str, ...]] = (
    "CLAUDE.md",
    "ROUTINE_PROMPT.md",
    "state.md",
    "run-log.md",
)


@dataclass(frozen=True)
class RoutineInitResult:
    success: bool
    repo_dir: Path | None = None
    spec_page: Path | None = None
    files_written: tuple[Path, ...] = ()
    error: str | None = None


def _render(text: str, placeholders: dict[str, str]) -> str:
    for ph, val in placeholders.items():
        text = text.replace(ph, val)
    return text


def _default_templates_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "templates"


def routine_init(
    name: str,
    *,
    dest_dir: Path,
    wiki_root: Path,
    trigger_type: str,
    linked_repo: str,
    skill: str,
    network_tier: str = "trusted",
    schedule: str = "",
    expected_output: str = "",
    env_secrets_ref: str = "",
    failure_email: str = "",
    today: str | None = None,
    templates_dir: Path | None = None,
) -> RoutineInitResult:
    # ── validation ──────────────────────────────────────────────
    if not name or not SLUG_RE.match(name):
        return RoutineInitResult(False, error=f"Invalid routine name {name!r}. Use kebab-case (e.g. daily-digest).")
    if trigger_type not in VALID_TRIGGERS:
        return RoutineInitResult(False, error=f"Invalid trigger_type {trigger_type!r}. One of: {sorted(VALID_TRIGGERS)}.")
    if network_tier not in VALID_TIERS:
        return RoutineInitResult(False, error=f"Invalid network_tier {network_tier!r}. One of: {sorted(VALID_TIERS)}.")
    if not skill or not skill.strip():
        return RoutineInitResult(False, error="A target /ren: skill is required (the skill the routine runs).")

    templates_dir = templates_dir or _default_templates_dir()
    repo_tmpl_dir = templates_dir / "repo"

    repo_dir = dest_dir / name
    if repo_dir.exists():
        return RoutineInitResult(False, error=f"Refusing to overwrite existing directory {repo_dir}.")

    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    placeholders = {
        "{{routine_name}}": name,
        "{{trigger_type}}": trigger_type,
        "{{linked_repo}}": linked_repo,
        "{{network_tier}}": network_tier,
        "{{env_secrets_ref}}": env_secrets_ref or "(none declared)",
        "{{schedule}}": schedule,
        "{{expected_output}}": expected_output or "(describe what this routine produces)",
        "{{failure_handler}}": f"email {failure_email} via Resend MCP" if failure_email else "(set a failure email)",
        "{{failure_email}}": failure_email or "(set --failure-email)",
        "{{skill}}": skill.strip(),
        "{{today}}": today,
        "{{framework_version}}": FRAMEWORK_VERSION,
    }

    written: list[Path] = []

    # ── scaffold the lean repo ──────────────────────────────────
    repo_dir.mkdir(parents=True, exist_ok=False)
    for fname in REPO_TEMPLATE_FILES:
        src = repo_tmpl_dir / f"{fname}.tmpl"
        out = repo_dir / fname
        out.write_text(_render(src.read_text(encoding="utf-8"), placeholders), encoding="utf-8")
        written.append(out)

    return RoutineInitResult(
        success=True,
        repo_dir=repo_dir,
        files_written=tuple(written),
    )


__all__ = [
    "FRAMEWORK_VERSION",
    "VALID_TRIGGERS",
    "VALID_TIERS",
    "RoutineInitResult",
    "routine_init",
]
```

- [ ] **Step 5: Run tests to verify they PASS**

Run: `( cd skills/routine-init && python3 -m pytest lib/tests -q -p no:cacheprovider )`
Expected: all tests in `TestValidation` + `TestScaffold` PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/routine-init/lib skills/routine-init/templates/repo
git commit -m "feat(routine-init): lean-repo scaffold + input validation (C4)

routine_init() validates kebab name / trigger_type / network_tier / skill,
refuses to overwrite, and renders the lean cloud-routine repo (CLAUDE.md,
ROUTINE_PROMPT.md with the failure footer + skill-as-prompt + single-pass
conventions baked in, state.md, run-log.md) from templates."
```

---

## Task 3: `/ren:routine-init` lib — write the `routine-spec` wiki page

**Files:**
- Modify: `skills/routine-init/lib/__init__.py` (add the spec-page write + a second collision check)
- Test: `skills/routine-init/lib/tests/test_routine_init.py` (append a `TestSpecPage` class)

- [ ] **Step 1: Append failing tests**

Append to `skills/routine-init/lib/tests/test_routine_init.py`:

```python
class TestSpecPage:
    def test_writes_routine_spec_page(self, tmp_path):
        r = _run(tmp_path)
        assert r.success, r.error
        page = tmp_path / "wiki" / "routines" / "daily-digest.md"
        assert page.is_file()
        assert r.spec_page == page
        content = page.read_text()
        assert "type: routine-spec" in content
        assert "schema_version: 1" in content
        assert "daily-digest" in content
        assert '"cron"' in content
        assert '"trusted"' in content

    def test_spec_page_has_required_fields(self, tmp_path):
        r = _run(tmp_path)
        content = (tmp_path / "wiki" / "routines" / "daily-digest.md").read_text()
        for key in ("name:", "trigger_type:", "linked_repo:", "network_tier:"):
            assert key in content
        assert 'framework_version: "1.0.0"' in content

    def test_refuses_existing_spec_page(self, tmp_path):
        (tmp_path / "wiki" / "routines").mkdir(parents=True)
        (tmp_path / "wiki" / "routines" / "daily-digest.md").write_text("x", encoding="utf-8")
        r = _run(tmp_path)
        assert not r.success and "routine-spec page" in r.error
        # No partial repo created when the spec page already exists.
        assert not (tmp_path / "repos" / "daily-digest").exists()
```

- [ ] **Step 2: Run to verify the new tests FAIL**

Run: `( cd skills/routine-init && python3 -m pytest lib/tests/test_routine_init.py::TestSpecPage -q -p no:cacheprovider )`
Expected: FAIL (`spec_page` is `None`; no page written).

- [ ] **Step 3: Add the spec-page write to the lib**

In `skills/routine-init/lib/__init__.py`, after the `repo_dir` collision check, add a `spec_page` collision check (both checks run before any `mkdir`, so a pre-existing spec page yields a clean refusal with no partial repo):

```python
    repo_dir = dest_dir / name
    if repo_dir.exists():
        return RoutineInitResult(False, error=f"Refusing to overwrite existing directory {repo_dir}.")
    spec_page = wiki_root / "routines" / f"{name}.md"
    if spec_page.exists():
        return RoutineInitResult(False, error=f"Refusing to overwrite existing routine-spec page {spec_page}.")
```

Then, immediately before the final `return RoutineInitResult(...)`, render and write the wiki page and include it in `written`:

```python
    # ── write the routine-spec wiki page (the "report home" record) ──
    wiki_tmpl = templates_dir / "wiki" / "routine-spec.md.tmpl"
    spec_page.parent.mkdir(parents=True, exist_ok=True)
    spec_page.write_text(_render(wiki_tmpl.read_text(encoding="utf-8"), placeholders), encoding="utf-8")
    written.append(spec_page)

    return RoutineInitResult(
        success=True,
        repo_dir=repo_dir,
        spec_page=spec_page,
        files_written=tuple(written),
    )
```

(Remove the old `return` that omitted `spec_page`.)

- [ ] **Step 4: Run the full lib suite to verify PASS**

Run: `( cd skills/routine-init && python3 -m pytest lib/tests -q -p no:cacheprovider )`
Expected: all tests PASS (validation, scaffold, spec page).

- [ ] **Step 5: Commit**

```bash
git add skills/routine-init/lib
git commit -m "feat(routine-init): write routine-spec wiki page on scaffold (C4)

Each scaffold now also writes wiki/routines/<slug>.md from the conformant
routine-spec template, closing the report-home loop: the wake-up hook and
/ren:doctor read these pages. Refuses to overwrite an existing page with no
partial repo left behind."
```

---

## Task 4: `/ren:routine-init` skill surface (SKILL.md + eval + references)

**Files:**
- Create: `skills/routine-init/SKILL.md`
- Create: `skills/routine-init/eval/eval.json`
- Create: `skills/routine-init/references/lean-repo.md`
- Create: `skills/routine-init/learnings.md`

- [ ] **Step 1: Write the SKILL.md** (conforms to ADR-011; ≤200 lines)

Create `skills/routine-init/SKILL.md`:

```markdown
---
name: routine-init
description: |
  Use when the friend wants to deploy a scheduled/cloud automation ("set up a
  daily digest", "run X on a schedule", "make a Cloud Routine"). Triggers on
  /ren:routine-init <name>. Scaffolds a lean per-routine GitHub repo (small
  CLAUDE.md + a skill-as-prompt with the failure footer baked in) and writes a
  routine-spec wiki page so the wake-up hook + /ren:doctor can see it. Per
  ADR-034: thin glue over Cloud Routines — no scheduler of its own. For picking
  the right cadence tier (/loop vs Cron vs /goal vs Cloud), use /ren:cadence first.
version: 0.1.0
license: MIT
framework_version: "1.0.0"
schema_version: 1
type: skill
owner_module: sf-cadence

contract:
  required_outputs:
    - "A lean routine repo at <dest>/<slug>/ with CLAUDE.md, ROUTINE_PROMPT.md, state.md, run-log.md"
    - "A routine-spec wiki page at ~/.startup-framework/wiki/routines/<slug>.md (conformant frontmatter)"
    - "A printed next-steps checklist (push to GitHub, create the cloud env with network tier + secrets, Run-Now before scheduling)"
  budgets:
    turns: 4
    files_written: 5
    duration_seconds: 30
  permissions:
    read:
      - "skills/routine-init/templates/**"
      - "~/.startup-framework/wiki/identity.md"
    write:
      - "~/.startup-framework/wiki/routines/**"
      - "<dest-dir>/<slug>/**"
    execute:
      - "skills/routine-init/lib (routine_init)"
  completion_conditions:
    - "The repo dir and the routine-spec page both exist after a successful run"
    - "On any name/trigger/tier/skill validation failure OR an existing target, nothing is written (clean refusal)"
  output_paths:
    - "~/.startup-framework/wiki/routines/"
    - "<dest-dir>/<slug>/"

tags: [cadence, routines, scaffold, cloud, lifecycle]
related_skills: [cadence, recall, doctor, backup]
references_required:
  - "references/lean-repo.md"
references_on_demand: []
---

# routine-init

Scaffolds a **lean per-routine repo** for a Cloud Routine and records it in the wiki. The repo is the *muscle* (only what this one routine needs); the wiki routine-spec page is the *truth* (the wake-up hook surfaces it; `/ren:doctor` audits it). Per ADR-034.

## When to use

- Friend invokes `/ren:routine-init <slug> …` (canonical trigger).
- Friend says "set up a daily/weekly automation" or "deploy this as a Cloud Routine" — confirm the tier with `/ren:cadence` first (Cloud Routine is the right tier only for machine-off, ≥1h cadence), then run this.

## When NOT to use

- For an **intra-session** watch (deploy/PR/context-budget) → that's `/loop`, not a routine repo. Use `/ren:cadence`.
- For a **long autonomous loop with a measurable exit** → that's `/goal`. Use `/ren:cadence`.
- Empty `<slug>`, non-kebab-case, or unknown trigger/tier → refuse (the lib validates).

## Behavior

1. **Gather inputs** (ask only for what's missing):
   - `name` (kebab-case slug), `--skill <verb>` (the `/ren:` skill the routine runs),
   - `--trigger <cron|api|github>`, `--repo <git-url>` (the linked repo),
   - `--tier <trusted|full|custom>` (default `trusted` — see § Safety),
   - `--schedule "<natural language>"` (cron trigger only), `--expected "<one line>"`,
   - `--secrets "<env var names>"`, `--failure-email <addr>` (default: friend's email from `identity.md`),
   - `--dest <dir>` (where to create the repo; default the cwd).
2. **Resolve paths**: `wiki_root` = `~/.startup-framework/wiki`; `dest_dir` = `--dest` or cwd.
3. **Invoke the lib** `routine_init(...)` (see `lib/__init__.py`). It validates, refuses to overwrite, scaffolds the four repo files (templates baked with the skill-as-prompt + failure footer + single-pass + env-var-sourcing conventions), and writes the conformant routine-spec page.
4. **Print next steps** (the lib does NOT touch GitHub or the cloud — those are the friend's outward actions):
   - `git init && git add -A && git commit` the new repo, then create a private GitHub repo and push.
   - In Claude Code, create a **Cloud Environment**: set network tier (`trusted` unless arbitrary domains are genuinely needed), add the secrets named in `--secrets` as env vars (NOT in the repo).
   - Configure the routine: linked repo + the prompt is `ROUTINE_PROMPT.md` + the schedule.
   - **Run-Now once** and watch it one-shot cleanly before scheduling (green-before-schedule, the TDD of cadence).

## Safety (ADR-034 §4)

- **Network tier defaults to `trusted`** (Anthropic allowlist). `full` = unrestricted egress = a prompt-injection exfiltration surface; only choose it deliberately. `/ren:doctor` flags `full`-tier routines.
- **Secrets live in the cloud env, never the repo.** The scaffolded CLAUDE.md/ROUTINE_PROMPT.md tell the run to use env vars directly and never look for a `.env`.
- **Never bypass-permissions for cadence.** Auto Permission Mode for team-plan unattended runs; manual allow/deny for solo (ADR-031).

## What this skill does NOT do

- Talk to GitHub or Anthropic's cloud (no repo creation, no scheduling) — it prints the steps; the friend acts.
- Pick the cadence tier — that's `/ren:cadence`.
- Run a daemon or watch for the routine's pushes — pull-model only (ADR-003/026).

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Non-kebab name | Refuse, no writes | "Invalid routine name … Use kebab-case" |
| Bad trigger/tier | Refuse, no writes | "Invalid trigger_type/network_tier …" |
| Target repo or spec page exists | Refuse, no writes | "Refusing to overwrite …" |

## Eval

`eval/eval.json` asserts: a clean run writes the 4 repo files + the spec page; the spec page carries `type: routine-spec` + required fields; the prompt bakes in the Resend failure footer and `/ren:recall --routine .`; invalid inputs and existing targets refuse with no writes.

## References

- `references/lean-repo.md` — the lean-repo discipline + the export-from-rich-session step.
- ADR-034 (cadence-as-glue), ADR-026 (git pull-model write-back), ADR-027 (routine-spec page-type).
```

- [ ] **Step 2: Write the eval.json**

Create `skills/routine-init/eval/eval.json`:

```json
{
  "name": "routine-init",
  "description": "Binary-assertion suite for /ren:routine-init. Each test simulates a scaffold against a temp dest + wiki and verifies the files and refusals.",
  "schema_version": 1,
  "framework_version": "1.0.0",
  "tests": [
    {
      "id": "scaffold-and-spec",
      "prompt": "/ren:routine-init daily-digest --skill insights --trigger cron --repo https://github.com/u/daily-digest --schedule \"every day 8am\" --expected \"Yesterday's digest\" --secrets RESEND_API_KEY --failure-email me@example.com",
      "expected_output_summary": "Lean repo + routine-spec page created; next-steps printed.",
      "trigger_test": true,
      "binary_assertions": [
        "<dest>/daily-digest/ contains CLAUDE.md, ROUTINE_PROMPT.md, state.md, run-log.md",
        "~/.startup-framework/wiki/routines/daily-digest.md exists and contains 'type: routine-spec'",
        "The routine-spec page contains name, trigger_type, linked_repo, network_tier frontmatter keys",
        "ROUTINE_PROMPT.md contains the substring 'mcp__resend__send-email'",
        "ROUTINE_PROMPT.md contains the substring '/ren:recall --routine .'",
        "ROUTINE_PROMPT.md contains the substring '/ren:insights'",
        "Output prints a next-steps checklist mentioning 'Run-Now' (or 'Run Now') before scheduling"
      ]
    },
    {
      "id": "invalid-name-refused",
      "prompt": "/ren:routine-init DailyDigest --skill insights --trigger cron --repo https://github.com/u/x",
      "expected_output_summary": "Non-kebab name refused; nothing written.",
      "trigger_test": true,
      "binary_assertions": [
        "User-facing output mentions 'kebab-case'",
        "No directory named DailyDigest or dailydigest is created",
        "No routine-spec page is written"
      ]
    },
    {
      "id": "full-tier-warns",
      "prompt": "/ren:routine-init scraper --skill insights --trigger cron --repo https://github.com/u/scraper --tier full",
      "expected_output_summary": "Scaffolds but the next-steps/safety note flags the full network tier.",
      "trigger_test": false,
      "binary_assertions": [
        "The routine-spec page has network_tier value 'full'",
        "Output warns that 'full' network tier is an exfiltration/prompt-injection surface"
      ]
    },
    {
      "id": "existing-target-refused",
      "prompt": "/ren:routine-init daily-digest --skill insights --trigger cron --repo https://github.com/u/daily-digest",
      "expected_output_summary": "When the repo dir or spec page already exists, refuse with no overwrite.",
      "trigger_test": false,
      "binary_assertions": [
        "Output contains the substring 'Refusing to overwrite'",
        "No pre-existing file under the target repo or the spec page has its content changed"
      ]
    }
  ],
  "non_triggers": [
    {
      "id": "loop-not-routine",
      "prompt": "/loop every 5 minutes check the deploy",
      "expected_outcome": "skill_not_activated"
    },
    {
      "id": "recall-not-routine",
      "prompt": "/ren:recall postgres decision",
      "expected_outcome": "skill_not_activated"
    }
  ]
}
```

- [ ] **Step 3: Write the reference + learnings stub**

Create `skills/routine-init/references/lean-repo.md`:

```markdown
# Lean-repo discipline (ADR-034 · research tension #5)

A Cloud Routine clones its linked repo, loads `CLAUDE.md`, runs, and destroys the env. A large `CLAUDE.md` + unrelated project code burns the run's context budget and quota on irrelevant tokens. So each routine gets its **own minimal repo** — the *muscle*, nothing more.

## What goes in a routine repo

- A small `CLAUDE.md` — what the routine does, where its secrets are (env vars, never `.env`), the cross-run memory files.
- `ROUTINE_PROMPT.md` — the skill-as-prompt: one named `/ren:` skill, explicit order of operations, the required failure footer, single-pass exit.
- `state.md` / `run-log.md` — the cross-run memory trail (read at start via `/ren:recall --routine .`, written back via git push).
- Only the scripts/skills this one routine needs.

## What stays OUT

- Unrelated project source, other projects' CLAUDE.md, the whole dev-wiki.
- Secrets of any kind (those live in the cloud environment).

## The export-from-rich-session step

The lean-repo principle conflicts with wanting the rich context that makes a system prompt specific. The resolution (Nate Herk): design/iterate the routine **inside** your rich interactive session, then export only the necessary context into the lean routine repo. `/ren:routine-init` is that export step — it captures the skill + conventions into a minimal repo so the cloud run starts clean.

## Green-before-schedule

Use **Run-Now** to iterate on the routine interactively before committing it to a schedule — run, observe, fix the prompt/env, repeat until it one-shots cleanly. Same discipline as TDD: green before schedule.
```

Create `skills/routine-init/learnings.md`:

```markdown
# routine-init — learnings

_(Append durable, non-obvious lessons from real routine deployments here. Empty at ship.)_
```

- [ ] **Step 4: Verify SKILL.md conforms + eval is valid JSON**

Run:
```bash
python3 tests/integration/schema-conformance/conformance.py
python3 -c "import json; json.load(open('skills/routine-init/eval/eval.json')); print('eval ok')"
```
Expected: conformance exit 0 (routine-init SKILL.md now scanned as `type: skill`, passes name+description); `eval ok`.

- [ ] **Step 5: Commit**

```bash
git add skills/routine-init/SKILL.md skills/routine-init/eval skills/routine-init/references skills/routine-init/learnings.md
git commit -m "feat(routine-init): SKILL.md + eval + lean-repo reference (C4)

Completes the /ren:routine-init surface: ADR-011-conformant SKILL.md (gather
inputs, invoke the scaffold lib, print outward next-steps), binary-assertion
eval, and the lean-repo discipline reference."
```

---

## Task 5: `/ren:cadence` — the decision-matrix / router skill (LLM-only)

**Files:**
- Create: `skills/cadence/SKILL.md`
- Create: `skills/cadence/references/cadence-matrix.md`
- Create: `skills/cadence/references/conventions.md`
- Create: `skills/cadence/eval/eval.json`
- Create: `skills/cadence/learnings.md`

This skill has no `lib/` (LLM-only, like `bootstrap-project`). Its "tests" are conformance (SKILL.md) + a valid eval.json; no pytest.

- [ ] **Step 1: Write the SKILL.md**

Create `skills/cadence/SKILL.md`:

```markdown
---
name: cadence
description: |
  Use when the friend wants to automate a recurring task and needs to pick the
  RIGHT primitive ("should this be a /loop, a cron, a /goal, or a Cloud
  Routine?"). Triggers on /ren:cadence. Presents the decision matrix (ADR-034
  §1), routes to the lowest tier that fits, and applies the framework
  conventions (self-terminating loops, auto-compact companion cron, measurable
  /goal exit, failure footer, env-var sourcing). For the cloud tier it hands off
  to /ren:routine-init. Thin glue over native primitives — runs nothing itself.
version: 0.1.0
license: MIT
framework_version: "1.0.0"
schema_version: 1
type: skill
owner_module: sf-cadence

contract:
  required_outputs:
    - "A recommended cadence tier (/loop | Cron | /goal | Cloud Routine) with the one-line reason it fits"
    - "For local tiers: the exact guarded invocation (self-terminating stop + failure footer; auto-compact companion cron for long loops; measurable exit for /goal)"
    - "For the cloud tier: a handoff to /ren:routine-init"
  budgets:
    turns: 3
    files_written: 0
    duration_seconds: 15
  permissions:
    read:
      - "references/**"
    write: []
    execute: []
  completion_conditions:
    - "A tier is recommended with its reason"
    - "Run is side-effect-free (no files written; no schedule created without the friend's go-ahead)"
  output_paths: []

tags: [cadence, routines, loop, cron, goal, routing, read-only]
related_skills: [routine-init, recall, doctor]
references_required:
  - "references/cadence-matrix.md"
  - "references/conventions.md"
---

# cadence

The cadence router. Answers "what's the right way to make this recur?" with the **decision matrix** (ADR-034 §1) and applies the framework's safety conventions. It runs nothing itself — it routes to native primitives (`/loop`, `CronCreate`, `/goal`, Cloud Routines) and to `/ren:routine-init`.

## When to use

- Friend invokes `/ren:cadence` or asks "should this be a loop or a cron or a routine?"
- Before `/ren:routine-init`, to confirm a Cloud Routine is actually the right tier.

## When NOT to use

- The friend already knows the tier and just wants to scaffold a cloud routine → `/ren:routine-init` directly.

## Behavior

1. **Clarify the task's shape** (ask only what's needed): does it need to run with the machine off? what's the cadence (continuous / minutes / hourly+ / one long push)? is there a measurable done-criterion? does it fan out into many parallel pieces?
2. **Route via the matrix** (`references/cadence-matrix.md`). Use the **lowest tier that fits**:
   - intra-session watch (deploy/PR/context-budget) → `/loop`
   - scheduled session loop (machine on) → `CronCreate`
   - long autonomous loop with a measurable exit → `/goal`
   - machine-off / production cadence (≥1h) → **Cloud Routine** → hand off to `/ren:routine-init`
3. **Apply the conventions** (`references/conventions.md`) to whatever tier is chosen:
   - **Self-terminating**: every `/loop`/cron carries a stop condition (kill after N iterations or a time window) so no orphaned background job persists.
   - **Auto-compact companion cron**: for a long-running loop, pair it with a second cron whose sole payload is `/clear` (~every 5 min) to prevent context rot.
   - **Failure footer**: any unattended prompt appends "if this fails, email me via Resend MCP `mcp__resend__send-email`".
   - **Measurable exit for `/goal`**: a concrete done-criterion (passing test, coverage threshold), never a subjective prompt (which loops forever).
   - **Env-var sourcing**: tell the run secrets are env vars; do not look for `.env`.
4. **Emit** the recommended tier + reason + the exact guarded command (or the `/ren:routine-init` handoff). Create a schedule only with the friend's explicit go-ahead, and recommend **Run-Now before scheduling**.

## What this skill does NOT do

- Reimplement `/loop`/Cron/`/goal` — those are native; this routes to them.
- Run a daemon or scheduler (ADR-003).
- Scaffold the cloud repo — that's `/ren:routine-init`.

## Eval

`eval/eval.json` asserts the router recommends the correct tier for canonical prompts (machine-off→Cloud Routine + routine-init handoff; intra-session watch→/loop with a stop condition; measurable long job→/goal) and always attaches the relevant convention.

## References

- `references/cadence-matrix.md` — the primitive ladder + the decision matrix (ADR-034 §1).
- `references/conventions.md` — self-terminating, auto-compact companion cron, failure footer, measurable exit, env-var sourcing, off-peak, terminal-vs-desktop cron + jitter.
```

- [ ] **Step 2: Write the matrix reference**

Create `skills/cadence/references/cadence-matrix.md`:

```markdown
# Cadence decision matrix (ADR-034 §1)

**Rule: use the lowest tier that fits.** (Capability ladder: quick ask → skill → sub-agent → agent team → /goal → dynamic workflow.)

| Primitive | Statefulness / durability | Use for |
|---|---|---|
| `/loop` | intra-session, **retains context**, ≤ 3 days | deploy/PR watches, context-budget checks |
| `CronCreate` / `CronList` / `CronDelete` | session-scoped; terminal **7d** / desktop **3d**; ~30-min jitter | scheduled session loops (interval mental model, not wall-clock) |
| `/goal` | autonomous depth-first loop until a **measurable** exit (≤ 24h+) | overnight `/ren:improve-skill`, weekly scans |
| **Cloud Routines** | machine-off; cron/API/GitHub triggers; cold fresh env each run; quota (Max 15/day, min 1h) | production cadence → use `/ren:routine-init` |

## Width vs. depth

- "Does this break into many independent pieces running simultaneously?" → dynamic workflow (Haiku workers + one Opus synthesizer).
- "Do I need to keep checking against a done-criterion until it flips?" → `/goal`.
- Combining width and depth is very expensive — do it deliberately.

## Trigger types (Cloud Routines)

- **cron** — natural-language schedule, min 1 hour.
- **api** — outbound POST from another automation (enables chaining).
- **github** — PR / push / issue / release webhook (CI/CD integration).

## Behavioral gotchas

- **Terminal vs desktop cron:** in the terminal, crons survive `/clear` and persist up to 7 days; in the desktop app, `/clear` kills all crons and expiry is 3 days.
- **Jitter:** cron firing adds up to 30 minutes of random jitter — think intervals, not exact wall-clock.
- **Quota:** Pro 5/day, Max 15/day, Team/Enterprise 25/day; min interval 1 hour. `/ren:doctor` surfaces headroom.
```

- [ ] **Step 3: Write the conventions reference**

Create `skills/cadence/references/conventions.md`:

```markdown
# Cadence conventions (ADR-034 §3–4 · research)

Apply these to whatever tier `/ren:cadence` routes to. The cloud scaffold (`/ren:routine-init`) bakes the relevant ones into its templates automatically; for local `/loop`/cron/`/goal` you apply them by hand.

## Self-terminating loops
Every `/loop` or `CronCreate` carries a stop condition — "kill the cron after N iterations" or "stop after <time window>". Prevents orphaned background jobs persisting past their useful life.

## Auto-compact companion cron
For a long-running loop that accumulates stale context, pair the work cron with a second cron whose sole payload is `/clear` (~every 5 minutes). Prevents context rot.

## Failure-notification footer (required for unattended runs)
Append to any unattended prompt: *"If this run fails for any reason, send me an email via the Resend MCP tool `mcp__resend__send-email` with the error."* Headless runs fail silently by default; this is zero-infrastructure observability.

## Measurable exit for `/goal`
`/goal` must have a concrete, measurable done-criterion (a passing test, a coverage threshold, a file that exists). A subjective prompt causes infinite iteration.

## Explicit env-var sourcing
Tell the run exactly where secrets are: *"My X key is an environment variable — use it directly, do not look for a `.env`."* Without this, Claude searches for `.env` per CLAUDE.md conventions and fails silently.

## Run-Now before scheduling
Iterate on the routine interactively with **Run-Now** until it one-shots cleanly, then schedule. Green-before-schedule — the TDD of cadence.

## Off-peak scheduling
Anthropic throttles session-window drain by demand; peak ≈ 8am–2pm ET weekdays. Schedule heavy multi-agent / large-refactor cadence off-peak.

## Permission posture (ADR-031)
Auto Permission Mode for team-plan unattended runs; manual allow/deny for solo Pro/Max. **Never** bypass-permissions for cadence.
```

- [ ] **Step 4: Write the eval.json + learnings stub**

Create `skills/cadence/eval/eval.json`:

```json
{
  "name": "cadence",
  "description": "Binary-assertion suite for /ren:cadence — the cadence router. Asserts correct tier routing + convention attachment.",
  "schema_version": 1,
  "framework_version": "1.0.0",
  "tests": [
    {
      "id": "machine-off-routes-cloud",
      "prompt": "/ren:cadence I want a daily digest emailed every morning while my laptop is closed",
      "expected_output_summary": "Recommends a Cloud Routine and hands off to /ren:routine-init.",
      "trigger_test": true,
      "binary_assertions": [
        "Output recommends a Cloud Routine (names 'Cloud Routine' or 'routine')",
        "Output names '/ren:routine-init' as the next step",
        "Output mentions the failure footer / Resend notification convention"
      ]
    },
    {
      "id": "intra-session-routes-loop",
      "prompt": "/ren:cadence keep checking my deploy every few minutes while I work",
      "expected_output_summary": "Recommends /loop with a self-terminating stop condition.",
      "trigger_test": true,
      "binary_assertions": [
        "Output recommends '/loop'",
        "Output attaches a self-terminating stop condition (mentions stopping after N iterations or a time window)"
      ]
    },
    {
      "id": "measurable-job-routes-goal",
      "prompt": "/ren:cadence run improve-skill overnight until coverage hits 80%",
      "expected_output_summary": "Recommends /goal with the measurable exit criterion.",
      "trigger_test": false,
      "binary_assertions": [
        "Output recommends '/goal'",
        "Output requires a measurable exit criterion (references the 80% coverage as the done-condition)"
      ]
    }
  ],
  "non_triggers": [
    {
      "id": "plain-question",
      "prompt": "What does ADR-034 say?",
      "expected_outcome": "skill_not_activated"
    }
  ]
}
```

Create `skills/cadence/learnings.md`:

```markdown
# cadence — learnings

_(Append durable, non-obvious cadence-routing lessons here. Empty at ship.)_
```

- [ ] **Step 5: Verify conformance + valid eval**

Run:
```bash
python3 tests/integration/schema-conformance/conformance.py
python3 -c "import json; json.load(open('skills/cadence/eval/eval.json')); print('eval ok')"
```
Expected: conformance exit 0 (cadence SKILL.md passes); `eval ok`.

- [ ] **Step 6: Commit**

```bash
git add skills/cadence
git commit -m "feat(cadence): /ren:cadence decision-matrix router skill (C4)

LLM-only glue skill: presents the ADR-034 primitive ladder + decision matrix,
routes to the lowest tier that fits (/loop, Cron, /goal, Cloud Routine), applies
the conventions (self-terminating, auto-compact companion cron, measurable /goal
exit, failure footer, env-var sourcing), and hands off to /ren:routine-init for
the cloud tier. Runs nothing itself."
```

---

## Task 6: Extend `/ren:recall` to read routine `state.md` / `run-log.md`

**Files:**
- Modify: `skills/recall/lib/__init__.py` (add `RoutineState`, `read_routine_state`, helpers, `__all__`)
- Test: `skills/recall/lib/tests/test_recall.py` (append a `TestRoutineState` class)
- Modify: `skills/recall/SKILL.md` (frontmatter read path + a body section for `--routine`)

- [ ] **Step 1: Append failing tests**

Append to `skills/recall/lib/tests/test_recall.py`:

```python
class TestRoutineState:
    def test_reads_state_and_runlog(self, tmp_path):
        from ..__init__ import read_routine_state
        (tmp_path / "state.md").write_text("# state\n\nlast run ok\n", encoding="utf-8")
        (tmp_path / "run-log.md").write_text(
            "# run log\n\n## [2026-06-10 08:00 UTC] ran\n## [2026-06-11 08:00 UTC] ran again\n",
            encoding="utf-8",
        )
        rs = read_routine_state(tmp_path)
        assert rs.found is True
        assert "last run ok" in rs.state_md
        assert "ran again" in rs.run_log_tail

    def test_missing_files_not_found(self, tmp_path):
        from ..__init__ import read_routine_state
        rs = read_routine_state(tmp_path)
        assert rs.found is False
        assert rs.state_md == ""
        assert rs.run_log_tail == ""

    def test_runlog_tail_caps_entries(self, tmp_path):
        from ..__init__ import read_routine_state
        entries = "".join(f"## [2026-06-{d:02d} 08:00 UTC] run {d}\n" for d in range(1, 16))
        (tmp_path / "run-log.md").write_text("# run log\n\n" + entries, encoding="utf-8")
        rs = read_routine_state(tmp_path, runlog_tail=10)
        assert rs.found is True
        assert "run 15" in rs.run_log_tail        # newest kept
        assert "run 5" not in rs.run_log_tail      # 15 entries, tail 10 → first 5 dropped
```

- [ ] **Step 2: Run to verify FAIL**

Run: `( cd skills/recall && python3 -m pytest lib/tests/test_recall.py::TestRoutineState -q -p no:cacheprovider )`
Expected: FAIL (`ImportError: cannot import name 'read_routine_state'`).

- [ ] **Step 3: Implement in recall's lib**

In `skills/recall/lib/__init__.py`, add these constants near the other `Final` constants (after `DEFAULT_N_HITS`):

```python
ROUTINE_STATE_FILENAME: Final[str] = "state.md"
ROUTINE_RUNLOG_FILENAME: Final[str] = "run-log.md"
DEFAULT_RUNLOG_TAIL: Final[int] = 10
```

Add the dataclass after `RecallResult`:

```python
@dataclass(frozen=True)
class RoutineState:
    """A routine repo's cross-run memory trail, read at run start (ADR-034)."""

    repo_root: Path
    state_md: str        # full content of state.md ("" if missing)
    run_log_tail: str    # last N run-log entries ("" if missing)
    found: bool          # True if state.md or run-log.md existed
```

Add the helpers + public entry near the end (before `__all__`):

```python
def _safe_read(path: Path) -> str:
    """Read a file; return "" on any error (mirrors grep_wiki's guard)."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("could not read %s: %s", path, exc)
        return ""


def _runlog_tail(content: str, n_entries: int) -> str:
    """Return the last n run-log entries (entries start with '## [')."""
    entries: list[list[str]] = []
    current: list[str] = []
    for line in content.splitlines():
        if line.startswith("## ["):
            if current:
                entries.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        entries.append(current)
    tail = entries[-n_entries:]
    return "\n".join("\n".join(e) for e in tail).strip()


def read_routine_state(repo_root: Path, *, runlog_tail: int = DEFAULT_RUNLOG_TAIL) -> RoutineState:
    """
    Read a routine repo's state.md + run-log.md (the cross-run memory trail).

    Invoked by /ren:recall --routine <repo_root> at the start of a routine run
    so a stateless cloud run knows what prior runs did (ADR-034).
    """
    state_path = repo_root / ROUTINE_STATE_FILENAME
    runlog_path = repo_root / ROUTINE_RUNLOG_FILENAME
    state_md = _safe_read(state_path)
    runlog_content = _safe_read(runlog_path)
    return RoutineState(
        repo_root=repo_root,
        state_md=state_md,
        run_log_tail=_runlog_tail(runlog_content, runlog_tail) if runlog_content else "",
        found=state_path.is_file() or runlog_path.is_file(),
    )
```

Extend `__all__` with the new names:

```python
__all__ = [
    "STOP_WORDS",
    "KIND_MULTIPLIERS",
    "DEFAULT_N_HITS",
    "DEFAULT_RUNLOG_TAIL",
    "RecallHit",
    "RecallResult",
    "RoutineState",
    "tokenize_query",
    "grep_wiki",
    "recall",
    "read_routine_state",
]
```

- [ ] **Step 4: Run the full recall suite to verify PASS**

Run: `( cd skills/recall && python3 -m pytest lib/tests -q -p no:cacheprovider )`
Expected: existing tests + `TestRoutineState` all PASS.

- [ ] **Step 5: Update recall's SKILL.md**

Read `skills/recall/SKILL.md`. In the `contract.permissions.read` list, add the routine-state read paths (so the contract reflects reads outside the wiki):

```yaml
  permissions:
    read:
      - "~/.startup-framework/wiki/**"
      - "<routine-repo>/state.md"
      - "<routine-repo>/run-log.md"
    write: []
    execute: []
```

Then append this section to the end of the body:

```markdown
## Reading routine state (`--routine <path>`)

When invoked as `/ren:recall --routine <repo-path>` (no query), recall switches to **state-read mode** instead of grep: it reads that routine repo's `state.md` (full) and `run-log.md` (last 10 entries) via `read_routine_state()` and prints the cross-run memory trail. This is the call a Cloud Routine makes at run start (ADR-034) so a stateless run knows what prior runs did. Read-only, like the grep path. If neither file exists, it reports "no prior state" and exits cleanly.
```

- [ ] **Step 6: Verify conformance still passes (recall SKILL.md unchanged shape)**

Run: `python3 tests/integration/schema-conformance/conformance.py`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add skills/recall/lib skills/recall/SKILL.md
git commit -m "feat(recall): --routine state-read mode for cadence runs (C4)

Adds read_routine_state(repo_root): reads a routine repo's state.md (full) +
run-log.md (tail 10) — the cross-run memory trail a stateless Cloud Routine
loads at run start per ADR-034. Grep path unchanged."
```

---

## Task 7: Extend `/ren:doctor` — ROUTINES section (network-tier + quota audits)

**Files:**
- Create: `skills/doctor/scripts/check-routines.sh`
- Test: `skills/doctor/scripts/tests/test_check_routines.sh`
- Modify: `skills/doctor/SKILL.md` (8 spots: description, contract ×3, table, flag, output example, eval)

- [ ] **Step 1: Write the failing bash harness**

Create `skills/doctor/scripts/tests/test_check_routines.sh`:

```bash
#!/usr/bin/env bash
# test_check_routines.sh — hermetic tests for /ren:doctor ROUTINES section (ADR-034).
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SCRIPT="$(cd "$SCRIPT_DIR/.." && pwd)/check-routines.sh"

PASS_COUNT=0; FAIL_COUNT=0
pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL_COUNT=$((FAIL_COUNT+1)); }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
ROUTINES="$TMP/wiki/routines"; mkdir -p "$ROUTINES"

mk_routine() {  # $1=slug $2=trigger $3=tier
  cat > "$ROUTINES/$1.md" <<EOF
---
type: routine-spec
schema_version: 1
framework_version: "1.0.0"
name: "$1"
trigger_type: "$2"
linked_repo: "https://github.com/u/$1"
network_tier: "$3"
---

# $1
EOF
}

echo "▶ Scenario A — no routines dir: skip, exit 0"
OUT_A="$(env -u SF_PLAN_TIER CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMP/empty-wiki" bash "$CHECK_SCRIPT" 2>&1)"; RC_A=$?
[[ $RC_A -eq 0 ]] && pass "exits 0" || fail "expected 0 got $RC_A"
echo "$OUT_A" | grep -q '^routines|skip|' && pass "emits routines|skip" || fail "expected routines|skip"

echo "▶ Scenario B — a 'full' tier routine is flagged warn"
mk_routine "scraper" "cron" "full"
mk_routine "digest" "cron" "trusted"
OUT_B="$(SF_PLAN_TIER=max CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMP/wiki" bash "$CHECK_SCRIPT" 2>&1)"; RC_B=$?
[[ $RC_B -eq 0 ]] && pass "exits 0" || fail "expected 0 got $RC_B"
echo "$OUT_B" | grep -q '^routine-net:scraper|warn|network tier = full|' \
  && pass "flags full-tier routine" || fail "expected routine-net:scraper|warn"

echo "▶ Scenario C — quota line reflects cron count vs Max cap"
echo "$OUT_B" | grep -q '^routine-quota|ok|2/15 scheduled (max cap)|' \
  && pass "quota 2/15 for max" || fail "expected routine-quota|ok|2/15 scheduled (max cap)"

echo "▶ Scenario D — pro cap is 5; 8 cron routines => warn"
for i in 1 2 3 4 5 6; do mk_routine "r$i" "cron" "trusted"; done
OUT_D="$(SF_PLAN_TIER=pro CLAUDE_PLUGIN_OPTION_WIKIROOT="$TMP/wiki" bash "$CHECK_SCRIPT" 2>&1)"
echo "$OUT_D" | grep -q '^routine-quota|warn|' && pass "warns over pro cap" || fail "expected routine-quota|warn"

echo "═══════════════════════════════════════════════"
if (( FAIL_COUNT == 0 )); then
  printf '\033[32m  check-routines tests: %d PASS\033[0m\n' "$PASS_COUNT"; exit 0
else
  printf '\033[31m  check-routines: %d FAIL / %d total\033[0m\n' "$FAIL_COUNT" "$((PASS_COUNT+FAIL_COUNT))"; exit 1
fi
```

- [ ] **Step 2: Run to verify FAIL**

Run: `( cd skills/doctor && bash scripts/tests/test_check_routines.sh )`
Expected: FAIL (`check-routines.sh` does not exist yet → scenarios error).

- [ ] **Step 3: Write check-routines.sh**

Create `skills/doctor/scripts/check-routines.sh` (mirrors `check-schemas.sh`'s dependency-free Python heredoc frontmatter parser; emits the 4-field `KEY|STATUS|VALUE|HINT` format like `check-backup.sh`):

```bash
#!/usr/bin/env bash
# check-routines.sh — sf-doctor ROUTINES section (ADR-034)
#
# Output: `KEY|STATUS|VALUE|HINT`
# Keys: routines (skip), routine-net / routine-net:<name> (network-tier audit),
#       routine-quota (defined cron routines vs plan cap).
#
# Side effects: NONE. Reads wiki/routines/*.md frontmatter.
# Plan tier: SF_PLAN_TIER (pro|max|team|enterprise); defaults to max.
set -uo pipefail
emit() { printf '%s|%s|%s|%s\n' "$1" "$2" "${3:-}" "${4:-}"; }

WIKI_ROOT="${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}"
ROUTINES_DIR="$WIKI_ROOT/routines"
PLAN_TIER="$(printf '%s' "${SF_PLAN_TIER:-max}" | tr '[:upper:]' '[:lower:]')"

if [[ ! -d "$ROUTINES_DIR" ]]; then
  emit "routines" "skip" "no routines defined" "→ /ren:routine-init scaffolds a cadence routine (ADR-034)"
  exit 0
fi

exec python3 - "$ROUTINES_DIR" "$PLAN_TIER" <<'PYEOF'
import os, sys, re, glob

routines_dir, plan_tier = sys.argv[1], sys.argv[2]
CAPS = {"pro": 5, "max": 15, "team": 25, "enterprise": 25}
cap = CAPS.get(plan_tier, 15)

frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def parse_fm(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(8192)  # frontmatter is at the top; 8K is plenty
    except OSError:
        return {}
    m = frontmatter_re.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm

def emit(key, status, value="", hint=""):
    print(f"{key}|{status}|{value}|{hint}")

specs = []
for fp in sorted(glob.glob(os.path.join(routines_dir, "*.md"))):
    fm = parse_fm(fp)
    if fm.get("type") != "routine-spec":
        continue
    specs.append((os.path.splitext(os.path.basename(fp))[0], fm))

if not specs:
    emit("routines", "skip", "no routine-spec pages", "→ /ren:routine-init scaffolds one")
    sys.exit(0)

# Network-tier audit — flag any routine on the 'full' (unrestricted egress) tier.
full_tier = [name for name, fm in specs if fm.get("network_tier", "trusted") == "full"]
if full_tier:
    for name in full_tier:
        emit(f"routine-net:{name}", "warn", "network tier = full",
             "→ 'full' = unrestricted egress = a prompt-injection exfiltration surface. "
             "Prefer 'trusted' (Anthropic allowlist) unless this routine genuinely needs arbitrary domains.")
else:
    emit("routine-net", "ok", f"{len(specs)} routine(s), none on 'full' tier", "")

# Quota / headroom audit — counts DEFINED cron routines (not live runs) vs the plan cap.
scheduled = [name for name, fm in specs if fm.get("trigger_type", "") == "cron"]
used = len(scheduled)
if used >= cap:
    emit("routine-quota", "warn", f"{used}/{cap} scheduled ({plan_tier} cap)",
         f"→ at/over the {plan_tier} cap of {cap} scheduled routines/day; consolidate or upgrade. "
         "(Counts DEFINED cron routines, not live runs consumed today.)")
else:
    emit("routine-quota", "ok", f"{used}/{cap} scheduled ({plan_tier} cap)", "")
PYEOF
```

- [ ] **Step 4: Make it executable + run the harness to verify PASS**

Run:
```bash
chmod +x skills/doctor/scripts/check-routines.sh
( cd skills/doctor && bash scripts/tests/test_check_routines.sh )
```
Expected: all four scenarios PASS.

- [ ] **Step 5: Wire the section into SKILL.md (8 edits)**

In `skills/doctor/SKILL.md`:

**(a)** Line 3 description — change "Composes a four-section report (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE) plus a BACKUP section" to:
```
Composes a five-section report (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, ROUTINES) plus a BACKUP section
```

**(b)** `contract.required_outputs` first item — change "five sections (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, BACKUP)" to:
```
    - "A human-readable report with six sections (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, ROUTINES, BACKUP) plus a final summary line"
```

**(c)** `contract.permissions.execute` — add after the `check-backup.sh` line:
```
      - "scripts/check-routines.sh"
```

**(d)** `contract.completion_conditions` first item — change "All five status sections rendered" to "All six status sections rendered".

**(e)** `--section <name>` flag row (line ~65) — change the value list to include `routines`:
```
| `--section <name>` | Run only one section: `env` / `plugins` / `schemas` / `update` / `routines` / `backup` |
```

**(f)** "How it works" table — add this row after the `check-backup.sh` row:
```
| `scripts/check-routines.sh` | ROUTINES | None — reads `wiki/routines/*.md` frontmatter (network tier + cron count vs plan cap) |
```

**(g)** Output-format example — add this block after the `▶ BACKUP` block (before "All systems go."):
```
▶ ROUTINES  (per ADR-034)
  Network tiers:   ✅ 2 routine(s), none on 'full' tier
  Quota headroom:  2/15 scheduled (max cap)
```

**(h)** "## Eval" section — append a bullet:
```
- ROUTINES flags any routine on the `full` network tier and surfaces defined-cron-routines vs the plan cap; skips cleanly when no `wiki/routines/` exists
```

- [ ] **Step 6: Verify conformance + the other doctor harnesses still pass**

Run:
```bash
python3 tests/integration/schema-conformance/conformance.py
( cd skills/doctor && for t in scripts/tests/test_*.sh; do bash "$t" >/dev/null && echo "ok $t" || echo "FAIL $t"; done )
```
Expected: conformance exit 0; every doctor harness prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add skills/doctor/scripts/check-routines.sh skills/doctor/scripts/tests/test_check_routines.sh skills/doctor/SKILL.md
git commit -m "feat(doctor): ROUTINES section — network-tier + quota audits (C4)

Adds check-routines.sh: flags routine-spec pages on the 'full' network tier
(exfiltration surface) and surfaces defined cron routines vs the plan cap
(SF_PLAN_TIER, default Max=15). Skips cleanly when no wiki/routines/ exists.
Wires the section into SKILL.md (now six sections + BACKUP)."
```

---

## Task 8: Wake-up hook surfaces live automations

**Files:**
- Modify: `hooks/wake-up/wakeup/__init__.py` (add `import re`, two constants, `read_live_routines`, a compose block, `__all__`)
- Test: `hooks/wake-up/wakeup/tests/test_routines.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `hooks/wake-up/wakeup/tests/test_routines.py`:

```python
"""Tests for the wake-up hook's live-automations (routine-spec) surfacing — C4 / ADR-034."""
from __future__ import annotations

from pathlib import Path

from ..__init__ import compose_wake_up_context, read_live_routines


def _write_routine(routines_dir: Path, slug: str, *, trigger="cron", tier="trusted",
                   repo="https://github.com/u/r") -> None:
    routines_dir.mkdir(parents=True, exist_ok=True)
    (routines_dir / f"{slug}.md").write_text(
        "---\n"
        "type: routine-spec\n"
        "schema_version: 1\n"
        'framework_version: "1.0.0"\n'
        f'name: "{slug}"\n'
        f'trigger_type: "{trigger}"\n'
        f'linked_repo: "{repo}"\n'
        f'network_tier: "{tier}"\n'
        "---\n\n"
        f"# {slug}\n",
        encoding="utf-8",
    )


def test_read_live_routines_empty(tmp_path):
    assert read_live_routines(tmp_path) == ""


def test_read_live_routines_lists_and_flags_full(tmp_path):
    _write_routine(tmp_path / "routines", "daily-digest", tier="trusted")
    _write_routine(tmp_path / "routines", "scraper", tier="full")
    out = read_live_routines(tmp_path)
    assert "daily-digest" in out and "scraper" in out
    assert out.count("⚠️ full-network") == 1   # only the full-tier one flagged


def test_read_live_routines_ignores_non_routine_md(tmp_path):
    rd = tmp_path / "routines"
    rd.mkdir(parents=True)
    (rd / "README.md").write_text("# not a routine\n", encoding="utf-8")
    assert read_live_routines(tmp_path) == ""


def test_compose_includes_live_automations(tmp_path):
    (tmp_path / "index.md").write_text("# Master index\n", encoding="utf-8")
    _write_routine(tmp_path / "routines", "daily-digest")
    out = compose_wake_up_context(cwd=tmp_path, wiki_root=tmp_path)
    assert "Live automations" in out
    assert "daily-digest" in out


def test_compose_omits_when_no_routines(tmp_path):
    (tmp_path / "index.md").write_text("# Master index\n", encoding="utf-8")
    out = compose_wake_up_context(cwd=tmp_path, wiki_root=tmp_path)
    assert "Live automations" not in out
```

- [ ] **Step 2: Run to verify FAIL**

Run: `( cd hooks/wake-up && python3 -m pytest wakeup/tests/test_routines.py -q )`
Expected: FAIL (`ImportError: cannot import name 'read_live_routines'`).

- [ ] **Step 3: Implement in the wakeup lib**

In `hooks/wake-up/wakeup/__init__.py`:

Add `import re` to the imports (after `import os`):
```python
import logging
import os
import re
from pathlib import Path
from typing import Final
```

Add two constants after `PROJECT_LOG_FILENAME`:
```python
MASTER_ROUTINES_DIRNAME: Final[str] = "routines"
```
and after `PROJECT_LOG_BUDGET`:
```python
ROUTINE_SPEC_BUDGET: Final[int] = 400
```

Add the reader + a tiny dependency-free frontmatter field parser after `read_log_tail`:
```python
_ROUTINE_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_routine_fields(content: str) -> dict[str, str]:
    """Tiny dependency-free frontmatter field reader (no PyYAML at hook runtime)."""
    m = _ROUTINE_FM_RE.match(content)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip().strip('"').strip("'")
    return fields


def read_live_routines(wiki_root: Path) -> str:
    """
    Scan wiki/routines/ for routine-spec pages and format a one-line-per-routine
    digest for the wake-up payload (ADR-034: surface which automations are live).
    Returns "" if no routines/ dir or no routine-spec pages.
    """
    routines_dir = wiki_root / MASTER_ROUTINES_DIRNAME
    if not routines_dir.is_dir():
        return ""
    rows: list[str] = []
    for path in sorted(routines_dir.glob("*.md")):
        fm = _parse_routine_fields(_read_text_safe(path))
        if fm.get("type") != "routine-spec":
            continue
        name = fm.get("name", path.stem)
        trigger = fm.get("trigger_type", "?")
        repo = fm.get("linked_repo", "?")
        flag = " ⚠️ full-network" if fm.get("network_tier", "trusted") == "full" else ""
        rows.append(f"- **{name}** · {trigger} · {repo}{flag}")
    return "\n".join(rows)
```

In `compose_wake_up_context`, add this block immediately after the "2. Master log tail" block and before "3. Project context":
```python
    # 2b. Live automations (routine-specs) — ADR-034 (master-level, always shown)
    live_routines = read_live_routines(wiki_root)
    if live_routines:
        sections.append("### Live automations (routine-specs)")
        sections.append(truncate_text_to_tokens(live_routines, ROUTINE_SPEC_BUDGET))
```

Extend `__all__` with the new public names:
```python
    "MASTER_ROUTINES_DIRNAME",
    "ROUTINE_SPEC_BUDGET",
    "read_log_tail",
    "read_live_routines",
    "compose_wake_up_context",
]
```
(Insert `MASTER_ROUTINES_DIRNAME`, `ROUTINE_SPEC_BUDGET`, and `read_live_routines` into the existing `__all__` list — keep the others.)

- [ ] **Step 4: Run the full wake-up suite to verify PASS**

Run: `( cd hooks/wake-up && python3 -m pytest -q )`
Expected: existing `test_compose.py` + `test_entry.py` + the new `test_routines.py` all PASS.

- [ ] **Step 5: Commit**

```bash
git add hooks/wake-up/wakeup/__init__.py hooks/wake-up/wakeup/tests/test_routines.py
git commit -m "feat(wake-up): surface live automations (routine-specs) (C4)

The SessionStart payload now lists routine-spec pages from wiki/routines/ as a
master-level 'Live automations' section (name · trigger · repo, full-network
flagged), within a 400-token budget. Dependency-free frontmatter read to keep
hook latency low. ADR-034."
```

---

## Task 9: Wiki write-back (the truth layer records the capability)

**Files:**
- Modify: `wiki/log.md` (append a milestone — chronological invariant)
- Modify: `wiki/index.md` (note the cadence skills + routine-spec page-type)
- Modify: `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md` (tick C4)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Append the master log milestone**

Read `wiki/log.md`. Append a new entry at the **bottom** (newest last — never rewrite earlier days). Use the existing entry format (`## [YYYY-MM-DD HH:MM] type | description`). Match the exact header style already in the file; example body:

```markdown
## [2026-06-11 21:00] build | C4 cadence-as-glue shipped

Cadence glue layer (ADR-034) landed: `routine-spec` page-type registered
(schemas.json + conformance); `/ren:routine-init` scaffolds a lean cloud-routine
repo + writes the routine-spec page; `/ren:cadence` routes to the right primitive
tier; `/ren:recall --routine` reads a routine's state.md/run-log.md; `/ren:doctor`
gained ROUTINES audits (network-tier + quota headroom); the wake-up hook surfaces
live automations. No daemon (ADR-003) — pull-model write-back (ADR-026).
```
(Adjust the timestamp to the actual run time; keep it ≥ the previous entry's.)

- [ ] **Step 2: Update the master index**

Read `wiki/index.md`. Add the two new skills + the page-type to the appropriate sections (mirror how existing skills/page-types are listed). Minimally: list `/ren:routine-init` and `/ren:cadence` wherever the skill inventory lives, and note `routine-spec` wherever page-types are catalogued. Keep summaries to one line each.

- [ ] **Step 3: Tick C4 in the roadmap**

In `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`:
- In "## The decomposition (the slices)" table, change the **C4** row Status cell from `Not started` to `✅ **DONE 2026-06-11** — routine-spec page-type + /ren:routine-init + /ren:cadence + recall/doctor/wake-up extensions; plan docs/superpowers/plans/2026-06-11-c4-cadence-as-glue.md`.
- Add a "## Status log" entry near the top documenting the C4 ship (one paragraph, mirroring the A1 entry's style).

- [ ] **Step 4: Update CHANGELOG.md**

Read `CHANGELOG.md`. Under the current unreleased/working section, add bullets:
```markdown
### Added
- **Cadence-as-glue (C4, ADR-034):** `routine-spec` wiki page-type; `/ren:routine-init` (scaffolds a lean Cloud-Routine repo + writes the routine-spec page); `/ren:cadence` (decision-matrix router over /loop · Cron · /goal · Cloud Routines); `/ren:recall --routine` (reads a routine's state.md/run-log.md); `/ren:doctor` ROUTINES audits (network-tier + quota headroom); wake-up hook "Live automations" section.
```
(Match the CHANGELOG's existing heading/format conventions.)

- [ ] **Step 5: Commit**

```bash
git add wiki/log.md wiki/index.md docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md CHANGELOG.md
git commit -m "docs(c4): record cadence-as-glue ship — log, index, roadmap, changelog

Truth-layer write-back for C4: master log milestone, index entries for the two
new skills + routine-spec page-type, roadmap C4 status → DONE, CHANGELOG."
```

---

## Task 10: Full verification gate

**Files:** none (verification only).

- [ ] **Step 1: Run every per-module test suite**

Run (each must be green):
```bash
( cd skills/routine-init && python3 -m pytest lib/tests -q -p no:cacheprovider )
( cd skills/recall && python3 -m pytest lib/tests -q -p no:cacheprovider )
( cd hooks/wake-up && python3 -m pytest -q )
python3 -m pytest tests/integration/schema-conformance/ -q
```
Expected: all PASS (conformance: prior 10 + 1 xfail + 2 new routine-spec tests).

- [ ] **Step 2: Run every doctor bash harness**

Run:
```bash
( cd skills/doctor && for t in scripts/tests/test_*.sh; do bash "$t" >/dev/null && echo "ok $t" || echo "FAIL $t"; done )
```
Expected: every harness prints `ok` (including `test_check_routines.sh`).

- [ ] **Step 3: Confirm the prior green baseline is intact**

Run the full per-module sweep for the untouched skills (regression guard):
```bash
for m in skills/backup skills/improve-skill skills/install skills/note skills/wrap; do
  ( cd "$m" && python3 -m pytest -q -p no:cacheprovider ) || echo "FAIL: $m"
done
```
Expected: no `FAIL:` lines (baseline: backup 70, improve-skill 144, install 33, note 18, wrap 90).

- [ ] **Step 4: Validate the plugin (strict)**

Run: `claude plugin validate ./ --strict`
Expected: ✔ (the two new skills' SKILL.md validate; namespace `ren`).

- [ ] **Step 5: End-to-end smoke (routine-init → wake-up → doctor)**

Manually verify the loop closes against a throwaway temp wiki:
```bash
python3 - <<'PY'
import tempfile, pathlib, sys
sys.path.insert(0, "skills/routine-init")
from lib import routine_init  # noqa: E402
tmp = pathlib.Path(tempfile.mkdtemp())
r = routine_init("smoke-digest", dest_dir=tmp/"repos", wiki_root=tmp/"wiki",
                 trigger_type="cron", linked_repo="https://github.com/u/smoke-digest",
                 skill="insights", network_tier="full", schedule="daily 8am",
                 expected_output="smoke", failure_email="me@example.com",
                 today="2026-06-11", templates_dir=pathlib.Path("skills/routine-init/templates"))
assert r.success, r.error
print("repo + spec written:", r.repo_dir, r.spec_page)
print("WIKI_ROOT for doctor smoke:", tmp/"wiki")
PY
```
Then point doctor + wake-up at that wiki and confirm the routine surfaces and the `full` tier is flagged:
```bash
# (use the printed WIKI_ROOT)
SF_PLAN_TIER=max CLAUDE_PLUGIN_OPTION_WIKIROOT=<printed-wiki> bash skills/doctor/scripts/check-routines.sh
python3 - <<'PY'
import sys, pathlib
sys.path.insert(0, "hooks/wake-up")
from wakeup import read_live_routines  # noqa: E402
print(read_live_routines(pathlib.Path("<printed-wiki>")))
PY
```
Expected: `check-routines.sh` emits `routine-net:smoke-digest|warn|network tier = full|…` and `routine-quota|ok|1/15 scheduled (max cap)|`; `read_live_routines` prints `- **smoke-digest** · cron · … ⚠️ full-network`. Clean up the temp dir afterward.

- [ ] **Step 6: Final state check**

Run: `git status --porcelain` (expect clean after all task commits) and `git log --oneline -10` (expect the C4 commit chain).

---

## Self-Review (run after writing; fix inline)

**Spec coverage (ADR-034 §3 glue surface):**
- `ren-routine-init` lean-repo scaffold → Tasks 2–4. ✅
- Skill-as-routine-prompt convention → baked into `ROUTINE_PROMPT.md.tmpl` (Task 2). ✅
- Required failure-notification footer → `ROUTINE_PROMPT.md.tmpl` + cadence conventions (Tasks 2, 5). ✅
- Self-terminating loops + auto-compact companion cron → `ROUTINE_PROMPT.md.tmpl` (single-pass) + `cadence/references/conventions.md` (Tasks 2, 5). ✅
- `routine-spec` page-type + schemas.json registration + template → Task 1. ✅
- `/ren:recall` reads state.md/run-log.md → Task 6. ✅
- `/ren:doctor` network-tier + quota audits → Task 7. ✅
- Wake-up surfaces live automations → Task 8. ✅
- Decision matrix (`/loop`/Cron/`/goal` "wrappers") → `/ren:cadence` (Task 5). ✅
- Git pull-model write-back (ADR-026) → documented in `ROUTINE_PROMPT.md.tmpl` step 3 (Task 2). ✅
- Write-back to the truth layer → Task 9. ✅

**Placeholder scan:** every code/template/script step contains complete content; no "TBD"/"add error handling"/"similar to Task N". Schema/SKILL.md edits that depend on unseen surrounding text (schemas.json tail, recall SKILL.md body) are framed as "Read first, then apply" with the exact insert content. ✅

**Type consistency:** `RoutineInitResult`/`routine_init` signature is identical across Tasks 2–4; `RoutineState`/`read_routine_state` consistent in Task 6; `read_live_routines`/`ROUTINE_SPEC_BUDGET`/`MASTER_ROUTINES_DIRNAME` consistent in Task 8; the routine-spec frontmatter keys (`name`, `trigger_type`, `linked_repo`, `network_tier`) match across the template (Task 1), `REQUIRED_FIELDS_BY_TYPE` (Task 1), the doctor parser (Task 7), and the wake-up parser (Task 8). The quota emit string `"{used}/{cap} scheduled ({plan_tier} cap)"` matches the harness assertion `2/15 scheduled (max cap)`. ✅

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-11-c4-cadence-as-glue.md`.

**Recommended:** execute in an isolated worktree (superpowers:using-git-worktrees) on `feat/c4-cadence-as-glue`, subagent-driven (fresh subagent per task + two-stage review between tasks). Tasks 1→9 are strictly ordered (each depends on the prior); Task 10 is the gate.
