---
title: "ADR-016: Framework's Own License — MIT"
status: accepted
date: 2026-05-28
sunset-review: 2027-05-28
references-pages: [superpowers, claude-mem, context-mode, skill-creator, gsd-redux]
affects-components: [licensing, distribution, sharing, contributions]
relates-to: [002-token-efficiency-stack, 006-curated-stack, 007-provider-vetting-principle, 015-onboarding]
---

# ADR-016: Framework's Own License — MIT

## Context

The framework itself (the configuration's source files: skills, hooks, slash commands, the wiki, this decisions directory, the install skill, documentation) needs a license.

This is separate from the licenses of plugins we recommend (which are covered by ADR-002 / ADR-006 and surfaced to friends via `LICENSES.md` per ADR-015):

- Superpowers: MIT
- Skill Creator: Apache-2.0
- claude-mem: Apache-2.0
- Context Mode: ELv2 (restricts SaaS distribution)
- qmd: MIT (v2 upgrade path)

The friend-group context shapes the license choice:

- **Internal use first.** The friend group is the primary audience; we aren't a commercial product (yet).
- **Possible future open-sourcing.** If the framework becomes interesting beyond the friend group, openness matters.
- **License compatibility with the stack.** The framework includes references to the plugins. Our license should compose cleanly with theirs.
- **Contribution accessibility.** If a friend (or eventually a community member) wants to contribute, license should be permissive enough to invite participation.

Common open-source license choices:

| License | Permissive? | Patent grant? | Notable users |
|---|---|---|---|
| **MIT** | Yes (very permissive) | No | Most JS/TS, many Rust, many Python |
| **Apache-2.0** | Yes (permissive) | Yes (explicit) | Skill Creator, claude-mem, many enterprise OSS |
| **BSD-3-Clause** | Yes | No | Many academic projects |
| **GPL-3.0** | Copyleft (viral) | Yes | Linux kernel-adjacent projects |
| **AGPL-3.0** | Strong copyleft + SaaS provision | Yes | Some database projects |
| **ELv2** | Source-available, NOT open-source | No | Elastic, Context Mode |
| **BUSL-1.1** | Source-available, NOT open-source | No | MariaDB, Sentry |
| **Unlicense** | Public-domain-like | No | Some utility libraries |

The framework's content includes:
- Original skills + hooks + slash command implementations
- Original wiki content (research syntheses, ADRs)
- Configuration files
- Documentation
- The install skill

None of this requires patent protection (we're not implementing patented algorithms). None of it is commercially valuable enough to justify restrictive licensing. Permissive is the right axis.

## Decision

**The framework is licensed under MIT.**

A `LICENSE` file at the framework's root contains the standard MIT text + the copyright line. Year: 2026. Holder: "the startup-framework contributors" (a placeholder that the friend group can refine when they pick a real org name).

**License placement:**

```
startup-framework/
├── LICENSE                       ← MIT text, full file
├── LICENSES.md                   ← stack license summary (auto-generated, see ADR-015)
└── ...
```

**Why MIT over Apache-2.0**:

1. **Simplest possible permissive license.** MIT is shorter, more familiar, less legalese. Aligns with the lightweight thesis of the framework.
2. **No patent grant needed.** We're not implementing patented algorithms; we're integrating existing plugins + a wiki pattern. Patent grant is over-protection.
3. **Compatible with all plugins in the stack.** MIT can coexist with Apache-2.0 + ELv2 without conflict. Users redistributing the framework + plugins have a clean story.
4. **Inviting to friend-group contributions.** Anyone in the friend group can contribute without legal friction.
5. **Anthropic's Superpowers is MIT.** Matches the conventional choice for Anthropic-marketplace-adjacent tools.

**Why NOT each alternative:**

- **Apache-2.0**: explicit patent grant is good but we don't need it. Extra clauses add complexity for no current benefit. Switch later if patent concerns arise.
- **GPL-3.0**: viral copyleft restricts use cases we want to enable (e.g., a friend builds a closed-source product on top — we want that to be allowed).
- **AGPL-3.0**: same plus SaaS-clause — even more restrictive. Not aligned with friend-group flexibility.
- **ELv2 / BUSL-1.1**: source-available but not open-source. Our framework isn't commercially valuable enough to merit this restriction; we want maximal sharability.
- **Unlicense / public domain**: legal status of public domain varies by jurisdiction; MIT is more reliably interpreted everywhere.

### License interactions in the stack

The friend group's effective license terms when using the framework are the intersection of:

- **MIT** (our framework)
- **MIT** (Superpowers)
- **Apache-2.0** (Skill Creator, claude-mem)
- **ELv2** (Context Mode)
- **TBD permissive** (Frontend Design — verify on install)

The most restrictive is **ELv2**, which restricts hosted-SaaS distribution. So:

- **Personal/team use**: completely fine
- **Internal company use**: fine
- **Sharing the framework + plugins with another person**: fine (each plugin's redistribution rules apply)
- **Distributing as a commercial hosted service**: **blocked by Context Mode's ELv2**; would require replacing Context Mode or obtaining a commercial license

The `LICENSES.md` file per ADR-015 surfaces this to friends at install time.

### Open-sourcing decision (separate from licensing)

This ADR commits to a license but **doesn't require the framework to be public**. The friend group can keep the repo private if they want to; MIT just sets the legal terms if they later open-source.

Recommendation (not part of this ADR): the framework would benefit from being public eventually. The wiki we've built (research + decisions + alternatives) is genuinely useful to others designing similar configurations. Going public extends the framework's value beyond the friend group. **Defer this decision to when the friend group is ready.**

## Consequences

**Easier:**
- **One license, one file, done.** No legal complexity blocking iteration.
- **Anyone can contribute.** Friends adding skills/wiki content know the legal terms are simple.
- **Future open-sourcing has zero license friction.** When the group decides to go public, the LICENSE file is already in place.
- **License compatibility across the stack is documented.** `LICENSES.md` (per ADR-015) makes the practical implications visible.

**Harder:**
- **No patent protection.** If someone patents a technique we use, we have no defensive grant. Mitigation: switching to Apache-2.0 is straightforward if/when this becomes a real concern.
- **No attribution-enforcement teeth.** MIT's attribution requirement is honor-system. Friends could (in theory) strip the copyright notice. In practice this is non-issue for the friend-group context.

**Now impossible:**
- Adopting copyleft / source-available licenses without re-licensing all framework content.

**Sunset review trigger conditions:**
- The friend group commits to commercializing the framework as a SaaS → license diversity becomes a real blocker (Context Mode's ELv2); reconsider stack composition more than this ADR
- A specific patent concern emerges → switch to Apache-2.0
- The friend group's legal context changes (incorporation, investor concerns) → revisit
- The framework gains substantial external contributors → consider CLA or DCO if needed

## Alternatives considered

### A) Apache-2.0

**Considered shape**: Use Apache-2.0 instead of MIT.

**Why rejected (for now)**: Adds patent-grant complexity for benefit we don't currently need. Switching from MIT to Apache-2.0 later is straightforward (relicensing within permissive family is common). Switching the OTHER direction is harder, so MIT is the safer default starting point.

### B) Dual-licensed (MIT + Apache-2.0)

**Considered shape**: Let users pick whichever applies.

**Why rejected**: Confusion for downstream. Pick one. If patent concerns emerge, switch fully.

### C) Custom license

**Considered shape**: Write our own license tailored to friend-group use.

**Why rejected**: Almost always a bad idea. Established OSI licenses have legal review behind them; custom licenses confuse and risk hidden problems.

### D) No license / "all rights reserved"

**Considered shape**: Don't include a LICENSE file. By default, all rights reserved (no one can legally use it).

**Why rejected**: Blocks friend-group contributions on technicality. Even for internal use, having an explicit license makes the legal posture clear. MIT is essentially "go ahead" — appropriate.

### E) Source-available (ELv2 / BUSL)

**Considered shape**: Restrict SaaS / competing-service use of our framework.

**Why rejected**: Our framework isn't a commercial offering. ELv2-type restrictions make sense for businesses protecting their commercial product (Elastic, Sentry, MariaDB). Doesn't fit our context.

## References

- `wiki/research/superpowers.md` — MIT licensed (precedent in our stack)
- `wiki/research/claude-mem.md` — Apache-2.0 (alternative model)
- `wiki/research/context-mode.md` — ELv2 (the most restrictive piece of the stack)
- `wiki/research/skill-creator.md` — Apache-2.0 (Anthropic's choice; document skills are source-available)
- `wiki/research/gsd-redux.md` — MIT (trusted fork)
- ADR-002 (Token-Efficiency Stack) — adopts mix of licenses; this ADR adds our own to the mix
- ADR-006 (Curated Stack) — the full plugin set with their licenses
- ADR-007 (Provider-Vetting Principle) — license assessment is part of provider trust
- ADR-015 (Onboarding) — generates `LICENSES.md` summary at install
