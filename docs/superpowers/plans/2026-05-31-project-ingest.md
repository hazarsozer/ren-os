# sf-ingest-project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/sf:ingest-project` — a user-invoked skill that turns an existing project directory into a first-class framework citizen by reading it (read-only), drafting a populated ADR-014 sub-wiki from what's actually there, showing one preview, and on approval writing the sub-wiki + registering it in the master wiki.

**Architecture:** A 4-stage pipeline. (1) SCAN: a read-only Python scanner (`scripts/scan.py`) emits a structured facts JSON on stdout — it touches nothing in the project. (2) INTERPRET: the LLM consumes the facts and drafts all 7 ADR-014 pages in context, following `references/page-mapping.md`; thin evidence → honest placeholder, never invented. (3) PREVIEW: the skill prints an additive manifest (which pages would be written, the 2 master-wiki registration lines, a content sample) and asks for ONE approval. (4) WRITE: following the existing `template-loader.md` additive/no-overwrite discipline, the skill writes only missing pages and appends the 2 master-wiki registration lines + a project log init entry.

**Tech Stack:** Python 3.12 stdlib only (no third-party deps — matches `sf-insights/collect.py`), pytest for the scanner unit tests, markdown SKILL.md + reference docs (matches every existing `sf-*` skill), `eval/eval.json` binary assertions (matches `sf-bootstrap-project` + `sf-insights`).

**Branch:** `feat/project-ingest` (already created; spec committed at `docs/superpowers/specs/2026-05-31-project-ingest-design.md`).

**Spec:** `docs/superpowers/specs/2026-05-31-project-ingest-design.md` — read it first.

> **Implement in a separate git worktree** (per `superpowers:using-git-worktrees`): create one off `feat/project-ingest` so the build is isolated from the main checkout. The skill writes only under `skills/sf-ingest-project/**`, `commands/` (none), and the wiki — never the user's project.

---

## ⚠️ Review Corrections (authoritative — apply these; they win over conflicting task text below)

A multi-agent review (2026-05-31) found issues in the task bodies below. **Four were fixed inline** in their code blocks (Task 2 `_git_tracked_files` zero-commit `None` fallback; Task 3 `detect_stack` dedup; Task 5 `collect_git_facts` zero-commit guard; Task 6 `scan()` non-dir complete dict). The rest are corrections to apply as you reach each task. Where this section conflicts with a task body, **this section is authoritative.**

### C1 — `framework_version` comes from `scan.py`, NOT a "markdown import" (HIGH)
The instruction to "import `lib/sf_paths.py` from the SKILL.md procedure" is ambiguous (a SKILL.md is markdown, not a module) and no sibling does it. Resolve mechanically: **`scan.py` emits `framework_version` into the facts JSON; the LLM reads it from there.**
- Add to `scan.py` (top-level imports include `import sys`) and call it in the `scan()` assembly + the non-dir guard:
```python
def _framework_version() -> str:
    """Best-effort framework version for page frontmatter. Imports lib.sf_paths
    from the plugin root; falls back to '1.0.0' in a bare checkout. Read-only."""
    try:
        plugin_root = Path(__file__).resolve().parents[3]  # scripts→skill→skills→<plugin>
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        from lib.sf_paths import framework_version
        return framework_version()
    except Exception:
        return "1.0.0"
```
- In `scan()` assembly add `facts["framework_version"] = _framework_version()`.
- Add `"framework_version": "1.0.0"` to the facts-JSON contract block (top of plan) and to `extraction-spec.md` (Task 8).
- Task 9 `page-mapping.md`: bind frontmatter `framework_version` ← `facts.framework_version` (delete the "import sf_paths" phrasing). (This is the same root cause as the shipped `sf-wrap/lib/diff_plan.py:150` hardcoded-version bug — fixing it here keeps the new skill correct.)

### C2 — page frontmatter must match the templates EXACTLY (HIGH, Task 9)
Replace Task 9's "Frontmatter (every page)" list with this per-page table (mirrors `skills/sf-bootstrap-project/templates/*.tmpl`):

| Page | `type:` | extra |
|---|---|---|
| PROJECT.md | `project-main` | `status: ingested` |
| REQUIREMENTS.md | `project-requirements` | — |
| ROADMAP.md | `project-roadmap` | — |
| STATE.md | `project-state` | — |
| CONTEXT.md | `project-context` | — |
| index.md | `project-index` | — |
| log.md | `project-log-entry` | — |

