# Extraction spec — what `scripts/scan.py` reads and emits

This is the canonical reference for the read-only scanner in
`skills/ingest-project/`. It documents the facts JSON contract, the detection
rules per section, and the safety bounds. The scanner is the mechanical core;
this doc lets a maintainer or the LLM consumer verify scanner behaviour without
reading the source.

---

## Contract: facts JSON on stdout

```
python3 scripts/scan.py [PATH] [--depth standard|light|deep]
```

Prints a single JSON object on stdout. Exit codes:

| Code | Meaning |
|---|---|
| `0` | Scan succeeded. A non-project path still exits 0 — it just sets `looks_like_project: false`. |
| `2` | Invocation error: path does not exist, or bad argument. |

### Top-level keys

```jsonc
{
  "schema_version": 1,            // integer — contract revision
  "scanned_path": "/abs/path",    // resolved absolute path
  "looks_like_project": true,     // bool: has manifest OR is git repo OR has README
  "framework_version": "1.0.0",  // string — from lib/sf_paths.framework_version(); fallback "1.0.0"
  "name_candidates": { … },
  "stack": { … },
  "tree_digest": { … },
  "entry_points": [ … ],
  "doc_inventory": [ … ],
  "git": { … },
  "size_signals": { … },
  "warnings": [ … ]               // list of strings; empty on a clean scan
}
```

When the path is not a directory, all section keys are still present (empty /
false / zero values) so the consumer never KeyErrors.

### `name_candidates`

```jsonc
{
  "dir": "my-app",       // kebabified directory name (always present)
  "manifest": "my-app",  // kebabified name from manifest; null if not found
  "chosen": "my-app"     // manifest name if present, else dir
}
```

Kebabification: lowercase, replace runs of non-alphanumeric chars with `-`,
strip leading/trailing `-`. Empty result falls back to `"project"`.

Sources checked (in order): `pyproject.toml` (`name = "…"`), `package.json`
(`"name": "…"`), `Cargo.toml` (`name = "…"`).

### `stack`

```jsonc
{
  "languages": [
    {"name": "Python", "evidence": "pyproject.toml", "confidence": "high"}
  ],
  "package_managers": ["uv"],
  "frameworks": ["fastapi"],
  "manifests": ["pyproject.toml"]
}
```

