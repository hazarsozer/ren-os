---
title: "ADR-028: Locked Build-Time Contracts — Framework Path + Marketplace Name + Schema Placement + Feed API Shape + RC Channel + Snapshot Location"
status: accepted
amended-by:
  - "ADR-031 (2026-05-30, solo-first pivot): the split feed-write API and FEED_LOCAL_ONLY_FILES contract are retired with the feed module. The framework-root / wiki-path / handle / schema contracts move to lib.sf_paths (semantics unchanged). AMENDED, not superseded — the non-feed locked contracts stand."
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [anthropic-marketplace-catalog]
affects-components: [install, marketplace, feed, schemas, distribution, snapshots]
relates-to: [006-curated-stack, 017-per-friend-wiki-scope, 018-activity-feed, 019-framework-distribution, 021-privacy-boundaries, 022-identity-interview-skill, 027-schema-versioning]
---

# ADR-028: Locked Build-Time Contracts

> 📝 **Amended by [ADR-031](031-solo-first-pivot.md) (2026-05-30).** Solo-first: the feed-write API + `FEED_LOCAL_ONLY_FILES` are retired with the feed module; the framework-root / wiki-path / handle / schema contracts move verbatim to `lib.sf_paths`. The non-feed locked contracts stand.

## Context

ADRs 001-027 settled the design. Building V1.0 surfaced seven cross-cutting decisions that the design ADRs had left underspecified — questions whose answers needed to be **the same** across all four teammates' modules but weren't explicitly stated anywhere. Without a single source of truth, peer DM-coordination produced drifting answers that bit at integration time.

The 4-teammate `sf-build-v1` Agent Team flagged these during planning + implementation; team-lead arbitrated and locked the answers. This ADR captures them in one place so future contributors (or a future build session) inherit the invariants instead of re-deriving them.

This is partly a **map** ADR (in the style of ADR-023's V1 scope fence): no new design decisions, just consolidation of decisions that emerged during build-time coordination.

## Decision

### 1. Framework root path: `~/.startup-framework/`

The friend's local framework state lives at `~/.startup-framework/` with sub-directories:

```
~/.startup-framework/
├── wiki/                  # the friend's per-friend-local wiki (ADR-017)
├── activity-feed/         # local clone of the shared Activity Feed repo (ADR-018)
├── backups/               # tarball fallback location (ADR-026)
├── logs/                  # wake-up hook + skill error logs
└── state/                 # per-session opt-out markers (ADR-021)
```

CC reserves `~/.claude/` for harness internals (settings.json, plugins/, projects/). Friends interact directly with the framework dir for backup, inspection, git remote, recovery — putting it at `~/.startup-framework/` keeps it visible and self-contained.

The install-state checkpoint (`install-state.json`) is the only piece of friend infrastructure NOT at `~/.startup-framework/`: it lives at `$XDG_STATE_HOME/sf/install-state.json` because it's machine-local infrastructure, not friend-owned content.

### 2. Marketplace name: `sf-marketplace`

The private GitHub plugin marketplace repo is named `sf-marketplace` (kebab-case, public-facing in `/plugin install sf@sf-marketplace`). Verified against CC's reserved-name blocklist — clean.

RC channel uses a separate repo: `sf-marketplace-rc` (per § 6 below).

Hazar can rename at first ship via single PR (`marketplace.json#name` is the only canonical location). Locked here for development consistency; not load-bearing for v1.0.

### 3. `<handle>.log.md` schema_version placement: file-top YAML frontmatter

Each Activity Feed log file is a single "page" with one `schema_version` at the top:

```markdown
---
schema_version: 1
handle: hazar
---

## [2026-05-28 14:30] start | hazar | working in Dev/sidecar/
...
```

Individual log entries do **not** carry their own schema_version — they're append-only within the file. Migration of feed entries operates on the whole file at once. Same pattern as `wiki/log.md` itself.

This decision was needed because feed-2's plan + lifecycle-2's plan + distribution-2's `schemas.json` all needed to agree on where the version lives before any one of them could write code.

### 4. Feed write API shape: SPLIT functions, not polymorphic

The feed module's public write API exposes three named functions:

```python
feed_write_session_start(*, handle, cwd, schema_version=1, skip=False, timestamp=None, continuation_hint=None) -> FeedWriteResult
feed_write_session_end(*, handle, project, task_brief, files_touched, schema_version=1, skip=False, timestamp=None) -> FeedWriteResult
feed_write_release(*, handle, version, note, schema_version=1, skip=False, timestamp=None) -> FeedWriteResult
```

A polymorphic single-entrypoint shape (`feed_write_entry(kind="start"|"end"|"release", ...)`) emerged from peer DM coordination between feed-2 and lifecycle-2 before team-lead arbitration locked the split. Implementation initially shipped the polymorphic shape; team-lead caught the drift at code review time; feed-2 refactored to the split surface preserving the original dispatch logic as a private `_write_entry_dispatch` (no working code thrown away).

**Why split**:
- Different param sets per kind (start needs `cwd`; end needs `project + task_brief + files_touched`; release needs `version + note`). The polymorphic shape required nullable mishmash.
- Type signature self-documents what's required per kind.
- Adding a new kind = new function (additive); not touching the dispatcher of the existing ones.
- Symmetric with the read API (`feed_read_friends_tails`, `feed_read_tail` — already split by purpose).

**Rejected alternative — polymorphic `feed_write_entry(kind=...)`**: functionally equivalent at runtime but loses type-signature self-documentation. The polymorphic version's negotiation chain (peer DM → confirmed in feed-2's "Plan accepted" reply via the structured-inputs aspect → shipped) became the canonical worked example of the test-against-real-contract-instances anti-pattern (see ADR-029).