Every page also binds: `title: "<project_title> — <Page>"`, `schema_version: 1`, `framework_version` (from facts), `project_name` (kebab), `created`/`updated` (today); H1 = `# <project_title> — <Page>`. PROJECT.md uses `status: ingested` (records provenance vs bootstrap's `bootstrapped`).

### C3 — real `index.md` headers (MEDIUM, Task 9)
`taxonomy-templates.md` mis-states them. The REAL `index.md` headers (from `templates/index.md.tmpl`) are **Core taxonomy / Research / Decisions / Patterns / See also** — there is NO "States" section. Enumerate these in `page-mapping.md`; do not trust the sibling doc.

### C4 — eval assertions idempotent-safe + write accounting (HIGH, Task 11)
The two master-registration assertions say "exactly one NEW line" — false on re-run, contradicts the additive/idempotent contract. Replace with:
- "After the run, `wiki/index.md` contains exactly ONE bullet under '## Projects' linking to `projects/demo-api/index.md` (re-running adds no second — idempotent)."
- "After the run, `wiki/log.md` contains exactly ONE `## [2026-05-31] init | Project sub-wiki ingested for demo-api` entry (idempotent)."
Add a write-accounting assertion mirroring bootstrap: "Files written = 7 pages + 3 `.gitkeep` = 10; master `index.md`/`log.md` are edits, not new files." Set SKILL.md `budgets.files_written: 10` (standard/light); note `--depth deep` may add ≤N `decisions/`/`research/` summary files, out of the v1 binary-eval scope.

### C5 — ADR-032 cites the LIVE principle, ADR-031 (MEDIUM, Task 12)
ADR-017 is `status: superseded` (by ADR-031). Anchor the "wiki ships no framework content / starts empty" reconciliation to **ADR-031** (live home), mention ADR-017 only as historical origin (keep it in `relates-to`). Attribute "no silent writes / show-diffs-require-approval" to ADR-027 (+ ADR-017 backwards-compat clause) precisely.

### C6 — add zero-commit-repo tests (CRITICAL coverage; Tasks 2 & 5)
Every existing git fixture commits first, so the two inline CRITICAL fixes are untested. Add (TDD: add test → run → the inline fix makes it pass):
```python
def test_zero_commit_repo_falls_back_to_walk(tmp_path):
    (tmp_path / "a.py").write_text("print(1)\n")
    _git_init(tmp_path)                 # init, do NOT commit
    rels = {str(p.relative_to(tmp_path)) for p in scan.enumerate_files(tmp_path)}
    assert "a.py" in rels              # uncommitted file still found via walk fallback

def test_git_facts_zero_commit_repo(tmp_path):
    (tmp_path / "a.py").write_text("1\n")
    _git_init(tmp_path)                 # no commit
    g = scan.collect_git_facts(tmp_path)
    assert g["is_repo"] is True
    assert g["commit_count"] == 0
    assert g["no_commits"] is True
    assert g["dirty"] is False         # untracked-only is NOT "dirty" here
```

### C7 — smaller fixes (MEDIUM/LOW)
- **Task 5 tag dates:** lightweight tags report tag-*creation* date, not commit date. Use annotated tags in the fixture (`git tag -a v1.0 -m v1.0`) for determinism, or document `tags[].date` as best-effort in `extraction-spec.md`; don't assert exact tag dates.
- **Task 7 `_snapshot`:** exclude `.git/` to avoid cross-git-version flakiness — iterate `p for p in root.rglob("*") if ".git" not in p.parts`. (Read-only invariant covers the project's own files; git internals are git's.)
- **Task 6 Step 2 wording:** the "expected FAIL reason" holds only for `test_recommend_subagents_for_large_repo` (KeyError on `size_signals`); `test_name_falls_back_*` fails with AssertionError on `looks_like_project`. Reword to allow either.
- **Imports (Tasks 2/5/6):** put every new import (`fnmatch`, `subprocess`, `sys`, `from collections import Counter`, `import re`) in `scan.py`'s top-level import block, not mid-file (PEP 8 E402).
- **Task 9 `_TBD`:** thin-evidence sections retain the template's EXISTING markers verbatim (bare `- _TBD_` bullets + italic `_..._` prose). No-invention = "no concrete claim absent from facts JSON," not a literal grep. Keep the eval's `'_TBD'` substring check.
- **SKILL.md contract paths:** note that the `~/.startup-framework/...` paths in the `contract:` block are illustrative; the real path is `wiki_path()` (mirrors bootstrap).
- **Log wording:** use the eval-pinned `## [<today>] init | Project sub-wiki ingested for <name>` consistently in `page-mapping.md` (fix the one example reading "ingested from existing project").

---

## Conventions for the implementer (read once)

- **Per-module test command** (root pytest collides on duplicate `lib.tests.*` — pre-existing, do NOT "fix"):
  ```bash
  ( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/ -q )
  ```
- **Commit-message hook gotcha:** a `block-no-verify` PreToolUse hook blocks `git commit --no-verify` AND false-positives on any command containing the literal tokens `pre-commit`, `commit-msg`, or `--no-verify`. Never put those tokens in a commit message or any bash command in this plan.
- **Attribution:** commit messages follow `<type>: <description>` (conventional commits). Do not add co-author trailers (disabled globally).
- **Read-only on the project is load-bearing.** The scanner opens project files read-only and writes nothing into the project dir. The skill only ever writes under `wiki/projects/<name>/` and appends 2 lines to master wiki files. This invariant has a dedicated test (Task 7) and eval assertion (Task 11) — do not weaken it.
- **No-invention is load-bearing.** When evidence is thin, pages get a literal placeholder marker (`_TBD — <reason>; fill in._`), never fabricated content. The framework's whole identity is honesty (cf. the F2b honest `sf-improve`).
- **Do NOT refactor `sf-bootstrap-project` or `sf-install`.** Ingest reuses the template-loader's *documented discipline* (copy_if_missing / never-overwrite / additive-diff) as a procedure; it does not modify those skills or fork their logic.
- **Path/handle resolution:** import from `lib/sf_paths.py` (`wiki_path()`, `handle()`, `framework_version()`). Never hard-code `~/.startup-framework`.

---

## File structure

**Create:**
- `skills/sf-ingest-project/SKILL.md` — orchestration procedure, contract block, flags, edge cases, anti-patterns.
- `skills/sf-ingest-project/scripts/scan.py` — read-only Python scanner → facts JSON on stdout.
- `skills/sf-ingest-project/scripts/tests/__init__.py` — empty package marker.
- `skills/sf-ingest-project/scripts/tests/test_scan.py` — scanner unit tests (the mechanical-core safety net).
- `skills/sf-ingest-project/references/extraction-spec.md` — the scanner's detection-rules spec (manifest→stack table, skip-dirs, never-read globs, caps).
- `skills/sf-ingest-project/references/page-mapping.md` — facts→ADR-014 page mapping + drafting rules (no-invention, timeline clustering, summarize+backlink).
- `skills/sf-ingest-project/eval/eval.json` — binary-assertion suite.
- `skills/sf-ingest-project/eval/fixtures/ingest-python-project.yaml` — simulated env: existing wiki + a python project to ingest.
- `skills/sf-ingest-project/eval/fixtures/ingest-name-collision.yaml` — simulated env: sub-wiki already exists.
- `wiki/decisions/032-project-ingest.md` — the new ADR.

**Modify:**
- `README.md` — add `/sf:ingest-project` to the command list.
- `CHANGELOG.md` — add an `[Unreleased]` entry.
- `wiki/index.md` — note the new skill/command.
- `wiki/log.md` — append a decision/build entry (chronological invariant; append-only).

**Do NOT modify:** `.claude-plugin/plugin.json` (skills are auto-discovered from `skills/`; the plugin declares no `commands` key), `.claude-plugin/marketplace.json` (no per-skill listing), `scripts/publish.sh` (uses `git ls-files` — new tracked files ship automatically).

### Command registration — there is NO command file (verified)

The framework ships **zero** `commands/` files. There is no `commands/` directory on disk or in git, and `plugin.json` has no `commands` key. All 12 existing `/sf:*` commands (`/sf:wrap`, `/sf:insights`, `/sf:bootstrap-project`, …) are backed **solely** by `skills/<name>/SKILL.md` — Claude Code surfaces the skill and the `/sf:` invocation maps to it (stage-7 walkthrough: "Each maps to a skill the friend already has installed"). So `/sf:ingest-project` is registered by **the skill's `name: sf-ingest-project` frontmatter alone** (Task 10). Do **NOT** add a `commands/` file — it would be a pattern no sibling uses and risk a double registration. The skill is the command.

---

## The facts JSON contract (target shape `scan.py` emits)

This is the stable scanner↔LLM interface. Every scanner task builds part of it. Final shape:

```jsonc
{
  "schema_version": 1,
  "scanned_path": "/abs/path",
  "looks_like_project": true,
  "name_candidates": { "dir": "myapp", "manifest": "my-app", "chosen": "my-app" },
  "stack": {
    "languages": [{"name": "Python", "evidence": "pyproject.toml", "confidence": "high"}],
    "package_managers": ["uv"],
    "frameworks": ["fastapi"],
    "manifests": ["pyproject.toml"]
  },
  "tree_digest": { "depth_cap": 4, "entry_count": 312, "truncated": false,
                   "top_dirs": ["src", "tests", "docs"], "notable_files": ["README.md", "pyproject.toml"] },
  "entry_points": ["src/main.py"],
  "doc_inventory": [{"path": "README.md", "kind": "readme", "bytes": 4210},
                    {"path": "docs/adr/0001.md", "kind": "adr", "bytes": 900}],
  "git": { "is_repo": true, "first_commit": "2025-01-03", "last_commit": "2026-05-20",
           "commit_count": 487, "branch": "main", "dirty": false,
           "tags": [{"name": "v1.0", "date": "2025-06-01"}],
           "timeline": [{"month": "2025-01", "count": 40}],
           "recent": [{"date": "2026-05-20", "subject": "fix: ..."}] },
  "size_signals": { "file_count": 312, "loc_estimate": 18400, "recommend_subagents": false },
  "warnings": ["no README.md found"]
}
```

When `git.is_repo` is `false`, the `git` object is `{"is_repo": false}` and all git-derived fields are omitted.

---

## Task 1: Scaffold skill dir + scanner skeleton

**Files:**
- Create: `skills/sf-ingest-project/scripts/scan.py`
- Create: `skills/sf-ingest-project/scripts/tests/__init__.py`
- Create: `skills/sf-ingest-project/scripts/tests/test_scan.py`

(No `commands/` file — see "Command registration" above. The skill's `name:` frontmatter, added in Task 10, is the sole command registration, matching all 12 sibling skills.)

- [ ] **Step 1: Create the empty test package marker**

Create `skills/sf-ingest-project/scripts/tests/__init__.py` with empty content (zero bytes is fine; write a single newline).

```python
```

- [ ] **Step 2: Write the failing test for the JSON envelope**

Create `skills/sf-ingest-project/scripts/tests/test_scan.py`:

```python
"""Hermetic tests for skills/sf-ingest-project/scripts/scan.py.

Every test builds a throwaway project tree under tmp_path, runs the read-only
scanner against it, and asserts on the parsed facts JSON. The load-bearing
invariant (Task 7): the scanner mutates NOTHING in the project.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scan  # noqa: E402


def run_scan(path: Path) -> dict:
    """Call scan.scan() and return the parsed facts dict."""
    return scan.scan(str(path))


def test_empty_dir_is_not_a_project(tmp_path):
    facts = run_scan(tmp_path)
    assert facts["schema_version"] == 1
    assert facts["scanned_path"] == str(tmp_path)
    assert facts["looks_like_project"] is False
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py::test_empty_dir_is_not_a_project -q )`
Expected: FAIL with `ModuleNotFoundError: No module named 'scan'`.

- [ ] **Step 4: Write the minimal scanner skeleton**

Create `skills/sf-ingest-project/scripts/scan.py`:

```python
#!/usr/bin/env python3
"""
scan.py — read-only project scanner for /sf:ingest-project.

Walks an existing project directory and emits a bounded, structured facts JSON
on stdout. The LLM (per references/page-mapping.md) turns those facts into a
populated ADR-014 sub-wiki; this script only collects facts.

INVARIANTS:
  - NO writes. Every file is opened read-only; nothing in the project is
    created, modified, or deleted.
  - NO network. Pure local filesystem + read-only git subprocess reads.
  - Bounded. Tree depth/entry caps, git summarized, code-skim capped, large
    and sensitive files never read.
  - Tolerant. A project with no git, no README, or no manifest still scans.

Usage:
    python3 scan.py [PATH] [--depth standard|light|deep]

Exit codes:
    0 — scan succeeded (a non-project path is still success: looks_like_project=false)
    2 — invocation error (bad args / path missing)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA_VERSION = 1


def scan(path: str, *, depth: str = "standard") -> dict:
    """Scan a project directory and return the facts dict.

    Never writes. Never raises on a readable-but-empty dir — returns
    looks_like_project=false instead.
    """
    root = Path(path).expanduser().resolve()
    facts: dict = {
        "schema_version": SCHEMA_VERSION,
        "scanned_path": str(root),
        "looks_like_project": False,
        "warnings": [],
    }
    if not root.is_dir():
        facts["warnings"].append(f"path is not a directory: {root}")
        return facts
    # Remaining sections are filled by later tasks.
    return facts


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scan.py",
        description="Read-only project scanner for /sf:ingest-project.",
    )
    p.add_argument("path", nargs="?", default=".", help="project directory (default: cwd)")
    p.add_argument(
        "--depth",
        choices=["light", "standard", "deep"],
        default="standard",
        help="extraction depth (default: standard)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    target = Path(args.path).expanduser()
    if not target.exists():
        sys.stderr.write(f"scan.py: path does not exist: {target}\n")
        return 2
    facts = scan(str(target), depth=args.depth)
    try:
        sys.stdout.write(json.dumps(facts, indent=2) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py::test_empty_dir_is_not_a_project -q )`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add skills/sf-ingest-project/scripts/scan.py skills/sf-ingest-project/scripts/tests/
git commit -m "feat(ingest): scaffold sf-ingest-project skill dir + scan.py skeleton"
```

---

## Task 2: File enumeration (git-aware, .gitignore-respecting, safety-filtered)

This is the read-safety core. In a git repo we enumerate **tracked files** via `git ls-files` (which respects `.gitignore` for free); otherwise we walk with an explicit skip-dir set. On top of either, we apply never-read globs + a size cap so secrets and large blobs are never opened.

**Files:**
- Modify: `skills/sf-ingest-project/scripts/scan.py`
- Modify: `skills/sf-ingest-project/scripts/tests/test_scan.py`

- [ ] **Step 1: Write the failing tests for enumeration + safety filters**

Add to `skills/sf-ingest-project/scripts/tests/test_scan.py`:

```python
def _git_init(root: Path) -> None:
    """Init a git repo with a deterministic identity (read-only-safe for tests)."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
    }
    subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=True)


def _git_commit_all(root: Path, message: str, when: str | None = None) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
    }
    if when:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, env=env, check=True)


def test_enumeration_skips_secrets_and_vendor_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')\n")
    (tmp_path / ".env").write_text("API_KEY=FAKE_SECRET_VALUE_123\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("x" * 100)
    files = scan.enumerate_files(tmp_path)
    rels = {str(p.relative_to(tmp_path)) for p in files}
    assert "src/main.py" in rels
    assert ".env" not in rels                       # never-read glob
    assert not any(r.startswith("node_modules/") for r in rels)  # skip-dir


def test_git_repo_enumeration_respects_gitignore(tmp_path):
    (tmp_path / "keep.py").write_text("print(1)\n")
    (tmp_path / "secret.log").write_text("nope\n")
    (tmp_path / ".gitignore").write_text("*.log\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "init")
    files = scan.enumerate_files(tmp_path)
    rels = {str(p.relative_to(tmp_path)) for p in files}
    assert "keep.py" in rels
    assert "secret.log" not in rels                 # gitignored → not tracked


def test_large_files_excluded(tmp_path):
    (tmp_path / "big.bin").write_bytes(b"0" * (scan.MAX_READ_BYTES + 1))
    (tmp_path / "small.py").write_text("ok\n")
    files = scan.enumerate_files(tmp_path)
    rels = {str(p.relative_to(tmp_path)) for p in files}
    assert "small.py" in rels
    assert "big.bin" not in rels
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k "enumeration or gitignore or large_files" )`
Expected: FAIL with `AttributeError: module 'scan' has no attribute 'enumerate_files'`.

- [ ] **Step 3: Implement enumeration + safety filters**

In `skills/sf-ingest-project/scripts/scan.py`, add these constants below `SCHEMA_VERSION` and the functions below `scan()`:

```python
import fnmatch
import subprocess

MAX_READ_BYTES = 256 * 1024  # never open a file larger than this

SKIP_DIRS = frozenset(
    {
        ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
        "target", "vendor", ".next", "coverage", ".idea", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".gradle", ".tox", "site-packages",
    }
)

# Never read these (secret/credential/binary-ish), even if tracked.
NEVER_READ_GLOBS = (
    ".env", ".env.*", "*.pem", "*.key", "id_rsa", "id_rsa.*", "id_ed25519",
    "credentials", "credentials.*", "*.sqlite", "*.sqlite3", "*.db",
    "*.p12", "*.pfx", "*.keystore", "*.jks",
)


def _is_never_read(name: str) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in NEVER_READ_GLOBS)


def _safe_size(path: Path) -> bool:
    try:
        return path.stat().st_size <= MAX_READ_BYTES
    except OSError:
        return False


def _git_tracked_files(root: Path) -> list[Path] | None:
    """Return tracked files via `git ls-files`, or None if not a git repo."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(root), capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", errors="replace")
    rels = [r for r in out.split("\0") if r]
    # A git repo with ZERO commits returns rc=0 + EMPTY stdout here. Return None
    # (→ enumerate_files falls back to _walk_files), NOT [] ("no files") — else a
    # freshly `git init`-ed, uncommitted project scans as empty. (Review: CRITICAL)
    if not rels:
        return None
    return [root / r for r in rels]


def _walk_files(root: Path) -> list[Path]:
    """Fallback enumeration for non-git dirs: os.walk with skip-dir pruning."""
    import os
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            found.append(Path(dirpath) / fn)
    return found


def enumerate_files(root: Path) -> list[Path]:
    """Enumerate readable project files, respecting .gitignore (in git repos),
    skip-dirs, never-read globs, and the size cap. Read-only.
    """
    candidates = _git_tracked_files(root)
    if candidates is None:
        candidates = _walk_files(root)
    out: list[Path] = []
    for p in candidates:
        # Any path component in SKIP_DIRS → drop (covers git submodule edge cases).
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        if _is_never_read(p.name):
            continue
        if not p.is_file():
            continue
        if not _safe_size(p):
            continue
        out.append(p)
    return out
```

Also add `import os` to the top-level imports if you prefer it there instead of the local import inside `_walk_files` (either is fine; keep it consistent with the file's style — the local import keeps the dependency obvious).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k "enumeration or gitignore or large_files" )`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add skills/sf-ingest-project/scripts/scan.py skills/sf-ingest-project/scripts/tests/test_scan.py
git commit -m "feat(ingest): git-aware read-only file enumeration with secret/size/skip-dir filters"
```

---

## Task 3: Stack detection (manifest → language / package-manager / framework)

**Files:**
- Modify: `skills/sf-ingest-project/scripts/scan.py`
- Modify: `skills/sf-ingest-project/scripts/tests/test_scan.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_scan.py`:

```python
def test_stack_python_uv(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='x'\ndependencies=['fastapi']\n[tool.uv]\n"
    )
    (tmp_path / "uv.lock").write_text("# lock\n")
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    langs = {l["name"] for l in st["languages"]}
    assert "Python" in langs
    assert "uv" in st["package_managers"]
    assert "fastapi" in st["frameworks"]
    assert "pyproject.toml" in st["manifests"]


def test_stack_typescript_npm(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name":"x","dependencies":{"next":"14","react":"18"}}'
    )
    (tmp_path / "package-lock.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text("{}")
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    langs = {l["name"] for l in st["languages"]}
    assert "TypeScript" in langs
    assert "npm" in st["package_managers"]
    assert "next" in st["frameworks"]


def test_stack_polyglot(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "Cargo.toml").write_text("[package]\nname='y'\n")
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    langs = {l["name"] for l in st["languages"]}
    assert {"Python", "Rust"} <= langs


def test_stack_unknown_is_empty_not_error(tmp_path):
    (tmp_path / "notes.txt").write_text("hello\n")
    st = scan.detect_stack(tmp_path, scan.enumerate_files(tmp_path))
    assert st["languages"] == []
    assert st["package_managers"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k stack )`
Expected: FAIL (`module 'scan' has no attribute 'detect_stack'`).

- [ ] **Step 3: Implement stack detection**

Add to `scan.py`:

```python
# manifest filename → (language, evidence-confidence). Order matters only for
# readability; detection is set-based.
_MANIFEST_LANG = {
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "setup.py": "Python",
    "setup.cfg": "Python",
    "Pipfile": "Python",
    "package.json": "JavaScript",  # upgraded to TypeScript if tsconfig present
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "build.gradle.kts": "Kotlin",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "pubspec.yaml": "Dart",
}

# lockfile / marker → package manager
_PM_MARKERS = {
    "uv.lock": "uv",
    "poetry.lock": "poetry",
    "Pipfile.lock": "pipenv",
    "requirements.txt": "pip",
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "bun.lockb": "bun",
    "Cargo.lock": "cargo",
    "go.sum": "go modules",
    "Gemfile.lock": "bundler",
    "composer.lock": "composer",
}

# framework name → substrings that, if present in a manifest's text, imply it.
_FRAMEWORK_HINTS = {
    "fastapi": ("fastapi",),
    "django": ("django",),
    "flask": ("flask",),
    "pytorch": ("torch", "pytorch"),
    "next": ("next",),
    "react": ("react",),
    "vue": ("vue",),
    "svelte": ("svelte",),
    "express": ("express",),
    "spring": ("spring-boot", "springframework"),
    "rails": ("rails",),
    "laravel": ("laravel",),
    "axum": ("axum",),
    "actix": ("actix",),
}


def detect_stack(root: Path, files: list[Path]) -> dict:
    """Detect languages, package managers, and frameworks from manifest presence
    + a bounded substring scan of manifest contents. Read-only."""
    names = {p.name for p in files}
    manifests = sorted(n for n in names if n in _MANIFEST_LANG)

    languages: list[dict] = []
    seen_langs: set[str] = set()
    for m in manifests:
        lang = _MANIFEST_LANG[m]
        # package.json → TypeScript if a tsconfig is present.
        if m == "package.json" and "tsconfig.json" in names:
            lang = "TypeScript"
        if lang not in seen_langs:
            seen_langs.add(lang)
            languages.append({"name": lang, "evidence": m, "confidence": "high"})

    package_managers = sorted({pm for marker, pm in _PM_MARKERS.items() if marker in names})

    # Framework hints: read manifest texts (bounded by MAX_READ_BYTES already).
    blob = ""
    # dict.fromkeys dedups: a manifest already in `manifests` (e.g. pyproject.toml
    # on a Python project) must not be read twice. (Review: HIGH)
    for m in dict.fromkeys(manifests + ["package.json", "pyproject.toml"]):
        fp = root / m
        if fp.is_file() and _safe_size(fp):
            try:
                blob += "\n" + fp.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
    frameworks = sorted(
        fw for fw, hints in _FRAMEWORK_HINTS.items() if any(h in blob for h in hints)
    )

    return {
        "languages": languages,
        "package_managers": package_managers,
        "frameworks": frameworks,
        "manifests": manifests,
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k stack )`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add skills/sf-ingest-project/scripts/scan.py skills/sf-ingest-project/scripts/tests/test_scan.py
git commit -m "feat(ingest): stack detection (language/package-manager/framework from manifests)"
```

---

## Task 4: Tree digest, entry points, doc inventory

**Files:**
- Modify: `skills/sf-ingest-project/scripts/scan.py`
- Modify: `skills/sf-ingest-project/scripts/tests/test_scan.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_scan.py`:

```python
def test_tree_digest_and_entry_points(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n")
    files = scan.enumerate_files(tmp_path)
    td = scan.build_tree_digest(tmp_path, files)
    assert "src" in td["top_dirs"]
    assert "tests" in td["top_dirs"]
    assert td["entry_count"] == len(files)
    eps = scan.detect_entry_points(tmp_path, files)
    assert "src/main.py" in eps


def test_doc_inventory_classifies(tmp_path):
    (tmp_path / "README.md").write_text("# Title\nbody\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "adr").mkdir()
    (tmp_path / "docs" / "adr" / "0001-foo.md").write_text("# ADR\n")
    files = scan.enumerate_files(tmp_path)
    inv = scan.build_doc_inventory(tmp_path, files)
    kinds = {d["kind"] for d in inv}
    paths = {d["path"] for d in inv}
    assert "readme" in kinds
    assert "README.md" in paths
    assert "adr" in kinds
```

- [ ] **Step 2: Run to verify failure**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k "tree_digest or doc_inventory" )`
Expected: FAIL (missing attributes).

- [ ] **Step 3: Implement**

Add to `scan.py`:

```python
TREE_DEPTH_CAP = 4
TREE_ENTRY_CAP = 500

_ENTRY_POINT_CANDIDATES = (
    "main.py", "src/main.py", "app.py", "src/app.py", "__main__.py",
    "manage.py", "index.js", "src/index.js", "index.ts", "src/index.ts",
    "main.go", "cmd/main.go", "src/main.rs", "src/lib.rs", "Main.java",
)

_DOC_PATTERNS = (
    ("readme", ("readme.md", "readme.rst", "readme.txt", "readme")),
    ("changelog", ("changelog.md", "changelog")),
    ("contributing", ("contributing.md",)),
)


def build_tree_digest(root: Path, files: list[Path]) -> dict:
    """Summarize the directory shape: top-level dirs, entry count, truncation."""
    top_dirs: set[str] = set()
    notable: list[str] = []
    truncated = False
    for p in files:
        rel = p.relative_to(root)
        parts = rel.parts
        if len(parts) > 1:
            top_dirs.add(parts[0])
        if len(parts) > TREE_DEPTH_CAP:
            truncated = True
        name = parts[-1]
        if name in ("README.md", "pyproject.toml", "package.json", "Cargo.toml",
                    "go.mod", "Makefile", "Dockerfile", "docker-compose.yml"):
            if str(rel) not in notable:
                notable.append(str(rel))
    if len(files) > TREE_ENTRY_CAP:
        truncated = True
    return {
        "depth_cap": TREE_DEPTH_CAP,
        "entry_count": len(files),
        "truncated": truncated,
        "top_dirs": sorted(top_dirs),
        "notable_files": sorted(notable),
    }


def detect_entry_points(root: Path, files: list[Path]) -> list[str]:
    rels = {str(p.relative_to(root)) for p in files}
    return [c for c in _ENTRY_POINT_CANDIDATES if c in rels]


def _doc_kind(rel: str) -> str | None:
    low = rel.lower()
    base = low.rsplit("/", 1)[-1]
    if "/adr/" in "/" + low or "/decisions/" in "/" + low:
        if low.endswith(".md"):
            return "adr"
    for kind, names in _DOC_PATTERNS:
        if base in names:
            return kind
    if low.startswith("docs/") and low.endswith((".md", ".rst")):
        return "doc"
    return None


def build_doc_inventory(root: Path, files: list[Path]) -> list[dict]:
    inv: list[dict] = []
    for p in files:
        rel = str(p.relative_to(root))
        kind = _doc_kind(rel)
        if kind is None:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        inv.append({"path": rel, "kind": kind, "bytes": size})
    inv.sort(key=lambda d: d["path"])
    return inv
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k "tree_digest or doc_inventory" )`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add skills/sf-ingest-project/scripts/scan.py skills/sf-ingest-project/scripts/tests/test_scan.py
git commit -m "feat(ingest): tree digest, entry-point detection, doc inventory"
```

