---
type: external-source
source: Web survey conducted by background agent
captured: 2026-05-28
note: Survey of Claude Code plugins and related research, focused on novel approaches. NOT COMPLETED — agent had no network access in this environment. See "Status" section below.
status: blocked-no-network
---

# Web Survey: Claude Code Plugins With Novel Approaches

## Status: NOT EXECUTED — environment had no network access

This file is a placeholder, not a survey. The background agent that was given this task could not reach the public web from its sandbox. Concretely:

- The `WebSearch` tool returned `Permission to use WebSearch has been denied` on every query attempted.
- The `WebFetch` tool returned the same denial on direct URL fetches (tried Google search results page, GitHub search page).
- Bash-based fallbacks (`curl`, `wget`, `gh` CLI) were also denied — every `Bash` invocation that touched the network or even probed for the binaries was blocked with the same permission error.
- Only filesystem-local Bash operations (listing directories, reading files) were permitted.

Per the task's own quality bar — *"Each entry must include a real, working URL"* and *"If you can't find enough material for a theme, say so honestly in that section rather than padding"* — the only honest action was to stop and report rather than hallucinate plugin names and URLs from training data. Fabricating sources would have poisoned the wiki ingest the user explicitly said this file is destined for, which is the worst possible outcome for a knowledge-base project.

The rest of this document records (a) what the agent attempted, (b) what local context already exists so the next run doesn't redo work, and (c) how to unblock a real survey.

## What was attempted before stopping

1. `WebSearch` queries — denied:
   - `claude code plugin 2026 cross-session memory novel`
   - `claude code skills self-improving registry composition`
   - `claude code agent harness token efficiency dotfiles`
2. `WebFetch` against:
   - `https://www.google.com/search?q=claude+code+plugin+memory+novel+approach+github` — denied
   - `https://github.com/search?q=claude-code-plugin&type=repositories&s=stars&o=desc` — denied
3. `Bash` probes:
   - `curl --max-time 5 -sI https://github.com` — denied (Bash itself blocked on network commands)
   - `which gh curl wget` — denied
4. Filesystem inspection (allowed):
   - Confirmed existing assets under `/home/hsozer/Dev/startup-framework/raw/transcripts/` and `/home/hsozer/Dev/startup-framework/wiki/research/`.

## Local context already in the repo (so the next run skips this)

The transcripts directory already holds the creators the task explicitly marked as "already covered":

- `raw/transcripts/ben-fellows-anchor-tags`
- `raw/transcripts/caleb-agent-harness`
- `raw/transcripts/nate-herk-best-6-skills`
- `raw/transcripts/nate-herk-give-me-10-mins`
- `raw/transcripts/prompt-engineering-agent-harness`
- `raw/transcripts/py-harness-engineering`
- `raw/transcripts/simon-scrapes-agentic-os`
- `raw/transcripts/simon-scrapes-claude-skills-upgrade`
- `raw/transcripts/simon-scrapes-self-improving-skills`

The wiki has one ingested research page:

- `wiki/research/llm-wiki-pattern.md` — Karpathy's LLM Wiki pattern, the foundational memory model the friend group is adopting.

`wiki/alternatives/` and `wiki/decisions/` are empty. `wiki/log.md` and `wiki/index.md` reflect a single ingest. The "Open questions" listed in the Karpathy page double as the open-questions section a real survey would attempt to answer:

- Session-start token budget / wake-up hook design
- Hierarchical wikis (master + project sub-wikis)
- Page format conventions and link discipline
- Conflict resolution between contradicting ingests
- Page sharding / splitting thresholds
- Multi-author wiki coordination
- Editor-agnostic vs. Obsidian-specific tricks

These are exactly the questions a real survey of Claude Code plugins should be aiming at — they tell the next run *what to look for*, not just *what terms to search*.

## How to unblock a real survey

In order of cheapest to most effort:

