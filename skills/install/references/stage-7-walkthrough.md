# Stage 7 — First-session walkthrough

Per ADR-015 Stage 7. Last stage of `/ren:install`. One-shot per checkpoint.

## Procedure

### 7.1 Print the daily-command tour

```
✓ Install complete. Your framework, organized by the Four C's
  (Context → Connections → Capabilities → Cadence — each built on the last):

  Context — a wiki that remembers:
    /ren:wake-up        — start a session; loads relevant wiki context (automatic on SessionStart)
    /ren:recall <query> — search your wiki for past context
    /ren:note <text>    — quick capture without ending the session

  Connections — your stack + its keys:
    /ren:doctor               — verify environment, plugins, schema versions, updates, backups
    /ren:doctor --permissions — read-only audit of the tool-keys on your ring (keys ≠ instructions)

  Capabilities — skills (some EXPERIMENTAL — bike-method: training wheels until earned):
    /ren:bootstrap-project <kebab-name>  — new project sub-wiki
    /ren:improve-skill <skill-name>      — Karpathy loop on a skill you've written (EXPERIMENTAL)
    /ren:interview                       — re-run identity questions; refresh sections or full

  Cadence — the daily loop:
    /ren:wrap           — end a session; promote real signal to the wiki (classifier is EXPERIMENTAL)
    /ren:insights       — read-only: what's working / what's slowing you down, from your session history
    /ren:update         — pull a newer framework version + migrate wiki schema
    /ren:backup         — push wiki to a private git remote
    /ren:install --reset  — wipe install state and restart (does NOT touch wiki/plugins)

  CLAUDE.md hygiene (from claude-md-management plugin):
    /revise-claude-md   — per-project CLAUDE.md cleanup; complements /ren:wrap
```

### 7.2 When-to-use-what guidance

Per ADR-015 amendment + ADR-009 amendment:

```
/ren:wrap vs /revise-claude-md:
  /ren:wrap          → promotes session signal to the wiki (team-level memory)
  /revise-claude-md → cleans up the current project's CLAUDE.md (project-level config)
  Both are useful; they target different layers.

/ren:insights vs reading the wiki log by hand:
  /ren:insights      → mines your local session history; "what's working / what's hindering"
  hand-read         → fine for spelunking, slower for daily orientation

/ren:improve-skill vs editing SKILL.md by hand:
  /ren:improve-skill → Karpathy loop, eval-driven, branch-per-run
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
  /ren:wake-up           ← starts your first session; sees your fresh identity
  (or, if you're ready to start a project)
  /ren:bootstrap-project <name>
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
- Doesn't repeat content from `/ren:doctor`'s summary; Stage 6 covered that.
- Doesn't show every framework command. Edge-case slash commands live in `/ren:help` (future).

## Edge cases

- **Friend re-runs `/ren:install` after a successful completion** — Stage 7 sees `walkthrough_acknowledged: true` in the checkpoint; skips. Print "already complete" summary instead.
- **Friend uses `--redo-stage 7`** — re-shows the tour; re-prompts acknowledgment.
- **Friend says "no" or anything other than `y`** — print the tour again. Loop until acknowledged or the friend exits.

## Cross-references

- ADR-015 Stage 7
- ADR-009 amendment (/revise-claude-md complements /ren:wrap)
- ADR-031 (solo-first pivot) — Four C's framing; no Activity Feed; `/ren:insights` + `/ren:doctor --permissions` are the new read-only surfaces
- team-lead pushback P3 (manual handoff, no auto-invoke)
