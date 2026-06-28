# sf-doctor — Output Format Reference

The exact shape of every section the doctor renders. Used by:
- The SKILL.md renderer at runtime
- The `--json` mode's output schema (defined inline below in § "`--json` output schema")
- The CI snapshot tests in `tests/golden/`

---

## Section 1 — ENVIRONMENT

```
▶ ENVIRONMENT
  Claude Code:        {status} {version}  ({constraint})
  Node.js:            {status} {version}  ({constraint})
  git:                {status} {version}
  gh CLI:             {status} {version}  (authenticated as {handle} | NOT authenticated)
  claude auth:        {status} ({email} | NOT logged in)
  OS:                 {status} {os-info}
  ANTHROPIC_API_KEY:  {status}
  Upstash key:        {status}
  OpenTelemetry:      {status} (configured | skipped — no OTLP endpoint configured)
  Snapshot retain:    {N}  (configurable via userConfig.snapshotRetain)
```

Status symbols:
- `✅` = present + valid
- `⚠️` = present but below recommended threshold or warning condition
- `❌` = missing or invalid (requires action)
- `⏭️` = skipped / optional / not applicable

Failure-state remediation:

```
gh CLI:             ❌ not found
                       → Install: https://cli.github.com/
                       → Or via package manager: brew install gh / apt install gh
                       → After install, run `gh auth login`

claude auth:        ❌ not logged in
                       → Run: claude auth login

ANTHROPIC_API_KEY:  ❌ not set
                       → export ANTHROPIC_API_KEY=sk-ant-... in your shell rc
                       → See: https://console.anthropic.com/settings/keys
```

---

## Section 2 — PLUGINS

```
▶ PLUGINS
  RenOS:    {status} v{version}  (installed via {marketplace-name})
  Superpowers:          {status} v{version}
  Skill Creator:        {status}
  claude-mem:           {status} v{version}  ({worker-status})
  Context Mode:         {status} v{version}  (ELv2 — SaaS distribution restricted; see LICENSES.md)
  context7:             {status}             (Upstash API key {ok|missing})
  claude-md-management: {status}
  Frontend Design:      {status}  ({reason if not installed})
  Hooks registered:     {status} SessionStart ({hook-name}, matcher: {matcher}, timeout: {s}s)
  Wiki:                 {status} {wikiRoot}  ({entry-count} entries, {project-count} projects)
```

Failure-state remediation:

```
claude-mem worker:   ❌ not running on :37777
                        → claude-mem's responsibility; try: /plugin reload claude-mem
                        → or restart your session

Hooks registered:    ⚠️  SessionStart hook missing
                        → Run /ren:update which re-registers hooks, OR /reload-plugins
```

The Context Mode entry ALWAYS surfaces the ELv2 caveat — even when green — because friends sometimes forget licensing applies indefinitely.

---

## Section 3 — SCHEMA VERSIONS

```
▶ SCHEMA VERSIONS  (per ADR-027)
  {page-type}:        {your-schema}  (current: {current-schema})   {status}{annotation}
  ...

  {summary line}
```

