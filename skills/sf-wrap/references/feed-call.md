---
title: "/sf:wrap feed contract usage"
type: skill-reference
parent_skill: sf-wrap
version: 0.1.0
date: 2026-05-28
contract-partner: feed-2 (sf-feed teammate)
---

# Calling the feed module from `/sf:wrap`

This document is the **operational** version of the lifecycle ↔ feed contract. The contract was negotiated between `lifecycle-2` and `feed-2` and **arbitrated by team-lead 2026-05-28** in favor of the split-API shape (one function per `kind`). It resides at the file level in:
- `feed/__init__.py` (the feed module's public API; locked re-exports)
- `feed/writer.py`, `feed/reader.py`, `feed/format.py`, `feed/skip.py`, `feed/config.py` (implementations)

This skill consumes three functions from feed:

```python
from feed import feed_write_session_end, is_skip_active, FeedWriteResult
from feed.config import handle as get_handle
```

(`/sf:wrap` only needs the `end` writer. The wake-up hook uses `feed_write_session_start` separately. The `feed_write_release` variant is owned by distribution-2's release notification flow.)

## Function signatures (as shipped post-refactor 2026-05-28)

### `feed.feed_write_session_end(...)`

Used by `/sf:wrap` at session end. All keyword-only:

```python
def feed_write_session_end(
    *,
    handle: str,
    project: str | None,                   # cwd-derived; None for unscoped work
    task_brief: str,                       # ≤300 chars; format-validated upstream + by feed
    files_touched: list[str],              # ≤8 displayed; "…and N more" beyond
    schema_version: int = 1,               # matches distribution-2's schemas.json
    skip: bool = False,                    # computed via is_skip_active()
    timestamp: datetime | None = None,     # default now()
) -> FeedWriteResult
```

### `feed.feed_write_session_start(...)` — for reference; called by wake-up hook, not `/sf:wrap`

```python
def feed_write_session_start(
    *,
    handle: str,
    cwd: str,
    schema_version: int = 1,
    skip: bool = False,
    timestamp: datetime | None = None,
    continuation_hint: str | None = None,
) -> FeedWriteResult
```

### `feed.feed_write_release(...)` — for reference; owned by distribution-2 release flow

```python
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

**History note**: feed-2 originally shipped a single polymorphic `feed_write_entry(kind=...)` (per the lifecycle-2 ↔ feed-2 DM negotiation that preceded team-lead's arbitration). Team-lead enforced the split per the original arbitration; feed-2's refactor (2026-05-28) replaced the polymorphic public surface with the three named functions above. The polymorphic helper remains as a private engine in `feed/writer.py` (implementation detail). This was a useful precedent: **peer-DM agreements that contradict prior lead arbitration are not binding** — coordinate up the chain before implementing.

### `feed.is_skip_active(...)`

```python
def is_skip_active(*, wrap_flag: bool = False) -> tuple[bool, str]:
    """
    Single source of truth for whether to skip the feed entry.
    Reads, in priority order:
      1. /sf:disable-feed state file (~/.startup-framework/feed-state.json) — persistent
      2. SF_SKIP_FEED env var
      3. --skip-feed CLI flag (passed in via wrap_flag arg)
    Returns (skip: bool, reason: str). reason is one of:
      'session-disabled' | 'env-var' | 'wrap-flag' | ''
    """
```

### `feed.config.handle()`

```python
def handle() -> str:
    """
    Returns the friend's handle, read from wiki/identity.md's frontmatter
    `handle:` field. Raises FeedConfigError if identity.md is missing or
    malformed (caller should refuse to /sf:wrap and prompt the user to
    re-run /sf:interview).
    """
```

## `FeedWriteResult` shape

```python
@dataclass(frozen=True)
class FeedWriteResult:
    success: bool          # True if the write was accepted (even if push deferred)
    entry_id: str          # f"{handle}-{ts_unix_minute}-{kind}" hash; empty if skipped
    pushed: bool           # True if push to remote succeeded
    queued: bool           # True if write succeeded locally but push deferred
    error: str | None      # populated on any non-format failure
    violation: str | None  # populated when format validation rejected the entry (see codes below)
```

## Violation codes (post-refactor)

feed-2 exposes a precise set of `violation` codes. Each maps to a specific UX response:

| `result.violation` | UX category | `/sf:wrap` action |
|---|---|---|
| `not-bootstrapped` | User-actionable: setup | Surface "Activity Feed not set up. Run `/sf:install` Stage 3 to bootstrap." — do NOT re-prompt LLM (no amount of rewording fixes a missing .git) |
| `schema-mismatch` | User-actionable: migration | Surface "Feed schema out of date. Run `/sf:update` to migrate." — do NOT re-prompt LLM |
| `too-long` | Format-shape (re-prompt) | Re-prompt LLM with "previous summary exceeded 300 chars; shorten" |
| `forbidden-substring` | Format-shape (re-prompt) | Re-prompt LLM with "previous summary contained a code fence / Error: / Traceback marker; remove" |
| `html-bleed` | Format-shape (re-prompt) | Re-prompt LLM with "previous summary contained `<` or `>` outside the header; remove" |
| `shape-mismatch` | Format-shape (re-prompt) | Re-prompt LLM with "summary structure doesn't match template" |
| `missing-files` / `missing-project` / `missing-cwd` | Internal bug | "Internal error: missing required field. Filing a bug." — our pre-validator should have caught it; if feed sees it, that's a bug in our validator |
| `unknown-kind` | Internal bug | Same as missing-field; shouldn't happen with the split API |

*(Note: `continuation-hint-too-long` is start-only — surfaces from `feed_write_session_start`, never from the end writer this skill uses. Documented in the wake-up hook's references.)*

The format-shape codes (`too-long`, `forbidden-substring`, `html-bleed`, `shape-mismatch`) all trigger the **one-retry-then-abandon** path per team-lead's locked spec. The bootstrap/schema codes are NOT re-promptable — they require user action.

## Call site (the `/sf:wrap` step 6)

```python
# Step 6 in the SKILL.md pipeline
skip, skip_reason = is_skip_active(wrap_flag=args.skip_feed)

result = feed_write_session_end(
    handle=get_handle(),
    project=active_project_or_None,
    task_brief=composed_summary,           # already format-checked by our pre-validator
    files_touched=touched_files,
    schema_version=1,
    skip=skip,
)
```

## Result handling (the `/sf:wrap` step 7)

```python
# Format-shape violations that are re-promptable from /sf:wrap.
# (continuation-hint-too-long is start-only; not in this set.)
RE_PROMPTABLE_VIOLATIONS = {
    "too-long", "forbidden-substring", "html-bleed", "shape-mismatch",
}

# Violations that need user action (NOT re-promptable)
USER_ACTIONABLE_VIOLATIONS = {"not-bootstrapped", "schema-mismatch"}

# Violations that indicate a bug in OUR pre-validator
INTERNAL_BUG_VIOLATIONS = {
    "missing-files", "missing-project", "missing-cwd", "unknown-kind",
}


match result:
    case FeedWriteResult(success=True, pushed=True):
        emit_user_line("✓ feed entry pushed")

    case FeedWriteResult(success=True, queued=True):
        emit_user_line("⚠ feed entry queued locally; will retry next session-start")

    case FeedWriteResult(success=True, error=None) if skip:
        emit_user_line(f"(feed skipped: {skip_reason})")

    case FeedWriteResult(success=False, violation=v) if v in USER_ACTIONABLE_VIOLATIONS:
        emit_user_action_required(v, result.error)
        # Do NOT re-prompt the LLM; the user needs to /sf:install or /sf:update

    case FeedWriteResult(success=False, violation=v) if v in RE_PROMPTABLE_VIOLATIONS:
        new_brief = reprompt_for_terse_summary(violation_reason=v)
        result_retry = feed_write_session_end(
            handle=get_handle(),
            project=active_project_or_None,
            task_brief=new_brief,
            files_touched=touched_files,
            schema_version=1,
            skip=skip,
        )
        if not result_retry.success:
            # Per team-lead spec: abandon feed write, keep wiki updates intact
            emit_user_line(f"⚠ feed entry rejected ({result_retry.violation}); wiki saved")
        else:
            emit_user_line("✓ feed entry pushed (after re-prompt)")

    case FeedWriteResult(success=False, violation=v) if v in INTERNAL_BUG_VIOLATIONS:
        log.error("Internal: pre-validator missed violation=%s — should not reach feed", v)
        emit_user_line("⚠ internal validation error; wiki saved. Please file a bug.")

    case FeedWriteResult(success=False, error=err):
        emit_user_line(f"⚠ feed write failed: {err}; wiki saved")
```

## Defense-in-depth validation

Per the locked contract, BOTH sides validate the format. Our pre-validator (in `lib/validate.py`) checks:

```python
def validate_task_brief(brief: str) -> str | None:
    """Returns None if valid; otherwise a violation reason string."""
    if "\n" in brief:
        return "summary must not contain newlines"
    if len(brief) > 300:
        return f"summary {len(brief)} chars; max 300"
    if "```" in brief:
        return "summary must not contain triple-backtick fences"
    if "Error:" in brief or "Traceback" in brief:
        return "summary must not contain stack-trace markers"
    # Note: we intentionally do NOT scan for secret patterns (ADR-021 line).
    return None
```

If our pre-validation fails, we re-prompt the LLM BEFORE calling feed — saves a round trip. Feed's validation is the second line of defense.

## V1 dev environment (using feed-2's fakes)

feed-2 ships matching `_fake` variants for each split writer. Use them in unit tests where the real git plumbing would be heavy:

```python
# For unit tests (no I/O, deterministic FeedWriteResult)
from feed import feed_write_session_end_fake

# For integration (real I/O, requires bootstrapped feed clone)
from feed import feed_write_session_end

# Either way:
from feed import is_skip_active, FeedWriteResult
from feed.config import handle as get_handle
```

The fakes match the real signatures exactly — only the side effects differ. Tests typically inject the fake via dependency injection or module-level `monkeypatch`.

## Failure-mode coupling with /sf:wrap

Per the lifecycle plan §5 + the violation-code table above:

| Scenario | Behavior | User-visible |
|---|---|---|
| Feed push conflict | feed retries internally; on N=3 failures returns `queued=True` | "feed entry queued locally; will retry next session-start" |
| Feed auth/network failure | Same as push conflict (queued) | Same |
| Skip active | No actual write; result.success=True with empty entry_id | "(feed skipped: \<reason\>)" |
| Format violation (re-promptable) | One LLM re-prompt with violation reason; on second failure abandon feed write | "feed entry rejected (\<code\>); wiki saved" |
| `not-bootstrapped` | Refuse the call; surface setup instructions | "Activity Feed not set up. Run `/sf:install` Stage 3 to bootstrap." |
| `schema-mismatch` | Refuse the call; surface migration instructions | "Feed schema out of date. Run `/sf:update` to migrate." |
| Internal-bug violation (`missing-*`, `unknown-kind`) | Log; emit user-facing bug-filing prompt; abandon feed write | "internal validation error; wiki saved. Please file a bug." |

**Invariant**: the friend never loses wiki updates because of a feed problem. The wiki write completes atomically BEFORE the feed call (per SKILL.md step 5 → step 6 order). Feed failures only affect the feed-side artifact, never the wiki.

If the queue persists across multiple sessions, the friend can manually flush: `cd ~/.startup-framework/activity-feed && git push`.

## References

- ADR-018 (Activity Feed) — design rationale
- ADR-021 (Privacy Boundaries) — terse-format-as-privacy
- `feed/README.md` — the canonical feed module docs (shipped 2026-05-28)
- Team-lead's contract arbitration messages (2026-05-28) — locked function signatures
- feed-2's refactor ship-message (2026-05-28) — final violation-code catalog
