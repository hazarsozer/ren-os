# Hook + Sibling-Module Path Registry

Where `sf-doctor` looks for sibling modules. Update this file (via PR) when a sibling module renames a path; the doctor's scripts will pick up the new path.

This file exists per team-lead's pushback on §3 of the sf-distribution plan: rather than hard-coding hook IDs that lifecycle-2 hadn't yet locked, surface them in a stable registry.

---

## SessionStart hook (owned by sf-lifecycle / `lifecycle-2`)

### What we grep for

The hook's registered `command` (as shipped in `hooks/hooks.json`) is:

```jsonc
{
  "description": "sf-wake-up: SessionStart context injection per ADR-008 (fresh sessions)",
  "type": "command",
  "command": "python3 \"$CLAUDE_PLUGIN_ROOT/hooks/wake-up/sf-wake-up.py\"",
  "timeout": 10
}
```

**Primary grep substring**: `sf-wake-up.py` (the hook is a Python script — `hooks.json`'s own `$comment` documents that the doctor greps for `sf-wake-up.py`).

**Secondary detection (defense in depth)**: the substring `sf-wake-up:` in the `description` field of the hook entry. If primary fails but secondary succeeds, report a degraded green: "✅ SessionStart hook found via description sentinel (command did not match — check script path)".

Behavior:

| Detection state | Doctor reports |
|---|---|
| `command` contains `sf-wake-up.py` AND matcher in `{startup, "*", omitted}` | `✅ SessionStart (sf-wake-up.py, matcher: <m>, timeout: <s>s)` |
| `command` matches but matcher is `compact`-only or similar | `⚠️ SessionStart matcher='<m>' — wake-up will not fire on fresh sessions` |
| `command` missing but description sentinel found | `⚠️ SessionStart description matches but command path is wrong — check ${CLAUDE_PLUGIN_ROOT}/hooks/wake-up/sf-wake-up.py exists` |
| Neither detector fires | `⚠️ SessionStart hook missing — run /ren:update or /reload-plugins` |

### Why `sf-wake-up.py` instead of `hooks/wake-up`

- More precise: the script name itself is the sentinel (not the parent directory) — defends against future path refactors that don't touch the script name.
- Unique enough across the plugin set per ADR-006 curation (no other plugin ships an `sf-wake-up.py`).
- The `sf-wake-up` prefix is stable; if the implementation language ever switches (e.g. back to `sf-wake-up.js`), widen the grep to `sf-wake-up\.(js|py)` here and in `check-plugins.sh`. (Historical note: this registry originally specified `.js` based on an early coordination message; the shipped hook has always been `.py` — fixed 2026-05-29, REVIEW H1.)

### When to update this

- lifecycle-2 renames the script → ping required; update primary substring.
- lifecycle-2 changes implementation language → ping; widen primary substring or accept both extensions.
- lifecycle-2 ships a SECOND SessionStart hook (e.g., the cache-verification probe under § 1.2) → add new substring entry below.

---

## Wiki layer references (owned by sf-onboarding / `onboarding-2`)

### What we read

`check-schemas.sh` walks `${CLAUDE_PLUGIN_OPTION_WIKIROOT}` looking for:

- `identity.md` (per `schemas.json#identity.path_pattern`)
- `projects/*/PROJECT.md`, `STATE.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `CONTEXT.md` (per `schemas.json#project-*.path_pattern`)
- `research/*.md`
- `decisions/*.md`
- `patterns/*.md`
- `log.md` (file-top schema_version)
- `skills/*/SKILL.md`

For each file: parse YAML frontmatter, extract `schema_version`, `framework_version`, `type`. Compare against `schemas.json#page_types[type].current`.

### When to update this

- onboarding-2 changes a path pattern → PR to `schemas.json` first (its `path_pattern` field) AND update this section.
- A new page-type is added → PR to `schemas.json` and this registry's path list.

---

## Marketplace + plugin manifest references

### What we read

- `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` — current installed version.
- `gh api repos/<org>/<repo>/contents/.claude-plugin/plugin.json` — latest published version. `<org>/<repo>` parsed from `repository` field of the installed `plugin.json`.

If user has `userConfig.rcChannel = true`: ALSO fetch from `<org>/ren-os-rc`'s repo.

### When to update this

- We change repo name from `ren-os` to something else → update path in `check-update.sh` + here.
- We restructure marketplace.json layout → update the gh api path here.

---

## How to propose a registry update

1. PR to this file with the new value.
2. Update the relevant `scripts/check-*.sh`.
3. Add a CHANGELOG entry under `### Changed` (registry updates are MINOR-bump material if they change behavior, PATCH if cosmetic).
4. Ping sf-distribution for review.

This file is itself authoritative — `check-plugins.sh` etc. import constants from here at script-load time (via shell-readable `# REGISTRY: KEY=value` markers).
