---
title: "lean-ctx (yvgude) — Context Mode Competitor with AST + Knowledge Graph"
type: research
source_url: https://github.com/yvgude/lean-ctx
source_fetched: 2026-05-28
license: Apache-2.0 + MIT (dual)
version_at_capture: v3.6.21
ingested: 2026-05-28
tags: [token-efficiency, ast-compression, knowledge-graph, memory, rust, foreground-research, context-mode-alternative]
status: ingested
related: [context-mode, claude-mem, memory-architecture-alternatives, ecc-everything-claude-code]
---

# lean-ctx (yvgude) — Context Mode Competitor with AST + Knowledge Graph

## TL;DR

**Genuine competitor to Context Mode (ADR-002).** lean-ctx is a "cognitive context layer" for AI coding agents — Rust-based single binary, **dual-licensed Apache-2.0 + MIT** (more permissive than Context Mode's ELv2), 62 MCP tools (vs Context Mode's 11), tree-sitter AST compression across 21 languages, knowledge graph with temporal validity, browser dashboard with real-time token tracking. **Worth considering as a swap or supplement.** v3.6.21, 2.2K stars (gained 1,800+ in 4 months), daily release cadence.

## Architecture (3 layers)

### Layer 1: Compression
- **10 file read modes**: `full`, `map`, `signatures`, `diff`, `lines:N-M`, others
- **56 shell pattern modules + 270 passthrough rules** (git, npm, cargo, docker, kubectl, terraform)
- **Tree-sitter AST** for structural understanding across 21 languages (since v1.5.0; replaced regex extractor)
- Compression ratios: file reads 60–99% reduction, shell output 60–90%, cached re-reads cost ~13 tokens

### Layer 2: Memory
- **Session memory (CCP)** persists facts/decisions across chats
- **Knowledge graph** with temporal validity windows
- **Property graph**: multi-edge code graph (imports, calls, exports, type references)
- Structured recovery queries survive compaction

### Layer 3: Governance
- **Context Manager browser dashboard** with real-time token tracking
- **Budget profiles + throttling policies**
- **Cryptographic context proofs** (4-layer verification of what was sent)

Total: **62 MCP tools**, 51+ documented.

## Architectural advantages over Context Mode

| Feature | Context Mode (mksglu) | lean-ctx (yvgude) |
|---|---|---|
| License | ELv2 (SaaS-restricted) | **Apache-2.0 + MIT (permissive)** |
| Approach | Subprocess sandboxing | **AST compression + read modes** |
| MCP tools | 11 | **62** |
| Languages | (language-agnostic sandboxing) | **21 languages with tree-sitter** |
| Shell handling | Subprocess + structured event capture | **270 passthrough rules + pattern modules** |
| Memory | Per-project SQLite + session_resume snapshot | **Knowledge graph + temporal validity** |
| Code graph | None | **Property graph (imports/calls/exports/types)** |
| Runtime | Node.js subprocess | **Single Rust binary, no runtime deps** |
| Daemon | No (subprocess only) | Optional `lean-ctx serve` HTTP mode |
| Dashboard | `ctx_insight` (90 metrics) | **Browser dashboard with real-time tracking** |
| Budget controls | None | **Budget profiles + throttling** |
| Stars (proxy for maturity) | ~ (not captured) | 2.2K (1,800+ gained in 4 months) |

## Install path

```bash
lean-ctx setup
lean-ctx init --agent claude
```

Auto-detects Claude Code (and other 28 AI coding agents — Cursor, Copilot, Windsurf, Codex, Gemini, etc.). Activates MCP + shell hooks. Single restart of shell + editor needed.

Disable: `lean-ctx-off`. Per-project config: `.lean-ctx.toml`.

## License: Apache-2.0 + MIT (dual)

Significantly more permissive than Context Mode's ELv2. **No SaaS restriction.** This matters if friend group ever commercializes the framework as a hosted service.

## How this informs the framework

### The honest evaluation