---

## Task 5: Git facts (monthly timeline, tags, recent, metadata)

**Files:**
- Modify: `skills/sf-ingest-project/scripts/scan.py`
- Modify: `skills/sf-ingest-project/scripts/tests/test_scan.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_scan.py`:

```python
def test_git_facts_non_repo(tmp_path):
    (tmp_path / "x.py").write_text("1\n")
    g = scan.collect_git_facts(tmp_path)
    assert g == {"is_repo": False}


def test_git_facts_repo_with_commits_and_tag(tmp_path):
    (tmp_path / "a.py").write_text("1\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "feat: first", when="2025-01-10T12:00:00")
    (tmp_path / "b.py").write_text("2\n")
    _git_commit_all(tmp_path, "feat: second", when="2025-03-15T12:00:00")
    subprocess.run(["git", "tag", "v1.0"], cwd=tmp_path, check=True)
    g = scan.collect_git_facts(tmp_path)
    assert g["is_repo"] is True
    assert g["commit_count"] == 2
    months = {b["month"] for b in g["timeline"]}
    assert "2025-01" in months and "2025-03" in months
    tag_names = {t["name"] for t in g["tags"]}
    assert "v1.0" in tag_names
    assert g["recent"]                       # at least one recent commit
    assert g["branch"]                        # some branch name
    assert g["dirty"] is False                # clean working tree after commit
```

