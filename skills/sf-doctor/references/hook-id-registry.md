# Hook + Sibling-Module Path Registry

Where `sf-doctor` looks for sibling modules. Update this file (via PR) when a sibling module renames a path; the doctor's scripts will pick up the new path.

This file exists per team-lead's pushback on §3 of the sf-distribution plan: rather than hard-coding hook IDs that lifecycle-2 hadn't yet locked, surface them in a stable registry.

---

## SessionStart hook (owned by sf-lifecycle / `lifecycle-2`)

### What we grep for

Per lifecycle-2's coordination message on 2026-05-28, the hook's registered `command` will be:

```jsonc
{
  "description": "sf-wake-up: SessionStart context injection (ADR-008)",
  "type": "command",
  "command": "node \"$CLAUDE_PLUGIN_ROOT/hooks/wake-up/sf-wake-up.js\"",
  "timeout": 10
}
```

**Primary grep substring**: `sf-wake-up.js`

**Secondary detection (defense in depth)**: the substring `sf-wake-up:` in the `description` field of the hook entry. If primary fails but secondary succeeds, report a degraded green: "✅ SessionStart hook found via description sentinel (command did not match — check script path)".

Behavior:

| Detection state | Doctor reports |
|---|---|
| `command` contains `sf-wake-up.js` AND matcher in `{startup, "*", omitted}` | `✅ SessionStart (sf-wake-up.js, matcher: <m>, timeout: <s>s)` |
| `command` matches but matcher is `compact`-only or similar | `⚠️ SessionStart matcher='<m>' — wake-up will not fire on fresh sessions` |
| `command` missing but description sentinel found | `⚠️ SessionStart description matches but command path is wrong — check ${CLAUDE_PLUGIN_ROOT}/hooks/wake-up/sf-wake-up.js exists` |
| Neither detector fires | `⚠️ SessionStart hook missing — run /sf:update or /reload-plugins` |

### Why `sf-wake-up.js` instead of `hooks/wake-up`

- More precise: the script name itself is the sentinel (not the parent directory) — defends against future path refactors that don't touch the script name.
- Unique enough across the plugin set per ADR-006 curation (no other plugin ships an `sf-wake-up.js`).
- The `sf-wake-up` prefix is stable; if implementation language switches (e.g. `sf-wake-up.py`), lifecycle-2 will ping me to bump the regex to `sf-wake-up\.(js|py)` or similar.

### When to update this

- lifecycle-2 renames the script → ping required; update primary substring.
- lifecycle-2 changes implementation language → ping; widen primary substring or accept both extensions.
- lifecycle-2 ships a SECOND SessionStart hook (e.g., the cache-verification probe under § 1.2) → add new substring entry below.

---

## Activity Feed status script (owned by sf-feed / `feed-2`)

### What we shell out to

Path: `skills/activity-feed/scripts/status.sh` (confirmed by feed-2 on 2026-05-28; lives inside the activity-feed skill, not directly under `feed/`).

`check-plugins.sh` invokes with 5s timeout. Resolved at runtime via `${CLAUDE_PLUGIN_ROOT}/skills/activity-feed/scripts/status.sh`.

### Actual JSON shape (per feed-2's shipped impl)

```json
{
  "remote": "git@github.com:friend-group/activity-feed.git",
  "last_sync_iso": "2026-05-28T14:30:00+00:00",
  "push_ok": true,
  "pending_commit_count": 0,
  "consecutive_push_failures": 0,
  "local_path": "/home/hazar/.startup-framework/activity-feed",
  "auth_ok": true,
  "auth_reason": null,
  "schema_version_expected": 1
}
```

All fields above are present in every successful response. `remote`, `last_sync_iso`, `auth_reason` may be `null` when not-yet-known or not-applicable. The two extra fields beyond the original sf-doctor spec are `auth_reason` (gh auth status stderr when `auth_ok=false`; `null` otherwise) and `schema_version_expected` (so doctor can render "schema N expected" alongside whatever it sees in actual log files).

### Exit-code semantics (CORRECTED per feed-2's actual impl)

| Exit | Meaning | Doctor's response |
|---|---|---|
| `0` | JSON printed successfully. Doctor parses + branches on JSON-encoded health fields. | See branching below. |
| `1` | Catastrophic failure (Python import broken, status.sh itself crashed) | `❌ Activity Feed: status.sh crashed — installation broken; reinstall via /sf:update` |

There is NO separate exit code for "not configured" or "unreachable" — those are encoded in the JSON fields. Specifically:

**Branching on JSON fields when exit == 0:**

| Condition | Doctor reports |
|---|---|
| `remote == null` (and `activityFeedUrl` unset) | `⏭️ disabled (activityFeedUrl not set)` |
| `remote != null` AND `auth_ok == true` AND `push_ok == true` | `✅ <remote> (last sync <last_sync_iso>)` |
| `auth_ok == false` | `❌ <remote> — auth failed: <auth_reason>` + remediation: `→ Run: gh auth login` |
| `push_ok == false` AND `consecutive_push_failures > 0` | `⚠️ <remote> — push failing (×<consecutive_push_failures>)` + remediation: `→ Check 'gh api repos/<remote>' or run 'git push' manually` |
| `pending_commit_count > 0` | append: `(<pending_commit_count> commit(s) pending push)` |
| `last_sync_iso == null` (first run before any sync) | append: `— first sync pending` |

### When to update this

- feed-2 changes the JSON shape → ping required; align doctor's branching.
- feed-2 changes path → ping; this registry entry updates.
- feed-2 bumps `feed-entry` schema_version via a migration → the migration directory takes care of it; this registry doesn't need updating.

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

If user has `userConfig.rcChannel = true`: ALSO fetch from `<org>/sf-marketplace-rc`'s repo.

### When to update this

- We change repo name from `sf-marketplace` to something else → update path in `check-update.sh` + here.
- We restructure marketplace.json layout → update the gh api path here.

---

## How to propose a registry update

1. PR to this file with the new value.
2. Update the relevant `scripts/check-*.sh`.
3. Add a CHANGELOG entry under `### Changed` (registry updates are MINOR-bump material if they change behavior, PATCH if cosmetic).
4. Ping sf-distribution for review.

This file is itself authoritative — `check-plugins.sh` etc. import constants from here at script-load time (via shell-readable `# REGISTRY: KEY=value` markers).
