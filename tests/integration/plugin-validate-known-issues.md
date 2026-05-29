# `claude plugin validate` — known issues

Triage for warnings + errors surfaced by the validator. Each entry: owner, severity, current workaround, planned resolution.

---

## ERROR 1 — `sf-improve-skill/SKILL.md` malformed YAML frontmatter — RESOLVED 2026-05-28

**Owner**: lifecycle-2 (Task #15)
**Severity**: was blocker (validator exited non-zero with `--strict`)
**Status**: ✅ **RESOLVED 2026-05-28**. lifecycle-2 applied Option B (annotation moved to YAML comment); their pytest cases (52/52) green after fix. Baseline re-captured shows clean validation.

**Original diagnostic**:
```
✘ frontmatter: YAML frontmatter failed to parse: YAML Parse error: Unexpected token.
```

**Original root cause**: line 46 of `skills/sf-improve-skill/SKILL.md`:
```yaml
  output_paths:
    - "skills/<skill-name>/" (only target skill modified)
```

YAML can't parse a quoted scalar followed by unquoted trailing text in a block sequence.

**Applied fix** (Option B):
```yaml
  output_paths:
    - "skills/<skill-name>/"  # only target skill modified
```

Comment is YAML-idiomatic (parser strips it; readers see the annotation).

**Lifecycle-2 also did a wider sweep**: `grep -rnE '^\s*-\s+"[^"]+"\s+\S' skills/ hooks/` returned no other instances of the same antipattern in their owned files. `sf-wrap/SKILL.md` confirmed clean.

**v1.1 candidate** (per lifecycle-2 suggestion): add a per-skill YAML-only lint to `validate.yml` that does `yaml.safe_load(frontmatter)` against every SKILL.md + ADR. Faster failure signal than waiting for `claude plugin validate`. Deferred from v1.0 because the existing CI workflow already catches this; the v1.1 lint is a tighter-error-surface optimization.

---

## DISCOVERY 1 — `metadata.pluginRoot` rejected by validator (docs out of sync)

**Owner**: sf-distribution (me; documenting for upstream report)
**Severity**: dev-time friction only; baseline now uses the documented-working form
**First seen**: 2026-05-28 baseline capture

**Diagnostic**: when marketplace.json contained:
```jsonc
{
  "metadata": {"pluginRoot": "./plugins"},
  "plugins": [{"name": "startup-framework", "source": "startup-framework"}]
}
```
…the validator returned:
```
✘ plugins.0.source: Invalid input
```

**Per CC docs** (`code.claude.com/docs/en/plugin-marketplaces` § Optional fields):
> `metadata.pluginRoot` (string): Base directory prepended to relative plugin source paths (for example, `"./plugins"` lets you write `"source": "formatter"` instead of `"source": "./plugins/formatter"`)

The validator does NOT apply `metadata.pluginRoot` to `plugins[].source`. So either:
- The docs are stale and `metadata.pluginRoot` is not implemented, OR
- The validator has a bug skipping the prefix-prepend step.

**Workaround applied at 2026-05-28**: removed `metadata.pluginRoot` from `marketplace.json`; changed `source` to the explicit `"./plugins/startup-framework"`. The marketplace now validates ✅.

**Superseded 2026-05-29 (C2+C4 restructure)**: the repo moved to the Crucible one-repo layout — `source` is now `"./"` (the repo root *is* the plugin). `metadata.pluginRoot` remains unused. Still validates ✅.

**Upstream report**: TODO — file an issue against Anthropic's plugin-marketplaces docs to either fix the validator or update the docs. Low priority — explicit source paths are at most ~10 chars longer per entry.

---

## DISCOVERY 2 — Plugin tree assembly via symlinks — REMOVED 2026-05-29 (C2+C4 restructure)

**Owner**: sf-distribution
**Severity**: informational (historical)
**Status**: ❌ **OBSOLETE.** The symlink approach was removed entirely in the Crucible one-repo restructure.

**What we used to do** (V1.0-pre-fix): `plugins/startup-framework/{skills,hooks}` were symlinks to `../../{skills,hooks}`, so the flat dev tree could present a CC-expected nested layout. The packaged plugin missed `feed -> ../../feed` → the Activity Feed `ImportError`'d on every install (this was blocker **C2**), and copying only `plugins/startup-framework/` left the `../../` symlinks dangling (this was blocker **C4**).

**Current layout** (V1.0): the repo **root** *is* the plugin (mirrors Hazar's `crucible` plugin). `.claude-plugin/{marketplace.json,plugin.json}` live at root with `source: "./"`; `hooks/`, `skills/`, `feed/`, `wiki-skeleton/` are **real directories** at root — **no symlinks anywhere**. This dissolves C2 (nothing to omit) and C4 (nothing to dangle on copy).

**Ship boundary**: maintainer-only content (`wiki/`, `raw/`, `REVIEW*.md`, `docs/superpowers/`, `tour/`, `.claude/`, maintainer docs) is excluded from the shipped repo per ADR-019. See `docs/RELEASING.md` for the publish model (allowlist publish, NOT a denylist over the dev history).

---

## WARNING 1 — marketplace.json description is required (we already have one)

**Owner**: sf-distribution
**Severity**: not applicable in production; only fires during validator tests where a stripped-down marketplace.json is used
**Status**: ignore (false positive in test contexts)

Surfaced during the source-form exploratory tests as:
```
⚠ description: No marketplace description provided.
```

This appeared only when I built minimal test fixtures without a `description` field, to isolate the `plugins.0.source` issue. The actual `marketplace.json` has a `description`. Not a real issue.

---

## Re-running this triage

After fixing any of the above, re-run:
```bash
cd /home/hsozer/Dev/startup-framework
claude plugin validate ./ --strict
```

Update this file to reflect new state. Aim: zero errors, zero warnings at first-ship.
