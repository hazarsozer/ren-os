# Stage 3 — Conditional plugins

Per ADR-015 Stage 3 (revised 2026-05-28) + ADR-006 + ADR-031 (solo-first pivot).

Solo-first (ADR-031): the former Activity Feed setup that opened Stage 3 was removed with the feed module. Stage 3 is now conditional-plugins-only. There is no repo prompt, no repo-state detection, no clone/bootstrap, and no mini-handle prompt — with no shared feed there are no cross-friend handle collisions to guard against. The handle is set in Stage 4 (interview).

## Two conditionals

### Frontend Design (install-on-demand)

Ask:

```
Will you build user-facing UIs (web or mobile apps) in the near term?
  yes      — install Frontend Design now
  later    — skip; you can install later via /plugin install frontend-design
  no       — skip; we'll never auto-prompt again
```

- **yes** → run `/plugin install frontend-design@anthropic-agent-skills` (or the marketplace path sf-distribution's registry specifies).
- **later** → skip; do NOT persist a "never-ask" flag.
- **no** → skip; persist `stage_artifacts.3.frontend_design_dismissed: true` so future re-runs of Stage 3 don't re-prompt.

Persist outcome to `stage_artifacts.3.frontend_design_installed: <bool>`.

### Ralph autonomous loop (documented, NOT installed)

Per ADR-006 + ADR-015: Ralph is a powerful pattern but should NOT be auto-installed. Print the documentation message:

```
Ralph (autonomous loop pattern) is documented but not auto-installed.
  When you have a long-running task that benefits from "loop until done"
  semantics, install it manually with:
    /plugin install ralph-loop@claude-plugins-official
  Caveat: Ralph's Stop hook collides with /sf:wrap; if you adopt Ralph,
  review ADR-009 to understand the trade-off.
```

No prompt; just inform. Persist `stage_artifacts.3.ralph_loop_documented_only: true` if the friend acknowledges (any continuation gesture); otherwise leave the field unset.

## State recorded

After both conditionals run:

```json
{
  "stage_artifacts": {
    "3": {
      "frontend_design_installed": false,
      "frontend_design_dismissed": false,
      "ralph_loop_documented_only": true
    }
  }
}
```

## Cross-references

- ADR-006 (curated stack) — conditional vs required vs documented-only
- ADR-015 Stage 3 (amendment)
- ADR-031 (solo-first pivot) — Activity Feed removal; Stage 3 is conditional-plugins-only
