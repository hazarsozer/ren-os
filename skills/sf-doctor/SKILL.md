---
name: sf-doctor
description: Use when the user runs /sf:doctor (or when /sf:install Stage 6 invokes it) to verify the framework is correctly installed and operating. Composes a four-section report (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE) plus a BACKUP section, runs read-only checks in parallel, and surfaces remediation paths for any failures. Never writes to the wiki.
version: 0.1.0
license: MIT
type: skill
schema_version: 1
framework_version: 1.0.0
owner_module: sf-distribution

contract:
  required_outputs:
    - "A human-readable report with five sections (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, BACKUP) plus a final summary line"
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
      - "hooks/hooks.json"
    write: []
    execute:
      - "scripts/check-env.sh"
      - "scripts/check-plugins.sh"
      - "scripts/check-schemas.sh"
      - "scripts/check-update.sh"
      - "scripts/check-backup.sh"
      - "scripts/check-permissions.sh"
      - "gh (read-only: gh api repos/<org>/sf-marketplace/contents/.claude-plugin/marketplace.json)"
  completion_conditions:
    - "All five status sections rendered (or a crashed check-script degraded to a per-section failure note without crashing the report)"
    - "Run is side-effect-free: nothing under the wiki or settings is created, modified, or deleted"
    - "With --permissions: no secret/env/token/header value appears anywhere in the output"
  output_paths: []
---

# sf-doctor

Verification command. Read-only. Side-effect-free.

Per ADR-010 (the original promise) + ADR-015 Stage 6 (the install touchpoint) + ADR-025 (the tech stack matrix it verifies) + ADR-027 (the schema drift surface).

## When to invoke

- User runs `/sf:doctor` directly to diagnose their install.
- `/sf:install` Stage 6 invokes `/sf:doctor --install-mode` for verification.
- `/sf:update` calls `/sf:doctor --post-update` after applying migrations.

## Flags

| Flag | Effect |
|---|---|
| (none) | Full report including FRAMEWORK UPDATE check (fetches marketplace) |
| `--install-mode` | Skip FRAMEWORK UPDATE check (just-installed; nothing to compare) |
| `--post-update` | Skip marketplace fetch; assume version is current (called from `/sf:update`) |
| `--json` | Emit machine-readable JSON instead of the human-readable report |
| `--section <name>` | Run only one section: `env` / `plugins` / `schemas` / `update` / `backup` |
| `--permissions` | Run the standalone read-only **permission audit** ("KEYS ON YOUR RING") instead of the status sections — enumerates MCP servers (name + transport + granted tool-keys), tallies `permissions.{allow,deny,ask}`, flags broad grants (bare `Bash`, `mcp__*`), and lists enabled plugins + hooks. Never prints secret/env values. See § Permission audit. |

## How it works

Four scripts run in parallel (read-only):

| Script | Section | Side effects |
|---|---|---|
| `scripts/check-env.sh` | ENVIRONMENT | None — only reads `claude --version`, `node --version`, env vars |
| `scripts/check-plugins.sh` | PLUGINS | None — reads plugin marketplace cache + `hooks/hooks.json` for hook registration |
| `scripts/check-schemas.sh` | SCHEMA VERSIONS | None — reads `schemas.json` + scans wiki YAML frontmatter |
| `scripts/check-update.sh` | FRAMEWORK UPDATE | Network read — `gh api` fetches marketplace.json from `<org>/sf-marketplace` |
| `scripts/check-backup.sh` | BACKUP | None — reads `.git/config` of `wikiRoot` for remote, last commit time |

The skill body (`SKILL.md`) is the renderer + parallel-fanout orchestrator. Each script outputs a structured fragment; the skill composes the human-readable report.

**On-demand (NOT in the parallel fan-out):** `scripts/check-permissions.sh` powers `--permissions`. It is a standalone read-only audit that prints its own self-contained "KEYS ON YOUR RING" report (not a `KEY|STATUS|VALUE|HINT` fragment), so it runs only when explicitly requested. See § Permission audit.

## Output format

See `reference.md` for the full format spec + every failure-state example.

The TL;DR shape:

```
$ /sf:doctor

▶ ENVIRONMENT
  Claude Code:        ✅ v2.1.150  (≥ 1.0.33 required)
  Node.js:            ✅ v22.10.0  (≥ 22.5 required)
  ...
  Snapshot retain:    3  (configurable via userConfig.snapshotRetain)

▶ PLUGINS
  Startup Framework:    ✅ v1.0.0  (installed via sf-marketplace)
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
                       → Recommend:  /sf:backup --setup <your-private-repo-url>

All systems go.

💡 Run /sf:doctor --permissions to audit which tool-keys are on your ring (keys ≠ instructions).
```

