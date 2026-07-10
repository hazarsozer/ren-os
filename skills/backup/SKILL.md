---
name: backup
description: |
  Use when the friend wants to back up their wiki to a private remote, or
  check backup status. Triggers on /ren:backup with optional subcommands
  (--setup, --tarball, --status). Git push primary, tarball fallback.
version: 0.4.3
license: MIT

framework_version: "0.4.3"
schema_version: 1
type: skill
execution_tier: deterministic

contract:
  required_outputs:
    - "For /ren:backup: either a successful git push to the 'backup' remote, OR a tarball at plugin_data_dir()/backups/wiki-<timestamp>.tar.gz"
    - "For /ren:backup --setup: git remote 'backup' configured on the wiki repo at the provided URL"
    - "For /ren:backup --tarball: a tarball, regardless of remote configuration"
    - "For /ren:backup --status: a printed report including last-backup timestamp + remote URL (or 'not configured')"
    - "Tarball retention enforced: at most TARBALL_RETENTION_KEEP (default 20) most-recent tarballs in the backups dir"
  budgets:
    turns: 2
    files_written: 1
    duration_seconds: 30
  permissions:
    read:
      - "~/.renos/wiki/**"
    write:
      - "~/.claude/plugins/data/renos/backups/**"
    execute: []
  completion_conditions:
    - "On --status: status output naming wiki path, remote URL (or 'not configured'), and last-backup timestamp"
  output_paths:
    - "~/.claude/plugins/data/renos/backups/"

tags: [backup, wiki, remote, tarball]
related_skills: [metric-watch, doctor]
references_required: []
references_on_demand: []
---

# backup

Wiki-only backup: git push to a configured `backup` remote is primary; a local tarball is the fallback (no remote configured, push fails, or `--tarball` forced).

## Delta from donor: the remote is named `"backup"`, not `"origin"`

`skills.metric-watch.lib`'s `_check_backup` (Task 6.3, shipped first) already checks for a git remote literally named `"backup"` and reads tarballs from `plugin_data_dir()/"backups"`. This skill's default remote name and backup directory match that contract exactly — `backup_configured()` (this skill) and `_check_backup()` (metric-watch) read the exact same state, so they can never silently disagree.

## When to use this skill

- Friend invokes `/ren:backup` (commits + pushes if the `backup` remote is configured; else tarball)
- Friend invokes `/ren:backup --setup <remote-url>` to configure the `backup` git remote (typically a private GitHub repo)
- Friend invokes `/ren:backup --tarball` to force a tarball even if a remote is configured
- Friend invokes `/ren:backup --status` for a status report

## Behavior

### `/ren:backup`

1. Refuse if the wiki isn't a git repo (point at `/ren:install`).
2. Commit any pending changes (idempotent if the tree is clean).
3. If a `backup` remote is configured: push. Success → done, no tarball. Non-fast-forward → refuse (never force-push automatically; point at the recovery doc). Transport failure → tarball fallback + warning.
4. If no remote configured: tarball, with a nag to run `--setup`.
5. After any tarball: prune to `TARBALL_RETENTION_KEEP` (default 20) most recent.

### `/ren:backup --setup <remote-url>`

Validates the URL shape, confirms the wiki is a git repo, adds or updates the `backup` remote, and reads it back to confirm.

### `/ren:backup --tarball`

Skips the push path entirely; always tarball (commits pending changes first).

### `/ren:backup --status`

Read-only report: is the wiki a git repo, remote URL (or "not configured"), last commit sha/date, tarball count + oldest/newest tarball dates.

## Remote-change confirmation is NOT re-implemented here

Donor's SKILL.md described a "confirm before changing the backup remote" behavior at the skill level. In RenOS, that confirmation is enforced structurally by the Task 6.2 `write_gate` PreToolUse hook (`hooks/guards/write_gate.py`), which already gates backup-remote-change operations per spec §3.6 A-8 item 6. This skill's `setup_remote()` does not duplicate that confirmation — it trusts the hook layer to have already gated the call before this function runs.

## What this skill does NOT do

- Back up anything other than the wiki. Plugin-internal state (e.g. other plugins' local caches) is explicitly out of scope.
- Force-push on a non-fast-forward rejection. That's a human decision, always.
- Decide backup cadence. `/ren:metric-watch`'s `backup-unconfigured` finding is the nag mechanism for "you haven't backed up"; this skill just performs the backup when invoked.

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| No remote configured + `/ren:backup` | Tarball fallback automatic + nag | "No remote configured. Created tarball at \<path\>. Configure with /ren:backup --setup \<url\>" |
| git push network failure | Tarball fallback + warning | "Push failed (network). Tarball at \<path\>. Retry with /ren:backup later." |
| Non-fast-forward push rejection | Refused, no auto-tarball (user decision moment) | "Push rejected: remote diverged. See recovery doc. Force-push NOT performed automatically." |
| Wiki not a git repo | Refused | "Wiki is not a git repo. Run /ren:install to bootstrap." |

## References

- Task 6.3 (`skills/metric-watch/lib`) — the `_check_backup` contract this skill's `backup_configured()`/remote-name/dir match exactly
- Task 6.2 (`hooks/guards/write_gate.py`) — the remote-change confirmation enforcement layer
- `skills/backup/lib/__init__.py` (donor, `~/Dev/startup-framework`) — the carried implementation
