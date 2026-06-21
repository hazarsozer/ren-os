---
name: doctor
description: Use when the user runs /ren:doctor (or when /ren:install Stage 6 invokes it) to verify the framework is correctly installed and operating. Composes a nine-section report (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, BACKUP, ROUTINES, CODE-MAP, CONTEXT & TOKEN ECONOMICS, WIKI HEALTH), runs read-only checks in parallel, and surfaces remediation paths for any failures. Never writes to the wiki.
version: 0.1.0
license: MIT
type: skill
schema_version: 1
framework_version: 1.0.0
owner_module: sf-distribution

contract:
  required_outputs:
    - "A human-readable report with nine sections (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, BACKUP, ROUTINES, CODE-MAP, CONTEXT & TOKEN ECONOMICS, WIKI HEALTH) plus a final summary line"
    - "With --permissions: a standalone read-only 'KEYS ON YOUR RING' audit (MCP servers by name+transport, allow/deny/ask tallies, broad-grant flags, plugins + hooks) that NEVER prints a secret/env/token/header value"
    - "With --json: machine-readable JSON of the same status sections + summary"
    - "Exit code 0 when no blocker (❌) is present; exit 1 only on a blocker"
  budgets:
    turns: 4
    files_written: 0
    duration_seconds: 60
  permissions:
    read:
      - "skills/wiki-migration/schemas.json"
      - "~/.startup-framework/wiki/**"
      - "~/.claude.json"
      - "~/.claude/settings.json"
      - "~/.claude/settings.local.json"
      - "~/.claude/CLAUDE.md"
      - "./CLAUDE.md"
      - "hooks/hooks.json"
    write: []
    execute:
      - "scripts/check-env.sh"
      - "scripts/check-plugins.sh"
      - "scripts/check-schemas.sh"
      - "scripts/check-update.sh"
      - "scripts/check-backup.sh"
      - "scripts/check-routines.sh"
      - "scripts/check-code-map.sh"
      - "scripts/check-context.sh"
      - "scripts/check-wiki-health.sh"
      - "scripts/check-permissions.sh"
      - "gh (read-only: gh api repos/<org>/ren-os/contents/.claude-plugin/marketplace.json)"
  completion_conditions:
    - "All nine status sections rendered (or a crashed check-script degraded to a per-section failure note without crashing the report)"
    - "Run is side-effect-free: nothing under the wiki or settings is created, modified, or deleted"
    - "With --permissions: no secret/env/token/header value appears anywhere in the output"
  output_paths: []
---

# sf-doctor

Verification command. Read-only. Side-effect-free.

Per ADR-010 (the original promise) + ADR-015 Stage 6 (the install touchpoint) + ADR-025 (the tech stack matrix it verifies) + ADR-027 (the schema drift surface).

## When to invoke

- User runs `/ren:doctor` directly to diagnose their install.
- `/ren:install` Stage 6 invokes `/ren:doctor --install-mode` for verification.
- `/ren:update` calls `/ren:doctor --post-update` after applying migrations.

## Flags

| Flag | Effect |
|---|---|
| (none) | Full report including FRAMEWORK UPDATE check (fetches marketplace) |
| `--install-mode` | Skip FRAMEWORK UPDATE check (just-installed; nothing to compare) |
| `--post-update` | Skip marketplace fetch; assume version is current (called from `/ren:update`) |
| `--json` | Emit machine-readable JSON instead of the human-readable report |
| `--section <name>` | Run only one section: `env` / `plugins` / `schemas` / `update` / `backup` / `routines` / `context` / `wiki-health` |
| `--permissions` | Run the standalone read-only **permission audit** ("KEYS ON YOUR RING") instead of the status sections — enumerates MCP servers (name + transport + granted tool-keys), tallies `permissions.{allow,deny,ask}`, flags broad grants (bare `Bash`, `mcp__*`), and lists enabled plugins + hooks. Never prints secret/env values. See § Permission audit. |

## How it works

Nine scripts run in parallel (read-only):

| Script | Section | Side effects |
|---|---|---|
| `scripts/check-env.sh` | ENVIRONMENT | None — only reads `claude --version`, `node --version`, env vars |
| `scripts/check-plugins.sh` | PLUGINS | None — reads plugin marketplace cache + `hooks/hooks.json` for hook registration |
| `scripts/check-schemas.sh` | SCHEMA VERSIONS | None — reads `schemas.json` + scans wiki YAML frontmatter |
| `scripts/check-update.sh` | FRAMEWORK UPDATE | Network read — `gh api` fetches marketplace.json from `<org>/ren-os` |
| `scripts/check-backup.sh` | BACKUP | None — reads `.git/config` of `wikiRoot` for remote, last commit time |
| `scripts/check-routines.sh` | ROUTINES | None — reads `wiki/routines/*.md` frontmatter (network tier + cron count vs plan cap) |
| `scripts/check-code-map.sh` | CODE-MAP | None — checks if `lean-ctx` binary is on PATH |
| `scripts/check-context.sh` | CONTEXT & TOKEN ECONOMICS | None — reads `~/.claude.json`, `~/.claude/settings.json`, plugin `SKILL.md` files, and CLAUDE.md files |
| `scripts/check-wiki-health.sh` | WIKI HEALTH | None — reads wiki `*.md` files for dead links, stale pages, and oversized pages |