1. **Run the same task from a foreground Claude Code session.** Foreground sessions on this machine have `WebSearch` / `WebFetch` enabled (the user runs them daily). The background-agent sandbox is the only context where they were denied. The deliverable spec doesn't actually require backgrounding — it just requires the markdown file at the given path.
2. **Delegate to `product-researcher` from `idea-generator/`.** The `Dev/CLAUDE.md` bridge file documents that the project has a `product-researcher` agent that uses the Gemini CLI (`gemini -p ... -m gemini-2.5-flash -o json`) for token-heavy web work. Web-survey research is its exact remit, and it bypasses Claude's token budget for the ingestion step. Suggested entry point:
   - Open a session in `Dev/idea-generator/`.
   - Invoke `product-researcher` with the same task brief.
   - It can route heavy fetches to Gemini Flash, return a structured list, and the main thread can then write the same markdown file at `/home/hsozer/Dev/startup-framework/raw/web-survey-claude-code-plugins.md`.
3. **Manual seed list.** If the user wants to bound scope before any agent runs, drop a list of candidate repos/posts into `raw/web-survey-seed.md` and have the next run *only* deep-dive those rather than open-ended search. This is cheaper, faster, and avoids the kitchen-sink-of-searches failure mode.

## Suggested search vocabulary for the next run

Surfaced here so the next run doesn't have to re-derive it. Tuned to the friend-group's stated north star (token efficiency, curation, anti-kitchen-sink, Karpathy-style wiki memory):

**Plugins / repos**
- `claude code plugin memory`
- `claude code skills registry`
- `claude code agent harness`
- `agentic os claude` (the user has Simon Scrapes' take; look for OTHER takes)
- `claude code subagent orchestration`
- `claude code hooks SessionStart PreToolUse PostToolUse`
- `claude code MCP curation`
- `claude code dotfiles` and `claude code .claude/ examples`

**Memory / context engineering**
- `LLM wiki memory pattern` (Karpathy is foundational, but look for derivatives)
- `markdown knowledge base LLM agent`
- `context engineering claude` (Anthropic uses this term in some posts)
- `cross-session memory claude code`
- `claude code resume-session save-session` (filed as patterns by some users)

**Token efficiency**
- `claude code token budget`
- `claude code context window management`
- `claude code progressive disclosure skills`
- `index-first retrieval skills`

**Avoid (already covered or low-signal)**
- Anything from Nate Herk, Simon Scrapes, Caleb, Ben Fellows on Claude Code skills/agents — the transcripts are already in `raw/transcripts/`.
- Generic "introduction to Claude Code" content.
- Launch announcements without code links.

## Top finds — by theme

### Memory & cross-session continuity

_No findings — no network access. See Status section._

### Curation & opinionated tooling

_No findings — no network access. See Status section._

### Agent orchestration / multi-agent patterns

_No findings — no network access. See Status section._

### Hooks & lifecycle innovations

_No findings — no network access. See Status section._

### Skills (self-improving, registries, composition)

_No findings — no network access. See Status section._

### Token efficiency techniques

_No findings — no network access. See Status section._

### MCP integration patterns

_No findings — no network access. See Status section._

### Honorable mentions / interesting tangents

_No findings — no network access. See Status section._

## Patterns that recur across multiple sources

_Cannot be assessed without a corpus. The transcripts already in `raw/transcripts/` would be a starting point for an internal cross-reference pass, but the task explicitly said to focus on OTHER creators and written sources, not re-cover those._

## Contrarian / divisive takes

_No findings — no network access._

## Open questions raised by this survey

The survey itself didn't run, but the *act of stopping* surfaced one design question that's worth filing:

- **Background-agent web access.** The friend group's framework will eventually run background research agents. If the sandbox they run in routinely lacks network access, the framework needs an explicit doctrine for that case: either (a) provision long-running research jobs only from foreground sessions, (b) require background agents to delegate web work to a tool that *does* have network access (e.g., a local MCP server the user runs that proxies search), or (c) ship a research-tool MCP as part of the v1 plugin so any session — foreground or background — has a single dependable web surface. Worth a decision page once the friend group is choosing v1 tools.

## Source list

_Empty. No URLs were successfully fetched._

---

## Recommendation to the caller

Re-run this task as a foreground session, or hand it to the `product-researcher` agent from `Dev/idea-generator/`. Either path has network access. The transcripts and the Karpathy ingest in this repo are the right local context to seed it with. Suggested re-run prompt is the same brief; just remove the implicit assumption that the agent has `WebSearch` available, and add: *"If you cannot reach the web, stop and write the survey-blocked stub. Do not fabricate URLs."* — that one line preserves wiki integrity even if the next runtime is also sandboxed.
</content>
</invoke>