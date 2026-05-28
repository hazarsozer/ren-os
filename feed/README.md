# `feed/` — Activity Feed module

The framework's only cross-friend layer. Per-friend log files in a shared private GitHub repo,
terse-format session-start + session-end entries, opt-out at three precedence levels.

**Owner:** `sf-feed` teammate
**Tracking task:** #3 (umbrella) + #17 (scaffolding) + #19/#21/#22/#23 (impl)

## What this module is

The `feed/` module is the cross-friend layer of the startup framework. It writes terse session
reports to a per-friend log file in a shared private GitHub repo, and reads recent activity from
the other friends' log files. It is the **only** module in the framework that touches state
shared across friends — every other module is per-friend-local.

## Anchoring ADRs

In order of precedence:

1. [ADR-018](../wiki/decisions/018-activity-feed.md) — architecture (shared repo, per-friend files, hooks)
2. [ADR-021](../wiki/decisions/021-privacy-boundaries.md) — **terse format IS the privacy mechanism**
3. [ADR-020](../wiki/decisions/020-joiner-and-leaver-experience.md) — `/sf:catch-up` spec
4. [ADR-017](../wiki/decisions/017-per-friend-wiki-scope.md) — wiki is local; feed is the only cross-friend layer
5. [ADR-019](../wiki/decisions/019-framework-distribution.md) — distribution distinctions (feed repo ≠ marketplace repo)

## Hard constraints (do not violate)

- **Per-friend file separation** is the conflict-avoidance mechanism. Each friend writes ONLY to
  their own `<handle>.log.md`. No shared content files. (ADR-018 alt E rejected)
- **Terse format is the privacy mechanism.** Session-end entries: project + 1–2 sentence task
  brief + file list. NO code, NO decisions, NO transcripts. (ADR-021)
- **No framework-level secret scanning.** The format constraint does the work. We do NOT reinvent
  Aikido / AgentShield. (ADR-021 §"No framework-level secret scanning")
- **No advisory locks, no file reservations.** (ADR-018 alt E rejected)
- **Auto-deliver, no approval queue.** Friends trust each other. (ADR-018)
- **Graceful degradation on push failure.** Log warning, continue session, retry next session.
  Never block session start/end on network failures. (ADR-018 Consequences)
- **Repo URL is a config value**, not hardcoded. Onboarding Stage 3 sets it during install.

## Module layout

```
feed/
├── README.md           # this file
├── __init__.py         # public re-exports for the locked API
├── config.py           # paths (~/.startup-framework/activity-feed/), handle resolution
├── format.py           # terse-format builders + validators (ADR-021 schema)
├── skip.py             # is_skip_active() — the only file that ships REAL impl in scaffold phase
├── writer.py           # feed_write_session_{start,end} + feed_write_release + fakes
├── reader.py           # feed_read_friends_tails + feed_read_tail (stubs + _fakes)
├── io_github.py        # pull/push via gh+git (stub)
├── identity_sync.py    # identities/<handle>.md upsert (stub)
├── bootstrap.py        # detect_repo_state, bootstrap_first_friend, clone_existing (stub)
└── tests/
    ├── test_skip.py    # real tests for is_skip_active
    └── test_format.py  # placeholder — fills in during #19
```

## Locked public API (the contract)

This is what `lifecycle-2` (wake-up hook + `/sf:wrap`) and `onboarding-2` (Stage 3 install) call.
Signatures are frozen per team-lead approval (2026-05-28). Implementation can change; signatures
cannot, without team-lead arbitration.

### Writers (called by wake-up + /sf:wrap) — SPLIT per team-lead arbitration

```python
def feed_write_session_start(
    *,
    handle: str,
    cwd: str,
    schema_version: int = 1,
    skip: bool = False,
    timestamp: datetime | None = None,
    continuation_hint: str | None = None,   # optional body line, ≤140 chars
) -> FeedWriteResult

def feed_write_session_end(
    *,
    handle: str,
    project: str,
    task_brief: str,
    files_touched: list[str],
    schema_version: int = 1,
    skip: bool = False,
    timestamp: datetime | None = None,
) -> FeedWriteResult

def feed_write_release(
    *,
    handle: str,
    version: str,
    note: str,
    schema_version: int = 1,
    skip: bool = False,
    timestamp: datetime | None = None,
) -> FeedWriteResult
```

