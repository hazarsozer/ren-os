---
title: "ADR-019: Framework Distribution & Updates — Private Marketplace + Stable Releases + Update Notifications"
status: accepted
amended-by:
  - "ADR-031 (2026-05-30, solo-first pivot): the 4-repo distinction (marketplace / activity-feed / dev-wiki / friend-wiki) collapses to 2 (marketplace / per-friend wiki). No activity-feed repo. AMENDED, not superseded — the marketplace/semver/update model stands."
date: 2026-05-28
sunset-review: 2026-11-28
references-pages: [anthropic-marketplace-catalog, ecc-everything-claude-code, superpowers]
affects-components: [distribution, install, updates, versioning, doctor]
relates-to: [006-curated-stack, 015-onboarding, 017-per-friend-wiki-scope, 018-activity-feed, 027-schema-versioning]
---

# ADR-019: Framework Distribution & Updates

> 📝 **Amended by [ADR-031](031-solo-first-pivot.md) (2026-05-30).** Solo-first: the 4-repo distinction collapses to 2 (marketplace + per-friend wiki); there is no activity-feed repo. The marketplace / semver / update model stands.

## Context

The framework today lives in Hazar's local `/home/hsozer/Dev/startup-framework/` dev repo. Friends need to install something. We need a distribution mechanism that:

