# Stage 4 — Identity bootstrap

Per ADR-015 Stage 4 + ADR-022 + ADR-031 (solo-first pivot). Delegates the full work to the `sf-interview` skill.

Solo-first (ADR-031): Stage 4 writes ONLY the local `wiki/identity.md`. The former Activity Feed identity push (public summary) and the handle-rename-on-feed behavior were removed with the feed module. The handle still lives in identity.md frontmatter; it's just no longer mirrored to any shared feed.

## Procedure

### 4.1 Invoke sf-interview

Call the `sf-interview` skill with the orchestrator context. The skill receives access to:

- `state.framework_version` — written into identity.md frontmatter
- A flag indicating "first-run during install" so the skill knows to skip its own detection-of-existing-identity branch

Pass the state via the skill's invocation contract; the orchestrator doesn't need to inline the question template here. See `skills/sf-interview/SKILL.md`.

### 4.2 Capture outcomes

After sf-interview completes, the local file `~/.startup-framework/wiki/identity.md` exists with all required frontmatter, including the `handle:` field collected during the interview.

Persist:

```json
{
  "stage_artifacts": {
    "4": {
      "identity_path": "~/.startup-framework/wiki/identity.md",
      "handle_written": "<final-handle-from-interview>"
    }
  }
}
```

The handle is a local-only field in identity.md frontmatter. With no shared feed there is no public mirror to rename, no collision check against other friends, and no push step — identity.md is the single source of truth.

### 4.3 Friend-facing summary

```
Stage 4 — Identity bootstrapped:
  Handle:           <handle>
  Local file:       ~/.startup-framework/wiki/identity.md
```

## What this stage deliberately does NOT do

- Doesn't run the interview itself. Sf-interview is the canonical implementation.
- Doesn't validate the frontmatter schema beyond what sf-interview's eval already asserts.
- Doesn't push anything to a shared feed (removed with the solo-first pivot, ADR-031). identity.md is local-only.

## Cross-references

- ADR-022 — sf-interview spec
- ADR-031 (solo-first pivot) — Activity Feed removal; identity is local-only
- `skills/sf-interview/SKILL.md` — the delegated work
