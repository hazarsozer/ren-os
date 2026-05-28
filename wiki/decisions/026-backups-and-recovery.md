---
title: "ADR-026: Backups & Recovery — `/sf:backup` Command + Per-Layer Recovery Story"
status: accepted
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [claude-mem, context-mode]
affects-components: [skills, install, doctor, distribution, wiki, recovery]
relates-to: [015-onboarding, 017-per-friend-wiki-scope, 018-activity-feed, 019-framework-distribution, 025-tech-stack-matrix]
---

# ADR-026: Backups & Recovery

## Context

Friends lose laptops, accidentally `rm -rf` directories, or have SQLite corruptions. The framework's per-friend-local design (per ADR-017) means each friend bears their own backup responsibility for their wiki. Without clear documentation + tooling, friends are left guessing what's recoverable when.

Per user direction:
- Yes — ship a `/sf:backup` command (small wrapper; useful)
- No — don't backup claude-mem / Context Mode SQLites (their plugin's responsibility)
- Yes — write a recovery doc + flag missing remote in `/sf:doctor`

## Decision

### `/sf:backup` slash command (ships with framework)

A convenience wrapper that backs up the friend's wiki + everything in it (identity, project sub-wikis, custom skills authored by the friend, decisions/ ADRs the friend has written for their own use).

**Behavior:**

```
/sf:backup                          # Push wiki to configured git remote (commits any uncommitted changes first)
/sf:backup --setup <remote-url>      # Configure a git remote for wiki (typically a private GitHub repo)
/sf:backup --tarball                 # Force local tarball backup even if remote configured (for offline use)
/sf:backup --status                  # Show last backup timestamp + remote URL
```

**What gets backed up:**
- Everything in `~/.startup-framework/wiki/` (the per-friend wiki, including identity.md, project sub-wikis, custom skills, decisions, etc.)
- The wiki is a git repo per ADR-017; this command is essentially:
  ```bash
  cd ~/.startup-framework/wiki/
  git add -A
  git commit -m "/sf:backup at <timestamp>"
  git push                          # if remote configured
  ```
- If no remote: creates `~/.startup-framework/backups/wiki-<timestamp>.tar.gz`

