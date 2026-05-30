# sf-doctor — Output Format Reference

The exact shape of every section the doctor renders. Used by:
- The SKILL.md renderer at runtime
- The `--json` mode's `output-schema.json`
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
  OpenTelemetry:      {status} ({otlp-endpoint} | skipped — no OTLP endpoint configured)
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
  Startup Framework:    {status} v{version}  (installed via {marketplace-name})
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
                        → Run /sf:update which re-registers hooks, OR /reload-plugins
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
                                          → Run /sf:update to apply (see CHANGELOG for v1.3 schema changes)

  identity.md:        1  (current: 4)   ❌  schema v1 is now beyond the N+3 deprecation window
                                          → page is READ-ONLY; the framework will not write to it.
                                          → Recovery options:
                                            (a) Restore from snapshot at ${CLAUDE_PLUGIN_DATA}/wiki-snapshots/
                                                and step through intermediate versions via /sf:update
                                            (b) Edit identity.md manually to schema v4 (see docs/RECOVERY.md
                                                "Schema beyond deprecation")
                                            (c) Discard if not valuable
```

Summary line, by precedence:
- All page-types green → `No schema migrations pending.`
- Any `⚠️ migration available` → `{N} page-type(s) have migrations available. Run /sf:update.`
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
  Latest RC:      v{latest-rc} | —    ({rc-status} | subscribe to sf-marketplace-rc to receive release candidates)
  Update channel: {stable | rc}
```

Status:
- `✅ up to date` (installed == latest)
- `⚠️ update available: v{X}` (latest > installed via strict semver)
- `❌ installed version is ahead of latest published (downgrade or unstable)` (installed > latest — should not happen via `/sf:update` normally)
- `⚠️ network failure ({error})` (gh api call failed)

With `--install-mode`: section is replaced with `▶ FRAMEWORK UPDATE  ⏭️  skipped (install mode)`.
With `--post-update`: section is replaced with `▶ FRAMEWORK UPDATE  ✅ v{version} (just installed via /sf:update)`.

If `userConfig.rcChannel = true`: Latest stable AND Latest RC are both checked. Otherwise only stable is checked.

CHANGELOG excerpt is fetched + shown when an update is available:

```
  Latest stable:  v1.3.0   ⚠️ update available

  CHANGELOG v1.3.0 — 2026-08-15:
    ### Added
    - new optional field `phase` in identity.md frontmatter
    - new command /sf:audit-stack
    ### Schema
    - identity.md schema 1 → 2: scripted migration
  
  → Run /sf:update to install.
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

See `output-schema.json` in this same skill directory. Roughly:

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
    "backup": {...}
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
