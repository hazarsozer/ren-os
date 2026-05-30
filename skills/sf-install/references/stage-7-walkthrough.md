# Stage 7 — First-session walkthrough

Per ADR-015 Stage 7. Last stage of `/sf:install`. One-shot per checkpoint.

## Procedure

### 7.1 Print the daily-command tour

```
✓ Install complete. Your framework, organized by the Four C's
  (Context → Connections → Capabilities → Cadence — each built on the last):

  Context — a wiki that remembers:
    /sf:wake-up        — start a session; loads relevant wiki context (automatic on SessionStart)
    /sf:recall <query> — search your wiki for past context
    /sf:note <text>    — quick capture without ending the session

  Connections — your stack + its keys:
    /sf:doctor               — verify environment, plugins, schema versions, updates, backups
    /sf:doctor --permissions — read-only audit of the tool-keys on your ring (keys ≠ instructions)

  Capabilities — skills (some EXPERIMENTAL — bike-method: training wheels until earned):
    /sf:bootstrap-project <kebab-name>  — new project sub-wiki
    /sf:improve-skill <skill-name>      — Karpathy loop on a skill you've written (EXPERIMENTAL)
    /sf:interview                       — re-run identity questions; refresh sections or full

  Cadence — the daily loop:
    /sf:wrap           — end a session; promote real signal to the wiki (classifier is EXPERIMENTAL)
    /sf:insights       — read-only: what's working / what's slowing you down, from your session history
    /sf:update         — pull a newer framework version + migrate wiki schema
    /sf:backup         — push wiki to a private git remote
    /sf:install --reset  — wipe install state and restart (does NOT touch wiki/plugins)

  CLAUDE.md hygiene (from claude-md-management plugin):
    /revise-claude-md   — per-project CLAUDE.md cleanup; complements /sf:wrap
```

### 7.2 When-to-use-what guidance

Per ADR-015 amendment + ADR-009 amendment:

```
/sf:wrap vs /revise-claude-md:
  /sf:wrap          → promotes session signal to the wiki (team-level memory)
  /revise-claude-md → cleans up the current project's CLAUDE.md (project-level config)
  Both are useful; they target different layers.

/sf:insights vs reading the wiki log by hand:
  /sf:insights      → mines your local session history; "what's working / what's hindering"
  hand-read         → fine for spelunking, slower for daily orientation

/sf:improve-skill vs editing SKILL.md by hand:
  /sf:improve-skill → Karpathy loop, eval-driven, branch-per-run
  hand-edit         → fine for quick tweaks; you lose the eval safety net
```

### 7.3 Plugin marketplace as discovery surface

```
You can discover per-project domain plugins (e.g. AWS / Vercel / Supabase / Resend)
via:
  /plugin marketplace
Friends pick these when they commit to a project, not at install. The framework
won't auto-install domain plugins.
```

### 7.4 First-action suggestion

```
Suggested first action:
  /sf:wake-up           ← starts your first session; sees your fresh identity
  (or, if you're ready to start a project)
  /sf:bootstrap-project <name>
```

### 7.5 Acknowledge + persist

Ask:

```
Ready? (y to acknowledge and finish install; press anything else to re-read the tour)
```

On `y`, persist:

```json
{
  "stage_artifacts": {
    "7": {
      "walkthrough_acknowledged": true,
      "acknowledged_at": "<ISO>"
    }
  }
}
```

Append `7` to `state.completed_stages`. Print the final install summary (see SKILL.md step 4).

## What this stage deliberately does NOT do

- Doesn't auto-invoke any of the listed commands. The friend pulls the trigger; per pushback P3.
- Doesn't repeat content from `/sf:doctor`'s summary; Stage 6 covered that.
- Doesn't show every framework command. Edge-case slash commands live in `/sf:help` (future).

## Edge cases

- **Friend re-runs `/sf:install` after a successful completion** — Stage 7 sees `walkthrough_acknowledged: true` in the checkpoint; skips. Print "already complete" summary instead.
- **Friend uses `--redo-stage 7`** — re-shows the tour; re-prompts acknowledgment.
- **Friend says "no" or anything other than `y`** — print the tour again. Loop until acknowledged or the friend exits.

## Cross-references

- ADR-015 Stage 7
- ADR-009 amendment (/revise-claude-md complements /sf:wrap)
- ADR-031 (solo-first pivot) — Four C's framing; no Activity Feed; `/sf:insights` + `/sf:doctor --permissions` are the new read-only surfaces
- team-lead pushback P3 (manual handoff, no auto-invoke)