**What does NOT get backed up by `/sf:backup`:**
- claude-mem SQLite (per user direction — plugin's responsibility)
- Context Mode per-project SQLite (per user direction — plugin's responsibility)
- Activity Feed local clone (it's already on GitHub via Activity Feed's own pushes per ADR-018; the GitHub remote IS the backup)
- Plugin install state (just re-install via marketplace per ADR-019)
- Friends who care about plugin-internal state set up their own backup tooling (e.g., back up `~/.claude-mem/` to private cloud via their own cron)

**Setup walkthrough during `/sf:install` (amends ADR-015 Stage 5 — Wiki bootstrap):**

After creating the wiki, ask the friend: "Want to set up a remote for your wiki backup? Recommended: a private GitHub repo (your own, not the shared friend-group one)." → if yes: run through `gh repo create <name> --private` + `git remote add origin <url>` + `git push -u origin main`.

If friend skips: `/sf:doctor` will flag the missing remote as a warning (not error) later.

### `/sf:install --restore <remote-url>` for new-machine recovery

When a friend gets a new machine (or fresh-installs after losing their old wiki):

```
/sf:install --restore <wiki-remote-url>
```

Instead of Stage 5 creating a fresh wiki, it clones from the provided URL. Identity, project sub-wikis, all custom content restored. Wakes up next session with the right context.

### Per-layer recovery matrix (documented in `RECOVERY.md`)

The framework ships a `RECOVERY.md` doc covering the disaster scenarios honestly:

| Layer | Backup mechanism | Recovery mechanism |
|---|---|---|
| **Friend's local wiki** | `/sf:backup` → configured git remote (or tarball if no remote) | `/sf:install --restore <remote-url>` on a new machine; OR partial reconstruction from Activity Feed summary entries (lossy) |
| **claude-mem SQLite** | **Friend's own backup tooling** (recommendation: `~/.claude-mem/` to private cloud) — framework does NOT manage | Rebuilt naturally via new session capture; old observations lost if no friend-managed backup |
| **Context Mode SQLite** (per-project) | **Friend's own backup tooling** — framework does NOT manage | Rebuilt naturally via new session use; old session_resume snapshots lost |
| **Activity Feed local clone** | Activity Feed GitHub repo IS the backup (multi-friend redundancy) | `git clone` from GitHub; if GitHub itself goes down, any friend's local clone can re-push to a new remote |
| **Framework plugin code** | Marketplace repo IS the source; friends have local installs | `/sf:install` for fresh; `/sf:update` for existing |
| **Identity** | In wiki; covered by wiki backup | Re-run `/sf:interview` OR restore from wiki backup |
| **Project sub-wikis** | In wiki; covered by wiki backup | Same as wiki |
| **Custom-authored skills** | In wiki (skills live at `wiki/skills/<name>/` per ADR-011 convention); covered by wiki backup | Same as wiki |

### `/sf:doctor` integration

Per ADR-025's tech stack matrix + this ADR's recovery story, `/sf:doctor` adds backup-status checks:

```
Wiki backup:
  Git remote: ⚠️  not configured (recommend: /sf:backup --setup <your-private-repo-url>)
  Last commit: 3 days ago (3 commits ahead of any remote)

Activity Feed:
  Git remote: ✅ <our-org>/activity-feed
  Last push: 12 minutes ago
```

If a friend has no wiki remote AND it's been >7 days since their last commit, `/sf:doctor` upgrades the warning to a stronger nudge ("⚠️⚠️ Configure a wiki backup before you lose context — it would be hard to reconstruct"). Don't block work, just nag clearly.

### Disaster scenarios documented in RECOVERY.md

Honest walkthrough of common situations:

1. **"I lost my laptop"**
   - On new machine: `/sf:install --restore <wiki-remote>` (if you set one up)
   - If no remote: your wiki is gone; partial reconstruction from Activity Feed possible (lossy)
   - claude-mem + Context Mode observations are gone; rebuild over time

2. **"I accidentally rm -rf'd my wiki"**
   - If remote configured: `cd ~/.startup-framework && git clone <remote> wiki`
   - If only tarball backups: `tar -xzf ~/.startup-framework/backups/wiki-<latest>.tar.gz -C ~/.startup-framework/`

3. **"GitHub is down"**
   - Activity Feed pushes fail silently; sessions still work locally
   - Marketplace pulls fail; you can't `/sf:update`; existing install still works
   - Wait for GitHub to come back, or switch remotes to GitLab/Gitea later

4. **"My claude-mem DB got corrupted"**
   - claude-mem's own recovery story applies (see their docs)
   - In the worst case, delete `~/.claude-mem/` and let it rebuild from new sessions

5. **"I want to delete a session report from Activity Feed"**
   - Per ADR-021: hard. Requires coordinated git history rewrite + force push + every friend re-cloning. Document the procedure but emphasize prevention.

6. **"A friend left the group and I need to wipe their data"**
   - GitHub admin removes them as collaborator on both repos (per ADR-020)
   - Their existing log entries stay in Activity Feed as historical record (not deleted; ADR-020 design)
   - If a destructive scrub is needed: ADR-021's coordinated history rewrite

## Consequences

**Easier:**
- Friends have a one-command backup (`/sf:backup`) for the layer that matters most (wiki)
- New-machine recovery is a single command (`/sf:install --restore`)
- Friends know what's NOT backed up by the framework (honest about plugin-internal state)
- `RECOVERY.md` is concrete; not "good luck, figure it out"
- `/sf:doctor` nags about missing remotes — friends won't accidentally go a year without backup

**Harder:**
- Friends still need to set up their own git remote (one-time; can skip but at their own risk)
- Plugin-internal state (claude-mem, Context Mode) has no framework-managed safety net — friends who lose their machine lose observation history
- Tarball fallback is "better than nothing" but tarballs are a hassle to manage (timestamps, where to store, when to prune)

**Now impossible:**
- A friend losing their wiki to disk failure without prior remote setup — RECOVERY.md is honest that this is unrecoverable beyond Activity Feed summaries
- The framework silently managing plugin-internal state friends didn't know existed

**Sunset review trigger conditions:**
- A friend actually has a "I lost my wiki" incident and the recovery is messier than documented → improve
- claude-mem or Context Mode ships a built-in cross-machine sync that obviates a chunk of this concern → adapt
- `/sf:tidy` (the v2 disk-growth skill flagged in ADR-025) ships and ties into recovery (e.g., pre-tidy backup automatic) → integrate

## Alternatives considered

### A) Skip `/sf:backup`; document `git remote` recipe only

**Considered shape**: Tell friends `git remote add + git push` covers it; no command.

**Why rejected per user direction**: User said "I think backup command is useful. It might be okay to ship." Convenience wrapper has real value for friends who don't think about git daily.

### B) Auto-backup on every session end

**Considered shape**: Hook into `/sf:wrap` (or SessionStart) to auto-push wiki to remote every session.

**Why rejected**: Friction. Network failures would make sessions fail. Friends should backup deliberately (or via cron if they want). `/sf:doctor` nags if it's been too long; that's enough.

### C) Framework manages claude-mem + Context Mode backups too

**Considered shape**: `/sf:backup` includes plugin-internal SQLites.

**Why rejected per user direction**: "Not necessary. Their responsibility." Right call — those plugins have their own state management; we shouldn't reach in.

### D) `/sf:backup` only does git push; no tarball fallback

**Considered shape**: Require a remote; refuse to backup if no remote configured.

**Why rejected**: Tarball is a useful fallback for friends in low-connectivity situations or who haven't set up a remote yet. Better-than-nothing > nothing.

### E) Cloud-managed backup service (Backblaze / S3 integration)

**Considered shape**: Framework integrates with a cloud backup provider for the wiki.

**Why rejected**: Scope explosion. Friends can configure their own cloud sync tools (Dropbox, iCloud, rclone to S3, etc.) on top of the wiki directory if they want. Framework provides the git-remote pattern as the primary recommendation; other clouds are friend-DIY.

## Open questions for implementation phase

1. **Where do tarballs go by default?** `~/.startup-framework/backups/` is my suggestion; would need to be created on first tarball backup. Configurable via env or settings.

2. **How many tarballs to retain?** Without pruning, tarballs accumulate forever. Default policy: keep last 7 daily tarballs + last 4 weekly + last 12 monthly? Or simpler: keep last N, where N=20. Defer to implementation.

3. **`/sf:doctor` nag thresholds** — when does "missing remote" become a warning vs. a stronger nag? 7 days is my suggestion; tune based on actual friend usage.

4. **`/sf:backup --restore` vs. `/sf:install --restore`** — should restore be its own command (operates on an existing install) or only available during fresh install? Probably both: `/sf:install --restore` for new machine + `/sf:backup --restore <archive>` for "I lost my wiki on an existing setup."

5. **What if the wiki git remote URL is in identity.md** (so it's restored automatically when you clone the wiki from remote)? Chicken-and-egg: you need the wiki to know where to clone the wiki from. Best path: friend stores the wiki URL somewhere portable (password manager, README in their personal notes), or `/sf:install --restore` accepts the URL on the command line.

## References

- `wiki/research/claude-mem.md` — plugin-internal state we don't manage
- `wiki/research/context-mode.md` — same
- ADR-015 (Onboarding) — Stage 5 wiki bootstrap, this ADR adds optional remote setup
- ADR-017 (Per-Friend Wiki Scope) — self-sync recommendation that this ADR operationalizes
- ADR-018 (Activity Feed) — Activity Feed's own GitHub-as-backup story (no framework action needed)
- ADR-019 (Framework Distribution) — marketplace re-install path for plugin code
- ADR-021 (Privacy Boundaries) — "deletion is hard" reality + the destructive-scrub procedure
- ADR-025 (Tech Stack Matrix) — `/sf:doctor` formal output format, this ADR adds the backup checks