lean-ctx is **objectively more comprehensive than Context Mode** on most metrics:
- More permissive license (no SaaS restriction)
- More tools (62 vs 11)
- Tree-sitter AST (Context Mode doesn't have)
- Knowledge graph (Context Mode doesn't have)
- Code property graph (Context Mode doesn't have)
- Browser dashboard with budget profiles (Context Mode has `ctx_insight` but different scope)
- Rust single binary (cleaner than Context Mode's Node.js dependency)

**But:**
- lean-ctx is newer (4 months, 2.2K stars) than Context Mode (status uncertain from our research but probably similar age + maturity)
- lean-ctx has a much larger MCP surface area (62 tools) — could affect prompt cache prefix sensitivity per ADR-008
- lean-ctx's memory layer overlaps with both claude-mem AND our wiki — three layers all trying to do "remember things across sessions" creates collision risk
- Context Mode's specific value (subprocess isolation for tool outputs) is mechanically distinct from lean-ctx's AST compression — they're not direct equivalents

### Three reasonable positions on this

**Position A: Swap Context Mode for lean-ctx in ADR-002.**
- Pro: more permissive license, more tools, better architectural fit with our "files + git" philosophy (Rust single binary)
- Con: less battle-tested, memory-layer overlap with claude-mem and wiki, larger MCP surface

**Position B: Keep Context Mode, document lean-ctx as alternative.**
- Pro: Context Mode is already in ADR-002 and tested in our research; switching costs effort + reopens decisions
- Con: ELv2 license restriction is real if future commercialization happens

**Position C: Use both — Context Mode for tool-output sandboxing + lean-ctx for AST + knowledge graph.**
- Pro: best of both
- Con: significant MCP surface area collision risk, hook ordering complexity worse than ADR-010 already accommodates, costs friends 2 plugin installs for same problem area

### Recommendation pending discussion

I lean toward **Position B (keep Context Mode for now, document lean-ctx as alternative)** for v1, with a note in ADR-002's sunset review triggers that adds: "If Context Mode's ELv2 becomes a friction point OR lean-ctx demonstrates stable production use across friend group, reconsider swap."

Reason: we've already filed ADR-002 with Context Mode + reasoning. Swapping requires substantial amendment + re-validation. The improvement lean-ctx offers is real but not urgent. Context Mode works; the SaaS restriction is theoretical at the friend-group level for now.

**But Position A has real merit** and the user should decide.

### Knowledge graph note

lean-ctx's knowledge graph with temporal validity is the **first time** we've seen this pattern in our research base (Zep does similar via Neo4j but is out-of-scope per memory-architecture-alternatives.md). Worth knowing about as a v2 idea even if we don't adopt now.

## Tensions / open questions

1. **Memory layer collision risk** if we adopt lean-ctx alongside claude-mem (both have memory) and our wiki (team-level). Three layers attempting to remember things may collide on lifecycle hooks per ADR-010.
2. **MCP surface bloat** — 62 tools is a lot. Adds to the "/" autocomplete clutter and the prompt prefix size. ADR-008's prompt cache constraint depends on system prompt prefix size; many MCP tools may bloat that.
3. **Maturity gap** — 4 months / 2.2K stars vs claude-mem's 46-89K and Superpowers' 150K+. Newer plugins carry bus-factor + sustainability risk (per ADR-007).
4. **Daily release cadence** — exciting but could mean instability. Pinning a specific version (per ADR-006/015) is critical.
5. **Tree-sitter coverage** — 21 languages is great but the friend group's stack (Python, TypeScript, Go, Rust) is well-covered. No gap for our use case specifically.

## Connections to prior research

| Prior source | Connection |
|---|---|
| Context Mode | Direct competitor; this synthesis compares head-to-head |
| claude-mem | lean-ctx's memory layer overlaps; collision risk |
| Memory Architecture Alternatives | Knowledge graph pattern echoes Zep's approach |
| ECC | Like ECC, lean-ctx aims to be a comprehensive harness-level tool; both compete for "the layer we sit on" |
| ADR-002 (Token-Efficiency Stack) | Direct swap candidate or alternative-documented |
| ADR-007 (Provider-Vetting) | yvgude single maintainer + 4-month-old project = bus-factor concern but architecture is simple |
| ADR-010 (Hook Ordering) | 62 MCP tools + lifecycle hooks increase hook-coordination complexity |

## Followups

- If we decide to evaluate Position A (swap), need actual usage testing of lean-ctx in real Claude Code workflows
- Check whether `lean-ctx serve` HTTP mode is the daemon footprint (if so, would still be plugin-internal per ADR-003)
- Investigate the cryptographic context proofs feature — security implication worth understanding
- Browser dashboard for token tracking — could substitute for Nate Herk's separate dashboard recommendation in ADR-015 onboarding

## Reference

- Repo: https://github.com/yvgude/lean-ctx
- Product page: https://leanctx.com/
- Comparison page (not fetched): https://leanctx.com/compare/
- Author: yvgude
- Fetched: 2026-05-28
- Version at capture: v3.6.21
- License: Apache-2.0 (primary) + MIT (portions)
- Maturity: 2.2K stars (1.8K gained in 4 months), 194 releases, 28 AI agents supported