- [ ] **Step 2: Run to verify failure**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k git_facts )`
Expected: FAIL (`module 'scan' has no attribute 'collect_git_facts'`).

- [ ] **Step 3: Implement git facts**

Add to `scan.py`:

```python
from collections import Counter

GIT_TIMEOUT = 30
RECENT_COMMITS = 10


def _git(root: Path, args: list[str]) -> str | None:
    """Run a read-only git command; return stdout text or None on any failure."""
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=str(root),
            capture_output=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def collect_git_facts(root: Path) -> dict:
    """Collect bounded, read-only git history facts. Monthly timeline buckets;
    tags annotated; recent commits capped. Returns {'is_repo': False} for non-repos."""
    inside = _git(root, ["rev-parse", "--is-inside-work-tree"])
    if inside is None or inside.strip() != "true":
        return {"is_repo": False}

    facts: dict = {"is_repo": True}

    # Zero-commit repo: `rev-parse --is-inside-work-tree` is "true" but there is no
    # HEAD yet, so rev-list/status would emit misleading facts (dirty=True from
    # untracked-only). Report it honestly and return early. (Review: CRITICAL)
    head = _git(root, ["rev-parse", "--verify", "-q", "HEAD"])
    if head is None or not head.strip():
        facts["commit_count"] = 0
        facts["branch"] = (_git(root, ["symbolic-ref", "--short", "-q", "HEAD"]) or "").strip()
        facts["dirty"] = False
        facts["first_commit"] = ""
        facts["last_commit"] = ""
        facts["timeline"] = []
        facts["tags"] = []
        facts["recent"] = []
        facts["no_commits"] = True
        return facts

    count = _git(root, ["rev-list", "--count", "HEAD"])
    facts["commit_count"] = int(count.strip()) if count and count.strip().isdigit() else 0

    branch = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    facts["branch"] = branch.strip() if branch else ""

    dirty = _git(root, ["status", "--porcelain"])
    facts["dirty"] = bool(dirty and dirty.strip())

    # First/last commit dates (ISO short).
    first = _git(root, ["log", "--reverse", "--date=format:%Y-%m-%d",
                        "--pretty=%ad", "--max-parents=0"])
    facts["first_commit"] = first.splitlines()[0].strip() if first and first.strip() else ""
    last = _git(root, ["log", "-1", "--date=format:%Y-%m-%d", "--pretty=%ad"])
    facts["last_commit"] = last.strip() if last else ""

    # Monthly timeline buckets (single algorithm, per spec §7).
    months_out = _git(root, ["log", "--date=format:%Y-%m", "--pretty=%ad"])
    bucket: Counter = Counter()
    if months_out:
        for line in months_out.splitlines():
            m = line.strip()
            if m:
                bucket[m] += 1
    facts["timeline"] = [
        {"month": mth, "count": cnt} for mth, cnt in sorted(bucket.items())
    ]

    # Tags with their commit date (annotated into the timeline by the LLM later).
    tags_out = _git(root, ["tag", "--sort=creatordate",
                           "--format=%(refname:short)\t%(creatordate:short)"])
    tags: list[dict] = []
    if tags_out:
        for line in tags_out.splitlines():
            if "\t" in line:
                nm, dt = line.split("\t", 1)
                if nm.strip():
                    tags.append({"name": nm.strip(), "date": dt.strip()})
    facts["tags"] = tags

    # Recent commits (capped).
    recent_out = _git(root, [
        "log", f"-{RECENT_COMMITS}", "--date=format:%Y-%m-%d", "--pretty=%ad\t%s",
    ])
    recent: list[dict] = []
    if recent_out:
        for line in recent_out.splitlines():
            if "\t" in line:
                dt, subj = line.split("\t", 1)
                recent.append({"date": dt.strip(), "subject": subj.strip()[:120]})
    facts["recent"] = recent

    return facts
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k git_facts )`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add skills/sf-ingest-project/scripts/scan.py skills/sf-ingest-project/scripts/tests/test_scan.py
git commit -m "feat(ingest): read-only git facts (monthly timeline, tags, recent, metadata)"
```

---

## Task 6: Assemble full facts (name candidates, size signals, looks_like_project) + wire `scan()`

**Files:**
- Modify: `skills/sf-ingest-project/scripts/scan.py`
- Modify: `skills/sf-ingest-project/scripts/tests/test_scan.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_scan.py`:

```python
def test_full_scan_python_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='my-app'\ndependencies=['flask']\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "README.md").write_text("# My App\nDoes things.\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "init", when="2025-02-01T10:00:00")
    facts = scan.scan(str(tmp_path))
    assert facts["looks_like_project"] is True
    assert facts["name_candidates"]["chosen"] == "my-app"
    assert any(l["name"] == "Python" for l in facts["stack"]["languages"])
    assert "flask" in facts["stack"]["frameworks"]
    assert facts["git"]["is_repo"] is True
    assert facts["size_signals"]["file_count"] >= 3
    assert "src/main.py" in facts["entry_points"]


def test_name_falls_back_to_dir_when_no_manifest_name(tmp_path):
    proj = tmp_path / "cool-tool"
    proj.mkdir()
    (proj / "README.md").write_text("# Cool Tool\n")
    facts = scan.scan(str(proj))
    assert facts["looks_like_project"] is True   # README alone counts
    assert facts["name_candidates"]["chosen"] == "cool-tool"


def test_recommend_subagents_for_large_repo(tmp_path):
    facts_small = scan.scan(str(tmp_path))
    assert facts_small["looks_like_project"] is False
    # size_signals present even on empty dir
    assert facts_small["size_signals"]["recommend_subagents"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k "full_scan or name_falls_back or recommend_subagents" )`
Expected: FAIL (facts missing `name_candidates` / `stack` / `size_signals` keys).

- [ ] **Step 3: Implement name candidates, size signals, and wire them into `scan()`**

Add these helpers to `scan.py`:

```python
import re

_KEBAB_RE = re.compile(r"[^a-z0-9]+")
SUBAGENT_FILE_THRESHOLD = 800
SUBAGENT_LOC_THRESHOLD = 50_000


def _kebabify(name: str) -> str:
    s = _KEBAB_RE.sub("-", name.strip().lower()).strip("-")
    return s or "project"


def _manifest_name(root: Path, manifests: list[str]) -> str | None:
    """Best-effort project name from a manifest. Bounded, tolerant."""
    if "pyproject.toml" in manifests:
        txt = _read_small(root / "pyproject.toml")
        m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', txt)
        if m:
            return m.group(1)
    if "package.json" in manifests:
        txt = _read_small(root / "package.json")
        m = re.search(r'"name"\s*:\s*"([^"]+)"', txt)
        if m:
            return m.group(1)
    if "Cargo.toml" in manifests:
        txt = _read_small(root / "Cargo.toml")
        m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', txt)
        if m:
            return m.group(1)
    return None


def _read_small(path: Path) -> str:
    if not path.is_file() or not _safe_size(path):
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _build_name_candidates(root: Path, manifests: list[str]) -> dict:
    dir_name = _kebabify(root.name)
    manifest_name = _manifest_name(root, manifests)
    chosen = _kebabify(manifest_name) if manifest_name else dir_name
    return {
        "dir": dir_name,
        "manifest": _kebabify(manifest_name) if manifest_name else None,
        "chosen": chosen,
    }


def _estimate_loc(files: list[Path]) -> int:
    """Bounded line-count estimate over text-ish files (skips huge/binary)."""
    total = 0
    text_ext = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
                ".kt", ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs",
                ".md", ".rst", ".toml", ".yaml", ".yml", ".json", ".sh")
    for p in files:
        if p.suffix.lower() not in text_ext:
            continue
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                for _ in fh:
                    total += 1
        except OSError:
            continue
    return total


def _build_size_signals(files: list[Path]) -> dict:
    file_count = len(files)
    loc = _estimate_loc(files)
    return {
        "file_count": file_count,
        "loc_estimate": loc,
        "recommend_subagents": file_count > SUBAGENT_FILE_THRESHOLD
        or loc > SUBAGENT_LOC_THRESHOLD,
    }
```

