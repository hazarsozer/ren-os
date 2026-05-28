---
title: "ADR-008: Wake-Up Hook — Preserves Prompt Cache, Loads Wiki Into Conversation Layer"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [nate-herk-give-me-10-mins, prompt-engineering-agent-harness, caleb-agent-harness, simon-scrapes-agentic-os, llm-wiki-pattern]
affects-components: [memory, wiki, hooks, session-start, install]
relates-to: [004-wiki-design-hierarchical, 005-wiki-retrieval-evolution, 009-consolidate-wrap, 010-hook-ordering]
amendments:
  - "2026-05-28 (verified): SessionStart hook conversation-layer injection mechanism confirmed via `hookSpecificOutput.additionalContext` field (per `https://code.claude.com/docs/en/hooks-guide`). Validation triangulates three independent sources: (1) official docs explicitly describe injection as 'system reminder' (Claude reads as plain text — NOT system-prompt prefix); (2) Claude Code ships `--exclude-dynamic-system-prompt-sections` as a first-party CLI flag implementing the same architecture (moving per-machine sections from system prompt into the first user message specifically 'to improve cross-user prompt-cache reuse'); (3) empirical observation — the very session in which this ADR was being verified contains `<system-reminder>SessionStart hook additional context: ...</system-reminder>` rendered from another plugin's hook, exactly the documented mechanism in action. Cache-preservation experimental verification (§2 of the lifecycle plan: 20-30 sessions across arms A/B/C measuring `cache_read_input_tokens` distributions) deferred pending arm runs; documentation gate cleared. See `hooks/wake-up/CC_API_NOTES.md` for the full verification trail with verbatim source quotes."
---

# ADR-008: Wake-Up Hook — Preserves Prompt Cache, Loads Wiki Into Conversation Layer

## Context

The wake-up mechanism is **how the LLM gets relevant context at the start of a session** — the operational complement to the wiki structure ADR-004 established and the retrieval mechanism ADR-005 defined.

Three constraints converge on this design:

