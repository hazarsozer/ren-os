# Stage 4 — Identity bootstrap

Per ADR-015 Stage 4 + ADR-022. Delegates the full work to the `sf-interview` skill.

## Procedure

### 4.1 Invoke sf-interview

Call the `sf-interview` skill with the orchestrator context. The skill receives access to:

- `state.stage_artifacts.3.proposed_handle` — pre-fill Q1
- `state.framework_version` — written into identity.md frontmatter
- A flag indicating "first-run during install" so the skill knows to skip its own detection-of-existing-identity branch

Pass the state via the skill's invocation contract; the orchestrator doesn't need to inline the question template here. See `skills/sf-interview/SKILL.md`.

### 4.2 Capture outcomes

After sf-interview completes:

- The local file `~/.startup-framework/wiki/identity.md` exists with all required frontmatter.
- The public summary has been (best-effort) pushed via `feed.upsert_identity`. If the push failed, sf-interview returned a non-fatal warning; capture it.

Persist:

```json
{
  "stage_artifacts": {
    "4": {
      "identity_path": "~/.startup-framework/wiki/identity.md",
      "handle_written": "<final-handle-from-q1>",
      "public_summary_pushed": true,
      "feed_push_warning": null
    }
  }
}
```

If `handle_written` differs from `state.stage_artifacts.3.proposed_handle`, the friend changed their handle mid-interview. Sf-feed's `rename_handle` helper covers this:

```
ok = feed.rename_handle(old=stage3_handle, new=stage4_handle)
```

Behavior (per the locked contract):
- Renames `<local_path>/<old>.log.md` → `<new>.log.md`
- Moves `<local_path>/identities/<old>.md` → `<new>.md` if present
- Rewrites the `handle:` field in both files' frontmatter
- **Idempotent**: returns `False` (without overwriting) if `<new>` files already exist
- Returns `False` if `<old>` doesn't exist (nothing to rename)
- Does NOT rewrite historical log entries (chronological-invariant per ADR-018)

After `rename_handle`:

| Result | Branch |
|---|---|
| `True` | Rename succeeded; the orchestrator's next `feed.upsert_identity(stage4_handle, public_md)` call writes the up-to-date public summary; push it with a commit message naming the rename. |
| `False` AND `stage3_handle == stage4_handle` | No-op (handle didn't actually change); proceed normally. |
| `False` AND `stage3_handle != stage4_handle` | Partial-rename collision OR `<old>` files vanished between Stage 3 and Stage 4. Surface a warning to the friend with `git -C <local_path> status` guidance so they can diagnose; continue with `feed.upsert_identity(stage4_handle, ...)`. |

## 4.3a Interpreting `feed.upsert_identity`'s `FeedWriteResult`

`feed.upsert_identity` returns:

```
@dataclass(frozen=True)
class FeedWriteResult:
    success: bool
    entry_id: str
    pushed: bool
    queued: bool = False
    error: str | None = None
    violation: str | None = None
```

Stage 4 renders the friend-facing summary based on this:

| `(success, pushed, queued, violation)` | Friend-facing line |
|---|---|
| `(True, True, _, None)` | `✓ Public summary pushed to <feed>/identities/<handle>.md (sha: <short-sha>)` |
| `(True, False, True, None)` | `⚠ Public summary committed locally but push deferred (network); will retry on next /sf:wrap or /sf:interview` |
| `(False, _, _, "schema-mismatch")` | `✗ Public summary write rejected: feed expected schema_version <n>; identity.md is at <m>. Run /sf:update to align.` |
| `(False, _, _, "missing-cwd"|"missing-files"|"shape-mismatch")` | `✗ Public summary render produced an invalid file: <violation>. This is an sf-onboarding bug — please report.` |
| `(False, _, _, other)` | `⚠ Public summary push reported: <error or violation>; identity.md is still source of truth locally.` |

Stage 4 NEVER fails the install because of a feed push issue — identity.md is source of truth. The violation surfaces; the friend can retry later.

### 4.3 Friend-facing summary

```
Stage 4 — Identity bootstrapped:
  Handle:           <handle>
  Local file:       ~/.startup-framework/wiki/identity.md
  Public summary:   <feed-url>/identities/<handle>.md  (pushed: yes | warning: <text>)
```

## What this stage deliberately does NOT do

- Doesn't run the interview itself. Sf-interview is the canonical implementation.
- Doesn't validate the frontmatter schema beyond what sf-interview's eval already asserts.
- Doesn't re-push the public summary if it was already pushed cleanly (idempotency lives in `feed.upsert_identity`).

## Cross-references

- ADR-022 — sf-interview spec
- `stage-3-activity-feed.md` — where `proposed_handle` is set
- `skills/sf-interview/SKILL.md` — the delegated work
- locked sf-feed contract — `feed.upsert_identity` + (asked) `feed.rename_handle`