Now replace the body of `scan()` (the part after the `is_dir()` guard) so it assembles every section:

```python
def scan(path: str, *, depth: str = "standard") -> dict:
    """Scan a project directory and return the facts dict. Never writes."""
    root = Path(path).expanduser().resolve()
    facts: dict = {
        "schema_version": SCHEMA_VERSION,
        "scanned_path": str(root),
        "looks_like_project": False,
        "warnings": [],
    }
    if not root.is_dir():
        # Return a COMPLETE facts dict (all contract keys present) so the LLM
        # consumer never KeyErrors on a bad path. (Review: HIGH)
        facts["warnings"].append(f"path is not a directory: {root}")
        facts["framework_version"] = _framework_version()
        facts["name_candidates"] = {"dir": "", "manifest": None, "chosen": "project"}
        facts["stack"] = {"languages": [], "package_managers": [],
                          "frameworks": [], "manifests": []}
        facts["tree_digest"] = {"depth_cap": TREE_DEPTH_CAP, "entry_count": 0,
                                "truncated": False, "top_dirs": [], "notable_files": []}
        facts["entry_points"] = []
        facts["doc_inventory"] = []
        facts["git"] = {"is_repo": False}
        facts["size_signals"] = {"file_count": 0, "loc_estimate": 0,
                                 "recommend_subagents": False}
        return facts

    files = enumerate_files(root)
    stack = detect_stack(root, files)
    git = collect_git_facts(root)
    doc_inventory = build_doc_inventory(root, files)

    has_manifest = bool(stack["manifests"])
    has_readme = any(d["kind"] == "readme" for d in doc_inventory)
    looks_like_project = has_manifest or git.get("is_repo", False) or has_readme

    facts["looks_like_project"] = looks_like_project
    facts["name_candidates"] = _build_name_candidates(root, stack["manifests"])
    facts["stack"] = stack
    facts["tree_digest"] = build_tree_digest(root, files)
    facts["entry_points"] = detect_entry_points(root, files)
    facts["doc_inventory"] = doc_inventory
    facts["git"] = git
    facts["size_signals"] = _build_size_signals(files)

    if not has_readme:
        facts["warnings"].append("no README found")
    if not git.get("is_repo", False):
        facts["warnings"].append("not a git repository; timeline will be skipped")
    if not has_manifest:
        facts["warnings"].append("no recognized package manifest found")

    return facts
```

- [ ] **Step 4: Run to verify pass**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k "full_scan or name_falls_back or recommend_subagents" )`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the whole scanner suite**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/ -q )`
Expected: PASS (all tests from Tasks 1–6).

- [ ] **Step 6: Commit**

```bash
git add skills/sf-ingest-project/scripts/scan.py skills/sf-ingest-project/scripts/tests/test_scan.py
git commit -m "feat(ingest): assemble full facts JSON (name candidates, size signals, looks_like_project)"
```

---

## Task 7: Read-only invariant + secret-skip property tests (LOAD-BEARING)

These two tests are the safety contract. They must pass for the feature to be acceptable.

**Files:**
- Modify: `skills/sf-ingest-project/scripts/tests/test_scan.py`

- [ ] **Step 1: Write the property tests**

Add to `test_scan.py`:

```python
def _snapshot(root: Path) -> dict[str, tuple[int, float, str]]:
    snap: dict[str, tuple[int, float, str]] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            st = p.stat()
            snap[str(p.relative_to(root))] = (
                st.st_size, st.st_mtime, hashlib.sha256(data).hexdigest()
            )
    return snap


def test_scan_mutates_nothing_in_project(tmp_path):
    # Build a realistic repo, snapshot it, scan, snapshot again — byte-identical.
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    pass\n")
    (tmp_path / "README.md").write_text("# X\n")
    _git_init(tmp_path)
    _git_commit_all(tmp_path, "init", when="2025-02-01T10:00:00")
    before = _snapshot(tmp_path)
    scan.scan(str(tmp_path))
    after = _snapshot(tmp_path)
    assert before == after


def test_secret_values_never_appear_in_facts(tmp_path):
    secret = "FAKE_SECRET_sk_live_abc123XYZ"
    (tmp_path / ".env").write_text(f"API_KEY={secret}\n")
    (tmp_path / "config.pem").write_text(f"-----BEGIN KEY-----\n{secret}\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "README.md").write_text("# X\n")
    facts = scan.scan(str(tmp_path))
    blob = json.dumps(facts)
    assert secret not in blob          # secret content never read → never emitted


def test_subprocess_scan_writes_nothing_and_emits_json(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    (tmp_path / "README.md").write_text("# X\n")
    before = _snapshot(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "scan.py"), str(tmp_path)],
        capture_output=True, text=True,
    )
    after = _snapshot(tmp_path)
    assert proc.returncode == 0, proc.stderr
    parsed = json.loads(proc.stdout)   # stdout is valid JSON
    assert parsed["schema_version"] == 1
    assert before == after             # nothing created/modified/deleted
```

- [ ] **Step 2: Run the property tests**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/test_scan.py -q -k "mutates_nothing or secret_values or subprocess_scan" )`
Expected: PASS (3 passed). If `test_secret_values_never_appear_in_facts` fails, the enumeration/never-read filter from Task 2 is leaking a sensitive file — fix Task 2, do not weaken the test.

- [ ] **Step 3: Run the entire scanner suite once more**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/ -q )`
Expected: PASS (all green).

- [ ] **Step 4: Commit**

```bash
git add skills/sf-ingest-project/scripts/tests/test_scan.py
git commit -m "test(ingest): read-only invariant + secret-skip property tests (load-bearing)"
```

---

## Task 8: `references/extraction-spec.md` (scanner detection-rules spec)

**Files:**
- Create: `skills/sf-ingest-project/references/extraction-spec.md`

- [ ] **Step 1: Write the reference doc**

Create `skills/sf-ingest-project/references/extraction-spec.md`:

```markdown
# Extraction spec — what `scripts/scan.py` reads and emits

This is the spec for the read-only scanner. It documents the facts JSON contract,
the detection rules, and the safety bounds. The scanner is the mechanical core;
this doc lets a reviewer compare intent vs. implementation.

## Contract: facts JSON on stdout

`python3 scripts/scan.py [PATH] [--depth standard|light|deep]` prints a single
JSON object (see the skill's SKILL.md for the full shape). Exit 0 on success
(a non-project path still exits 0 with `looks_like_project: false`); exit 2 on a
missing path or bad args.

## Read-safety bounds (load-bearing)

- **File enumeration:** in a git repo, `git ls-files` (tracked files only — this
  respects `.gitignore` for free). Otherwise, `os.walk` pruned by SKIP_DIRS.
- **SKIP_DIRS:** `.git, node_modules, .venv, venv, __pycache__, dist, build,
  target, vendor, .next, coverage, .idea, .pytest_cache, .mypy_cache,
  .ruff_cache, .gradle, .tox, site-packages`.
- **NEVER_READ globs:** `.env, .env.*, *.pem, *.key, id_rsa*, id_ed25519,
  credentials*, *.sqlite*, *.db, *.p12, *.pfx, *.keystore, *.jks`.
- **Size cap:** never open a file larger than 256 KB.
- **Git:** every git call is read-only, capped at a 30s timeout; failures
  degrade to "not a repo" / empty sections rather than aborting.

## Detection rules

### Stack (language / package manager / framework)

| Manifest file | Language | Notes |
|---|---|---|
| `pyproject.toml`, `requirements.txt`, `setup.py`, `setup.cfg`, `Pipfile` | Python | |
| `package.json` | JavaScript → **TypeScript** if `tsconfig.json` present | |
| `Cargo.toml` | Rust | |
| `go.mod` | Go | |
| `pom.xml`, `build.gradle` | Java | |
| `build.gradle.kts` | Kotlin | |
| `Gemfile` | Ruby | |
| `composer.json` | PHP | |
| `pubspec.yaml` | Dart | |

| Lockfile / marker | Package manager |
|---|---|
| `uv.lock` | uv |
| `poetry.lock` | poetry |
| `Pipfile.lock` | pipenv |
| `requirements.txt` | pip |
| `package-lock.json` | npm |
| `yarn.lock` | yarn |
| `pnpm-lock.yaml` | pnpm |
| `bun.lockb` | bun |
| `Cargo.lock` | cargo |
| `go.sum` | go modules |
| `Gemfile.lock` | bundler |
| `composer.lock` | composer |

**Frameworks** are inferred from a bounded, lower-cased substring scan of the
manifest texts: fastapi, django, flask, pytorch (torch), next, react, vue,
svelte, express, spring, rails, laravel, axum, actix. This is a hint, not a
guarantee — the LLM treats it as evidence, not fact.

### Tree digest

`top_dirs` (first-level dirs holding tracked files), `entry_count`, and a
`truncated` flag (set when depth > 4 or entry count > 500). `notable_files`
surfaces README / manifests / Makefile / Dockerfile / docker-compose.

### Entry points

Presence check against a fixed candidate list (`main.py`, `src/main.py`,
`app.py`, `manage.py`, `index.js/ts`, `main.go`, `src/main.rs`, `Main.java`, …).

### Doc inventory

Classifies tracked docs into `readme`, `changelog`, `contributing`, `adr`
(anything under `adr/` or `decisions/` ending in `.md`), and generic `doc`
(`docs/**.md|.rst`). Records path + kind + byte size.

### Git facts

`is_repo`, `commit_count`, `branch`, `dirty`, `first_commit`, `last_commit`,
a **monthly** `timeline` (`[{month, count}]` — one bucketing algorithm, per
design §7), `tags` (`[{name, date}]`, creator-date sorted), and `recent` (last
10 commits as `[{date, subject}]`). Non-repos emit `{"is_repo": false}`.

### Name candidates

`dir` (kebabified directory name), `manifest` (kebabified name field from
pyproject/package.json/Cargo, if any), `chosen` (manifest name if present, else
dir). The skill may override with `--name`.

### Size signals

`file_count`, `loc_estimate` (bounded line count over text-ish extensions),
`recommend_subagents` (file_count > 800 or loc_estimate > 50,000).

## What the scanner deliberately does NOT do

- It never writes anything, anywhere (not even a cache).
- It never opens a NEVER_READ or oversized file.
- It does not interpret — it emits facts. Drafting pages is the LLM's job
  (`references/page-mapping.md`).
- It does not call the network.
```

- [ ] **Step 2: Commit**

```bash
git add skills/sf-ingest-project/references/extraction-spec.md
git commit -m "docs(ingest): extraction-spec reference (scanner detection rules + safety bounds)"
```

---

## Task 9: `references/page-mapping.md` (facts → ADR-014 pages, drafting rules)

**Files:**
- Create: `skills/sf-ingest-project/references/page-mapping.md`

- [ ] **Step 1: Write the reference doc**

Create `skills/sf-ingest-project/references/page-mapping.md`:

```markdown
# Page mapping — turning facts into a populated ADR-014 sub-wiki

You (the LLM) have the `scan.py` facts JSON in context. Draft the 7 ADR-014
pages from it. This doc is the mapping + the drafting rules. The page *shapes*
match `skills/sf-bootstrap-project/templates/*.tmpl` exactly (same frontmatter,
same section headers) — you fill the bodies with real content instead of
placeholders.

## Frontmatter (every page)

Match the bootstrap templates' frontmatter exactly. Bind:
- `title`, `type`, `schema_version: 1`
- `framework_version` ← from `lib/sf_paths.py` `framework_version()`
- `project_name` ← the chosen kebab name
- `created` / `updated` ← today (ISO YYYY-MM-DD)

## The mapping

| Page | Draw from | If evidence is thin |
|---|---|---|
| `PROJECT.md` | `name_candidates`, `stack`, README purpose/users, `doc_inventory` links | Keep the template's placeholder prose for any section with no evidence |
| `REQUIREMENTS.md` | README "features"/usage + entry points | Leave `_TBD_` bullets (often light) |
| `ROADMAP.md` | `git.tags` as completed milestones; "we are here" = `git.branch` + `git.recent` | `## Phase 1: TBD` if no tags |
| `STATE.md` | `git.recent` (active work), `git.branch`, `git.dirty` | `_TBD_` bullets |
| `CONTEXT.md` | latest commit cluster / branch name as current focus | "Ingested from existing project; first session pending." |
| `index.md` | catalog of the pages you wrote (match bootstrap's index shape) | n/a |
| `log.md` | `git.timeline` → terse monthly entries (cap ~20) + the init entry | init entry only if non-repo |

## Timeline → log.md (single algorithm)

For each `git.timeline` entry (monthly bucket), emit one terse line. Annotate a
month with any tag whose date falls in it. Cap at ~20 lines (collapse the oldest
into a single "… and N earlier months" line if needed). Then append the init
entry. Example:

```
## [2025-01] backfill | 40 commits — project history begins
## [2025-06] backfill | 22 commits — shipped v1.0 (tag)
...
## [<today>] init | Project sub-wiki ingested from existing project
```

Use event type `backfill` for reconstructed history and `init` for the ingest
event, so they're distinguishable from live `/sf:wrap` entries.

## `--depth deep` docs → summarize + backlink (never copy)

When `--depth deep` and `doc_inventory` contains ADRs/design docs: for each, add
a one-paragraph **summary** to the sub-wiki's `decisions/` or `research/` with a
**backlink** to the in-project source path (e.g. `see ../../../<project>/docs/adr/0001.md`).
Never copy the full document into the wiki — that bloats it and drifts as the
source evolves (design §7; ADR-002/004). For `standard`/`light`, just list the
docs under `index.md`'s Research/Decisions sections; don't summarize.

## Hard drafting rules

1. **No invention.** Every concrete claim (stack, dates, milestones, features)
   must trace to a fact in the JSON. If a section has no evidence, keep the
   template's placeholder prose — a `_TBD — <reason>; fill in._` marker — rather
   than guessing. A grep for `{{` or `_TBD_` should reveal every unfilled hole.
2. **Never echo secrets.** Do not copy any token-/key-/password-looking string
   into a page, even if it somehow appears in a doc snippet.
3. **Honesty about confidence.** Frameworks/entry points are hints; phrase them
   as "appears to use X" when the only evidence is a manifest substring.
4. **Stay in the sub-wiki + 2 master lines.** Write nothing into the user's
   project directory. The only master-wiki writes are the registration lines
   (below).

## Master-wiki registration (registration-only footprint)

Append, idempotently (skip if an equivalent line already exists):

- `wiki/index.md` under `## Projects`:
  `- [<Title>](projects/<name>/index.md) — Ingested <today> from existing project (<primary language/stack>).`
  If the `## Projects` header is absent, refuse to guess — surface it and
  recommend `/sf:install --redo-stage 5` (mirrors `sf-bootstrap-project`).
- `wiki/log.md`:
  `## [<today>] init | Project sub-wiki ingested for <name>`

Do NOT write to master `patterns/`, `research/`, or `identity.md`. All extracted
knowledge lives in the project sub-wiki (design §6).
```

- [ ] **Step 2: Commit**

```bash
git add skills/sf-ingest-project/references/page-mapping.md
git commit -m "docs(ingest): page-mapping reference (facts to ADR-014 pages, no-invention rules)"
```

---

## Task 10: `SKILL.md` (orchestration procedure + contract)

**Files:**
- Create: `skills/sf-ingest-project/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Create `skills/sf-ingest-project/SKILL.md`:

```markdown
---
name: sf-ingest-project
description: |
  Use when the solo builder wants to bring an EXISTING project (one with real
  code/git history that predates the framework) into their wiki — turning it
  into a first-class citizen on par with a freshly bootstrapped project, but
  with pages populated from what's actually in the repo. Triggers on the
  /sf:ingest-project slash command (optional [path], --depth standard|light|deep,
  --name <kebab>). A read-only scanner mines the project and emits facts; the
  LLM drafts the full ADR-014 sub-wiki; one preview, one approval, then additive
  writes. NEVER modifies the user's project files. For brand-new empty projects
  use /sf:bootstrap-project instead.
version: 0.1.0
license: MIT

framework_version: "1.0.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "A populated project sub-wiki at wiki/projects/<name>/ matching ADR-014 taxonomy, drafted from the real repo"
    - "A one-line registration in master wiki/index.md under '## Projects'"
    - "A one-line init entry in master wiki/log.md"
    - "An init + backfill entry set in the project's own log.md"
  budgets:
    turns: 8
    files_written: 12
    duration_seconds: 180
  permissions:
    read:
      - "<project-path>/**"
      - "~/.startup-framework/wiki/**"
      - "skills/sf-ingest-project/references/**"
      - "skills/sf-bootstrap-project/templates/**"
    write:
      - "~/.startup-framework/wiki/projects/<name>/**"
      - "~/.startup-framework/wiki/index.md"
      - "~/.startup-framework/wiki/log.md"
    execute:
      - "scripts/scan.py"
  completion_conditions:
    - "All 7 top-level taxonomy files exist at the target path, populated from facts (or honest placeholders)"
    - "All 3 subdirectories (research, decisions, patterns) exist with .gitkeep markers"
    - "Master index.md + log.md each have exactly one new registration line (idempotent on re-run)"
    - "No file inside the user's project directory was created, modified, or deleted"
  output_paths:
    - "~/.startup-framework/wiki/projects/<name>/"

tags: [onboarding, project, wiki, ingest, brownfield, read-only]
related_skills: [sf-bootstrap-project, sf-install, sf-interview, brainstorming]
references_required:
  - "references/extraction-spec.md"
  - "references/page-mapping.md"
references_on_demand: []
---

# sf-ingest-project

Turns an **existing** project into a first-class framework citizen. The builder
goes into an old project dir, runs `/sf:ingest-project`, and gets a populated
ADR-014 sub-wiki + master-wiki registration — drafted from the repo's real
README, stack, docs, and git history. Read-only on the project; one approval
before any write.

This is the **brownfield** counterpart to `sf-bootstrap-project` (which stamps an
empty skeleton for a brand-new project).

## When to use this skill

- Builder invokes `/sf:ingest-project [path]` (default path = cwd)
- Builder says: "add this existing project to my wiki", "ingest my old repo",
  "bring sidecar into the framework" — confirm scope once, then run

## When NOT to use this skill

- The project is brand-new / empty → use `/sf:bootstrap-project <name>`
- The master wiki doesn't exist yet → run `/sf:install` first
- The builder wants a read-only retrospective on sessions → `/sf:insights`

## Flags

| Flag | Effect |
|---|---|
| `[path]` (positional) | Project directory to ingest. Default: current directory. |
| `--depth standard` (default) | Docs + tree + stack + git timeline + light code signal |
| `--depth light` | Docs + manifests + tree only (cheapest; more placeholders) |
| `--depth deep` | Standard + summarize existing ADRs/design docs into the sub-wiki (with backlinks) |
| `--name <kebab>` | Override the derived project name (must match `^[a-z][a-z0-9-]*$`) |

## Procedure

### 1. Pre-flight

- Resolve the wiki via `lib/sf_paths.py` `wiki_path()`. If `wiki_path()/index.md`
  is absent, refuse and recommend `/sf:install`.
- Resolve the project path (default cwd). If it doesn't exist or isn't a
  directory, refuse with a clear message.
- Read the handle via `lib/sf_paths.py` `handle()`. On `HandleNotConfiguredError`,
  fall back to `unknown` and warn (suggest `/sf:interview`) — same as bootstrap.

### 2. Scan (read-only)

Run the scanner:

```
python3 scripts/scan.py "<project-path>" --depth <depth>
```

It prints the facts JSON. The scanner writes nothing and never reads secrets or
oversized files (see `references/extraction-spec.md`).

- If `looks_like_project` is `false`: warn the builder ("This doesn't look like a
  project — no manifest, git repo, or README found. Ingest anyway?") and confirm
  before continuing.
- If `size_signals.recommend_subagents` is `true`: tell the builder the repo is
  large; offer to either fan out code-skim subagents (one per top dir) or proceed
  with `--depth light`. Keep the scan bounded regardless.
- Resolve the project name: `--name` if given (validate kebab-case); else
  `name_candidates.chosen`. Validate against `^[a-z][a-z0-9-]*$`; re-prompt if
  the builder's override is invalid.

### 3. Interpret (draft the pages)

Read `references/page-mapping.md` and draft all 7 ADR-014 pages in memory from
the facts. Match the bootstrap templates' frontmatter + section headers exactly.
**No invention**: thin evidence → keep the placeholder marker, never fabricate.

### 4. Preview (ONE approval gate)

Determine the additive manifest by checking which target paths already exist
under `wiki/projects/<name>/` (follow `template-loader.md` additive-diff
semantics). Then show the builder ONE preview:

```
Ingest plan for <name> (from <project-path>):
  target:  ~/.startup-framework/wiki/projects/<name>/
  pages:   PROJECT.md      (~28 lines, high confidence)
           REQUIREMENTS.md (~12 lines, placeholder — thin evidence)
           ROADMAP.md      (~9 lines, from 2 git tags)
           STATE.md        (~14 lines, from recent commits)
           CONTEXT.md      (~6 lines)
           index.md        (catalog)
           log.md          (18 backfilled monthly entries + init)
  master:  + index.md  "## Projects" line
           + log.md    init line
  sample:  <first ~10 lines of PROJECT.md>

Write these? [y / edit / abort]
```

- `y` → proceed to write.
- `edit` → let the builder adjust a page (or the name) in conversation; re-show
  the preview.
- `abort` → exit clean, write nothing.

This is the only write gate (design: extract → preview → one approval).

### 5. Write (additive-only)

Following `template-loader.md`'s additive/no-overwrite discipline (drafted pages
arrive already complete — there is NO placeholder substitution step here):

1. `mkdir -p` the target sub-wiki + `research/`, `decisions/`, `patterns/`
   (each with a `.gitkeep`).
2. Write each page **only if its target file does not already exist** (additive;
   never overwrite). On a re-run, only missing pages are written.
3. Append the master registration lines **idempotently** (skip if an equivalent
   `projects/<name>/index.md` line already exists in `index.md`).
4. Confirm with a per-file summary (`wrote` / `skipped (exists)`).

### 6. Hand off

Print the four key paths (PROJECT, REQUIREMENTS, ROADMAP, CONTEXT) and suggest
the builder skim PROJECT.md, then run `/sf:wrap` at the end of their next session
to keep STATE/CONTEXT current.

## Anti-patterns

- **Never write into the user's project directory.** Read-only on the project,
  always. The scanner enforces this; the skill must too (no marker files, no
  "ingested" stamp in the repo).
- **Never overwrite an existing sub-wiki page.** Additive-diff only, per
  `template-loader.md`. No flag, no force mode.
- **Never invent content.** Thin evidence → placeholder marker. The framework's
  credibility depends on honest pages (cf. honest `sf-improve`).
- **Don't touch the master wiki beyond the 2 registration lines.** No
  `patterns/`, no `identity.md` (that's `/sf:interview`'s).
- **Don't re-implement bootstrap's taxonomy.** Match the existing template
  shapes; if a page shape needs to change, that's an ADR-014 amendment, not an
  ad-hoc change here.

## Eval expectations (see `eval/eval.json`)

- 7 pages + 3 dirs present at the target after a run; pages populated from facts.
- Master index.md + log.md each gain exactly one registration line.
- Re-run is additive (no overwrites; idempotent master lines).
- The user's project directory is byte-identical before and after.
- A low-evidence project yields honest placeholders, not fabricated features.

## References

- `references/extraction-spec.md` — the scanner's detection rules + safety bounds
- `references/page-mapping.md` — facts → ADR-014 pages + no-invention drafting rules
- `../sf-bootstrap-project/references/template-loader.md` — additive/no-overwrite write discipline (reused, not forked)
- ADR-032 (Project Ingest), ADR-014 (taxonomy), ADR-017 (per-friend wiki), ADR-013 (namespacing)
```

- [ ] **Step 2: Sanity-check the skill validates**

Run: `claude plugin validate ./ --strict`
Expected: PASS (the new skill + command are well-formed). If it reports the skill, confirm no errors.

- [ ] **Step 3: Commit**

```bash
git add skills/sf-ingest-project/SKILL.md
git commit -m "feat(ingest): SKILL.md orchestration procedure + contract block"
```

---

## Task 11: Eval suite + fixtures

**Files:**
- Create: `skills/sf-ingest-project/eval/eval.json`
- Create: `skills/sf-ingest-project/eval/fixtures/ingest-python-project.yaml`
- Create: `skills/sf-ingest-project/eval/fixtures/ingest-name-collision.yaml`

- [ ] **Step 1: Create the python-project fixture**

Create `skills/sf-ingest-project/eval/fixtures/ingest-python-project.yaml`:

```yaml
# Simulated environment for the ingest happy-path eval.
# An installed master wiki + a pre-existing python project to ingest.
today: "2026-05-31"
framework_version: "1.0.0"
identity:
  handle: "tester"
wiki:
  exists: true
  index_has_projects_section: true
project_to_ingest:
  path: "/home/tester/Dev/demo-api"
  files:
    - "pyproject.toml"        # [project] name='demo-api' dependencies=['fastapi']
    - "uv.lock"
    - "src/main.py"
    - "README.md"             # "# Demo API\nA small FastAPI service."
  git:
    is_repo: true
    commit_count: 120
    first_commit: "2025-01-05"
    last_commit: "2026-05-20"
    tags: ["v1.0"]
```

- [ ] **Step 2: Create the name-collision fixture**

Create `skills/sf-ingest-project/eval/fixtures/ingest-name-collision.yaml`:

```yaml
# The sub-wiki already exists → additive-diff, never overwrite.
today: "2026-05-31"
framework_version: "1.0.0"
identity:
  handle: "tester"
wiki:
  exists: true
  index_has_projects_section: true
  existing_subwiki:
    name: "demo-api"
    present_files: ["PROJECT.md", "index.md", "log.md"]   # some pages already exist
project_to_ingest:
  path: "/home/tester/Dev/demo-api"
  files: ["pyproject.toml", "src/main.py", "README.md"]
  git:
    is_repo: true
    commit_count: 120
```

- [ ] **Step 3: Create the eval suite**

Create `skills/sf-ingest-project/eval/eval.json`:

```json
{
  "name": "sf-ingest-project",
  "description": "Binary-assertion test suite for /sf:ingest-project. Each test runs a simulated invocation against a fixture and verifies the assertions hold. Load-bearing: the user's project is never modified; writes are additive; no content is invented.",
  "schema_version": 1,
  "framework_version": "1.0.0",
  "tests": [
    {
      "id": "ingest-happy-path",
      "fixture": "fixtures/ingest-python-project.yaml",
      "prompt": "/sf:ingest-project /home/tester/Dev/demo-api",
      "expected_output_summary": "Scanner reads the python project read-only; the skill drafts a populated ADR-014 sub-wiki, previews once, and on approval writes it + registers it in the master wiki.",
      "trigger_test": true,
      "binary_assertions": [
        "scripts/scan.py is invoked read-only against the project path before any write",
        "Target directory wiki/projects/demo-api/ exists after the run",
        "All 7 top-level files exist: PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, CONTEXT.md, index.md, log.md",
        "All 3 subdirectories exist with .gitkeep markers: research/, decisions/, patterns/",
        "PROJECT.md names the detected stack (Python / FastAPI) drawn from the scanner facts, not invented",
        "log.md contains at least one '## [<YYYY-MM>] backfill |' entry derived from the git timeline AND a '## [2026-05-31] init |' entry",
        "Master wiki/index.md has exactly one new bullet under '## Projects' linking to projects/demo-api/index.md",
        "Master wiki/log.md has exactly one new entry matching '## [2026-05-31] init | Project sub-wiki ingested for demo-api'",
        "No file inside /home/tester/Dev/demo-api is created, modified, or deleted by the run (read-only on the project)",
        "A single approval gate is shown before any wiki file is written"
      ]
    },
    {
      "id": "ingest-name-collision-additive",
      "fixture": "fixtures/ingest-name-collision.yaml",
      "prompt": "/sf:ingest-project /home/tester/Dev/demo-api",
      "expected_output_summary": "Sub-wiki already exists → additive-diff: only missing pages are written, existing pages are never overwritten, master lines are idempotent.",
      "trigger_test": true,
      "binary_assertions": [
        "Skill output mentions 'already exists' OR 'additive' in the user-facing message",
        "Pre-existing pages PROJECT.md, index.md, log.md under wiki/projects/demo-api/ have unchanged modification times",
        "Missing pages (REQUIREMENTS.md, ROADMAP.md, STATE.md, CONTEXT.md) ARE written",
        "Master wiki/index.md does NOT gain a duplicate projects/demo-api/ line (idempotent registration)",
        "No file inside /home/tester/Dev/demo-api is modified"
      ]
    },
    {
      "id": "ingest-no-master-wiki-refused",
      "fixture": "fixtures/ingest-python-project.yaml",
      "prompt": "/sf:ingest-project /home/tester/Dev/demo-api",
      "expected_output_summary": "When the master wiki is absent, refuse and recommend /sf:install. (Override the fixture's wiki.exists to false when running this case.)",
      "trigger_test": false,
      "binary_assertions": [
        "If wiki/index.md does NOT exist, the skill refuses before scanning",
        "The refusal names '/sf:install' as the remediation",
        "No partial sub-wiki is created at wiki/projects/demo-api/"
      ]
    },
    {
      "id": "ingest-no-invention-on-thin-evidence",
      "fixture": "fixtures/ingest-python-project.yaml",
      "prompt": "/sf:ingest-project /home/tester/Dev/demo-api --depth light",
      "expected_output_summary": "With light depth and a sparse README, sections lacking evidence keep placeholder markers rather than fabricated content.",
      "trigger_test": false,
      "binary_assertions": [
        "REQUIREMENTS.md sections with no supporting evidence contain a '_TBD' placeholder marker, not invented requirements",
        "No fabricated feature, metric, date, or user-persona appears in any page that is not traceable to the scanner facts",
        "PROJECT.md still records the factually-detected stack"
      ]
    }
  ],
  "non_triggers": [
    {
      "id": "bootstrap-not-ingest",
      "prompt": "/sf:bootstrap-project brand-new-thing",
      "expected_outcome": "skill_not_activated"
    },
    {
      "id": "insights-not-ingest",
      "prompt": "/sf:insights",
      "expected_outcome": "skill_not_activated"
    },
    {
      "id": "install-not-ingest",
      "prompt": "/sf:install",
      "expected_outcome": "skill_not_activated"
    }
  ],
  "notes": [
    "fixture: path to a YAML file under eval/fixtures/ describing the simulated environment.",
    "trigger_test: when true, the eval harness also verifies SKILL.md's description activates on the prompt (ADR-012 Layer 1).",
    "All assertions are binary. The load-bearing ones: project dir unchanged, writes additive, no invention."
  ]
}
```

- [ ] **Step 4: Validate the eval JSON parses**

Run: `python3 -c "import json; json.load(open('skills/sf-ingest-project/eval/eval.json')); print('eval.json OK')"`
Expected: `eval.json OK`

- [ ] **Step 5: Commit**

```bash
git add skills/sf-ingest-project/eval/
git commit -m "test(ingest): eval suite + fixtures (happy path, additive collision, refusal, no-invention)"
```

---

## Task 12: ADR-032 + docs wire-up + full verification

**Files:**
- Create: `wiki/decisions/032-project-ingest.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `wiki/index.md`
- Modify: `wiki/log.md`

- [ ] **Step 1: Write ADR-032**

Create `wiki/decisions/032-project-ingest.md`:

```markdown
---
title: "ADR-032: Project Ingest — Brownfield Onboarding via /sf:ingest-project"
status: accepted
date: 2026-05-31
sunset-review: 2026-11-30
affects-components: [skills, onboarding, wiki, projects, install]
relates-to: [014-project-sub-wiki-taxonomy, 015-onboarding, 017-per-friend-wiki-scope, 013-slash-command-namespacing, 031-solo-first-pivot]
amends:
  - "ADR-015 (Onboarding): adds a brownfield path — onboarding is no longer additive/empty-only; existing projects can be ingested."
---

# ADR-032: Project Ingest — Brownfield Onboarding

## Context

Onboarding was additive, forward-only, and manual (ADR-015): `/sf:install`
stamps an empty master skeleton, the wake-up hook only sees a project if its
sub-wiki already exists, and `/sf:bootstrap-project` seeds empty placeholders.
A founder with N mature projects got an empty wiki + N manual empty bootstraps —
a real adoption gap. The framework neither ignored nor ingested prior work; it
simply didn't see it.

## Decision

Ship `/sf:ingest-project` — a user-invoked skill (`sf-ingest-project`) that turns
an existing project into a first-class citizen with a **populated** ADR-014
sub-wiki, drafted from the repo's real README, stack, docs, and git history.

Key properties (load-bearing):

1. **Read-only on the project.** A Python scanner (`scripts/scan.py`) emits a
   facts JSON; it writes nothing into the project and never reads secret/oversized
   files. The skill writes only under `wiki/projects/<name>/` + 2 master lines.
2. **Extract → preview → one approval.** The LLM drafts every page, shows one
   preview, and writes only on approval — honoring ADR-017's no-silent-writes.
3. **Additive / never overwrite.** Re-runs fill only missing pages (reuses the
   `template-loader.md` discipline; idempotent master registration).
4. **No invention.** Thin evidence → honest placeholder, never fabricated.
5. **Registration-only global footprint.** Master wiki gains one `index.md`
   line + one `log.md` line — same footprint as `sf-bootstrap-project`. All
   extracted knowledge lives in the sub-wiki.

`sf-bootstrap-project` (greenfield, empty stamp) and `sf-ingest-project`
(brownfield, populated) are kept as separate single-responsibility skills.

## Reconciliation with ADR-017 ("wiki starts empty")

ADR-017 still holds. "Wiki starts empty" means the framework ships no
framework-developer content into the friend's wiki. Ingest fills the **user's own
project knowledge**, on explicit invocation + approval — it never injects our
content. The principle is "your wiki, your machine, your business"; ingest serves
exactly that by importing *the user's* prior work, not ours.

## Scope (v1) and deliberate non-goals

In: single-project ingest, standard/light/deep depth, additive writes.
Out (filed as fast-follows): the wake-up discovery nudge (its own plan — must use
a cheap presence check in the hook hot path, NOT the scanner), bulk `~/Dev`
scan, and refresh-on-drift re-ingest.

## Consequences

**Easier:** founders adopt the framework without abandoning prior work; existing
projects become navigable wiki citizens; the gap ADR-015 left is closed.

**Harder:** the scanner must stay bounded + safe across arbitrary repos (caps +
never-read globs + read-only tests carry this); extraction quality varies with
how well-documented a repo is (mitigated by honest placeholders).

**Now impossible:** silently importing a project (always one approval); the
framework writing into a user's project directory (read-only by construction).

## References

- `docs/superpowers/specs/2026-05-31-project-ingest-design.md` — full design
- `docs/superpowers/plans/2026-05-31-project-ingest.md` — implementation plan
- ADR-014 (taxonomy), ADR-015 (onboarding, amended), ADR-017 (per-friend wiki),
  ADR-013 (namespacing), ADR-031 (solo-first pivot)
```

- [ ] **Step 2: Add the command to README**

`README.md` has a `Helpers:` bullet list. The existing `/sf:bootstrap-project` bullet reads exactly:

```markdown
- **`/sf:bootstrap-project <name>`** — scaffolds a project sub-wiki.
```

Add the ingest bullet immediately after it (same `- **\`...\`** — ...` format):

```markdown
- **`/sf:ingest-project [path]`** — brownfield counterpart to `/sf:bootstrap-project`: reads an existing project (read-only), drafts a populated sub-wiki from its README/stack/git history, previews it, and writes on your approval.
```

Do not invent a new format — match the surrounding bullets exactly.

- [ ] **Step 3: Add a CHANGELOG entry**

`CHANGELOG.md` already has a `## [Unreleased]` section whose entire body is the single line `Nothing yet.`. **Replace that `Nothing yet.` line** with the `### Added` block below (do not add a second `## [Unreleased]` header):

Find:
```markdown
## [Unreleased]

Nothing yet.
```
Replace with:
```markdown
## [Unreleased]

### Added
- `/sf:ingest-project` — brownfield onboarding: ingest an existing project into your wiki. A read-only scanner reads the repo (stack, docs, git history) and the skill drafts a populated ADR-014 sub-wiki, previews it once, and writes additively on approval. Never modifies the project's own files. (ADR-032)
```

- [ ] **Step 4: Note the skill in wiki/index.md**

In `wiki/index.md`, find where `sf-insights` / `sf-bootstrap-project` are listed and add a matching one-line entry for `sf-ingest-project` pointing at ADR-032. Match the existing line format exactly.

- [ ] **Step 5: Append a build entry to wiki/log.md**

Append (chronological order is the invariant — add at the end; do NOT rewrite prior days):

```markdown
## [2026-05-31] build | sf-ingest-project (brownfield ingest) shipped behind ADR-032

Added `/sf:ingest-project`: read-only scanner (`scripts/scan.py`) + LLM drafting
of a populated ADR-014 sub-wiki, one approval gate, additive writes. Closes the
ADR-015 brownfield onboarding gap. Spec + plan under docs/superpowers/.
```

- [ ] **Step 6: Run the full scanner test suite**

Run: `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/ -q )`
Expected: PASS (all green).

- [ ] **Step 7: Validate the plugin (strict)**

Run: `claude plugin validate ./ --strict`
Expected: PASS — the new skill, command, and ADR are well-formed; no schema errors.

- [ ] **Step 8: Confirm the publish snapshot would include the new files and leak no wiki**

Run: `bash scripts/publish.sh --dry-run` (verified: the script supports `--dry-run`, which builds + runs all guards then cleans up — no commit, no push).
Expected: the dry-run passes and the snapshot file count increased to include `skills/sf-ingest-project/**`; `wiki/` is still absent from the snapshot (dev-wiki never ships).

- [ ] **Step 9: Commit**

```bash
git add wiki/decisions/032-project-ingest.md README.md CHANGELOG.md wiki/index.md wiki/log.md
git commit -m "docs(ingest): ADR-032 + README/CHANGELOG/wiki wire-up for /sf:ingest-project"
```

- [ ] **Step 10: Final review against the spec**

Re-read `docs/superpowers/specs/2026-05-31-project-ingest-design.md` and confirm every section maps to shipped code/docs:
- §5 pipeline → scan.py (Tasks 1–7) + SKILL.md procedure (Task 10)
- §6 facts contract → scan.py output (Task 6) + extraction-spec.md (Task 8)
- §7 page mapping → page-mapping.md (Task 9)
- §8 read-safety → enumeration filters (Task 2) + property tests (Task 7)
- §9 edge cases → SKILL.md §Procedure + eval refusal cases (Tasks 10–11)
- §10 testing → scanner suite (Tasks 2–7) + eval.json (Task 11)
- §11 integration → skill registration via SKILL.md `name:` (Task 10, no command file), ADR-032 + README/CHANGELOG/wiki wire-up (Task 12)

If any gap remains, add a follow-up task before declaring done.

---

## Definition of done

- [ ] `( cd skills/sf-ingest-project && python3 -m pytest scripts/tests/ -q )` is green.
- [ ] `claude plugin validate ./ --strict` passes.
- [ ] The skill, command, both reference docs, eval + fixtures, and ADR-032 all exist.
- [ ] `eval.json` parses and its load-bearing assertions (project unchanged, additive writes, no invention) are encoded.
- [ ] README, CHANGELOG, wiki/index.md, wiki/log.md updated.
- [ ] Every commit on `feat/project-ingest` is conventional-commit formatted; the tree is clean.
```
