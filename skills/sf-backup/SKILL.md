---
name: sf-backup
description: |
  Use when the friend wants to back up their local wiki — either to a
  configured git remote (preferred) or to a local tarball (fallback). Triggers
  on /sf:backup with optional subcommands (--setup, --tarball, --status).
  Per ADR-026: the framework backs up the wiki ONLY; plugin-internal state
  (claude-mem, Context Mode SQLites) is each plugin's own responsibility and
  not in scope. New-machine recovery from a git remote is handled by
  /sf:install --restore (onboarding-2's surface), not by this skill.
version: 0.1.0
license: MIT

framework_version: "1.0.0"
schema_version: 1
type: skill

contract:
  required_outputs:
    - "For /sf:backup: either a successful git push to the configured remote, OR a tarball at ~/.startup-framework/backups/wiki-<timestamp>.tar.gz"
    - "For /sf:backup --setup: git remote 'origin' configured on the wiki repo at the provided URL"
    - "For /sf:backup --tarball: a tarball, regardless of remote configuration"
    - "For /sf:backup --status: a printed report including last-backup timestamp + remote URL (or 'not configured')"
    - "Tarball retention enforced: at most TARBALL_RETENTION_KEEP (default 20) most-recent tarballs in the backups dir"
  budgets:
    turns: 3
    files_written: 5
    duration_seconds: 60
  permissions:
    read:
      - "~/.startup-framework/wiki/**"
      - "~/.startup-framework/backups/**"
    write:
      - "~/.startup-framework/wiki/.git/**"
      - "~/.startup-framework/backups/**"
    execute:
      - "git (in ~/.startup-framework/wiki/)"
      - "tar (when fallback fires)"
  completion_conditions:
    - "Run exits with a printed status line clearly indicating which path was taken (push success / push deferred / tarball created / setup complete / status reported)"
    - "On --setup: wiki/.git/config contains the new remote URL"
    - "On --tarball or push-failure-fallback: tarball file exists at the expected path"
    - "On --status: status output naming wiki path, remote URL (or 'not configured'), and last-backup timestamp"
  output_paths:
    - "~/.startup-framework/wiki/"  # git remote config + commits
    - "~/.startup-framework/backups/"  # tarballs

tags: [backup, recovery, lifecycle, wiki]
related_skills: [sf-install, sf-doctor]
references_required: []
references_on_demand: []
---

# sf-backup

Per-friend wiki backup with two paths:
1. **Primary**: commit + push to a configured git remote (the canonical recommendation per ADR-026 — a private GitHub repo on the friend's own account)
2. **Fallback**: local tarball at `~/.startup-framework/backups/wiki-<YYYY-MM-DD-HHMMSS>.tar.gz` (when no remote configured, when push fails, or when `--tarball` is forced)

This skill ONLY backs up the wiki. Plugin-internal state (claude-mem / Context Mode SQLites) is each plugin's own responsibility per ADR-026's explicit "what does NOT get backed up" list. Friends who want those SQLites preserved bolt on their own cron/cloud-sync tooling.

## When to use this skill

- Friend invokes `/sf:backup` (canonical trigger; commits + pushes if remote configured; else tarball)
- Friend invokes `/sf:backup --setup <remote-url>` to configure a git remote for the wiki (typically a private GitHub repo)
- Friend invokes `/sf:backup --tarball` to force a tarball even if a remote is configured (offline use, paranoia, etc.)
- Friend invokes `/sf:backup --status` to check the wiki's backup state without performing any backup
- `/sf:doctor` may suggest invoking this when missing-remote nag fires (per ADR-026 §"/sf:doctor integration")

## When NOT to use this skill

- Friend wants new-machine recovery → `/sf:install --restore <url>` (onboarding-2's domain)
- Friend wants to back up claude-mem / Context Mode SQLites → that's their plugin's responsibility per ADR-026; the framework doesn't manage plugin-internal state
- Friend wants Activity Feed backed up → the GitHub remote IS the backup per ADR-026 §"What does NOT get backed up by /sf:backup"
- Friend wants to push the wiki to ANY non-git destination → out of scope; we only do git push or local tarball

## Behavior by subcommand

### `/sf:backup` (default)

1. Read wiki state at `~/.startup-framework/wiki/`. Refuse if not a git repo (point at `/sf:install` to bootstrap).
2. `git add -A` and commit any uncommitted changes with message `"sf:backup at <YYYY-MM-DD HH:MM:SS UTC>"`.
3. If a remote is configured:
   - Attempt `git push`. On success → "✓ wiki backed up to <remote>".
   - On auth/network failure → fall through to tarball with a note in the output: "git push failed; created tarball instead at <path>".
   - On force-push-required (history rewrite) → refuse with a pointer to RECOVERY.md; no tarball auto-fallback (this is a user-decision moment).
4. If no remote configured → tarball + status nag suggesting `--setup`.

### `/sf:backup --setup <remote-url>`

1. Validate `<remote-url>` looks like a git URL (basic shape check — defer to `git` for full validation).
2. `cd ~/.startup-framework/wiki && git remote add origin <url>` (or `set-url` if 'origin' already exists; we let the friend override).
3. Confirm by reading back `git remote get-url origin`.
4. Do NOT auto-push. Friend runs `/sf:backup` separately to actually push. This split keeps "configure" idempotent and disentangles auth-failure from setup confusion.

### `/sf:backup --tarball`

1. Read wiki state.
2. Create `~/.startup-framework/backups/wiki-<YYYY-MM-DD-HHMMSS>.tar.gz` covering the entire wiki directory (incl. `.git/` so the tarball is a complete restore artifact).
3. Prune to retain the most-recent `TARBALL_RETENTION_KEEP` (default 20) tarballs; older are deleted.
4. Report path + size.

### `/sf:backup --status`

Print:
- Wiki path: `~/.startup-framework/wiki/`
- Git remote: `<url>` or `not configured (suggest: /sf:backup --setup <url>)`
- Last commit: `<sha> from <date>` (or `no commits yet`)
- Last push: `<date>` (or `never`) — computed via `git log <remote>/main --oneline -1` if remote exists
- Tarballs: `<count>` files, oldest from `<date>`, newest from `<date>` (or `none`)

## Failure-degradation modes

| Failure | Behavior | User-visible |
|---|---|---|
| Wiki not a git repo | Refuse; suggest `/sf:install` to bootstrap | "Wiki at <path> is not a git repo. Run /sf:install to bootstrap." |
| No remote configured + `/sf:backup` | Tarball fallback automatic + nag | "No remote configured. Created tarball at <path>. Configure a remote with /sf:backup --setup <url>" |
| git push auth failure | Tarball fallback + warning | "Push failed (auth). Tarball at <path>. Check `gh auth status`." |
| git push network failure | Tarball fallback + warning | "Push failed (network). Tarball at <path>. Retry with /sf:backup later." |
| git push rejected (non-fast-forward) | Refuse force-push; surface RECOVERY.md | "Push rejected: remote diverged. See RECOVERY.md §'remote-history-rewrite' before proceeding." |
| Tarball dir unwritable | Surface error with override hint | "Backup dir unwritable. Override via SF_BACKUP_DIR env var or fix permissions." |
| `--setup` with bad URL shape | Refuse before touching git | "URL doesn't look like a git remote. Expected git@github.com:user/repo.git or https://..." |

## Implementation note

V1 implementation in `skills/sf-backup/lib/`:
- `lib/types.py` — `BackupResult`, `StatusResult` dataclasses (frozen)
- `lib/__init__.py` — public `backup()`, `setup_remote()`, `status()` entry points + pure-logic helpers (`tarball_filename_for`, `prune_old_tarballs`, `looks_like_git_url`)

The pure-logic layers are fully unit-testable. The subprocess calls (`git`, `tar`) are wrapped in thin functions that take `cwd` arg for tmpdir-driven integration tests.

## References

- ADR-026 (Backups and Recovery) — design rationale + the explicit "what does NOT get backed up" list
- ADR-017 (Per-Friend Wiki Scope) — self-sync recommendation this skill operationalizes
- `docs/RECOVERY.md` (distribution-2 shipped) — the recovery doc this skill points at on remote-history-rewrite refusal
- `skills/sf-install/SKILL.md` — Stage 5 wiki bootstrap that creates the git repo this skill backs up
- `skills/sf-doctor/SKILL.md` — surfaces the missing-remote nag that points friends at `/sf:backup --setup`