1. **Token-efficiency north star (the user's #1 pain).** Loading too much defeats the goal; loading nothing means re-explaining the project every session. The target from ADR-004 was 3–5K tokens of *relevant* material.

2. **Prompt-caching constraint (Nate Herk + Prompt Engineering sources).** Claude Code caches the system prompt prefix. Anthropic monitors hit rate at SEV level (per Thoric quote). **Anything that modifies the system prompt prefix invalidates the cache.** Per Nate Herk's mechanics: cached tokens cost 10% of normal input; sub-agent TTL is 5 minutes; subscription TTL is 1 hour; model switches reset cache; **CLAUDE.md mid-session edits do NOT break cache** (they only take effect at restart).

3. **CWD-aware loading (ADR-004).** The hook must read `pwd` and load master + project-relevant material, never the whole wiki.

The conflict to resolve: the obvious place to inject wiki context is the system prompt, but that breaks the cache. The non-obvious right place is the **conversation layer** — wiki content arrives as the first conversational turn, not as a system instruction.

Additionally, there's a Stop-hook collision concern: claude-mem also has a SessionStart hook. If our wake-up hook does too, plus claude-mem's, plus any others — order matters and conflicts are possible. This ADR designs the wake-up to coexist; ADR-010 handles the broader hook ordering coordination.

## Decision

**The wake-up mechanism uses a SessionStart hook that injects wiki context into the conversation layer, not the system prompt.**

**Concrete behavior of the SessionStart hook:**

1. **Reads cwd** to determine context (which project, if any).
2. **Reads master `wiki/index.md`** (always, small — maybe 1–2KB at v1).
3. **If cwd is inside a project directory**, reads:
   - `wiki/projects/<project>/index.md`
   - Last 10 entries of `wiki/projects/<project>/log.md`
   - **Session pointer** (one-paragraph "where I left off" written by the last session's consolidate)
4. **Reads master `log.md` tail** (last 5 entries) — surfaces recent cross-project events.
5. **Composes a single context-injection message** in the conversation layer. Format:

   ```
   ## Framework wake-up context (2026-05-28)
   
   ### Master wiki index
   <content of wiki/index.md, truncated if needed>
   
   ### Project context: <project-name> (if applicable)
   <content of wiki/projects/<project>/index.md>
   <last 10 log entries>
   
   ### Session pointer
   <one-paragraph "where I left off">
   
   ### Recent master log
   <last 5 entries from master log.md>
   ```

6. **Posts this as a user-role message in the conversation** — NOT as a system prompt modification. This is the critical compliance step for ADR-008's promise.

**What the wake-up hook explicitly does NOT do:**

- Modify the system prompt
- Modify CLAUDE.md mid-session (these only take effect at restart anyway, but the discipline is clearer this way)
- Modify settings.json or any configuration file Claude Code reads as part of its system-prompt assembly
- Load the entire wiki (defeats the token-efficiency goal)
- Read specific pages from the wiki unless they appear in the index AND the cwd-based heuristic surfaces them

**What stays cacheable:**

The system prompt prefix (Claude Code's defaults + plugin definitions + tool descriptions + CLAUDE.md) is unchanged by our hook. The cache prefix matching works exactly as Claude Code expects. Cache hits are preserved across sessions.

**What's freshly evaluated per session:**

The conversation-layer wake-up message — which is fine because conversation messages aren't expected to be cached the same way. They live in a less-cached tier of the context.

**Retrieval abstraction (required by ADR-005):**

The hook calls a `wake_up_context(cwd, master_wiki_path)` function that returns the composed context. v1 implementation reads `index.md` files directly. v2 implementation (after qmd adoption per ADR-005 triggers) calls `qmd query` instead. The hook's external behavior doesn't change.

## Consequences

**Easier:**
- **Prompt cache stays intact.** Friends pay 10× cheaper tokens for the system-prompt-prefix layer every session. Real money saved at the user's stated north star.
- **Cwd-awareness is built in.** No friction for cross-project work; switching project directories automatically loads the right context.
- **The wake-up is auditable.** It's a single hook + a single function with a clear contract.
- **v2 transition is clean.** ADR-005's retrieval abstraction is enforced here from day one.

**Harder:**
- **The conversation-layer injection costs tokens every session** (not cached as aggressively as system-prompt content). But the alternative (cache-breaking system prompt modification) costs **all** the cached tokens too — much worse trade.
- **Multiple plugins touching SessionStart need coordination** (claude-mem + ours + any others). ADR-010 handles this; the wake-up hook implementation must be robust to other hooks running before or after.
- **Composing the wake-up message at runtime requires reading files synchronously** at session start. At v1 scale, this is <100ms; at v2 with qmd, could add latency. Monitor.

**Now impossible:**
- Injecting wiki content as system prompt modification — explicitly forbidden by this ADR
- "Just load everything" approach — explicitly forbidden by the 3–5K target

**Sunset review trigger conditions:**
- Cache hit rate drops noticeably on friends' machines (telemetry from Claude Code, if available)
- Session-start latency exceeds 500ms routinely
- Sessions fail to know about recent project decisions despite the wake-up running — indicates the index/log are incomplete signals, possibly needing more aggressive retrieval (qmd transition per ADR-005)
- Friends report confusion about what got auto-loaded vs. what didn't — indicates the wake-up message format needs revision

## Alternatives considered

### A) Inject into system prompt via CLAUDE.md modification

**Considered shape**: SessionStart hook writes wiki content into the project's CLAUDE.md file before the session starts.

**Why rejected**: Nate Herk's research is explicit — CLAUDE.md changes affect the system prompt layer. The first session after the modification pays full cache miss. Even though CLAUDE.md edits "don't break cache mid-session" (they only apply on restart), the NEXT session's cache state starts from scratch. Over time, dynamic CLAUDE.md modification eats cache savings. Conversation-layer injection is the right place.

### B) Inject into system prompt via Claude Code's MCP prompt mechanism

**Considered shape**: Use a custom MCP server that contributes to system prompts dynamically.

**Why rejected**: Same caching problem as A. Plus introduces an MCP server (daemon-ish behavior — potentially violates ADR-003 if it's long-running). Plus more moving parts.

### C) Load wiki content lazily via slash command (no auto-wake)

**Considered shape**: Don't auto-load anything. Provide `/sf:wake-up` that the user runs manually when they want context.

**Why rejected**: Friction. Users would forget; sessions would lack context; the value of automatic context goes away. Auto-loading is the right default; manual override is acceptable for special cases.

### D) Inject ALL wiki content every session

**Considered shape**: Just load the whole wiki on session start. Modern context windows are big.

**Why rejected**: Defeats token-efficiency north star. Even at modest wiki size, this is 20-50K tokens per session. Cumulative cost is significant. The 3–5K target from ADR-004 is the correct discipline.

### E) Skip auto-wake; rely on claude-mem's auto-injection

**Considered shape**: claude-mem already has SessionStart hook + auto-context-injection. Just use that for wiki content too.

**Why rejected**: claude-mem injects observations it captured, not deliberately-curated team knowledge. The wiki is a different layer (per ADR-002). Conflating the two would either dilute claude-mem's signal or under-serve the wiki layer. Different tools, different concerns.

## References

- `wiki/research/nate-herk-give-me-10-mins.md` — prompt caching mechanics: TTLs, cache layer structure, what breaks cache
- `wiki/research/prompt-engineering-agent-harness.md` — system-prompt-assembly mechanics; "if you dynamically introduce components to the system prompt, that is going to break the caching"
- `wiki/research/caleb-agent-harness.md` — loops-with-fresh-context primitive; the wake-up is how we operationalize that at session level
- `wiki/research/simon-scrapes-agentic-os.md` — SessionStart hook + force-inject pattern; "Hooks > CLAUDE.md instructions"
- `wiki/research/llm-wiki-pattern.md` — Karpathy's index-first retrieval pattern that wake-up implements
- ADR-004 (Wiki Design Hierarchical) — provides the directory shape the wake-up navigates
- ADR-005 (Wiki Retrieval Evolution) — provides the abstraction layer the wake-up's retrieval function honors
- ADR-009 (Consolidate via /wrap) — the partner mechanism (what the consolidate writes is what the next wake-up reads)
- ADR-010 (Hook Ordering Coordination) — addresses multi-plugin SessionStart hook coexistence