See [Detection rules — Stack](#stack-language-package-manager-framework) for
the full tables.

### `tree_digest`

```jsonc
{
  "depth_cap": 4,
  "entry_count": 312,
  "truncated": false,       // true when depth > 4 OR entry count > 500
  "top_dirs": ["src", "tests", "docs"],
  "notable_files": ["README.md", "pyproject.toml"]
}
```

### `entry_points`

List of relative-path strings from a fixed candidate list.

### `doc_inventory`

```jsonc
[
  {"path": "README.md", "kind": "readme", "bytes": 4210},
  {"path": "docs/adr/0001.md", "kind": "adr", "bytes": 900}
]
```

### `git`

When `is_repo` is `false`:

```jsonc
{"is_repo": false}
```

When `is_repo` is `true` (with commits):

```jsonc
{
  "is_repo": true,
  "commit_count": 487,
  "branch": "main",
  "dirty": false,
  "first_commit": "2025-01-03",   // ISO date (YYYY-MM-DD)
  "last_commit": "2026-05-20",
  "timeline": [{"month": "2025-01", "count": 40}],
  "tags": [{"name": "v1.0", "date": "2025-06-01"}],
  "recent": [{"date": "2026-05-20", "subject": "fix: …"}]
}
```

When `is_repo` is `true` but there are **zero commits**:

```jsonc
{
  "is_repo": true,
  "commit_count": 0,
  "branch": "main",     // from symbolic-ref; may be empty string
  "dirty": false,       // untracked-only is NOT reported as dirty
  "first_commit": "",
  "last_commit": "",
  "timeline": [],
  "tags": [],
  "recent": [],
  "no_commits": true    // present ONLY in zero-commit repos; marks early-return path
}
```

`no_commits` is the sentinel that tells the consumer the repo is freshly
initialised. It is **absent** from normal (non-zero-commit) git facts.
Consumers should test `"no_commits" in git` (or check `commit_count == 0`)
before reading `timeline`/`tags`/`recent`, which are present-but-empty on a
zero-commit repo and would otherwise mislead.

`dirty` checks `git status --porcelain` — a non-empty result is `true`. An
untracked-only repo with zero commits is reported `dirty: false` (the zero-commit
early-return path skips the status call and hard-codes `false`).

`recent[].subject` is truncated at 120 characters.

`tags[].date` is the creator-date from `git tag --sort=creatordate
--format=%(refname:short)\t%(creatordate:short)`. For lightweight tags this is
the tag-creation date, not necessarily the tagged commit's author date. Treat as
best-effort.

Recent commits are capped at the last 10 (`RECENT_COMMITS = 10`).

### `size_signals`

```jsonc
{
  "file_count": 312,
  "loc_estimate": 18400,
  "recommend_subagents": false   // true when file_count > 800 OR loc_estimate > 50000
}
```

`loc_estimate` counts lines in text-ish files only (see
[Size signals](#size-signals) below for the extension list).

### `warnings`

Non-fatal observations appended during scan:

| Warning string | Trigger |
|---|---|
| `"no README found"` | No file classified as `kind: readme` |
| `"not a git repository; timeline will be skipped"` | `git.is_repo` is `false` |
| `"no recognized package manifest found"` | `stack.manifests` is empty |
| `"path is not a directory: <path>"` | The `path` argument is not a directory |

---

## Read-safety bounds (load-bearing)

These bounds are invariants, tested by `scripts/tests/test_scan.py`.

### File enumeration

1. In a git repo: `git ls-files -z` (tracked files only — `.gitignore` respected
   for free). A zero-commit repo returns an empty list from git; the scanner
   falls back to `os.walk` in that case, so uncommitted files in fresh repos are
   still visible.
2. Fallback (non-git or zero-commit): `os.walk` with `SKIP_DIRS` pruning applied
   to `dirnames` in-place.

### `SKIP_DIRS`

The following directory names are always skipped during `os.walk` (and any path
component matching them is dropped during git-list filtering):

```
.git  node_modules  .venv  venv  __pycache__  dist  build
target  vendor  .next  coverage  .idea  .pytest_cache
.mypy_cache  .ruff_cache  .gradle  .tox  site-packages
```

### `NEVER_READ_GLOBS`

Files matching these globs are never opened, even if tracked:

```
.env          .env.*
*.pem         *.key
id_rsa        id_rsa.*       id_ed25519
credentials   credentials.*
*.sqlite      *.sqlite3      *.db
*.p12         *.pfx          *.keystore   *.jks
```

Matching uses `fnmatch` against the filename only (not the full path).

### Size cap

`MAX_READ_BYTES = 256 KB` (262 144 bytes). Any file larger than this is skipped
entirely — no partial reads. The cap is checked via `stat().st_size` before any
`open()` call.

### Git subprocess bounds

- Every git call is read-only (no mutation flags).
- Per-call timeout: `GIT_TIMEOUT = 30` seconds.
- Any git failure (non-zero exit, timeout, OS error) degrades gracefully: the
  affected section returns an empty/false value; the scan continues.

---

## Detection rules

### Stack (language, package manager, framework)

**Languages** — inferred from manifest filename presence:

| Manifest file | Language | Notes |
|---|---|---|
| `pyproject.toml` | Python | |
| `requirements.txt` | Python | also implies `pip` package manager |
| `setup.py` | Python | |
| `setup.cfg` | Python | |
| `Pipfile` | Python | |
| `package.json` | JavaScript | upgraded to **TypeScript** if `tsconfig.json` also present |
| `Cargo.toml` | Rust | |
| `go.mod` | Go | |
| `pom.xml` | Java | |
| `build.gradle` | Java | |
| `build.gradle.kts` | Kotlin | |
| `Gemfile` | Ruby | |
| `composer.json` | PHP | |
| `pubspec.yaml` | Dart | |

Each language is listed at most once in `languages[]` (deduplication on lang
name). Evidence is the first manifest that implied it. Confidence is always
`"high"` (manifest presence is definitive for language detection).

**Package managers** — inferred from lockfile / marker presence:

| Lockfile / marker | Package manager |
|---|---|
| `uv.lock` | `uv` |
| `poetry.lock` | `poetry` |
| `Pipfile.lock` | `pipenv` |
| `requirements.txt` | `pip` |
| `package-lock.json` | `npm` |
| `yarn.lock` | `yarn` |
| `pnpm-lock.yaml` | `pnpm` |
| `bun.lockb` | `bun` |
| `Cargo.lock` | `cargo` |
| `go.sum` | `go modules` |
| `Gemfile.lock` | `bundler` |
| `composer.lock` | `composer` |

`package_managers` is sorted alphabetically. A project may have multiple.

**Frameworks** — inferred from a bounded, lower-cased substring scan of
manifest file contents (`pyproject.toml`, `package.json`, plus any other
detected manifest; each read at most once; bounded by `MAX_READ_BYTES`).

The hints are anchored to avoid false positives (e.g. `"react"` as a bare word
would match `reactive`; `"rails"` would match `guardrails-ai`; `"torch"` would
match `torchlight`). Exact patterns used:

| Framework | Match patterns |
|---|---|
| `fastapi` | `fastapi` |
| `django` | `django` |
| `flask` | `flask` |
| `pytorch` | `import torch`, `"torch"`, `'torch'`, `torch>=`, `torch==`, `pytorch` |
| `next` | `"next"`, `"nextjs"`, `next.js` |
| `react` | `"react"`, `'react'`, `react-dom`, `react-scripts` |
| `vue` | `"vue"`, `'vue'`, `vue.js` |
| `svelte` | `svelte` |
| `express` | `"express"`, `'express'` |
| `spring` | `spring-boot`, `springframework` |
| `rails` | `rails/all`, `rails/application`, `gem 'rails'`, `gem "rails"` |
| `laravel` | `laravel` |
| `axum` | `axum` |
| `actix` | `actix` |

`frameworks` is sorted alphabetically. Framework detection is a hint; the LLM
treats it as evidence, not fact.

### Tree digest

Traverses the enumerated file list (already safety-filtered):

- `top_dirs` — set of first-path-component directories that contain at least one
  tracked file (i.e. `parts[0]` for files with `len(parts) > 1`), sorted.
- `entry_count` — total number of files in the enumerated list.
- `truncated` — `true` when any file has `len(parts) > TREE_DEPTH_CAP` (4), OR
  when `entry_count > TREE_ENTRY_CAP` (500).
- `depth_cap` — constant `4` (always present in the output).
- `notable_files` — relative paths of files whose **name** (last component) is
  one of: `README.md`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`,
  `Makefile`, `Dockerfile`, `docker-compose.yml`.

### Entry points

Presence check (exact relative-path string match) against a fixed ordered
candidate list:

```
main.py        src/main.py
app.py         src/app.py
__main__.py
manage.py
index.js       src/index.js
index.ts       src/index.ts
main.go        cmd/main.go
src/main.rs    src/lib.rs
Main.java
```

Result is a list of those candidates found in the enumerated file set, in
candidate-list order.

### Doc inventory

Each enumerated file is classified into one of these kinds, or skipped:

| Kind | Classification rule |
|---|---|
| `readme` | Basename (lowercased) is one of: `readme.md`, `readme.rst`, `readme.txt`, `readme` |
| `changelog` | Basename (lowercased) is one of: `changelog.md`, `changelog` |
| `contributing` | Basename (lowercased) is `contributing.md` |
| `adr` | Path contains `/adr/` or `/decisions/` (matched as `/`-anchored segments) **and** filename ends with `.md` |
| `doc` | Path starts with `docs/` **and** filename ends with `.md` or `.rst` |

Files matching none of the above are excluded from the inventory. Output is
sorted by `path` (ascending). Each entry is `{path, kind, bytes}` where `bytes`
is the `stat().st_size`; `0` on stat error.

### Git facts

All git calls are read-only subprocesses (`subprocess.run`, no shell=True).

**Repo detection:** `git rev-parse --is-inside-work-tree`. Any result other than
`"true"` (or any failure) returns `{"is_repo": false}`.

**Zero-commit guard:** After confirming inside a work-tree, the scanner runs
`git rev-parse --verify -q HEAD`. If that fails (no HEAD ref yet), the scanner
returns early with the zero-commit shape — `commit_count: 0`,
`no_commits: true`, `dirty: false`, empty strings/lists for all date/timeline
fields. This prevents misleading facts from a freshly `git init`-ed repo.

**Normal (non-zero-commit) flow:**

| Field | Git command |
|---|---|
| `commit_count` | `git rev-list --count HEAD` |
| `branch` | `git symbolic-ref --short HEAD`; falls back to `git rev-parse --abbrev-ref HEAD`; empty string for detached HEAD |
| `dirty` | `git status --porcelain` — non-empty result → `true` |
| `first_commit` | `git log --reverse --date=format:%Y-%m-%d --pretty=%ad --max-parents=0` (first line) |
| `last_commit` | `git log -1 --date=format:%Y-%m-%d --pretty=%ad` |
| `timeline` | `git log --date=format:%Y-%m --pretty=%ad` — bucketed into `{month, count}` by `Counter`, sorted |
| `tags` | `git tag --sort=creatordate --format=%(refname:short)\t%(creatordate:short)` |
| `recent` | `git log -10 --date=format:%Y-%m-%d --pretty=%ad\t%s` — capped at `RECENT_COMMITS = 10`; subject truncated at 120 chars |

### Name candidates

See [Contract — `name_candidates`](#name_candidates) above.

### Size signals

`file_count` — length of the enumerated file list.

`loc_estimate` — line count over the subset of files whose extension (lowercased)
is in:

```
.py .js .ts .tsx .jsx .go .rs .java .kt .rb .php
.c  .cpp .h .hpp .cs
.md .rst .toml .yaml .yml .json .sh
```

Files outside this set, or that fail to open, are skipped. Reads are unbuffered
line-by-line (no full load into memory).

`recommend_subagents` — `true` when `file_count > 800` OR `loc_estimate > 50000`.

---

## What the scanner deliberately does NOT do

- It **never writes** anything, anywhere — not in the project, not in the
  framework wiki, not in a temp file or cache.
- It **never opens** a file matching `NEVER_READ_GLOBS` or exceeding
  `MAX_READ_BYTES`.
- It **never calls the network**. All facts come from the local filesystem and
  read-only git subprocesses.
- It **does not interpret** the facts it collects. Drafting ADR-014 pages from
  those facts is the LLM's job, guided by `references/page-mapping.md`.
- It **does not invent** missing data. If a manifest, README, or git history is
  absent, the corresponding section is empty, not fabricated.
- It **does not modify** `.gitignore`, `git` internals, or any project config.
- It does **not** run tests, lint, build, or execute any project code.
