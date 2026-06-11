---
title: "sf-backup learnings"
type: skill-learnings
parent_skill: sf-backup
version: 0.1.0
date: 2026-05-28
---

# sf-backup — learnings

## Open log

### 2026-05-28 — Refuse-force-push is the load-bearing safety invariant

The non-fast-forward branch is the one place where /ren:backup deliberately does NOT auto-fall-back to tarball. Reasoning: a diverged remote means the friend (or another friend with the same remote configured) pushed history that local doesn't have. Force-pushing would silently obliterate the remote's commits. The framework cannot make that call automatically.

The skill refuses with a pointer at `docs/RECOVERY.md §"remote-history-rewrite"`. The friend can:
1. `git pull --rebase` and resolve any conflicts, then re-run `/ren:backup`
2. Investigate via `git log origin/main..main` and `git log main..origin/main` to see what diverged
3. Explicitly force-push if they understand the consequences (NOT done by this skill; manual git command only)
4. Use `/ren:backup --tarball` to snapshot local state to a tarball while they figure out the divergence

The load-bearing pin: `binary_assertion`: "No force-push (`git push --force` / `--force-with-lease`) was issued during the run." If a future refactor accidentally adds force-push, this test fires immediately.

### 2026-05-28 — Use Python tarfile, not subprocess tar

Initial sketch was `subprocess.run(["tar", "czf", target, wiki_root])`. Switched to `tarfile.open(target, "w:gz")` for two reasons:
1. **Portability**: not all systems have `tar` on PATH (Windows especially); `tarfile` is stdlib.
2. **Cleanup discipline**: on failure mid-write, `tarfile` lets us `target.unlink()` the partial file in an `except` block. With subprocess, partial-tarball-on-error cleanup is harder.

Cost: `tarfile` is slightly slower than C `tar` for large wikis. At V1 wiki sizes (<<100 MB typical), the difference is sub-second; not worth the portability+cleanup trade.

### 2026-05-28 — Tarball includes .git/

The tarball captures the ENTIRE wiki dir including `.git/` so the restore artifact is complete. Without `.git/`, a friend restoring from tarball would have to re-init git + reconnect the remote + lose all branch/log history.

This is bigger than just the working files (`.git/objects/` can be MB-scale), but compression is good (most git objects are already zlib-deflated; gzip on top adds a bit of further compression).

Trade-off accepted: if the wiki includes any large binaries in `.git/lfs/` or similar, tarball sizes balloon. /ren:doctor could nag if tarball sizes exceed N MB, but that's v1.1 polish.

### 2026-05-28 — `--setup` is configure-only, not configure-and-push

Considered: have `--setup <url>` immediately also push as a UX shortcut ("set up + first backup in one command"). Rejected because:
1. Disentangles configure-failure from auth-failure in error messages
2. Idempotent: running `--setup` twice doesn't do unwanted writes
3. Friend may want to set up a remote that doesn't yet exist on GitHub (e.g., they'll `gh repo create` first), then run `/ren:backup` manually

The two-step flow is fine. Onboarding (Stage 5) walks friends through both.

### 2026-05-28 — `--restore` belongs to /ren:install, not here

ADR-026 §3 mentions both `/ren:install --restore <url>` (new-machine recovery) and a potential `/ren:backup --restore <archive>` (existing-machine recovery from a local tarball). 

I dropped both from this skill's scope:
- `/ren:install --restore` is mechanically Stage 5 wiki-bootstrap with a git clone instead of fresh init → onboarding-2's surface
- `/ren:backup --restore <archive>` from a tarball is a sharp tool (overwrites the wiki!) that warrants its own confirm-flow + safety semantics; v1.1 candidate if friends actually need it. Until then, restoring from tarball is `tar xzf` manually + tell the wiki path.

## Related artifacts

- ADR-026 (Backups and Recovery) — full design
- ADR-017 (Per-Friend Wiki Scope) — the self-sync recommendation this operationalizes
- `docs/RECOVERY.md` (distribution-2 shipped) — the recovery doc cited on remote-divergence refusal
- `skills/sf-install/SKILL.md` — Stage 5 wiki bootstrap that creates the git repo; future `--restore` invocation
- `skills/sf-doctor/SKILL.md` — surfaces the missing-remote nag that points at `/ren:backup --setup`
