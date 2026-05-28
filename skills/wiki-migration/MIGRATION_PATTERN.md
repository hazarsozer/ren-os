# Authoring a Migration

Contributor guide for adding a new schema migration to the framework. Per ADR-027.

> If you are looking at the example directory `migrations/_template/`, that is **NOT a real migration**. It is the copy-this scaffold. Do not invoke it. v1.0 ships with zero real migrations — the first one will appear in v1.1 or later when a real schema change ships.

---

## When you need a migration

Authoring a new migration is required whenever the SHAPE of a page type changes in a way that an older framework version can't read or a newer framework version can't write into. Examples:

| Change | Migration needed? | Mode |
|---|---|---|
| Add an optional field with a default | Sometimes (MINOR — additive-transparent) | scripted (additive) |
| Rename a field | Yes, MAJOR | scripted |
| Remove a field | Yes, MAJOR | scripted |
| Split one field into two with judgment about which value goes where | Yes, MAJOR | LLM-driven or hybrid |
| Restructure section ordering | Yes, MAJOR | scripted (if mechanical) or LLM (if semantic) |
| Change the meaning of an existing field while keeping the same name | Yes, MAJOR | LLM-driven (must read body context) |
| Bug fix to wording / typo in templates | No | not a schema change |

Refer to ADR-019's semver policy and ADR-027's schema-change scope table for which framework version can ship which kind of migration.

---

## Step-by-step

### 1. Pick a page-type + version numbers

The page-type identifier must already exist in `schemas.json#page_types`. If you're inventing a brand-new page-type, that's a separate PR — add the page-type at `current: 1, supported_from: 1, migrations: []`. No migration needed for brand-new types.

For an existing page-type at schema N, the migration you're authoring is `N` → `N+1`. The directory basename is `<page-type>-<N>-to-<N+1>`.

Example: identity is at schema 1. You're authoring the bump to schema 2. Directory: `migrations/identity-1-to-2/`.

### 2. Copy the template

```bash
cp -a migrations/_template migrations/identity-1-to-2
```

### 3. Pick a mode

| Mode | When | Files |
|---|---|---|
| **scripted** | Mechanical: field renames, deterministic-default insertions, file renames, regex normalisations | `migrate.sh` + `verify.json` |
| **LLM-driven** | Semantic: merging two fields with judgment, splitting one page into multiple based on content, free-form content restructuring | `migrate.md` + `verify.json` |
| **hybrid** | Most real cases: scripted does the mechanical ~80%, LLM polishes the semantic ~20% | `migrate.sh` + `migrate.md` + `verify.json` |

Declare the mode in the migration's `README.md`. Delete the file you don't need.

### 4. Fill in the four files

- **`README.md`** — what changes + why + mode declaration + compatibility notes + rollback location.
- **`migrate.sh`** — bash script, idempotent, exit 0 on success, non-zero on failure. Input: `$1 = absolute path to page`. Modifies in place. Origin lives in snapshot.
- **`migrate.md`** — prompt for Claude (LLM-driven mode). Receives the page content + snapshot content as inputs. Output: full new page contents.
- **`verify.json`** — binary assertions confirming the migration produced valid output. Conforms to `verify.schema.json`.

### 5. Update `schemas.json`

Bump the page-type's `current` and append the migration ID to `migrations`:

```diff
   "identity": {
-    "current": 1,
+    "current": 2,
     "supported_from": 1,
-    "migrations": []
+    "migrations": ["1-to-2"]
   }
```

If your migration takes the page-type's schema past the N+3 deprecation window for an older schema, also bump `supported_from` and document the deprecation in `CHANGELOG.md`.

### 6. Add a fixture for CI

The `verify-migrations.yml` workflow runs every migration against synthetic fixtures. Add a fixture at:

```
tests/fixtures/<page-type>-v<N>/sample-1.md
tests/fixtures/<page-type>-v<N>/sample-2.md   # optional, for edge cases
```

Each fixture is a realistic pre-migration page. CI applies `migrate.sh` (and/or `migrate.md` if hybrid/LLM), then runs `verify-page.sh` against the output. All non-optional assertions must PASS.

### 7. Write the CHANGELOG entry

Under the next-version heading in `CHANGELOG.md`, add an entry in the `### Schema` section:

```markdown
### Schema
- `identity.md` schema 1 → 2: added `phase` field (default: ideation); renamed `tech-preferences` → `tech_preferences`. Migration: scripted.
```

---

## Hard rules

These are enforced by CI (validate.yml + verify-migrations.yml) or reviewed at PR time.

