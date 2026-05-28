---
title: "Team-Coordination Plugin Survey (Mercury/Proton, MCP Agent Mail, Agent-MCP, etc.)"
type: research
sources:
  - https://www.mercury.build/proton/docs/mcp
  - https://github.com/Dicklesworthstone/mcp_agent_mail
  - https://github.com/rinadelph/Agent-MCP
  - https://github.com/gilbarbara/agent-hub-mcp
  - https://github.com/AndrewDavidRivers/multi-agent-coordination-mcp
source_fetched: 2026-05-28
ingested: 2026-05-28
tags: [team-coordination, multi-agent, mcp, ecosystem-survey, foreground-research, gap-fill]
status: ingested
related: [awesome-claude-skills-survey, ecc-everything-claude-code, claude-mem]
note: |
  Addresses the team-coordination gap surfaced before design-doc filing. Compares
  Mercury/Proton (commercial SaaS) with self-hostable open-source alternatives.
  **MCP Agent Mail (Dicklesworthstone) is the leading candidate** for adoption
  given our file-based + self-hosted philosophy.

  **CRITICAL FRAMING CORRECTION (2026-05-28)**: Original synthesis below assumed a
  SHARED wiki across the friend group with multi-author writes (file reservations
  to prevent conflicts on shared `STATE.md`, etc.). That model is WRONG for our
  framework — per ADR-004 amendment, each friend's wiki is LOCAL to their machine,
  not shared. The correct framing for MCP Agent Mail in our case is **inter-Claude
  messaging** (email between friends' AI agents), NOT shared-state coordination.
  Use cases below should be reread with that lens: file reservations don't apply
  to us; messaging + agent identity + inbox/thread features do.
---

# Team-Coordination Plugin Survey

## TL;DR

The team-collab gap we identified before design-doc filing has multiple existing solutions in the ecosystem. **Mercury/Proton** is the polished commercial SaaS option but sends coordination data to a third-party hosted service. **MCP Agent Mail (Dicklesworthstone/mcp_agent_mail)** is the self-hostable open-source candidate that aligns with our wiki + git + SQLite philosophy. Three other open-source MCP coordination tools exist but are smaller surface area. **Recommendation for the design doc**: adopt MCP Agent Mail as the team-coordination piece OR defer the decision to per-friend choice and document trade-offs.

## The gap this fills

The friend-group dimension of our framework requires SOME mechanism for cross-developer coordination:
- Who's editing what (avoid stomping on each other's changes)
- Inter-agent messaging (one friend's AI agent asks another's a question)
- Task ownership (who's running which long-running operation)
- Wiki write coordination (multi-author git merges on `log.md` and `STATE.md`)

Without this, the friend group operates as parallel individuals who happen to share a wiki — losing the "team" advantage.

## The four candidates

### A) Mercury / Proton (commercial SaaS)

- **Provider**: Mercury (mercury.build), commercial entity
- **Scope**: orchestration framework + Proton MCP server
- **Architecture**: hosted JSON-RPC over HTTP at `api.mercury.build`, per-agent API keys
- **MCP tools**: `mercury_send_message`, `mercury_wait_for_messages`, `mercury_read_thread`, `mercury_create_task`, `mercury_update_task`, `mercury_close_task`, `mercury_create_automation` (cron), `mercury_post_activity`, `mercury_update_status`
- **Install**: `claude mcp add --transport http --scope user mercury https://api.mercury.build/api/v1/mcp -H 'x-api-key: ak_agent_...'`
- **License**: not disclosed (closed-source likely, given commercial SaaS)
- **Self-hostable**: no
- **Pricing**: not in docs (separate pricing page)
- **Data residency**: third-party servers

**Pros**: polished, full feature set, admin team graph, automation scheduling, professional support
**Cons**: data leaves the friend group's machines; vendor lock-in; license + pricing opacity; per-agent API key management

### B) MCP Agent Mail (Dicklesworthstone — open source) — **most aligned with our values**

- **Provider**: Dicklesworthstone (individual maintainer, GitHub)
- **Scope**: "mail-like coordination layer for coding agents"
- **Architecture**:
  - **Git repository** for human-readable markdown messages + agent profiles + file reservation records
  - **SQLite with FTS5** for fast full-text search + file lease tracking
  - **FastMCP HTTP server** on port 8765 (localhost by default)
- **MCP tools**: `send_message()`, `fetch_inbox()`, `acknowledge_message()`, `file_reservation_paths()`, `release_file_reservations()`, `search_messages()`, `summarize_thread()`, `register_agent()`, `ensure_project()`, `macro_contact_handshake()`
- **Resources**: `resource://inbox/{agent}`, `resource://thread/{id}`
- **Install**: one-line installer
  ```bash
  curl -fsSL "https://raw.githubusercontent.com/Dicklesworthstone/mcp_agent_mail/main/scripts/install.sh?$(date +%s)" | bash -s -- --yes
  ```
  Auto-detects installed CC/Codex/Gemini/other agents
- **License**: open-source (LICENSE file present; specific terms not in docs we read)
- **Self-hostable**: by design (all local)
- **Daemon**: yes, on port 8765 (their daemon, not ours per ADR-003)
- **Standout features**:
  - **Persistent agent identities** ("GreenCastle" style names)
  - **Advisory file reservations** — agents signal "I'm editing this" so others avoid stomping
  - **Pre-commit hooks** (optional) block commits violating active exclusive leases
  - **Git as the audit trail** — every message, every reservation, in git history

**Pros**: self-hosted, no third-party data, git-auditable, integrates with our file-based philosophy, file-reservation pattern uniquely solves the multi-author conflict gap
**Cons**: single maintainer (bus factor); port conflict potential; large in-memory databases (>1-2GB) strain browser viewers; advisory locks, not enforced

### C) Agent-MCP (rinadelph)

- Multi-agent framework with MCP coordination
- Less detailed in our research; mentioned as a category leader for "multi-agent systems where multiple specialized agents work in parallel"
- Would need separate ingest if we go deep

### D) Agent Hub MCP (gilbarbara) and Multi-Agent Coordination MCP (AndrewDavidRivers)

- Universal coordination layers
- Smaller surface than A or B
- Would need separate ingest to evaluate fairly

## Comparison table

| Dimension | Mercury/Proton | MCP Agent Mail | Agent-MCP | Agent Hub MCP |
|---|---|---|---|---|
| Self-hostable | No (SaaS) | Yes | Yes | Yes |
| Open source | No (likely) | Yes | Yes | Yes |
| Git-auditable | No | Yes | Unclear | Unclear |
| File reservation pattern | Implied (task management) | **YES — flagship feature** | Possibly | Possibly |
| Maturity | Commercial product | Active OSS | Less mature | Less mature |
| Data residency | Third party | Friend group's machines | Friend group's machines | Friend group's machines |
| Install simplicity | One command + API key | One-line installer | Per-platform | Per-platform |
| Provider trust (ADR-007) | Commercial; opaque license | Individual maintainer; bus factor; open source | Individual; less established | Individual; less established |

## Recommendation

**Recommend MCP Agent Mail for the team-coordination layer in our curated stack.**

Reasoning:
1. **Architectural alignment**: Git + SQLite + FastMCP matches our file-based wiki philosophy. The Git audit trail is what we want for friend-group coordination — diffs are reviewable, history is durable.
2. **Self-hosted = data sovereignty**: friend-group coordination data stays on friends' machines. Critical for trust + privacy.
3. **File reservation pattern uniquely fills our gap**: the multi-author wiki conflict concern (e.g., two friends both editing `STATE.md` for the same project) gets a specific solution.
4. **One-line install**: minimal onboarding friction.
5. **License: open source** (verify specifics at adoption).
6. **Provider trust acceptable**: individual maintainer is a bus-factor concern (per ADR-007), but the project is active and the architecture is simple enough to fork if maintenance lapses.

**This becomes a new piece of the curated stack** (would amend ADR-006). Likely positioned as **optional in onboarding** ("install if friend group is more than 1 person") rather than required.

**Alternative if we decide NOT to add a team-coord tool**: defer to per-friend choice + provide guidance in onboarding docs. But that leaves a real coordination gap.

## How this informs the framework

### New ADR candidate

A new ADR (e.g., ADR-017) on team-coordination strategy:
- Adopt MCP Agent Mail as recommended team-coord tool
- Document alternatives (Mercury/Proton, Agent-MCP, others) with trade-offs
- Onboarding (ADR-015) prompt: "is your friend group >1 person?" → install MCP Agent Mail or skip

### Possible ADR-014 amendment

The project sub-wiki taxonomy (PROJECT.md / STATE.md / CONTEXT.md) is per-project. MCP Agent Mail's file reservations operate at the file level. Worth amending ADR-014 to note that friends should reserve `STATE.md` / `CONTEXT.md` etc. when actively editing.

### Possible ADR-007 amendment

ADR-007 added the provider-vetting principle. Mercury/Proton's opacity + Mercury Agent Mail's bus-factor are exactly the kinds of trust nuances ADR-007 prepares for. Add this comparison to ADR-007's example table.

## Tensions / open questions

1. **License verification needed** for MCP Agent Mail before formal adoption (the page didn't state the specific license).
2. **Port 8765 conflict** if a friend runs other services on that port. Mitigation: configurable port in MCP Agent Mail's config.
3. **Bus factor**: single maintainer Dicklesworthstone. Fork potential is open since it's small surface area.
4. **Advisory vs. enforced locks**: file reservations are advisory by default. Optional pre-commit hooks enforce. Should our framework recommend the pre-commit hooks too? Probably yes for production work.
5. **Should we evaluate Agent-MCP / Agent Hub MCP / Multi-Agent Coordination MCP** before settling on MCP Agent Mail? Three more research pages. Diminishing returns; MCP Agent Mail is clearly aligned. Defer unless we hit blockers.

## Connections to prior research

| Prior source | Connection |
|---|---|
| ECC | ECC's instinct-based memory doesn't address multi-author coordination; this fills that gap |
| claude-mem | Per-developer memory; this is per-team coordination — orthogonal concerns |
| ADR-002 (Token-Efficiency Stack) | Adds another plugin to the stack if we adopt MCP Agent Mail |
| ADR-004 (Wiki Design Hierarchical) | Multi-author wiki access is exactly the use case MCP Agent Mail addresses |
| ADR-006 (Curated Stack) | Amendment needed if we adopt |
| ADR-007 (Provider-Vetting) | Both candidates exemplify different trust profiles |
| ADR-014 (Project Sub-Wiki Taxonomy) | File reservations could apply to project pages |
| ADR-015 (Onboarding) | Optional install during `/sf:install` if friend group >1 |

## Followups

- Verify MCP Agent Mail's specific license (LICENSE file in repo)
- Evaluate one or two of the smaller alternatives (Agent-MCP or Agent Hub MCP) if the user wants more certainty
- Once design-doc decision is made on adoption, file the ADR

## Reference

- Mercury Proton MCP docs: https://www.mercury.build/proton/docs/mcp
- MCP Agent Mail repo: https://github.com/Dicklesworthstone/mcp_agent_mail
- Agent-MCP repo: https://github.com/rinadelph/Agent-MCP
- Agent Hub MCP repo: https://github.com/gilbarbara/agent-hub-mcp
- Multi-Agent Coordination MCP: https://github.com/AndrewDavidRivers/multi-agent-coordination-mcp
- Fetched: 2026-05-28