Status logic:
- `✅` your-schema == current-schema
- `⚠️ migration available` your-schema < current-schema AND your-schema >= supported_from
- `❌ schema vN is now beyond the N+3 deprecation window` your-schema < supported_from
- `⚠️ schema vN approaches deprecation (will become read-only in next major)` your-schema == supported_from-1 (early warning when `deprecated_below` is set)
- `❌ unknown page-type` (type field doesn't match any registered page-type — points to onboarding-2 schema-registry PR or a manually edited file)

Annotations (right-side of the line):

```
  identity.md:        1  (current: 2)   ⚠️  migration available
                                          → Run /ren:update to apply (see CHANGELOG for v1.3 schema changes)

  identity.md:        1  (current: 4)   ❌  schema v1 is now beyond the N+3 deprecation window
                                          → page is READ-ONLY; the framework will not write to it.
                                          → Recovery options:
                                            (a) Restore from snapshot at ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/
                                                and step through intermediate versions via /ren:update
                                            (b) Edit identity.md manually to schema v4 (see docs/RECOVERY.md
                                                "Schema beyond deprecation")
                                            (c) Discard if not valuable
```

Summary line, by precedence:
- All page-types green → `No schema migrations pending.`
- Any `⚠️ migration available` → `{N} page-type(s) have migrations available. Run /ren:update.`
- Any `❌ beyond deprecation` → `{N} page-type(s) stuck at deprecated schemas (read-only). See docs/RECOVERY.md "Schema beyond deprecation."`
- Mixed → enumerate.

For `project-state`, `project-roadmap`, `project-requirements`, `project-context`, `project-main`, `research`, `decision`, `pattern`: the per-line count is `(N files)` — e.g. `project-state: 1  (current: 1)   ✅  (4 files: sidecar, restore, era, idea-generator)`.

For `log-entry`: single file, single schema. No file-count annotation.

For `skill`: per-line annotation `(N friend-authored skills)` — distinct from framework-shipped skills (which don't have schema_version frontmatter; the doctor explicitly skips `${CLAUDE_PLUGIN_ROOT}/skills/`).

---

## Section 4 — FRAMEWORK UPDATE

```
▶ FRAMEWORK UPDATE
  Installed:  v{installed-version}
  Latest stable:  v{latest-stable}   {status}
  Latest RC:      v{latest-rc} | —    ({rc-status} | subscribe to ren-os-rc to receive release candidates)
  Update channel: {stable | rc}
```

Status:
- `✅ up to date` (installed == latest)
- `⚠️ update available: v{X}` (latest > installed via strict semver)
- `❌ installed version is ahead of latest published (downgrade or unstable)` (installed > latest — should not happen via `/ren:update` normally)
- `⚠️ network failure ({error})` (gh api call failed)

With `--install-mode`: section is replaced with `▶ FRAMEWORK UPDATE  ⏭️  skipped (install mode)`.
With `--post-update`: section is replaced with `▶ FRAMEWORK UPDATE  ✅ v{version} (just installed via /ren:update)`.

If `userConfig.rcChannel = true`: Latest stable AND Latest RC are both checked. Otherwise only stable is checked.

CHANGELOG excerpt is fetched + shown when an update is available:

```
  Latest stable:  v1.3.0   ⚠️ update available

  CHANGELOG v1.3.0 — 2026-08-15:
    ### Added
    - new optional field `phase` in identity.md frontmatter
    - new command /ren:audit-stack
    ### Schema
    - identity.md schema 1 → 2: scripted migration
  
  → Run /ren:update to install.
```

---

## Section 5 — BACKUP

```
▶ BACKUP  (per ADR-026)
  Wiki git remote:  {status} {remote-url | not configured}
                       → {action if applicable}
  Last commit:      {duration} ago, {ahead-count} commits ahead of {remote-name | any remote}
  Tarball backups:  {count} in ~/.startup-framework/backups/ (newest: {duration} ago)
```

Status escalation:
- `✅ remote configured` (remote present, last push <7d, push_ok)
- `⚠️ not configured` (no remote — gentle nudge)
- `⚠️⚠️ no remote AND >7d since last commit` (stronger nag per ADR-026)
- `❌ push failing` (remote present but `git push` returned error on last attempt — surfaced via `git config branch.main.remote` + cached push status)

Tarball line only present if any tarballs exist; otherwise that line is omitted.

---

## Section 8 — CONTEXT & TOKEN ECONOMICS

Script: `scripts/check-context.sh`  
Fragment format: `KEY|STATUS|VALUE|HINT` (STATUS ∈ `ok|warn|skip`)

```
▶ CONTEXT & TOKEN ECONOMICS
  MCP servers:       {icon} {count | (no ~/.claude.json)}  [{hint}]
  Enabled plugins:   {icon} {count}
  Framework skills:  {icon} {count}
  Skill size lint:   {icon} {ok-summary | offender-list}  [{hint}]
  CLAUDE.md global:  {icon} {N lines | (none)}  [{hint}]
  CLAUDE.md project: {icon} {N lines | (none)}  [{hint}]
  Auto-mode safety:  {icon} {mode-name}  [{hint}]
```

Fragment keys:

| Key | ok condition | warn condition | skip condition |
|---|---|---|---|
| `mcp_servers` | `~/.claude.json` present and readable | — | file absent |
| `enabled_plugins` | `~/.claude.json` present and readable | — | file absent |
| `framework_skills` | at least one `SKILL.md` found under `skills/` | — | none found |
| `skill_size_lint` | all skills < 500L + complete frontmatter | any skill ≥ 500L or missing frontmatter field | — |
| `claude_md_global` | `~/.claude/CLAUDE.md` ≤ 200 lines | `~/.claude/CLAUDE.md` > 200 lines | file absent |
| `claude_md_project` | `./CLAUDE.md` ≤ 200 lines | `./CLAUDE.md` > 200 lines | file absent |
| `auto_mode` | mode is `default` / `null` / other non-broad value | mode is `bypassPermissions` or `acceptEdits` | settings.json absent |

**Security invariant:** `auto_mode` prints only the mode name string. It NEVER prints an env value, token, or credential from `settings.json`.

Status → icon: `ok→✅  warn→⚠️  skip→·(dim)  error→❌`

---

## Section 9 — WIKI HEALTH

Script: `scripts/check-wiki-health.sh`  
Fragment format: `KEY|STATUS|VALUE|HINT` (STATUS ∈ `ok|warn|error|skip`)

```
▶ WIKI HEALTH
  Dead links:   {icon} {N dead links | 0 dead links}
  Stale pages:  {icon} {N (rel:days, …) | 0 pages > 90d}
  Heavy pages:  {icon} {N (rel:lines, …) | 0 pages > 500L}
  Health score: {icon} {N issue(s) across M pages}
```

Fragment keys:

| Key | ok condition | warn condition | error condition | skip condition |
|---|---|---|---|---|
| `dead_links` | 0 dead links | ≥ 1 dead link | — | — |
| `stale_pages` | 0 stale pages | ≥ 1 page > 90d without update | — | — |
| `heavy_pages` | 0 heavy pages | ≥ 1 page > 500L | — | — |
| `health_score` | 0 total issues | 1–5 total issues | > 5 total issues | wiki directory absent |

The `health_score` fragment is always last and summarises the entire section. When STATUS is `skip`, render the entire section as a single dim line:

```
▶ WIKI HEALTH  · (no wiki — run /ren:install to bootstrap)
```

Staleness threshold: 90 days (from `updated:` or `created:` frontmatter field).  
Heavy-page threshold: 500 lines.  
Dead-link check covers `[[wikilink]]` and relative `](path.md)` references; absolute `http://` / `https://` links are skipped.

---

## Final line

After all sections, one of:

- `All systems go.`  (all sections green / informational only)
- `{N} warning(s). See above for remediation.`  (any ⚠️)
- `{N} blocker(s). Address before continuing.`  (any ❌)

Exit code:
- `0` if all green or warnings only
- `1` if any blocker (`❌`)

---

## `--json` output schema

The `--json` mode emits this shape (canonical schema; no separate schema file ships):

```json
{
  "doctor_version": "1.0.0",
  "framework_version": "1.0.0",
  "timestamp_iso": "2026-05-28T20:00:00Z",
  "sections": {
    "environment": {"status": "ok|warn|error", "checks": [...]},
    "plugins": {...},
    "schema_versions": {...},
    "framework_update": {...},
    "backup": {...},
    "context": {
      "status": "ok|warn|skip",
      "checks": [
        {"key": "mcp_servers", "status": "ok|warn|skip", "value": "3", "hint": ""},
        {"key": "enabled_plugins", "status": "ok|warn|skip", "value": "4", "hint": ""},
        {"key": "framework_skills", "status": "ok|warn|skip", "value": "8", "hint": ""},
        {"key": "skill_size_lint", "status": "ok|warn", "value": "all skills < 500L + complete frontmatter", "hint": ""},
        {"key": "claude_md_global", "status": "ok|warn|skip", "value": "142 lines", "hint": ""},
        {"key": "claude_md_project", "status": "ok|warn|skip", "value": "312 lines", "hint": "token-heavy; loaded every session — trim or move detail into skills"},
        {"key": "auto_mode", "status": "ok|warn|skip", "value": "default", "hint": ""}
      ]
    },
    "wiki_health": {
      "status": "ok|warn|error|skip",
      "checks": [
        {"key": "dead_links", "status": "ok|warn", "value": "0 dead links", "hint": ""},
        {"key": "stale_pages", "status": "ok|warn", "value": "0 pages > 90d", "hint": ""},
        {"key": "heavy_pages", "status": "ok|warn", "value": "0 pages > 500L", "hint": ""},
        {"key": "health_score", "status": "ok|warn|error|skip", "value": "0 issue(s) across 47 pages", "hint": "GOOD"}
      ]
    }
  },
  "summary": {
    "status": "all-green|warnings|blockers",
    "warning_count": 0,
    "blocker_count": 0
  }
}
```

---

## CI snapshot tests

`tests/golden/` contains fixture wiki + plugin states with paired expected outputs. The CI workflow asserts byte-for-byte (modulo timestamps and durations, which get redacted to `<TS>` and `<DUR>`) for each fixture.

Fixtures:
- `tests/golden/all-green/` — fresh install, no drift
- `tests/golden/schema-warning/` — one page-type at v1, current is v2
- `tests/golden/schema-deprecation/` — one page-type at v1, supported_from is v2 (BLOCKER)
- `tests/golden/no-backup-remote/` — wiki has no git remote
- `tests/golden/install-mode/` — `--install-mode` skips update section
- `tests/golden/network-failure/` — gh api unreachable, doctor still renders cleanly

---

## § Deferred

The following scope was explicitly cut from H1 to keep the slice shippable:

- **Stable-ID rehydration for `--json` context + wiki_health:** The `--json` schema for `context` and `wiki_health` emits raw fragment keys. A future version should assign stable `id` fields to every check (matching the `key` values above) so downstream consumers can key on IDs rather than array position or label strings.

- **MCP-vs-CLI scope for `check-context.sh`:** The script currently reads `~/.claude.json` for MCP-server and plugin counts. It does NOT distinguish between MCP-native tools and tools exposed via the CLI plugin mechanism. A future version should enumerate the two sources separately (`mcp_servers_global`, `mcp_servers_project`) so the CONTEXT section can surface per-project overrides. Deferred because it requires parsing `projects.*.mcpServers` and cross-referencing `enabledPlugins`, which adds complexity without blocking the core health signal.
