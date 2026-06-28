# Recovery

Honest walkthroughs for the disaster scenarios that hit a RenOS install. Read this before something breaks, not after.

Per ADR-026 + ADR-027.

---

## Quick reference: what's recoverable vs not

| Layer | Backup mechanism | Recoverable? |
|---|---|---|
| Your wiki (`~/.startup-framework/wiki/`) | `/ren:backup` → configured git remote (or tarball fallback) | Yes, IF you set up a remote |
| Pre-migration wiki snapshots | Automatic at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/` | Yes, latest 3 retained |
| Framework plugin code | The marketplace repo IS the source; you have a local install | Yes — `/ren:install` or `/ren:update` |
| Identity (`wiki/identity.md`) | In wiki; covered by wiki backup | Yes (or re-run `/ren:interview`) |
| Project sub-wikis | In wiki; covered by wiki backup | Yes |
| Authored skills (`wiki/skills/<name>/`) | In wiki; covered by wiki backup | Yes |
| claude-mem SQLite | **Your own backup tooling** — framework does NOT manage | Rebuilds naturally from new sessions; old observations lost if no friend-managed backup |
| Context Mode per-project SQLite | **Your own backup tooling** — framework does NOT manage | Rebuilds naturally; old session_resume snapshots lost |

The framework's responsibility ends at the wiki layer. Plugin-internal SQLites are the plugin authors' surface; back them up yourself if you care about that history.

---

## Scenario 1: "I lost my laptop"

You have a new machine. Your old wiki is gone.

**If you had configured a remote** (`/ren:backup --setup` ran successfully earlier):

```bash
# 1. Install Claude Code on the new machine
# 2. Install the framework
/plugin marketplace add <org>/ren-os
/plugin install ren@ren-os

# 3. Restore on install
/ren:install --restore <your-wiki-remote-url>
```

`/ren:install --restore` clones the remote into the configured `wikiRoot` instead of Stage 5 creating a fresh wiki. Identity, project sub-wikis, authored skills — all restored. Wake up next session with the right context.

**If you did NOT configure a remote:**

Your wiki is gone, and there's no recovery path. (Activity Feed removed — ADR-031; there's no cross-machine copy of your terse session entries to reconstruct from.) Without a remote or tarball backup, the wiki is unrecoverable.

claude-mem + Context Mode observation history is also gone unless YOU backed up `~/.claude-mem/` and the Context Mode SQLites yourself. They will rebuild from new sessions.

**Lesson:** Configure a wiki remote on day 1. `/ren:doctor` nags you about this; don't dismiss the nag.

---

## Scenario 2: "I accidentally `rm -rf`'d my wiki"

The wiki dir on disk is gone. Disk is fine. Same machine.

**If remote configured:**

```bash
cd ~/.startup-framework
git clone <your-wiki-remote-url> wiki
# verify
/ren:doctor
```

**If only tarball backups exist** (you ran `/ren:backup --tarball` ever):

```bash
ls ~/.startup-framework/backups/wiki-*.tar.gz
# pick the latest
tar -xzf ~/.startup-framework/backups/wiki-<latest>.tar.gz -C ~/.startup-framework/
/ren:doctor
```

**Special case — recent `/ren:update` ran**: there is also a pre-migration snapshot at `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/` (see Scenario 4). Use the most recent snapshot if it's newer than your last `/ren:backup`. To find `CLAUDE_PLUGIN_DATA`:

```bash
ls ~/.claude/plugins/data/ | grep startup-framework
# typically: ren-ren-os
ls ~/.claude/plugins/data/ren-ren-os/wiki-snapshots/
# pick the most recent
cp -a ~/.claude/plugins/data/ren-ren-os/wiki-snapshots/<latest>/. ~/.startup-framework/wiki/
```

---

## Scenario 3: "A `/ren:update` migration broke my wiki"

You ran `/ren:update`, approved the diffs, but something feels wrong — a project STATE.md is missing data, identity got malformed, etc.

**First, check the snapshot.** Every `/ren:update` snapshots before migrating (per ADR-027). Locate the latest:

```bash
ls -lt ~/.claude/plugins/data/ren-ren-os/wiki-snapshots/
```

The most recent directory contains your wiki state immediately before the last `/ren:update`. To restore the whole wiki:

```bash
# Bash one-liner. Replace <latest> with the actual snapshot dir name.
SNAP=~/.claude/plugins/data/ren-ren-os/wiki-snapshots/<latest>
# Optional: tarball the current (broken) state in case you want to inspect it later
tar -czf ~/.startup-framework/backups/wiki-post-update-broken-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C ~/.startup-framework wiki
# Restore
rm -rf ~/.startup-framework/wiki
cp -a "$SNAP" ~/.startup-framework/wiki
# Verify
/ren:doctor
```

To restore a single page only:

```bash
SNAP=~/.claude/plugins/data/ren-ren-os/wiki-snapshots/<latest>
cp "$SNAP/identity.md" ~/.startup-framework/wiki/identity.md   # whatever the broken file is
/ren:doctor
```

**Alternative:** `/ren:update --restore-snapshot` (flag on the update command per ADR-023 V1 fence — no separate `/ren:rollback` slash command at v1). The flag triggers an interactive restore picker.

After restoring, decide:
- Was the migration buggy? File an issue on the marketplace repo so a patch ships.
- Was the diff approval mis-clicked? Re-run `/ren:update` and pay attention this time. The snapshot was retained per ADR-027's "leave snapshot in place so user can inspect" rule.

**Snapshot retention**: by default, the latest 3 snapshots are kept. Older snapshots beyond that are pruned automatically on each new `/ren:update`. Configurable via `userConfig.snapshotRetain`.

---

## Scenario 4: "GitHub is down"

GitHub is having an incident. Your local session works fine, but some commands fail.

What's affected:
- `/ren:backup` push fails (use `--tarball` as a temporary fallback).
- `/ren:update` marketplace fetch fails. **Your installed framework keeps running fine** — the failure only blocks the version check.
- `/ren:doctor` "FRAMEWORK UPDATE" section reports network failure but otherwise green.

What's not affected:
- Wiki reads + writes (local).
- claude-mem (local).
- Context Mode (local).
- Schema migrations already applied (local).

Wait for GitHub to come back. If GitHub is down for >24h and you need durability NOW, configure a secondary remote (GitLab or a self-hosted git) and `git push gitlab` as a fallback. The framework only cares about the primary remote name; you can have additional ones.

For fully-offline environments: set `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` so a failed marketplace pull doesn't wipe your local cache. See [CC docs § Marketplace updates fail in offline environments](https://code.claude.com/docs/en/plugin-marketplaces).

---

## Scenario 5: "My page is stuck at a deprecated schema (>N+3 versions behind)"

`/ren:doctor` reports:

```
▶ SCHEMA VERSIONS
  identity.md:        1  (current: 4)   ❌  schema v1 is now beyond the N+3 deprecation window
                                          → page is READ-ONLY; the framework will not write to it.