### 5. Cross-team `schemas.json` page-type registration matrix

`skills/wiki-migration/schemas.json` (owned by sf-distribution) registers the canonical page-type vocabulary. Ownership and initial assignments at v1.0:

| Page type | Owner module | Path pattern | Notes |
|---|---|---|---|
| `identity` | sf-onboarding (template) | `wiki/identity.md` | Hybrid YAML+markdown per ADR-022 |
| `project-main` | sf-onboarding (bootstrap template) | `wiki/projects/<name>/PROJECT.md` | ADR-014 taxonomy |
| `project-requirements` | sf-onboarding | `wiki/projects/<name>/REQUIREMENTS.md` | " |
| `project-roadmap` | sf-onboarding | `wiki/projects/<name>/ROADMAP.md` | " |
| `project-state` | sf-onboarding | `wiki/projects/<name>/STATE.md` | Per-signal session |
| `project-context` | sf-onboarding | `wiki/projects/<name>/CONTEXT.md` | Wake-up's session-pointer home (ADR-009) |
| `project-index` | sf-onboarding (project bootstrap template) | `wiki/projects/<name>/index.md` | |
| `project-log-entry` | universal | `wiki/projects/<name>/log.md` (entries) | Chronological invariant |
| `master-index` | sf-onboarding (wiki-skeleton template) | `wiki/index.md` | |
| `log-entry` | universal | `wiki/log.md` (entries) | Chronological invariant |
| `licenses` | sf-distribution | `wiki/LICENSES.md` | Auto-generated at install Stage 6 |
| `research` | universal (friend-authored later) | `wiki/research/*.md` | |
| `decision` | universal (friend-authored later) | `wiki/decisions/*.md` | ADR shape |
| `pattern` | universal (friend-authored later) | `wiki/patterns/*.md` | |
| `feed-entry` | sf-feed | `<activity-feed>/<handle>.log.md` | File-top frontmatter per § 3 |
| `skill` | sf-lifecycle (`/sf:improve-skill` writes) | `skills/<name>/SKILL.md` | Per ADR-011 |

All page-types start at `current: 1, supported_from: 1, migrations: []` for V1.0 (no real migrations ship; only `_template/` scaffold). Path patterns are **documentation-only** at v1; runtime enforcement is v1.1+.

### 6. RC channel: two separate private repos

Per CC docs (`code.claude.com/docs/en/plugin-marketplaces` § Release channels), the release-candidate pattern uses **two separate marketplace repos**, not branches of one:

- `sf-marketplace` (stable; friends pin via `/plugin install sf@sf-marketplace`)
- `sf-marketplace-rc` (pre-release; friends opt-in via `/plugin install sf@sf-marketplace-rc`)

Same friend-collaborator set on both (read access). Promotion is a manual maintainer-driven cherry-pick from rc → stable per `docs/RELEASING.md`; a draft-PR-on-tag GitHub Action template is shipped at `.github/workflows/promote-rc-draft.yml.template` for maintainers who want to wire it up.

**Why not same-repo two-branch**: CC's marketplace identity comes from `marketplace.json#name` which must be unique. Same-repo two-branch would collide. Two separate repos cleanest separates the collaborator-management surface anyway.

**Why this matters at all**: CC does NOT parse semver — `plugin.json#version` is treated as opaque "did the string change?" — so a `1.3.0-rc.1` version string would push to every stable subscriber as if it were stable. Separate channels are the only safe way to ship pre-release versions.

### 7. Snapshot location: `${CLAUDE_PLUGIN_DATA}/wiki-snapshots/`

Overrides ADR-027's suggested `~/.startup-framework/wiki-snapshots/` location. Per `code.claude.com/docs/en/plugins-reference` § Persistent data directory, `${CLAUDE_PLUGIN_DATA}` is the CC-blessed directory that survives plugin updates — exactly the lifetime snapshots need.