Each function has a tight, typed signature appropriate to its kind — no nullable
mishmash. All three internally delegate to a private `_write_entry_dispatch` engine
(originally the polymorphic `feed_write_entry` from the scaffold; lives on as
implementation detail per team-lead's "implementation bodies stay; just split the
dispatch" direction).

### Readers

```python
def feed_read_friends_tails(
    own_handle: str,
    *,
    n_per_friend: int = 5,
    include_self: bool = True,
    since: datetime | None = None,
    max_tokens: int | None = None,             # drop-oldest truncation; sets FriendsTail.truncated
    refresh: bool = True,
) -> FriendsTail
# Used by wake-up hook with refresh=False, max_tokens=2500

def feed_read_tail(
    n: int = 10,
    *,
    exclude_handle: str | None = None,
    since: datetime | None = None,
    refresh: bool = True,
) -> list[FeedEntry]
# Used by /sf:doctor + /sf:recall + future mid-session browsers

def read_all_entries(
    *,
    since: datetime | None = None,
    from_handles: list[str] | None = None,
    project_filter: str | None = None,
) -> list[FeedEntry]
# Used by /sf:catch-up
```

### Skip-chain (single source of truth)

```python
def is_skip_active(wrap_flag: bool = False) -> tuple[bool, str]
# Returns (skip?, reason). Reasons: 'session-disabled' | 'env-var' | 'wrap-flag' | 'not-skipping'
# Precedence (highest wins):
#   1. /sf:disable-feed state file (~/.startup-framework/state/session-<id>.json)
#   2. SF_SKIP_FEED=1 env var
#   3. wrap_flag arg (from /sf:wrap --skip-feed)
```

### Bootstrap (called by onboarding Stage 3)

```python
def feed_detect_repo_state(repo_url: str, local_path: str | None = None) -> RepoState
def feed_bootstrap_first_friend(local_path: str, handle: str, repo_url: str) -> None
def feed_clone_existing(repo_url: str, local_path: str, handle: str) -> None
```

### Identity push (called by onboarding Stage 4)

```python
def feed_upsert_identity(handle: str, public_identity_md: str) -> FeedWriteResult
```

### GitHub I/O (mostly internal; exposed for /sf:doctor)

```python
def pull(*, timeout_s: int = 10) -> PullResult
def push(commit_msg: str, *, timeout_s: int = 10) -> PushResult
def check_auth() -> AuthStatus
```

## Skip semantics (this trips people up — read carefully)

"Skip" means **no local write AND no remote push**. A local write without a push still pollutes
the next session-start's auto-push cycle, so honoring `--skip-feed` requires writing nothing at
all. Any of the three writers called with `skip=True` returns `FeedWriteResult(success=True, entry_id='', pushed=False, queued=False, error=None)` — i.e., it's a no-op that reports success.

The three opt-out surfaces (per [ADR-021](../wiki/decisions/021-privacy-boundaries.md)):

| Surface | Scope | Set by |
|---|---|---|
| `/sf:disable-feed` | Current session start + end + any intermediate writes | User mid-session |
| `SF_SKIP_FEED=1` | Process tree | User shell or wrapper script |
| `--skip-feed` on `/sf:wrap` | Only this wrap | User per-wrap |

ANY of the three being set → no write. Highest precedence wins for the reason string.

## Format constraints (the privacy mechanism)

### Session-start entry

```markdown
## [2026-05-28 14:30] start | hazar | working in ~/Dev/sidecar/
```

Optional continuation hint as a single parenthesized body line, ≤140 chars.

### Session-end entry

```markdown
## [2026-05-28 16:45] end | hazar | session complete

Worked on sidecar — JWT verification middleware finished; /api/login email regex fixed.
Touched: src/auth/jwt.ts, src/api/login.ts, wiki/projects/sidecar/STATE.md.
```

### Validators (hard-fail before write)

- Body ≤ 300 characters total
- No triple-backtick code fences
- No `Error:` or `Traceback` (format-noise; not security scanning)
- No `<` or `>` outside the header line (blocks HTML/private-tag bleed)
- Files cap at 8 displayed; overflow rendered as "…and N more"
- Mentions at least one file or directory
- Exactly two body lines for end entries matching the templates above

**Explicitly NOT enforced:** secret pattern scanning. The terse-format constraint IS the privacy
mechanism per ADR-021. Friends who want comprehensive scanning install AgentShield per-project.

## GitHub I/O strategy

- **`gh` CLI** for auth + repo metadata (clone, view, contents API)
- **Raw `git`** for hot path (pull, commit, push)
- **Auth check** upfront via `feed.check_auth()` at onboarding; on-demand only after push failure
- **Offline queue** on push failure: `local_path/.queue.log` + `local_path/.state.json`. Flushed on
  next successful pull. After 3 consecutive failures, `/sf:doctor` raises visibility.
- **Conflict resolution**: auto `pull --rebase --autostash` + retry N=3 with exp backoff (1s, 2s,
  4s). If still fails, queue and return `queued=True`. Never auto-resolve content conflicts (per
  ADR-018 per-friend files, we should never see one).

## File layout in the activity-feed repo

```
~/.startup-framework/activity-feed/      (clone of shared GitHub repo)
├── hazar.log.md
├── friend-b.log.md
├── friend-c.log.md
├── identities/
│   ├── hazar.md
│   ├── friend-b.md
│   └── friend-c.md
├── README.md
├── .queue.log              (local-only; gitignored)
└── .state.json             (local-only; gitignored)
```

Each `<handle>.log.md` has YAML frontmatter at the top:

```markdown
---
schema_version: 1
handle: hazar
---

## [2026-05-28 14:30] start | hazar | ...
## [2026-05-28 16:45] end | hazar | ...
```

Schema version is an integer (matches distribution-2's `schemas.json` "feed-entry" entry,
which uses `current: 1`). Bumps to 2, 3, etc. when migrations land.

## What this module does NOT do (V1)

- No secret scanner (ADR-021)
- No diff-review-by-default before pushing entries (ADR-021 alt A rejected)
- No advisory locks / file reservations (ADR-018 alt E rejected)
- No shared content files; only per-friend `<handle>.log.md` (ADR-018)
- No deletion / scrub commands (ADR-021 §"Deletion is hard" — document, don't automate)
- No `/sf:activity` mid-session browser (ADR-018 Open Q#4 — defer to v1.1)
- No real-time messaging, replies, threads (ADR-018 §"What this is NOT")
- No auto-resolution of git content conflicts
- No `--remove-activity-feed` cleanup command (ADR-020 leaver flow — separate task, not v1 blocker)
- No role check on `feed_write_release(...)` — social convention v1 (TODO v2)

## Cross-team contract status

| Boundary | Counterparty | Status |
|---|---|---|
| Writer + reader signatures | `lifecycle-2` | ✅ Sealed (2026-05-28) |
| Stage 3 detect-vs-bootstrap | `onboarding-2` | ✅ Auto-confirmed via identity.md.tmpl + lead approval |
| `schema_version` placement | `distribution-2` | ✅ File-top frontmatter, lead-approved |
| Framework root path convention | `distribution-2` | ✅ `~/.startup-framework/`, lead-approved |