```

This happens if you skipped several `/ren:update`s and crossed the deprecation threshold. Per ADR-027, pages stuck at a deprecated schema become read-only — the framework still reads them but refuses to write to them, so any feature relying on the new schema fails for that page.

**Options (pick one):**

### Option A: Stepwise migration via snapshot restore

If you have a snapshot from before you crossed the threshold:

```bash
SNAP=~/.claude/plugins/data/ren-ren-os/wiki-snapshots/<old-snapshot>
# Manually inspect to confirm the page is at an intermediate schema
grep '^schema_version:' "$SNAP/identity.md"
# Restore the single page
cp "$SNAP/identity.md" ~/.startup-framework/wiki/identity.md
# Then re-run /ren:update — it will apply the chained migrations
/ren:update
```

This works if you happen to have a snapshot in the supported range. If your only snapshots are at v1 and the framework is at v4, you may need...

### Option B: Manually update the page to match the current schema

The framework's current schema for the page-type is documented in `skills/wiki-migration/schemas.json` (look at `page_types[<type>].current` for the target version) and in the CHANGELOG entries for each MAJOR release. Edit the page by hand to match. After editing, set the page's `schema_version` field to the current value and run `/ren:doctor` to confirm.

This is tedious but recoverable. Take your time, copy values carefully.

### Option C: Discard the page

If the page isn't valuable, delete it. The framework will work without it. `wiki/identity.md` being gone means you should re-run `/ren:interview` to recreate it. Project sub-wikis being gone means those projects lose their context — not great, but bounded.

**Prevention:** at monthly stable cadence per ADR-019, N+3 = ~3 months. Don't skip 3 months of updates. `/ren:doctor`'s schema-drift warning will start showing as soon as you fall 1 version behind.

---

## Scenario 6: "My `claude-mem` DB got corrupted"

claude-mem owns its own SQLite at `~/.claude-mem/`. The framework does NOT manage this layer (per ADR-026 — plugin-internal state is the plugin's responsibility).

Options:
- Check claude-mem's own recovery story in its docs (their plugin, their rules).
- Worst case: `rm -rf ~/.claude-mem/` and let it rebuild from your new sessions. You lose accumulated observations history but the framework's wiki layer is untouched.

The framework will keep working. `/ren:wake-up` reads the wiki, not claude-mem directly.

---

> **Note:** the old Activity Feed recovery scenarios (deleting a shared session report; removing a departed friend's access) are gone — the Activity Feed / multi-user layer was removed (ADR-031, solo-first pivot). The framework is now single-user: there is no shared repo to scrub and no collaborators to revoke.

---

## When to file a recovery issue

If you hit a scenario that's NOT in this document — or one that IS but the documented steps didn't work — file an issue in the marketplace repo. Include:

- `/ren:doctor` output
- The relevant `wiki/log.md` entries
- The most recent `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/` directory listing
- What you tried + what the error was

Per ADR-026 § sunset-review-triggers: if a recovery is messier than documented here, that's a signal to improve this doc + the supporting tooling.

---

## Things this document deliberately doesn't cover

- Generic Claude Code recovery (use the CC docs).
- Generic git recovery (use `git reflog`, etc.).
- Disaster recovery for projects you build with the framework (your responsibility, project by project).
- The maintainer's release recovery — see `RELEASING.md` § Recovery from a bad release.