## Permission audit (`--permissions`)

`/sf:doctor --permissions` runs `scripts/check-permissions.sh` — a standalone, read-only **"KEYS ON YOUR RING"** audit. It answers one question: *which tool-keys are on your ring?*

**Framing — keys ≠ instructions.** Granting a tool hands Claude a key; it does NOT tell Claude to use it. The audit lists the keys you've handed out; it never claims Claude is using them.

What it reports (all read-only, no network):

- **MCP servers** by name + transport (`stdio`/`http`/`sse`) — global (`~/.claude.json#mcpServers`) and per-project (`projects.*.mcpServers`) — each with its count of explicitly-granted tool-keys (or a note that grants are wildcard-driven / approval-gated).
- **Permission rules** — `permissions.{allow,deny,ask}` from `~/.claude/settings.json` (+ a `settings.local.json` overlay if present), tallied by tool prefix.
- **Broad grants** — flags wide-open keys: bare `Bash` (every shell command), `mcp__*` (every tool on every server), and notes server-scoped `mcp__<server>__*` wildcards.
- **Enabled plugins** (`enabledPlugins` — a dict keyed `<plugin>@<marketplace>`) and **configured hooks** (by event).

**Security.** These config files are mode `0600` and hold secrets (MCP `env` values, HTTP `headers`, OAuth identifiers). The audit reads *structure only* — server names, transports, rule counts, tool prefixes. It NEVER prints an env value, header, command, arg, or token. (`scripts/tests/test_check_permissions.sh` seeds fake tokens and asserts they are absent from the output.)

**Onboarding touchpoint.** `/sf:install` Stage 7 runs `/sf:doctor --permissions` once, so a new friend sees their ring before first real use.

Tolerates every absence: no `settings.local.json`, empty per-project `mcpServers`, missing keys — it still renders a clean report and exits `0`.

## Contracts with peers

### With sf-onboarding (`onboarding-2`)

- `/sf:install` Stage 6 calls `/sf:doctor --install-mode`. This flag exists for that purpose.
- `/sf:install` Stage 1 environment check shares scripts with `check-env.sh` (single source of truth for "what does the framework need?"). At v1.0 they are duplicated; v1.1 should refactor `check-env.sh` to be importable by Stage 1.

### With sf-lifecycle (`lifecycle-2`)

- `check-plugins.sh` greps `hooks/hooks.json` for the literal substring documented in `references/hook-id-registry.md`. Current substring: `sf-wake-up.py` (the script name lifecycle ships per their CC_API_NOTES.md + hooks.json's `$comment`).
- lifecycle's wake-up hook MUST keep that script name (or coordinate a substring update via a PR to `hook-id-registry.md`).

### With sf-distribution (self)

- `check-schemas.sh` reads `skills/wiki-migration/schemas.json` as the authoritative registry.
- `check-update.sh` uses `gh api repos/<org>/sf-marketplace/contents/.claude-plugin/marketplace.json` to fetch the latest version. The org-and-repo-name come from `plugin.json#repository` — parsed at runtime.

## What this skill does NOT do

- Write to the wiki. Diagnostics only.
- Apply migrations. That's `/sf:update`.
- Install plugins. That's `/sf:install`.
- Modify hooks. That's `/sf:update` (or `/reload-plugins` for CC-internal refresh).
- Bypass the friend's consent. If `/sf:doctor` finds an issue, it reports + recommends; the friend acts.

## Failure modes

If a check-script crashes or hangs:
- Each script has a 10s timeout (enforced by the orchestrator).
- A crashed script reports its section as `❌ check failed: <error>` and the overall report still renders.
- The skill never blocks waiting for a hung script.

If `gh api` is rate-limited or offline:
- `check-update.sh` reports `⚠️ FRAMEWORK UPDATE: network failure (gh api): <err>` and continues.
- `/sf:doctor` exits successfully (non-zero exit is reserved for catastrophic failures only — missing skill files, malformed schemas.json, etc.).

## Eval

Binary assertions in `eval.json` validate:
- Output contains all five section headers (ENVIRONMENT, PLUGINS, SCHEMA VERSIONS, FRAMEWORK UPDATE, BACKUP)
- `--install-mode` skips FRAMEWORK UPDATE
- `--json` output is valid JSON conforming to `output-schema.json`
- Crashing any check-script does NOT cause the skill to crash
- `--permissions` lists every configured MCP server by name + transport, tallies `allow`/`deny`/`ask`, and flags broad grants (bare `Bash`, `mcp__*`)
- the permission audit NEVER prints secret/env/token values (backed by the hermetic fake-token-absence test) and tolerates all-absent config while exiting `0`
