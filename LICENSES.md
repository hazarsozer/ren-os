# Stack Licenses

This file summarises the license terms for every plugin the RenOS installs (per ADR-006) plus the framework's own license (per ADR-016). It is the friend-facing declaration of what they are agreeing to when they run `/ren:install`.

Generated at install time by `/ren:install` Stage 6 (per ADR-015). The template ships in the marketplace repo; the install-time copy is regenerated on the friend's machine with their conditional-install choices reflected.

> **Read this before you ship a hosted SaaS.** Most of the stack is permissive (MIT / Apache-2.0), but **Context Mode is ELv2**, which restricts certain commercial / SaaS distributions. If you intend to host the framework's output as a paid hosted service, see the Context Mode entry below.

---

## Required plugins (auto-installed by `/ren:install`)

### Superpowers — MIT

- Source: [obra/superpowers](https://github.com/obra/superpowers)
- License: [MIT](https://opensource.org/licenses/MIT) — fully permissive.
- Use: development methodology layer (7-phase workflow: brainstorm → worktree → plan → TDD → subagent → review → finish).
- Distribution: no restrictions. Can be bundled, modified, and re-distributed under any license-compatible terms with attribution.

### Skill Creator — Apache-2.0

- Source: [anthropics/skills](https://github.com/anthropics/skills) (Anthropic's official `agent-skills` marketplace).
- License: [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) — permissive with explicit patent grant.
- Use: skill authoring + Layer 1 description optimizer (the foundation of the framework's self-improvement loop per ADR-012).
- Distribution: include the Apache-2.0 NOTICE file if you redistribute. Patent grant covers downstream users.

### claude-mem — Apache-2.0

- Source: [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)
- License: [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)
- Use: cross-session memory (SQLite + ChromaDB + 3-layer progressive disclosure retrieval).
- Distribution: same as Skill Creator.

### Context Mode — ELv2 — **⚠️ NOT permissive for SaaS distribution**

- Source: [mksglu/context-mode](https://github.com/mksglu/context-mode)
- License: [Elastic License v2 (ELv2)](https://www.elastic.co/licensing/elastic-license)
- Use: within-session token efficiency (sandboxes tool outputs; 315 KB → 5.4 KB compression).
- **Distribution restriction:** ELv2 prohibits offering the software as a hosted/managed service to third parties without a separate commercial agreement with the licensor. Personal use, team use, and use inside a product you ship are FINE. Building a SaaS that wraps Context Mode and charges third parties for access is NOT permitted under ELv2.
- **What this means for you:**
  - ✅ Use it on your dev machine.
  - ✅ Use it with your friend group internally.
  - ✅ Use it inside a non-Context-Mode-as-the-feature SaaS you build.
  - ❌ Build a hosted "Context Mode as a service" and sell access.
  - ❌ Embed Context Mode in a product whose primary value IS Context Mode's functionality, and sell that product to third parties.
- **If your project moves toward SaaS:** either negotiate a commercial license with Context Mode's author, replace it with a permissively-licensed alternative, or design your offering so Context Mode is not the user-facing feature. The framework remains useable; the trade-off is on you.
- See ADR-006 + ADR-015 Stage 6 for the framework's stance on this license diversity.

### context7 — TBD permissive (verify on install)

- Source: [upstash/context7](https://github.com/upstash/context7)
- License: verify at install time. As of v1.0 of the framework, context7's license is TBD but the plugin is published in Anthropic's official marketplace, implying a permissive license. The framework's CI does NOT lock this; the friend's `/ren:install` should re-read the upstream license at install time.
- Use: version-aware documentation lookup (solves the "Claude wrote code against an outdated library version" failure mode).
- Distribution: defer to upstream's stated terms.

### claude-md-management — TBD permissive (verify on install)

- Source: [anthropics/claude-md-management](https://github.com/anthropics) (Anthropic-verified plugin)
- License: verify at install time. Anthropic's official-marketplace plugins are typically Apache-2.0 or MIT; the friend's `/ren:install` should confirm.
- Use: `claude-md-improver` skill audits CLAUDE.md quality; `/revise-claude-md` captures session learnings into CLAUDE.md (complements `/ren:wrap` at a different layer per ADR-009).
- Distribution: defer to upstream's stated terms.

---

## Conditional plugins (asked at `/ren:install` Stage 3)

### Frontend Design — TBD permissive (Anthropic, verify on install)

- Source: Anthropic's [claude-code plugins](https://github.com/anthropics) collection.
- License: verify at install time. Anthropic-published, expected permissive.
- Use: distinctive UI aesthetics for friend groups building user-facing UIs. Auto-activates on frontend work.
- Installed only if the friend answers "yes, we build user-facing UIs" during Stage 3. Skipped otherwise.

---

## Documented-not-bundled plugins

### Ralph / Ralph Wiggum — TBD permissive (Anthropic)

- Source: Anthropic's [claude-code plugins](https://github.com/anthropics) collection.
- License: verify if you install it. Anthropic-published.
- Use: autonomous loop pattern (Stop-hook-based session loop) for overnight task runs.
- NOT auto-installed by the framework — its Stop hook would compete with claude-mem's lifecycle hooks (per ADR-010). Documented in the README for friends who explicitly want it; install via `/plugin install ralph-loop@claude-plugins-official`.

---

## Framework itself

### RenOS — MIT

- Source: this repo (`ren-os`).
- License: [MIT](https://opensource.org/licenses/MIT).
- Reasoning per ADR-016:
  - The framework is a thin coordination layer + curated plugin set + per-friend wiki tooling. It does not contain proprietary algorithms or business-critical IP.
  - MIT maximises composability with the permissive plugins in the stack (Superpowers, Skill Creator, claude-mem, presumably context7 + claude-md-management).
  - MIT leaves friends free to fork, modify, and adapt without legal friction. The framework is meant to be small enough to throw away (per the spec's "lightweight harness thesis").
- See `LICENSE` in the marketplace repo root for the full MIT text.

---

## License mix summary

| Plugin | License | Distribution-friendly? |
|---|---|---|
| Superpowers | MIT | ✅ Fully |
| Skill Creator | Apache-2.0 | ✅ Fully (with NOTICE) |
| claude-mem | Apache-2.0 | ✅ Fully (with NOTICE) |
| Context Mode | ELv2 | ⚠️ Not for SaaS — see entry above |
| context7 | TBD permissive | ✅ (verify upstream) |
| claude-md-management | TBD permissive | ✅ (verify upstream) |
| Frontend Design (conditional) | TBD permissive | ✅ (verify upstream) |
| Ralph (not bundled) | TBD permissive | ✅ (verify upstream) |
| **RenOS** | **MIT** | ✅ Fully |

The mix is dominated by permissive licenses. ELv2 (Context Mode) is the one explicit caveat — surfaced here, surfaced in the install-time confirmation prompt, and re-surfaced in `/ren:doctor` output ("Context Mode: ELv2 — SaaS distribution restricted; see LICENSES.md").

---

## What to do if you don't agree

The framework's value depends on the stack, and the stack's mix includes ELv2. If you cannot accept Context Mode's terms:

1. **Don't run `/ren:install`** — exit before Stage 2.
2. **Or substitute Context Mode** with a permissively-licensed token-efficiency plugin of your choice. The framework's architecture supports plugin substitution (per ADR-002), but you give up Context Mode's specific sandboxing approach.
3. **Or accept Context Mode for personal/team use** and design any future SaaS offering so Context Mode is not the user-facing feature. This is the path the original framework was designed around.

This file is informational, not legal advice. If your use case is commercial enough to matter, talk to a lawyer.

---

## Verifying the upstream licenses

When in doubt, check the live source:

```bash
# Each plugin's LICENSE file is in its source repo
gh api repos/obra/superpowers/contents/LICENSE -q '.content' | base64 -d | head -5
gh api repos/anthropics/skills/contents/LICENSE -q '.content' | base64 -d | head -5
gh api repos/thedotmack/claude-mem/contents/LICENSE -q '.content' | base64 -d | head -5
gh api repos/mksglu/context-mode/contents/LICENSE -q '.content' | base64 -d | head -5
gh api repos/upstash/context7/contents/LICENSE -q '.content' | base64 -d | head -5
```

The framework does NOT pin upstream license file SHAs. If an upstream re-licenses, `/ren:doctor`'s plugin section will need to surface the change in a future framework MINOR release (per ADR-006 § sunset-review triggers).

---

## References

- ADR-002 (Token-Efficiency Stack) — names Context Mode + claude-mem as required.
- ADR-006 (Curated Stack) — names the full plugin set + rejects the alternatives.
- ADR-015 Stage 6 — onboarding prompts the friend to acknowledge this file.
- ADR-016 (Framework License) — MIT for the framework itself.
- ADR-017 (Per-Friend Wiki Scope) — the per-friend-local design that this license summary applies to.