The skill body (`SKILL.md`) is the renderer + parallel-fanout orchestrator. Each script outputs a structured fragment; the skill composes the human-readable report.

**On-demand (NOT in the parallel fan-out):** `scripts/check-permissions.sh` powers `--permissions`. It is a standalone read-only audit that prints its own self-contained "KEYS ON YOUR RING" report (not a `KEY|STATUS|VALUE|HINT` fragment), so it runs only when explicitly requested. See § Permission audit.

## Output format

See `reference.md` for the full format spec + every failure-state example.

The TL;DR shape:

```
$ /ren:doctor

▶ ENVIRONMENT
  Claude Code:        ✅ v2.1.150  (≥ 1.0.33 required)
  Node.js:            ✅ v22.10.0  (≥ 22.5 required)
  ...
  Snapshot retain:    3  (configurable via userConfig.snapshotRetain)

▶ PLUGINS
  RenOS:    ✅ v1.0.0  (installed via ren-os)
  Superpowers:          ✅ v5.1.0
  ...
  Hooks registered:     ✅ SessionStart (sf-wake-up)

▶ SCHEMA VERSIONS  (per ADR-027)
  identity.md:        1  (current: 1)   ✅
  ...

▶ FRAMEWORK UPDATE
  Installed:  v1.0.0
  Latest stable:  v1.0.0   ✅ up to date

▶ BACKUP
  Wiki git remote:  ⚠️  not configured
                       → Recommend:  /ren:backup --setup <your-private-repo-url>

▶ ROUTINES  (per ADR-034)
  Network tiers:   ✅ 2 routine(s), none on 'full' tier
  Quota headroom:  2/15 scheduled (max cap)

▶ CONTEXT & TOKEN ECONOMICS
  MCP servers:       ✅ 3
  Enabled plugins:   ✅ 4
  Framework skills:  ✅ 8
  Skill size lint:   ✅ all skills < 500L + complete frontmatter
  CLAUDE.md global:  ✅ 142 lines
  CLAUDE.md project: ⚠️  312 lines  (token-heavy; loaded every session — trim or move detail into skills)
  Auto-mode safety:  ✅ default

▶ WIKI HEALTH
  Dead links:   ✅ 0 dead links
  Stale pages:  ✅ 0 pages > 90d
  Heavy pages:  ✅ 0 pages > 500L
  Health score: ✅ 0 issue(s) across 47 pages

All systems go.

💡 Run /ren:doctor --permissions to audit which tool-keys are on your ring (keys ≠ instructions).
```

### Render instructions — CONTEXT & TOKEN ECONOMICS

`check-context.sh` outputs `KEY|STATUS|VALUE|HINT` fragments (STATUS ∈ `ok|warn|skip`). Render each as:

```
  {label}:  {icon} {VALUE}  [{HINT if non-empty}]
```

Status → icon mapping: `ok→✅  warn→⚠️  skip→·(dim)  error→❌`

Fragment keys and their display labels:

| Key | Label |
|---|---|
| `mcp_servers` | MCP servers |
| `enabled_plugins` | Enabled plugins |
| `framework_skills` | Framework skills |
| `skill_size_lint` | Skill size lint |
| `claude_md_global` | CLAUDE.md global |
| `claude_md_project` | CLAUDE.md project |
| `auto_mode` | Auto-mode safety |

The `auto_mode` line MUST NEVER print a secret or env value — it only prints the mode name (e.g. `default`, `bypassPermissions`) or the literal string `default` when not set.

### Render instructions — WIKI HEALTH

`check-wiki-health.sh` outputs `KEY|STATUS|VALUE|HINT` fragments (STATUS ∈ `ok|warn|error|skip`). Render each as:

```
  {label}:  {icon} {VALUE}
```

Fragment keys and their display labels:

| Key | Label |
|---|---|
| `dead_links` | Dead links |
| `stale_pages` | Stale pages |
| `heavy_pages` | Heavy pages |
| `health_score` | Health score |

The final `health_score` fragment is always the last line of this section and serves as the section summary. When STATUS is `skip` (no wiki directory), render the entire section as a single `·(dim)` line: `WIKI HEALTH  · (no wiki — run /ren:install to bootstrap)`.

## Permission audit (`--permissions`)

