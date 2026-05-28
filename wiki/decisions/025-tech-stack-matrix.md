---
title: "ADR-025: Tech Stack Matrix — Required Tools, Optional Tools, OS Support"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [context-mode, claude-mem, context7, superpowers, skill-creator]
affects-components: [install, doctor, distribution, system-requirements]
relates-to: [015-onboarding, 019-framework-distribution, 023-v1-scope-fence]
---

# ADR-025: Tech Stack Matrix

## Context

The framework depends on specific tools and runtime versions on each friend's machine. Without explicit documentation, friends hit "missing tool" or "version too old" errors mid-install and bounce off. ADR-015 already enumerates `/sf:install` Stage 1 environment checks; this ADR formalizes the **complete required stack matrix** + the recommended-but-optional surface, so contributors and friends know what to expect.

## Decision

### Required runtime tools

These MUST be present and functional on the friend's machine before `/sf:install` will complete:

| Tool | Why | Minimum version | Verified in |
|---|---|---|---|
| **Claude Code** | The harness our framework wraps | 1.0.33+ (Context Mode requirement) | `/sf:install` Stage 1 + `/sf:doctor` |
| **git** | Wiki self-sync + Activity Feed + marketplace clone | Any modern version (2.20+) | Stage 1 + doctor |
| **gh CLI** | Marketplace access (read collaborator) + Activity Feed push (write collaborator) | Latest stable | Stage 1 (with `gh auth status` check) + doctor |
| **Node.js** | Required by claude-mem, Context Mode, context7, and others | **22.5+** (Context Mode floor) | Stage 1 + doctor |

Note: Node.js 22.5 is the floor because Context Mode documented it. Friends on Node 18 or 20 LTS will need to upgrade. `/sf:doctor` should detect the version mismatch and provide a friendly upgrade hint (e.g., "Install nvm + run `nvm install 22 && nvm use 22`"), not just fail silently.

### Auto-installed dependencies (no friend action needed)

| Tool | Auto-installed by | Notes |
|---|---|---|
| **Bun** | claude-mem during its install | Friends don't need to install Bun themselves |
| **uv** (only if claude-mem needs it for vector search) | claude-mem if applicable | Per claude-mem's documentation |

### Optional / recommended tools

Friends may install these if their projects need them. The framework doesn't require them.