1. **Idempotency.** Running the migration twice must produce the same result as running it once. `migrate.sh` starts with a guard like `if grep -q '^schema_version: 2' "$PAGE"; then echo SKIP; exit 0; fi`.
2. **Deterministic.** Same input → same output. LLM-driven migrations get one chance per page (no retry-with-different-seed); verify.json catches non-determinism.
3. **No body data loss without explicit consent.** A `snapshot.body-identical` assertion in verify.json defends against accidental body rewrites in scripted migrations. LLM-driven migrations that intentionally rewrite the body must omit this assertion AND require user approval at DIFF_REVIEW.
4. **Frontmatter preservation.** All frontmatter keys not explicitly touched by the migration must survive verbatim. Use targeted `sed` ranges, NOT a full-file rewrite.
5. **PATCH-version migrations are forbidden.** If `/sf:update` detects a PATCH bump with any migrations queued, it aborts with an error. Only MINOR and MAJOR may ship migrations.
6. **No external network calls in `migrate.sh`.** Migrations run on the friend's machine, sometimes offline. `migrate.md` may use Claude (already a network call by virtue of running in CC), but `migrate.sh` is local-only.
7. **No writes outside the target page.** A migration for `identity.md` may not touch `wiki/projects/sidecar/STATE.md`. Cross-page migrations need a different design — flag for a follow-up ADR.

---

## verify.json predicates (v1 vocabulary)

| Predicate | Required fields | Meaning |
|---|---|---|
| `yaml.valid` | `target` (optional) | Output's YAML frontmatter parses cleanly. |
| `yaml.equals` | `field`, `value` | A frontmatter key equals an exact value. |
| `yaml.in` | `field`, `values[]` | A frontmatter key's value is one of the allowed values. |
| `yaml.absent` | `field` | A frontmatter key is NOT present. |
| `yaml.present` | `field` | A frontmatter key IS present (value unchecked). |
| `regex.matches` | `pattern`, `target` | Body or whole-file matches a POSIX-ERE regex. |
| `snapshot.value-preserved` | `snapshot_field`, `post_field` | The pre-migration value of one key equals the post-migration value of another key (catches rename bugs). |
| `snapshot.body-identical` | none | The body (everything after frontmatter) is byte-identical to the snapshot. |
| `file.exists` | `path` | A file at the given path exists. `${page_dir}` + `${wiki_root}` placeholders supported. |

If you need a new predicate, propose it in a PR adding to `verify.schema.json` + `scripts/verify-page.sh`. Predicates may be deprecated in MAJOR framework bumps; never removed in MINOR or PATCH.

---

## What you can rely on at runtime

When `/sf:update` invokes your migration:

- **The wiki has been fully snapshotted** at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/v<from>-pre-update-<timestamp>/` BEFORE your `migrate.sh` runs. Your script doesn't snapshot; the driver does. Snapshots are byte-isolated from the live wiki by default — modifications to the live wiki cannot corrupt the snapshot.
- **Advanced (opt-in): hardlink mode.** Friends with massive wikis can set `SF_SNAPSHOT_MODE=hardlink` to make snapshots share inodes with the live wiki (cheaper on disk). This is **safe ONLY if every migration script + LLM-driven migration uses atomic rename-on-write semantics** (GNU `sed -i` does; `open(path, "w")` does NOT). If you're authoring a migration and considering naive truncate-and-rewrite, your script will silently corrupt the hardlink-mode snapshot. Prefer:
  - shell: `sed -i`, `mv tmp file`, or write-to-temp-then-rename
  - Python: `pathlib.Path.write_text(...)` is unsafe; use `os.replace(tmp, target)` after writing to a temp file in the same directory
  - The default snapshot mode (copy) protects against this footgun. v1.0 ships with copy as the default for exactly this reason (REVIEW.md D2).
- **The snapshot path is available** to your script as the environment variable `SF_SNAPSHOT_DIR`. Read your page's pre-migration content via `cat "$SF_SNAPSHOT_DIR/$(realpath --relative-to="$SF_WIKI_ROOT" "$1")"`.
- **The wiki root is available** as `SF_WIKI_ROOT`.
- **Failure exits non-zero.** The driver enters ROLLBACK_PAGE if your script exits non-zero OR if any non-optional verify.json assertion fails. Other pages continue.
- **Idempotent rerun.** A failed migration may be retried by re-invoking `/sf:update`; the snapshot from the first attempt is preserved (per ADR-027's retention rule).

---

## What you must NOT do

- Don't call `git` from inside a migration. The wiki may not even be a git repo on every friend's machine (per ADR-026 — git remote is OPTIONAL).
- Don't write outside the page being migrated.
- Don't read `~/.startup-framework/` or `$HOME` for paths — use the `SF_WIKI_ROOT` env var the driver provides.
- Don't make the migration interactive. The DIFF_REVIEW happens in the driver, AFTER your migration completes. Your script must run silently.
- Don't print color codes or carriage returns to stdout. The driver parses your output line-by-line.

---

## Worked example: see `migrations/_template/`

The template directory shows the file structure + idempotency guard + typical sed patterns + verify.json shape. Copy it; rename it; edit the four files; write the fixture; PR.

Questions? File an issue in the marketplace repo or ping sf-distribution.