Resolves on a typical Linux install to `~/.claude/plugins/data/<plugin-id>/wiki-snapshots/`.

Documented in ADR-027's amendments block; implemented in `skills/sf-update/scripts/snapshot.sh`.

## Three contract-drift incidents (for posterity)

All three share the same root cause — implementation followed an in-memory model of a contract instead of the canonical written source — and are captured at length in ADR-029 + `docs/PATTERNS/test-against-real-contract-instances.md`. Summary here:

1. **Polymorphic-vs-split feed writer**: peer DM agreement on polymorphic survived into implementation despite team-lead arbitrating split. Caught at integration time via `inspect.signature` drift test; refactored.
2. **eval.json schema fork**: `/sf:improve-skill` preflight enforced an `assertions[].binary` object shape; ADR-011 specifies `binary_assertions: list[str]`. Every other framework-shipped skill used the ADR-011 shape, making `/sf:improve-skill` unusable on them. Caught in cross-team review; fixed at preflight + lifecycle-2's own sf-wrap eval.json (which had the same wrong shape — validator and fixture validated each other but neither matched the spec).
3. **Timeout-units routing slip**: an incorrect "timeout in ms" finding routed by team-lead without verifying against the JSON Schema. Caught when the recipient teammate cited `json.schemastore.org/claude-code-settings.json` verbatim ("Optional timeout in seconds"). Demonstrated that the antidote pattern applies to triage discipline, not just authoring.

## Consequences

**Easier:**
- Future contributors inherit the seven invariants without re-deriving them.
- The polymorphic-vs-split rejected-alternative is preserved as a worked example for ADR-029.
- The `schemas.json` page-type matrix is the single source of truth for who owns what.

**Harder:**
- Renaming the framework root path or marketplace name requires updating every place that references them. Worth keeping the surface narrow (`feed.config.local_path()`, `userConfig.wikiRoot`, etc.).
- The two-repo RC pattern doubles the marketplace-management surface. Acceptable cost given CC's opaque-version-string semantics.

**Now impossible:**
- Silently shipping a polymorphic feed writer (the split shape is locked + pinned by integration tests using `inspect.signature`).
- Silently relocating snapshots to a non-`${CLAUDE_PLUGIN_DATA}` path (the ADR-027 amendment + ADR-028 § 7 both name `${CLAUDE_PLUGIN_DATA}`).
- Adding a new page type without registering in `schemas.json` (distribution-2's strict-mode schema-conformance scan catches it).

**Sunset review trigger conditions:**
- Hazar (or future maintainer) renames `sf-marketplace` → revisit § 2 + § 6.
- Friend group outgrows the two-repo RC model (e.g., wants automated promotion with full provenance) → revisit § 6.
- CC adds real semver parsing → revisit § 6 (the workaround is no longer needed).
- Schema migrations actually start shipping → § 5 path-pattern enforcement moves from doc-only to runtime.

## Alternatives considered

### A) Settle these decisions in the design phase ADRs (001-027) instead of a separate consolidation ADR

**Why rejected**: They emerged from build-time peer coordination, not from design. Putting them inline in the original ADRs would rewrite history (the originals don't carry the build-time context). The consolidation ADR pattern (per ADR-023) is the right shape: keep originals authoritative; capture build-time decisions in a new ADR that cross-references.

### B) Leave each decision in the relevant teammate's `learnings.md` instead of an ADR

**Why rejected**: `learnings.md` files are per-skill institutional record. Cross-cutting invariants that span multiple teammates' modules need wiki-indexed visibility — the entry point is the wiki's decisions/ directory + index.md, not a particular skill's docs/.

### C) Skip ADR-028 — rely on the code + ADR-027's amendment + the `schemas.json` registry to encode the decisions

**Why rejected**: Future contributors reading the wiki to understand the framework wouldn't see the polymorphic-vs-split rejected-alternative or the RC channel mechanism, both of which are non-obvious from code archaeology. ADR-028 preserves the reasoning.

## References

- `wiki/log.md` — build-phase chronological entries documenting each decision's disposition
- `wiki/decisions/027-schema-versioning.md` — § 7 mirrors the ADR-027 amendment about `${CLAUDE_PLUGIN_DATA}`
- `wiki/decisions/029-test-against-real-contract-instances.md` — the antidote pattern for the three drift incidents summarized above
- `docs/PATTERNS/test-against-real-contract-instances.md` — the executable form of the antidote pattern
- `REVIEW.md` — the canonical worked example for incident (2) and the framing for the test-against-real-instances discipline
- `feed/writer.py` — the implementation of § 4 (with `_write_entry_dispatch` as the preserved private dispatcher)
- `skills/wiki-migration/schemas.json` — the implementation of § 5
- `docs/RELEASING.md` — the implementation of § 6
- `skills/sf-update/scripts/snapshot.sh` — the implementation of § 7
