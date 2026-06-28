# Stage 2 — Required plugin install

Per ADR-015 Stage 2 (with 2026-05-28 amendments) + ADR-010 hook ordering coordination. Six plugins; ordered so hooks register in the right priority order.

## Plugin list (in install order)

| # | Plugin | Source | Why this order |
|---|---|---|---|
| 1 | **Context Mode** | `mksglu/context-mode` (marketplace add first, then install) | Most-specific hooks (tool-call sandbox); must register before broader hooks per ADR-010 |
| 2 | **claude-mem** | `thedotmack/claude-mem` (marketplace add first) | Cross-session memory; SessionEnd hook ordering matters per ADR-010 |
| 3 | **Superpowers** | `superpowers@claude-plugins-official` (Anthropic marketplace already registered) | Methodology skills + brainstorming; expects sub-agent + worktree skills active |
| 4 | **Skill Creator** | `anthropics/skills` (marketplace add first; install `skill-creator@anthropic-agent-skills`) | Self-improvement infrastructure; Layer 1 optimizer needs ANTHROPIC_API_KEY (Stage 1 verified) |
| 5 | **context7** | `context7@claude-plugins-official` | Version-aware doc lookup; Upstash key from Stage 1 |
| 6 | **claude-md-management** | `claude-md-management@claude-plugins-official` | CLAUDE.md hygiene; complementary to `/ren:wrap` per ADR-009 amendment |

## Pin-version registry

Sf-distribution owns the pinned-version registry file. Read it at stage start (per plan §5.2 third bullet). Format expected (subject to sf-distribution's final shape):

```json
{
  "schema_version": 1,
  "framework_version": "1.0.0",
  "plugins": {
    "context-mode":         { "version": "^x.y.z", "marketplace": "mksglu/context-mode", "id": "context-mode@context-mode" },
    "claude-mem":           { "version": "^x.y.z", "marketplace": "thedotmack/claude-mem", "id": "claude-mem" },
    "superpowers":          { "version": "5.1.0",  "marketplace": "claude-plugins-official", "id": "superpowers@claude-plugins-official" },
    "skill-creator":        { "version": "^x.y.z", "marketplace": "anthropics/skills", "id": "skill-creator@anthropic-agent-skills" },
    "context7":             { "version": "^x.y.z", "marketplace": "claude-plugins-official", "id": "context7@claude-plugins-official" },
    "claude-md-management": { "version": "^x.y.z", "marketplace": "claude-plugins-official", "id": "claude-md-management@claude-plugins-official" }
  }
}
```

If the registry file isn't present yet (sf-distribution hasn't shipped or wasn't read correctly), Stage 2 surfaces a clear error and refuses to install with un-pinned versions. We never floating-install.

## Per-plugin procedure

For each plugin, in order:

### 1. Pre-check

Run `/plugin list` (or the Claude Code equivalent). If the plugin is already installed at the pinned version, mark it complete in `stage_artifacts.2.plugins_installed` and skip to the next.

If the plugin is installed at a DIFFERENT version, surface the mismatch:

```
Plugin <name> is installed at version X but framework pinned Y.
  Either:
    /plugin uninstall <id> && /ren:install --redo-stage 2
  (or accept the mismatch and continue at your own risk — say "continue")
```

Default: refuse. Pinned versions matter per ADR-006.

### 2. Add marketplace if needed

If the plugin's marketplace isn't already registered (e.g. `mksglu/context-mode`), run:

```
/plugin marketplace add <marketplace-source>
```

Capture stdout/stderr. On error, abort Stage 2 with the error surfaced.

### 3. Install

Run:

```
/plugin install <plugin-id>@<marketplace>
```

(For plugins already registered in `claude-plugins-official`, the marketplace add step is a no-op.)

Wait for the install to complete. On success, the plugin's hooks become active in the current session per Claude Code's plugin contract.

### 4. Brief verification

After each install, run `/plugin list` and confirm:

- The plugin name appears in the installed list.
- The version matches the pin.

If yes, mark it complete in state and move on. If no, abort Stage 2 with the discrepancy.

### 5. Append to checkpoint

```json
{
  "stage_artifacts": {
    "2": {
      "plugins_installed": [
        { "name": "context-mode", "version": "x.y.z" },
        { "name": "claude-mem", "version": "x.y.z" },
        ...
      ]
    }
  }
}
```

Persist atomically. Re-runs resume at the first non-installed entry.

## Friend-facing summary

After all 6 plugins:

```
Stage 2 — required plugins installed:
  ✓ context-mode         x.y.z
  ✓ claude-mem           x.y.z
  ✓ superpowers          5.1.0
  ✓ skill-creator        x.y.z
  ✓ context7             x.y.z
  ✓ claude-md-management x.y.z
```

## Failure modes

- **Network unreachable** during `/plugin install` → abort Stage 2; checkpoint records which plugins succeeded; re-run picks up at the failing one.
- **Marketplace not found** (e.g. typo in registry) → abort with the marketplace string surfaced; surfaces as a framework bug, not a friend problem.
- **License rejected during install prompt** → abort Stage 2; friend can re-run after reviewing the license. Don't auto-accept.
- **Plugin version-bump removed a feature we depend on** → flag in Stage 6 doctor; for Stage 2's purposes, install the pinned version and move on.

## What this stage deliberately does NOT do

- Doesn't ask about conditional plugins (Frontend Design, Ralph). Those live in Stage 3's conditional half.
- Doesn't toggle phase-gated Superpowers skills. Per ADR-022 phase question is informational only; toggling is the friend's call, not the orchestrator's.
- Doesn't run skill activation tests. Skill Creator's Layer 1 description optimizer can be invoked manually post-install if needed; Stage 6 doctor verifies activation matchers smoke-test.

## Cross-references

- ADR-006 (curated stack) — the 6 plugins
- ADR-010 (hook ordering) — install order rationale
- ADR-015 Stage 2 (2026-05-28 amendment) — context7 + claude-md-management additions
- plan §5.2 — sf-distribution registry contract
