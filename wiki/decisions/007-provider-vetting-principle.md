---
title: "ADR-007: Provider-Vetting Principle (Curate Providers, Not Just Tools)"
status: accepted
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: [gsd-redux, py-harness-engineering, claude-mem, memory-architecture-alternatives, ecc-everything-claude-code, context7, observability-tools-survey, team-coordination-survey]
amendments:
  - "2026-05-28: extended trust assessment table with ECC, Upstash (context7), Dash0, Mercury/Proton, Dicklesworthstone (MCP Agent Mail)"
affects-components: [curation, onboarding, docs, recommended-stack]
relates-to: [006-curated-stack]
---

# ADR-007: Provider-Vetting Principle (Curate Providers, Not Just Tools)

## Context

The GSD Redux research surfaced a sharp lesson: the original `gsd-build/get-shit-done` repository was abandoned by the `open-gsd` governance due to a documented **"meme-coin rug-pull incident."** The fork at `open-gsd/get-shit-done-redux` is the trusted continuation; the legacy is "outside open-gsd control."

This is not a story about a bad tool — the GSD methodology itself remains useful. It's a story about a **bad provider** who exploited trust in the tool to push something else (a meme-coin). The tool's reputation got compromised because the provider's incentives turned.

Separately, the PY harness-engineering research noted that **1 in 4 community-contributed agent skills contains a vulnerability**. Skills are not just code; they're prompt injection vectors, file-system access points, and shell execution paths. A malicious provider can ship a skill that does harm in ways pure code-review might not catch.

The broader insight: **curation that only evaluates tools misses half the risk surface**. Provider trustworthiness is a separate axis that has to be evaluated explicitly.

The friend group will install whatever the configuration recommends. They trust the configuration; the configuration must trust its providers. If we recommend a tool from a provider who later turns adversarial (rug-pull, malware injection, abrupt license change, abandonment without handoff), the friend group's security and continuity get hit through us.

This ADR codifies the principle so future curation decisions (ADR-006 amendments, new plugin additions, etc.) apply it explicitly.

## Decision

**The configuration's curation process must vet both the tool and the provider.** Adding a plugin / skill / dependency to the recommended stack requires positive answers to **both**:

**Tool fit (covered case-by-case in ADRs like ADR-002, ADR-006):**
1. Does it solve a real problem the friend group has?
2. Does it integrate cleanly with the rest of the stack?
3. Is its license compatible with our use?

