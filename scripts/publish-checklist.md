# RenOS 0.2.0 — Publish Checklist

> ✅ **Completed 2026-07-07** — published to `hazarsozer/ren-os` (main = full 0.2
> history, tag `v0.2.0`; prior release archived at `archive/v0.1.0`). Verified
> from a fresh clone: no dev content, clean stamp, `installed_version: 0.2.0`.

> Publishing is a HUMAN decision. Nothing in this repo pushes to a marketplace
> automatically; the orchestrated build deliberately configured no `origin`.

## Why publishing is now just a push

The 0.1-era `publish.sh` filter-repo pipeline is gone **by construction**: this
repo has no `wiki/` dev content, no maintainer docs, and no test code inside
shippable dirs (top-level `tests/` — enforced by `tests/test_repo_hygiene.py`).
The pre-push guard (`hooks/guards/pre_push_scan.py`) content-scans every
non-backup push as a runtime backstop.

## Steps (in order)

1. [x] Full suite green: `uv run pytest tests/ -q`
2. [x] Dev-content lint: `uv run python scripts/lint_no_dev_wiki_content.py`
3. [x] Frontmatter lint: `uv run python scripts/lint-yaml-frontmatter.py`
4. [x] Version check: `grep -rn '"version": "0.2.0"' .claude-plugin/plugin.json`
5. [x] Review `docs/exit-criteria.md` — accept the PENDING-CALENDAR items knowingly
6. [x] Decide the marketplace target (the `ren-os` marketplace repo hosts 0.1.0;
       0.2.0 replaces or ships alongside — HAZAR'S CALL, including whether the
       new repo slug is `renos`)
7. [x] `git remote add origin <marketplace-url>` (first time only)
8. [x] `git push origin main` — the pre-push guard scans the tree; a block here
       is a real finding, not noise
9. [x] Tag: `git tag v0.2.0 && git push origin v0.2.0`
10. [x] Verify live: fresh `/plugin marketplace` install on a clean machine or
        sandbox HOME; run `/ren:install`; confirm the first-session artifact
11. [x] Push `backup` remote one final time; update dev-repo memory/session notes
