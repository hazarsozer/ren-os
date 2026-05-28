---
title: "ADR-024: Cross-LLM Portability — Claude-Code-Only in v1; Content Portable by Default"
status: accepted
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: [superpowers, claude-mem, context-mode, ecc-everything-claude-code, lean-ctx]
affects-components: [scope, distribution, wiki, content]
relates-to: [001-harness-vs-framework-terminology, 006-curated-stack, 023-v1-scope-fence]
---

# ADR-024: Cross-LLM Portability — Claude-Code-Only in v1; Content Portable by Default

## Context

The friend group uses Claude as primary (per the user's CLAUDE.md preferences) but Gemini Pro is also available, and the broader ecosystem includes Codex, Cursor, Windsurf, OpenCode, Hermes, etc. Several plugins in our adopted stack are themselves multi-harness (Superpowers, claude-mem). The question: how much cross-LLM portability does v1 of the framework promise?

Without an explicit ADR, contributors might either over-invest in multi-harness adaptation (premature complexity) or accidentally trap users in Claude-Code in ways that surprise them later.

## Decision

### V1 is Claude-Code-only

The framework's installed surface — the plugin format, hooks, slash commands (`/sf:*`), the `/sf:install` flow, skill activation — depends on Claude Code's runtime. Other LLMs are out of v1 scope.

This is **not** an ideological stance against other LLMs. It's a scope choice: building one good Claude-Code-native framework is hard enough for v1. Multi-harness adaptation is v2+ work if the friend group ever needs it.

### Content is portable by virtue of being markdown

The framework's data is plain files:

- `wiki/index.md`, `wiki/log.md`, `wiki/identity.md`, `wiki/projects/<p>/*.md` — all markdown
- `<handle>.log.md` in the Activity Feed — markdown
- `CLAUDE.md` and project-level `CLAUDE.md` files — markdown
- Skill source (`SKILL.md`, `references/*.md`, `eval/eval.json`) — markdown + JSON

A friend who uses Gemini, Codex, or another tool for an occasional task can manually open their wiki files and read them. The content has no Claude-Code-specific format barriers. **What they LOSE in another tool is the framework's automation** (no wake-up hook, no `/sf:wrap`, no Activity Feed integration), not the content.

### Three things v1 does NOT do (user-confirmed)

Per the user's direction on the sub-questions:

1. **No `CLAUDE.md` ↔ `AGENTS.md` duplication or symlinking.** The framework writes `CLAUDE.md` (Claude Code's convention). It does not also write `AGENTS.md` (Codex/OpenCode convention) or `GEMINI.md`. If friends need that later, it's a v2 feature.

2. **No LLM declaration in `wiki/identity.md`.** No `llms: [claude, gemini]` frontmatter field. The framework doesn't ask which LLMs friends use during identity-interview (per ADR-022's question template).

3. **No documentation for "how to read your wiki from another LLM"**. The wiki being markdown is sufficient; friends who want to use another tool figure it out themselves.

### Plugins that happen to be multi-harness

Per ecosystem research, several plugins in our stack support multiple harnesses out-of-the-box:

| Plugin | Multi-harness? |
|---|---|
| Superpowers | Yes (Claude Code, Codex CLI, Gemini, Cursor, GitHub Copilot CLI, OpenCode, Factory Droid) |
| claude-mem | Yes (Claude Code, Cursor, Codex, Gemini, Windsurf, OpenClaw, Hermes, Copilot, OpenCode) |
| Context Mode | Partial (Claude Code full; Cursor + Codex limitations documented) |
| Skill Creator | Anthropic-official, primarily Claude Code |
| context7 | In Anthropic marketplace; Cursor support varies |
| claude-md-management | Anthropic, primarily Claude Code |

We don't actively leverage this multi-harness capability in v1, but **we don't break it either**. If a friend wants to install claude-mem in Cursor (in addition to or instead of Claude Code), the friend can — they just won't get our `/sf:*` slash commands or framework hooks in Cursor.

### What this means for the user concretely

- **You and your friends run Claude Code for the framework's full value.**
- **If you use Gemini Pro for an occasional task** (per your existing global MCP), you can read your wiki manually but the framework doesn't help you there.
- **If a friend prefers Cursor**, they can install Superpowers + claude-mem in Cursor too, but they lose the framework's `/sf:*` surface unless they also run Claude Code.
- **The framework's content is yours regardless** — git-backed, markdown, portable to any tool. No vendor lock-in beyond what Claude Code's plugin ecosystem itself implies.

## Consequences

**Easier:**
- Single-target development (Claude Code only) means we ship faster
- No multi-harness compatibility testing in v1
- No abstraction layers needed to support multiple plugin formats
- Cross-LLM concerns can be ignored for v1 design + implementation
- Content portability is automatic (markdown is markdown)

**Harder:**
- Friends who want first-class non-Claude-Code experience must wait for v2
- If Anthropic changes Claude Code's plugin API significantly, we're tightly coupled
- The "we considered cross-LLM" answer is "we explicitly didn't" rather than "we tried and here's the design"

**Now impossible:**
- A friend can't seamlessly switch from Claude Code to Codex mid-session and have the framework follow them (v2 problem)

**Sunset review trigger conditions:**
- Friend group ends up with someone who hard-prefers non-Claude (Gemini, Cursor) and friction becomes real
- Anthropic deprecates Claude Code or shifts the plugin ecosystem
- A neutral cross-harness plugin standard emerges (the way AGENTS.md is becoming for context files)
- Ecosystem v2 work demands multi-harness for distribution reasons

## Alternatives considered

### A) Ship `CLAUDE.md` + `AGENTS.md` (symlink or duplicate) for forward-compatibility

**Considered shape**: Anywhere the framework writes `CLAUDE.md`, also write an `AGENTS.md` so Codex/OpenCode users get the same content.

**Why rejected per user direction**: "Possibility, but not necessary for now." Adds complexity for a hypothetical use case. v2 if needed.

### B) Identity-interview asks about LLM usage

**Considered shape**: Q in `/sf:interview` asking "Which LLMs do you regularly use?" so the friend group can see who uses what.

**Why rejected per user direction**: "Not necessary." Friends communicate via WhatsApp/Discord; they don't need framework-level coordination of which LLM each uses.

### C) Documentation for cross-LLM manual fallback

**Considered shape**: A page in framework docs: "Using your wiki with non-Claude tools — here's how."

**Why rejected per user direction**: "No need." Wiki being markdown is self-explanatory; friends will figure it out if they want to.

### D) Build the framework as a portable harness from day one

**Considered shape**: Abstract over Claude Code's specifics so the framework runs on Codex/Cursor/Gemini-CLI/etc.

**Why rejected**: Major scope explosion. Each harness has its own plugin format, hook system, skill activation. Building portably means losing depth in Claude Code. Premature multi-target development for a friend group that's all on Claude.

### E) Provide a "wiki-only" mode that's truly LLM-agnostic

**Considered shape**: Ship just the wiki structure + tooling without the Claude Code plugin parts; friends can use it as a markdown knowledge base in any LLM.

**Why rejected**: The wiki's value comes from the hooks (auto wake-up at session start, auto consolidate, auto activity feed). Without the hooks, it's just a markdown directory friends already know how to make. Stripping the Claude Code integration loses the whole point.

## Open questions for v2 (if cross-LLM ever becomes a priority)

1. Would friends actually use a multi-harness framework, or would they just use the LLM they prefer + ignore the framework when not in Claude Code?
2. Does Anthropic ship something like `AGENTS.md` becoming a cross-harness standard? Worth tracking.
3. Would a small bridge layer (e.g., a generic wiki-loader script that any LLM can call) be useful for friends in non-Claude tools, without us porting the whole framework?

## References

- `wiki/research/superpowers.md` — multi-harness support documented
- `wiki/research/claude-mem.md` — multi-harness support documented
- `wiki/research/context-mode.md` — multi-harness with caveats documented
- `wiki/research/ecc-everything-claude-code.md` — ECC's portability across CC/Cursor/Codex/OpenCode/Zed (model we're not adopting, but it shows the pattern works at larger scope)
- `wiki/research/lean-ctx.md` — 28+ AI agents supported (Rust binary helps)
- ADR-001 (Terminology) — distinction between harness (Claude Code) and our meta-harness configuration
- ADR-023 (V1 Scope Fence) — cross-LLM listed as OUT for v1
