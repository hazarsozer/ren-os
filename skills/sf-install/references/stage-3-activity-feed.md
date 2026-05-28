# Stage 3 (a) — Activity Feed setup

Per ADR-015 Stage 3 (2026-05-28 amendment) + ADR-018 + ADR-020 + the locked sf-feed contract.

## Stage 3 is split

This doc covers the Activity Feed half. `stage-3-conditional-plugins.md` covers the Frontend Design / Ralph half. The orchestrator runs both in this order:

1. Activity Feed setup (this doc) — REQUIRED for v1
2. Conditional plugins (`stage-3-conditional-plugins.md`)

## Procedure

### 3.1 Prompt for repo URL

```
What's the GitHub repo URL for your friend group's Activity Feed?
Example: your-friend-group/activity-feed (org/repo or full URL both fine)
```

Accept either `org/repo` or `https://github.com/org/repo` form. Normalize to `org/repo` before calling feed.

If the friend's friend group doesn't have a repo yet (they're the first friend / Hazar case), point them at the out-of-band step:

```
No repo yet? Create a private one first:
  gh repo create <org>/<name> --private
  gh repo edit <org>/<name> --add-collaborator <friend-handle>  (for each friend, when they join)

Then come back here with the URL.
```

### 3.2 Resolve local clone path

Call `feed.config.local_path()` (sf-feed contract). Per the path lock, this returns `~/.startup-framework/activity-feed/`. Don't hardcode.

### 3.3 Detect repo state

Call:

```
state = feed.detect_repo_state(repo_url, local_path)
```

Returns a `RepoState` per the locked contract:

```yaml
mode: first-friend-bootstrap | joiner-clone | already-cloned
has_other_friends: bool
existing_handles: list[str]
needs_init: bool
local_path: str
```

Branch on `mode`:

- `inaccessible` (gh auth scoped wrong, repo private + friend lacks access) → abort Stage 3 with remediation: "Ask your group's maintainer to add you as collaborator on <repo>."
- `first-friend-bootstrap` → go to 3.4 (mini-handle prompt) then 3.5 (bootstrap)
- `joiner-clone` → go to 3.4 (mini-handle prompt) then 3.6 (clone)
- `already-cloned` → info-log "Activity Feed already set up at <path>; skipping"; mark Stage 3 complete; move to conditional plugins

### 3.4 Mini-handle prompt

The full identity interview runs at Stage 4. But `feed.bootstrap_first_friend` and `feed.clone_existing` both need a handle to know where to write the friend's first log + identity file. So we collect the handle here, with a tiny prompt:

```
Pick a handle for the Activity Feed:
  - lowercase letters, digits, hyphens
  - must start with a letter (regex: ^[a-z][a-z0-9-]*$)
  - shown to other friends in their wake-ups
```

Validate against the regex. For joiner mode, also check `state.existing_handles` and reject collisions:

```
The handle "<name>" is already used by another friend in this group.
  Existing handles: <list>
  Please pick a different one.
```

Re-prompt until a valid, non-colliding handle is provided.

Persist to `state.stage_artifacts.3.proposed_handle`. Stage 4 surfaces this as the Q1 default.

### 3.5 First-friend bootstrap

Call:

```
feed.bootstrap_first_friend(local_path, handle)
```

Sf-feed handles: `git init` (or clone-empty if URL points at an empty repo), README scaffolding, `identities/` directory creation, friend's first `<handle>.log.md` stub, identity placeholder, and first push.

On success, persist `state.stage_artifacts.3`:

```json
{
  "activity_feed_url": "<repo_url>",
  "feed_state": "first-friend-bootstrap",
  "local_clone_path": "<local_path>",
  "proposed_handle": "<handle>"
}
```

On failure: surface sf-feed's error, abort Stage 3.

### 3.6 Joiner clone

Call:

```
feed.clone_existing(repo_url, local_path)
```

Sf-feed handles: `gh repo clone`, verifies access, adds friend's first `<handle>.log.md` stub + identity placeholder, first push.

On success, persist `state.stage_artifacts.3`:

```json
{
  "activity_feed_url": "<repo_url>",
  "feed_state": "joiner-clone",
  "local_clone_path": "<local_path>",
  "proposed_handle": "<handle>"
}
```

On failure: surface sf-feed's error, abort Stage 3.

### 3.7 Friend-facing summary

```
Stage 3 — Activity Feed connected:
  Repo:  <repo_url>
  Mode:  <first-friend-bootstrap | joiner-clone>
  Path:  ~/.startup-framework/activity-feed/
  You:   <handle>
  Others visible: <count> (<list of other handles>)  ← only on joiner-clone
  Read:  ACTIVITY_FEED.md in your plugin's docs/ directory (privacy model + what gets shared)
         (find with: `find ~/.claude/plugins -name ACTIVITY_FEED.md` if needed)
```

## What this stage deliberately does NOT do

- Doesn't run the full `/sf:interview`. That's Stage 4. Only the handle is collected here.
- Doesn't push the full public identity summary. That happens at Stage 4 after the interview completes.
- Doesn't touch the friend's local wiki. Per the stage separation, only Stages 4 and 5 write wiki content.
- Doesn't auto-add other friends as collaborators. That's an out-of-band GitHub admin step per ADR-020.

## Edge cases

- **`gh auth` succeeded in Stage 1 but the friend lacks repo-level access** — surface during `feed.detect_repo_state`. The friend may need to be added as collaborator first.
- **Friend types an `https://` URL with `.git` suffix** — accept; normalize.
- **Friend's gh token has a different account than the repo expects** — surface as `inaccessible`; suggest `gh auth switch` or login with the correct account.
- **Repo exists but is empty (no commits)** — `feed.detect_repo_state` treats as `first-friend-bootstrap` per its locked decision tree (step 3 returns "no `*.log.md` files at root → bootstrap").
- **Friend cancels the mini-handle prompt** — abort Stage 3, do not persist; re-run resumes from the prompt.

## Cross-references

- locked sf-feed contract (team-lead message + my reply to feed-2)
- ADR-018 (Activity Feed) — shared repo design
- ADR-020 (joiner & leaver) — mode-detection rationale
- `stage-4-identity-bootstrap.md` — where the handle is reused
