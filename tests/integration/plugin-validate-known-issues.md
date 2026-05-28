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

**Upstream report**: TODO — file an issue against Anthropic's plugin-marketplaces docs to either fix the validator or update the docs. Low priority — explicit source paths are at most ~10 chars longer per entry.

---

## DISCOVERY 2 — Plugin tree assembly via symlinks (working as documented)

**Owner**: sf-distribution
**Severity**: informational
**First seen**: 2026-05-28 baseline capture

**What we do**: `plugins/startup-framework/skills` is a symlink pointing at `../../skills` (the repo-root dev directory where all teammates land code). Same for `hooks` once it exists. This lets the dev tree stay flat while the published tree matches CC's expected layout.

**Validator behavior**: walks the symlinked dir and validates contents as if they lived in the plugin root. ✅ works as documented.

**Caveat at first-ship**: when the marketplace repo is published as a real GitHub repo (not this monorepo), the symlink target paths (`../../skills`) must remain valid. CC's per-CC-docs cache copying dereferences inter-marketplace symlinks correctly. But if Hazar publishes the marketplace by copying only the `plugins/startup-framework/` dir (without `../../skills/`), the symlinks break.

**Mitigation** (already in `RELEASING.md`): the release process explicitly publishes the entire monorepo as the marketplace, so the symlink targets are always reachable. The publish step is `git push` of this repo to `sf-marketplace`, not a cherry-pick.

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
claude plugin validate ./plugins/startup-framework --strict
claude plugin validate .
```

Update this file to reflect new state. Aim: zero errors, zero warnings at first-ship.