`/ren:doctor --permissions` runs `scripts/check-permissions.sh` — a standalone, read-only **"KEYS ON YOUR RING"** audit. It answers one question: *which tool-keys are on your ring?*

**Framing — keys ≠ instructions.** Granting a tool hands Claude a key; it does NOT tell Claude to use it. The audit lists the keys you've handed out; it never claims Claude is using them.

What it reports (all read-only, no network):

- **MCP servers** by name + transport (`stdio`/`http`/`sse`) — global (`~/.claude.json#mcpServers`) and per-project (`projects.*.mcpServers`) — each with its count of explicitly-granted tool-keys (or a note that grants are wildcard-driven / approval-gated).
- **Permission rules** — `permissions.{allow,deny,ask}` from `~/.claude/settings.json` (+ a `settings.local.json` overlay if present), tallied by tool prefix.
- **Broad grants** — flags wide-open keys: bare `Bash` (every shell command), `mcp__*` (every tool on every server), and notes server-scoped `mcp__<server>__*` wildcards.
- **Enabled plugins** (`enabledPlugins` — a dict keyed `<plugin>@<marketplace>`) and **configured hooks** (by event).

**Security.** These config files are mode `0600` and hold secrets (MCP `env` values, HTTP `headers`, OAuth identifiers). The audit reads *structure only* — server names, transports, rule counts, tool prefixes. It NEVER prints an env value, header, command, arg, or token. (`scripts/tests/test_check_permissions.sh` seeds fake tokens and asserts they are absent from the output.)

**Onboarding touchpoint.** `/ren:install` Stage 7 runs `/ren:doctor --permissions` once, so a new friend sees their ring before first real use.

Tolerates every absence: no `settings.local.json`, empty per-project `mcpServers`, missing keys — it still renders a clean report and exits `0`.

## Contracts with peers

### With sf-onboarding (`onboarding-2`)

- `/ren:install` Stage 6 calls `/ren:doctor --install-mode`. This flag exists for that purpose.
- `/ren:install` Stage 1 environment check shares scripts with `check-env.sh` (single source of truth for "what does the framework need?"). At v1.0 they are duplicated; v1.1 should refactor `check-env.sh` to be importable by Stage 1.

### With sf-lifecycle (`lifecycle-2`)

- `check-plugins.sh` greps `hooks/hooks.json` for the literal substring documented in `references/hook-id-registry.md`. Current substring: `sf-wake-up.py` (the script name lifecycle ships per their CC_API_NOTES.md + hooks.json's `$comment`).
- lifecycle's wake-up hook MUST keep that script name (or coordinate a substring update via a PR to `hook-id-registry.md`).

### With sf-distribution (self)

- `check-schemas.sh` reads `skills/wiki-migration/schemas.json` as the authoritative registry.
- `check-update.sh` uses `gh api repos/<org>/ren-os/contents/.claude-plugin/marketplace.json` to fetch the latest version. The org-and-repo-name come from `plugin.json#repository` — parsed at runtime.

## What this skill does NOT do

- Write to the wiki. Diagnostics only.
- Apply migrations. That's `/ren:update`.
- Install plugins. That's `/ren:install`.
- Modify hooks. That's `/ren:update` (or `/reload-plugins` for CC-internal refresh).
- Bypass the friend's consent. If `/ren:doctor` finds an issue, it reports + recommends; the friend acts.

## Failure modes

If a check-script crashes or hangs:
- Each script has a 10s timeout (enforced by the orchestrator).
- A crashed script reports its section as `❌ check failed: <error>` and the overall report still renders.
- The skill never blocks waiting for a hung script.

If `gh api` is rate-limited or offline:
- `check-update.sh` reports `⚠️ FRAMEWORK UPDATE: network failure (gh api): <err>` and continues.
- `/ren:doctor` exits successfully (non-zero exit is reserved for catastrophic failures only — missing skill files, malformed schemas.json, etc.).

## Eval

Binary assertions in `eval.json` validate:
- Output contains all nine section headers (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, BACKUP, ROUTINES, CODE-MAP, CONTEXT & TOKEN ECONOMICS, WIKI HEALTH)
- `--install-mode` skips FRAMEWORK UPDATE
- `--json` output is valid JSON conforming to the `--json` output schema specified in `reference.md` § "`--json` output schema"
- Crashing any check-script does NOT cause the skill to crash
- `--permissions` lists every configured MCP server by name + transport, tallies `allow`/`deny`/`ask`, and flags broad grants (bare `Bash`, `mcp__*`)
- the permission audit NEVER prints secret/env/token values (backed by the hermetic fake-token-absence test) and tolerates all-absent config while exiting `0`
- ROUTINES flags any routine on the `full` network tier and surfaces defined-cron-routines vs the plan cap; skips cleanly when no `wiki/routines/` exists