| Tool | When useful |
|---|---|
| **uv** | If friend works in Python (your CLAUDE.md default; framework doesn't require it) |
| **Docker / OrbStack** | If friend works on containerized projects (per-project concern; not framework) |
| **A specific cloud CLI** (gcloud, aws-cli, etc.) | Per-project domain dependency |

These are friend's choice; framework doesn't install them, doesn't check them.

### API keys + accounts

These are required for the framework's full functionality:

| Credential | Used by | How obtained |
|---|---|---|
| `ANTHROPIC_API_KEY` | Skill Creator's Layer 1 description-optimizer (per ADR-006 caveat) | Friend's Claude account → settings → API keys |
| Upstash API key for context7 | context7's docs lookup MCP | `/sf:install` Stage 3 walks friend through Upstash OAuth flow |
| **GitHub account** | Marketplace access + Activity Feed; `gh auth login` covers this | Standard GitHub account; `gh auth login` flow |

Stage 1 of `/sf:install` checks each is set/authenticated and provides guidance if not.

### OS support matrix

| OS | Support level | Notes |
|---|---|---|
| **Linux** | Primary, well-tested | Most plugins authored on Linux first |
| **macOS** | Primary, well-tested | Friends on Mac (e.g., your MacBook Air) supported |
| **Windows native** | Works with caveats | claude-mem requires Node-on-PATH (per their README warning); Context Mode notes CUDA-parallelism issues; some plugin install paths assume Unix conventions |
| **Windows + WSL** | **Recommended Windows option** | WSL provides Unix environment + tooling compatibility. Friends on Windows are encouraged to develop in WSL rather than fight native Windows quirks |

`/sf:install` detects OS + Windows-vs-WSL during Stage 1 and applies platform-specific guidance.

### Disk space + growth

Initial install footprint (approximate):

- Plugins: ~500MB total (claude-mem + Context Mode binaries + Superpowers skills + others)
- claude-mem's ChromaDB: starts ~600MB (ONNX embedding models); **grows with use** (no documented cap)
- Context Mode's per-project SQLite: starts small; grows with sessions
- Wiki + Activity Feed: text only, negligible

**Storage growth is unbounded over time** for claude-mem + Context Mode. Friends with limited disk should monitor. Flagging as a v2 concern (per ADR-023's V2+ list): a `/sf:tidy` skill that helps friends prune old observations / archived projects to reclaim space.

### Hardware requirements

No specific minimums beyond "a typical dev laptop." Friends with very low-spec hardware (e.g., constrained chromebooks) may struggle with claude-mem's local ONNX inference. Not framework concern; flag as future-edge-case.

### What `/sf:doctor` verifies

Per ADR-010 + ADR-015, `/sf:doctor` is the runtime verification command. This ADR's tech stack matrix is what `/sf:doctor` actually checks:

```
$ /sf:doctor

Claude Code: ✅ v1.0.45 (≥ 1.0.33 required)
git: ✅ v2.41.0
gh CLI: ✅ v2.40.0 (authenticated as <handle>)
Node.js: ✅ v22.10.0 (≥ 22.5 required)
OS: ✅ Linux 6.18 (PopOS)

Plugins:
  Superpowers: ✅ v5.1.0
  Skill Creator: ✅ installed
  claude-mem: ✅ v6.5.0 (worker running on :37777)
  Context Mode: ✅ v1.10.2
  context7: ✅ installed (Upstash API key OK)
  claude-md-management: ✅ installed

Activity Feed: ✅ <our-org>/activity-feed (last sync 12 min ago)

Wiki: ✅ ~/.startup-framework/wiki/ (12 entries, 4 projects)

Framework: ✅ v1.0.0 (no updates available)

API keys:
  ANTHROPIC_API_KEY: ✅ set
  Upstash: ✅ set

OpenTelemetry: ⏭️ skipped (no OTLP endpoint configured)

Disk usage (informational):
  Plugins: 487 MB
  claude-mem DB: 1.2 GB
  Context Mode (across 4 projects): 234 MB
  Wiki: 142 KB

All systems go.
```

When something's missing, `/sf:doctor` offers remediation:
```
gh CLI: ❌ not found
    → Install: https://cli.github.com/
    → Or via package manager: brew install gh / apt install gh
    → After install, run `gh auth login`
```

## Consequences

**Easier:**
- Friends know exactly what's needed before they start `/sf:install`
- `/sf:doctor` becomes a real diagnostic tool, not a tick-box
- Storage growth is honest (we don't pretend the framework is free)
- Windows-on-WSL recommendation prevents friends from fighting native-Windows quirks

**Harder:**
- Node 22.5+ minimum may be friction for friends on older LTS who don't want to upgrade
- API key + Upstash + GitHub all-required is more credentials than a typical CC plugin demands; we document this honestly
- Disk growth has no automatic cleanup → friends are responsible for monitoring (v1)

**Now impossible:**
- "Just install the framework and don't think about anything" — there's a real environment matrix friends must satisfy
- Running on Node 18 or older (would break Context Mode)

**Sunset review trigger conditions:**
- A plugin in our stack drops Node 22.5 floor (newer minimum) — adapt
- A plugin we adopt eliminates a credential requirement (e.g., context7 becomes free-tier without auth) — adapt
- Disk growth becomes a real friend-blocker → ship `/sf:tidy` earlier than v2
- Anthropic ships official Windows support for Claude Code that obviates WSL → adapt OS matrix

## Alternatives considered

### A) Use lowest-common-denominator Node version (e.g., Node 18 LTS)

**Considered shape**: Floor at Node 18 LTS; refuse to adopt plugins that need newer.

**Why rejected**: Would mean rejecting Context Mode (needs 22.5+) which is already in our stack per ADR-002. Not worth losing token-efficiency for "older Node compatibility."

### B) Hard-require uv

**Considered shape**: uv as a framework requirement, not just per-friend preference.

**Why rejected per user direction**: uv is YOUR preference, not friend group's universal preference. Other friends may use pip, poetry, or no Python at all. Framework should be language-agnostic at v1.

### C) Refuse to run on native Windows

**Considered shape**: Force WSL or refuse to install.

**Why rejected**: Some friends might have native-Windows-only setups (gaming rigs, etc.). Document caveats, recommend WSL, but don't refuse. Friends can choose their pain.

### D) Bundle a Node manager (nvm, fnm, volta)

**Considered shape**: Framework's install script installs a Node manager + the right version automatically.

**Why rejected**: Massive scope creep. We're not a Node distribution. Document the requirement; let friends use whatever Node manager they prefer.

### E) Skip OS-specific guidance; "it'll work on your OS or it won't"

**Considered shape**: Don't differentiate Linux/macOS/Windows; same install everywhere.

**Why rejected**: Some plugins have documented OS-specific issues (claude-mem's PATH note, Context Mode's CUDA notes). Pretending those don't exist sets friends up to hit them blindly. Be honest about platform support.

## Open questions for implementation phase

1. **Friendly Node upgrade guidance** — when `/sf:doctor` finds Node < 22.5, what's the exact recommended message? Different OSes have different best paths (nvm vs. fnm vs. brew vs. apt). Default to nvm + cross-platform note, but doctor could detect OS + tailor.

2. **What if a friend doesn't have a GitHub account?** Realistically friends in our target audience all have one (this is a friend-group startup tool), but the install should fail with a clear message rather than crash.

3. **Disk-growth telemetry** — should `/sf:doctor` warn when claude-mem DB exceeds N GB? What threshold? Soft warn at 5GB, hard warn at 20GB? Defer to implementation; doctor should at least surface the number even without thresholds.

4. **Auto-install Bun?** claude-mem does this; should we duplicate the install during Stage 1 if it's missing, or trust claude-mem's auto-install? Probably trust claude-mem; one less thing to manage.

5. **`/sf:tidy` skill design** — when this v2 skill ships, what does it actually do? claude-mem prune-old-observations? Context Mode purge-stale-projects? Wiki orphan-page archival? Out of scope for ADR-025; flag for v2 ADR.

## References

- `wiki/research/context-mode.md` — Node 22.5+ requirement + Windows CUDA caveats
- `wiki/research/claude-mem.md` — Bun auto-install + Windows Node-on-PATH note
- `wiki/research/context7.md` — Upstash API key requirement
- `wiki/research/superpowers.md` — per-harness independence + multi-harness support
- `wiki/research/skill-creator.md` — ANTHROPIC_API_KEY requirement for Layer 1
- ADR-006 (Curated Stack) — plugin set that drives this matrix
- ADR-010 (Hook Ordering Coordination) — `/sf:doctor` defined here, this ADR populates what it checks
- ADR-015 (Onboarding) — Stage 1 environment check, this ADR formalizes the check list
- ADR-019 (Framework Distribution) — `gh` requirement and marketplace access
- ADR-023 (V1 Scope Fence) — `/sf:tidy` flagged as v2