1. Stays **private** to the friend group (not public, not on Anthropic's official marketplace)
2. Uses Claude Code's standard plugin install mechanism (so friends already know the pattern)
3. Supports versioning + opt-in updates
4. Lets friends learn about new versions without us nagging via Discord
5. Honors ADR-017's backwards-compatibility commitment

There are also two separate GitHub repos in our overall design — easy to confuse, so this ADR distinguishes them clearly:

| Repo | Purpose | Access | Owner |
|---|---|---|---|
| **Framework marketplace repo** (this ADR) | Distribution + versioning of the framework itself | Friends are READ collaborators | Hazar / framework maintainers |
| **Activity Feed repo** (ADR-018) | Cross-friend session reports | Friends are WRITE collaborators | The friend group |
| **Framework dev wiki** (ADR-017) | Our design history (this repo) | Maintainers only | Hazar |
| **Friend's installed wiki** (ADR-017) | Each friend's personal memory | Local-only | That friend |

## Decision

### Distribution: Private GitHub Marketplace Repo

The framework distributes via **a private GitHub repo configured as a Claude Code plugin marketplace**. Friends install via standard Claude Code commands:

```
/plugin marketplace add <our-org>/<framework-marketplace-repo>
/plugin install startup-framework@<our-org>-startup-framework-marketplace
```

The marketplace repo contains:
- `.claude-plugin/marketplace.json` — describes the plugin's installable variants
- The plugin's source files (skills, hooks, slash commands, settings, agent definitions)
- `CHANGELOG.md` — release notes per version (consumed by `/sf:doctor` for update notifications)
- `LICENSE` — MIT per ADR-016
- `README.md` — friend-facing install/usage docs

**Hosting**: location of the marketplace repo TBD by Hazar during setup (likely his personal GitHub or a dedicated friend-group org). The repo URL is the single configuration point friends need.

**Access pattern**: each friend is added as a collaborator with READ access. Read is sufficient because Claude Code's plugin install pulls from the repo without requiring write back. Write access stays with the framework maintainers (Hazar + whoever else maintains it later).

### Versioning: Semantic Versioning with Stable Monthly Cadence

The framework follows **semantic versioning** (`MAJOR.MINOR.PATCH`):
- `MAJOR` — breaking changes that require migration. Per ADR-017's backwards-compatibility commitment, migrations ship in the release with diffs + user approval.
- `MINOR` — new features, new skills, additive changes. Backwards-compatible.
- `PATCH` — bug fixes, doc updates, no schema changes.

**Release cadence**: monthly stable releases. NOT daily (rejected per discussion — daily releases like lean-ctx's are exciting but risky; friends need predictability over recency). If a patch is critical (security, broken hook), ship out-of-cycle with explicit notice in CHANGELOG + Activity Feed announcement.

**Pinning**: friends pin to specific versions per ADR-006 / ADR-015. `/plugin update` is opt-in, not automatic.

**Pre-release**: when shipping a MAJOR with potentially-breaking migration, ship a `<version>-rc.1` first to the marketplace; Hazar dogfoods for ~1 week before promoting to stable. Friends can opt-in to RC versions for testing but aren't pushed to.

### Update Notification: `/sf:doctor` Checks Latest Version

When a friend runs `/sf:doctor` (per ADR-010 / ADR-015's verification command), it:

1. Queries the marketplace repo's `marketplace.json` (via `gh api` since friends are collaborators) to get the latest available version
2. Compares against the friend's installed version
3. If behind: report alongside other doctor checks:
   ```
   ✅ Plugins installed
   ✅ Hooks registered
   ✅ Activity Feed reachable
   ⚠️  Framework update available: v1.3.0 (you have v1.2.1)
      Run /sf:update to install. See CHANGELOG for what's new.
   ```
4. If on RC: warn ("you're on a release candidate; promote to stable when comfortable")

`/sf:doctor` does NOT auto-update. Just notifies.

**Activity Feed announcement on release**: when a new version ships, Hazar posts a one-line entry in his `<hazar>.log.md` activity feed file (e.g., `## [<date>] release | framework | v1.3.0 shipped — see CHANGELOG`). Friends' next session-start pulls + sees the announcement in their wake-up context.

### Update Mechanism: `/sf:update`

A dedicated slash command (per ADR-013's `/sf:*` namespacing):

```
/sf:update           # Install latest stable, run migrations if needed
/sf:update --rc       # Install latest including release candidates
/sf:update --to <v>   # Install specific version (downgrade or specific upgrade)
```

What `/sf:update` does:

1. Pull latest from the marketplace repo (essentially `/plugin update startup-framework`)
2. Check if migration is needed (compare old version's schema vs. new version's schema)
3. If migration needed: run it via the framework's `wiki-migration` skill (forthcoming). Show diffs. Require user approval. Apply changes.
4. Re-register hooks (in case lifecycle hook code changed)
5. Verify via `/sf:doctor`
6. Report success or failure

Migration safety:
- All migrations are reversible (snapshots of wiki state before migration, kept until next migration or N days)
- Migrations are idempotent (running twice produces same result)
- Migrations log to wiki/log.md with the version-bump entry

### Release process (what maintainers do)

For ADR-019 to work, the maintainer (Hazar initially) follows this process when shipping a release:

1. Develop changes in the dev repo (this one, `/home/hsozer/Dev/startup-framework/`)
2. Test locally (run own `/sf:install` from a clean state)
3. Update `CHANGELOG.md` in the marketplace repo
4. Bump version in `marketplace.json`
5. Run any schema migrations on own wiki to verify migration logic works
6. Push to the marketplace repo
7. Tag the release in Git (e.g., `v1.3.0`)
8. Post Activity Feed announcement in `<hazar>.log.md`
9. Friends pick it up via `/sf:doctor` or their next `/sf:update`

### Adding new friends to the friend group

When Friend X joins later:

1. Hazar adds Friend X as collaborator on the framework marketplace repo (read access)
2. Hazar adds Friend X as collaborator on the Activity Feed repo (write access)
3. Friend X installs Claude Code if they don't have it
4. Friend X runs the install commands above
5. Friend X's `/sf:install` runs the standard 7-stage flow (per ADR-015 — much simpler now per ADR-017's per-friend-wiki principle: no group history to inherit)

Per ADR-017's principle: Friend X gets a fresh empty wiki. They don't inherit existing friends' wikis. The Activity Feed gives them visibility into recent group activity from their first session.

## Consequences

**Easier:**
- Standard Claude Code plugin install pattern — friends already know it
- Version pinning + opt-in updates = predictability over recency
- `/sf:doctor` notification removes "did I miss an update?" friction
- Stable monthly cadence is realistic for a friend-group tool (vs. daily-release ambitious)
- Private marketplace = no public maintenance burden

**Harder:**
- Hazar (and any future maintainer) owns the release process (write CHANGELOG, bump version, test migrations, push to marketplace)
- Two private GitHub repos to manage (marketplace + Activity Feed)
- Migration scripts must be carefully written + tested to satisfy ADR-017's backwards-compatibility commitment
- Initial bootstrap requires Hazar to create the marketplace repo + add friends as collaborators (one-time)

**Now impossible:**
- Auto-updating without friend's consent (per design — friends decide when to update)
- Distribution via the official Anthropic marketplace (we chose private; future change requires re-deciding)
- Drift between friends running different framework versions without their knowledge (`/sf:doctor` catches it)

**Sunset review trigger conditions:**
- Friend group decides to open-source the framework — switch to public marketplace
- Monthly cadence becomes too slow (active development period) → ship more often
- Hazar-bottleneck on releases (friends want to contribute fixes) → multi-maintainer pattern
- A migration causes data loss → re-think backwards-compat mechanics (likely ADR-027 amendment)

## Alternatives considered

### A) Anthropic's official plugin marketplace

**Considered shape**: Submit to `anthropics/claude-plugins-official`. Friends install via `/plugin install startup-framework@claude-plugins-official`.

**Why rejected**: This is a niche friend-group tool, not a polished public Anthropic-curated plugin. Doesn't fit the official marketplace's "high-quality, broadly-useful" curation. Also: forces public — we want private per the discussion.

### B) Direct git clone + manual setup

**Considered shape**: Friends `git clone <repo>` to a known location; run a setup script. No Claude Code marketplace involvement.

**Why rejected**: Loses the standard `/plugin install` UX friends already know from other plugins in our curated stack (Superpowers, Skill Creator, etc.). Inconsistent install patterns confuse onboarding.

### C) NPM / Cargo / PyPI distribution

**Considered shape**: Publish as a package on a language ecosystem registry.

**Why rejected**: The framework is a Claude Code plugin, not a software package in any specific language. Tying it to a language ecosystem would create artificial constraints. Plus public registries don't fit the private-only requirement.

### D) Auto-update on session start

**Considered shape**: Every session start checks for + applies updates automatically.

**Why rejected**: Per user direction ("stable releases"), automatic updates are wrong. Friends need to opt-in. Auto-update could break mid-flow on a critical session.

### E) Daily release cadence

**Considered shape**: Ship every day; small increments; lean-ctx style.

**Why rejected per user direction**: "Stable releases." Friends depend on the framework; rapid releases create churn. Monthly cadence balances velocity vs. stability for friend-group tooling.

### F) Notification via Activity Feed only (no `/sf:doctor` check)

**Considered shape**: Release announcements only in Activity Feed; no doctor integration.

**Why rejected**: A friend who hasn't pulled the Activity Feed recently misses the notification. `/sf:doctor` is the safety-net check; friends who explicitly verify their install get told what's available. Both channels combined > either alone.

## Open questions for implementation phase

1. **Where does the marketplace repo live initially?** Hazar's personal GitHub vs. a dedicated friend-group org. Out of scope for ADR-019; settled at first ship.

2. **CI for releases?** GitHub Actions to validate `marketplace.json` schema, run migration tests, etc. Probably yes; implement during writing-plans phase.

3. **Release candidate workflow** — how does the `-rc.N` versioning interact with Claude Code's plugin install? Need to verify Claude Code's marketplace supports pre-release versions. If not, fall back to "ship to a separate -rc marketplace repo for testing."

4. **What if a friend's `gh` auth lapses?** They lose marketplace access. `/sf:doctor` should catch this and prompt re-auth.

5. **Migration rollback path** — what if a migration fails partway? Need clear rollback semantics (snapshots + restore). ADR-027 should detail this.

## References

- `wiki/research/anthropic-marketplace-catalog.md` — survey of official marketplace; provides the `marketplace.json` schema we mirror in private form
- `wiki/research/ecc-everything-claude-code.md` — ECC's `minimal/core/full` profile pattern (we use single-profile for simplicity but the marketplace.json supports variants if we ever want)
- `wiki/research/superpowers.md` — Superpowers' per-harness install patterns; we follow same pattern privately
- ADR-006 (Curated Stack) — names what's IN the framework
- ADR-015 (Onboarding) — `/sf:install` consumes this ADR's marketplace repo
- ADR-017 (Per-Friend Wiki Scope) — backwards-compatibility commitment this ADR operationalizes
- ADR-018 (Activity Feed) — release announcements posted there
- ADR-027 (Schema Versioning) — forthcoming; details migration mechanics this ADR commits to in principle