**Provider trust (this ADR):**
1. **Identity is known and consistent.** Real human / known org name behind the project. Not anonymous + financialized. Pseudonyms acceptable if they have demonstrated track record.
2. **Governance is legible.** Either a known maintainer with a public history, or an org/foundation with stated governance. Sole-maintainer projects are accepted with awareness of bus-factor risk.
3. **History is clean.** No documented rug-pulls, sudden monetization pivots, prompt-injection scandals, or license bait-and-switches. Past incidents weighted by recency + severity + how the provider responded.
4. **Incentives are aligned or disclosed.** Commercial offerings adjacent to open-source tools are fine (e.g., Anthropic's Claude Code → Claude API revenue) when the relationship is transparent. Hidden monetization vectors (meme-coins, undisclosed sponsorship, telemetry) are red flags.
5. **Maintenance signal is positive.** Recent commits, recent releases, responsive issue triage, or — for stable mature tools — explicit "in maintenance mode" stance.

**Decision rule:**

> A plugin / skill / dependency does not enter the recommended stack until both tool fit AND provider trust are positively established. Either failing means we either:
> (a) find an alternative provider for the same tool (e.g., open-gsd fork instead of legacy gsd-build), OR
> (b) defer adoption until trust improves, OR
> (c) build our own minimal version if the tool is essential.

**When provider trust fails AFTER adoption:**

If a provider in our recommended stack turns adversarial (or simply abandons), the configuration's response is to file a follow-up ADR within 2 weeks documenting:

- What changed and how we noticed
- Whether the existing version is still safe to use frozen at the pre-incident state
- Migration plan to alternative / fork / replacement

Friends will receive the update via our framework's onboarding-version mechanism (ADR-015).

**Concrete examples from the research:**

| Project | Provider | Trust assessment |
|---|---|---|
| Superpowers (obra/superpowers) | Jesse Vincent / Prime Radiant | Known, public, in Anthropic marketplace — trusted |
| Skill Creator (anthropics/skills) | Anthropic | Org-backed, transparent — trusted |
| claude-mem (thedotmack/claude-mem) | thedotmack (handle) | Pseudonym + clean track record + Apache-2.0 + active maintenance + 46K-89K stars — trusted with awareness |
| Context Mode (mksglu/context-mode) | mksglu (handle) | Pseudonym + clean track record + ELv2 license + active maintenance — trusted with awareness |
| qmd (tobi/qmd) | Tobi Lütke (Shopify CEO) | Known public figure, strong reputation — trusted |
| Ralph (anthropics + community variants) | Geoffrey Huntley + Anthropic + community | Origin is known; Anthropic version is trusted; community variants vary |
| **gsd-build/get-shit-done (legacy)** | unknown maintainer post-incident | **Distrusted — meme-coin rug-pull on record** |
| open-gsd/get-shit-done-redux | open-gsd governance | Trusted (fork was MADE because of the trust event) |
| **(added 2026-05-28)** ECC (affaan-m/everything-claude-code) | affaan-m | Known maintainer; large active project (140K+ stars, 170+ contributors, 1,994 commits); MIT-licensed; Pro tier ($19/seat/mo for private repos) is transparent monetization — trusted, with awareness of bus factor + commercial-tier incentive alignment |
| **(added 2026-05-28)** context7 (upstash/context7) | Upstash | Known company (multiple OSS projects, commercial Redis-as-a-service); in Anthropic official marketplace; provides cloud documentation lookup — trusted; note Upstash API key required + queries leave the friend group's machines |
| **(added 2026-05-28)** Dash0 agent-skills (dash0hq) | Dash0 (commercial observability vendor) | Known company; transparent commercial offering (observability backend) + open-source agent-skills; trust depends on use case — for friend-group projects that emit OpenTelemetry, agent-skills are trusted; for the framework itself, we use native CC OTel instead per ADR-015 |
| **(added 2026-05-28)** Mercury / Proton MCP (mercury.build) | Mercury (commercial entity) | Known company; commercial SaaS — coordination data leaves friend-group machines; **NOT adopted** (per ADR-006 amendment, deferred in favor of self-hosted alternatives) |
| **(added 2026-05-28)** MCP Agent Mail (Dicklesworthstone) | Dicklesworthstone (individual maintainer) | Pseudonym + open-source + self-hostable + Git-backed audit trail — provider-trust acceptable but bus-factor is real concern; documented as deferred per ADR-006 amendment |

## Consequences

**Easier:**
- Future curation decisions have a checklist beyond "does this work" — provider trust evaluation is mandatory, not optional
- When friends ask "why this and not that," we have a documented answer that includes WHO maintains each tool
- Reputational risk to the friend group via the stack is bounded — we're not blindly trusting

**Harder:**
- More work per plugin evaluation. Each candidate needs both tool-fit and provider-trust assessment.
- Pseudonymous providers are not auto-rejected, but require more care — track record + license + maintenance signal substitute for legal identity
- We may have to reject genuinely useful tools because of provider concerns (e.g., if a great memory plugin appeared from an anonymous provider with no track record, we'd defer)

**Now impossible:**
- Casual / impulsive plugin additions to the stack without provider assessment
- Quiet "everyone is using it so it must be fine" reasoning

**Sunset review trigger conditions:**
- The ecosystem matures enough that provider-vetting becomes a solved problem at the marketplace layer (e.g., Anthropic adds verified-provider badges with real meaning) — we could rely more on the marketplace and trim this ADR
- A pattern of provider misbehavior we hadn't anticipated emerges, requiring stricter criteria
- A trusted provider in our stack has an incident, forcing a real test of the migration response

## Alternatives considered

### A) Skip this ADR; vet providers ad-hoc per plugin decision

**Considered shape**: Each curation ADR handles its own provider concerns implicitly; no separate principle document.

**Why rejected**: Without a documented principle, future ADRs will be inconsistent. The meme-coin incident was specific enough that "be careful" without a process is lip service. A documented checklist forces real evaluation per addition.

### B) Stricter: only trust org-backed projects (Anthropic, established companies)

**Considered shape**: Reject all pseudonymous-maintainer projects regardless of track record.

**Why rejected**: Would eliminate claude-mem (thedotmack), Context Mode (mksglu), and most of the community plugins that ARE high-quality. Pseudonyms in open-source are normal and not inherently suspicious. Track record + license + maintenance is the right substitute for legal identity in this domain.

### C) Looser: trust signal = popularity (stars / downloads / installs)

**Considered shape**: If it has enough adoption, it's vetted.

**Why rejected**: The meme-coin incident proves popularity ≠ safety. The original gsd-build repo had high adoption right up to the incident. Stars are a lagging indicator of trust; they don't tell you what the provider will do next.

### D) Bundle a "stack inspection" tool in the framework

**Considered shape**: Build / recommend a tool that audits the installed stack for known-bad providers, abandoned projects, license changes.

**Why rejected**: Cool idea, out of v1 scope. Could be a v2 contribution — a `/sf:audit-stack` slash command that checks each plugin against a list of red flags. Filed as a v2 idea, not adopted now.

## References

- `wiki/research/gsd-redux.md` — the meme-coin rug-pull incident that inspired this principle
- `wiki/research/py-harness-engineering.md` — "1 in 4 community-contributed agent skills contains a vulnerability"
- `wiki/research/claude-mem.md` — example of a pseudonymous provider we trust based on track record + license + maintenance
- `wiki/research/memory-architecture-alternatives.md` — comparison that touched on org-backed vs. community-backed memory systems
- ADR-006 (Curated Stack) — applies this principle implicitly; this ADR makes it explicit for future amendments
