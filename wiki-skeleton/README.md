# wiki-skeleton/

**Audience:** framework contributors. **Not shipped to a friend's installed wiki as-is.**

## What this is

`wiki-skeleton/` holds the empty templates the framework's `/ren:install` skill and `/ren:bootstrap-project` skill stamp into a friend's machine when they run the framework for the first time (or bootstrap a new project).

It is **the plugin's shipping payload** for the wiki layer — not a copy of the framework's own development wiki. The friend's wiki starts EMPTY of any framework-developer content. The skeleton provides structure + page-format conventions; the friend fills in content through their own work.

## What this is NOT

- **Not the framework's development wiki.** That lives outside this shippable tree. Our own ADRs and research pages are how WE designed the framework. They never ship to users.
- **Not a content seed.** No example research entries, no example decisions, no founder names, no project-history references. The lint at `tests/wiki_skeleton/test_dev_content_lint.py` (via `scripts/lint_no_dev_wiki_content.py`) enforces this.

## Layout

```
wiki-skeleton/
├── README.md                    # this file
├── manifest.yaml                # file set + per-file rules (profiles: master, project, venture)
├── templates/
│   ├── index.md.tmpl            # master wiki index — empty section headers
│   ├── log.md.tmpl              # master log — single init entry
│   ├── identity.md.tmpl         # identity + working-style profile stub; /ren:interview populates it
│   ├── LICENSES.md.tmpl         # plugin-license summary; written at doctor verification
│   ├── research/.gitkeep        # ingested-source pages live here once friend ingests
│   ├── decisions/.gitkeep       # friend's own ADRs live here
│   ├── alternatives/.gitkeep    # friend's rejected options live here
│   ├── patterns/.gitkeep        # friend's reusable patterns live here
│   └── projects/.gitkeep        # per-project sub-wikis live here
└── modules/
    └── venture/                 # OPTIONAL founder/venture-arc templates.
        ├── company.md.tmpl      # NOT stamped by default — see manifest.yaml's
        ├── market.md.tmpl       # `venture` profile. Only used when a friend
        ├── icp.md.tmpl          # explicitly opts into the venture arc of
        ├── team.md.tmpl         # /ren:interview (§3.8: full venture arc is
        └── brain-dump.md.tmpl   # out of scope for the default 0.2 onboarding path).
```

The dev-content lint script and its forbidden-substring list live in `scripts/` (`scripts/lint_no_dev_wiki_content.py`, `scripts/forbidden-substrings.txt`) and the pytest wrapper lives in `tests/wiki_skeleton/` — never inside this directory, per the repo's test-layout rule (zero test code in shippable dirs).

## Template variables

Templates use a tiny `{{var}}` placeholder syntax. The install / bootstrap-project loader (`lib/skeleton.py`) substitutes these at write time:

| Placeholder         | Source                                          |
| ------------------- | ----------------------------------------------- |
| `{{handle}}`        | friend's kebab-case handle (from `/ren:interview`)  |
| `{{name}}`          | friend's display name (from `/ren:interview`)       |
| `{{today}}`         | ISO date (YYYY-MM-DD) of install / bootstrap       |
| `{{framework_version}}` | framework semver from the plugin registry      |

If a placeholder is encountered with no available value, the loader writes the literal placeholder back and logs a warning (so the friend can fill it in by hand). No silent dropping.

## Additive-only contract

- The loader reads `manifest.yaml` to learn the expected file set for a profile.
- For each manifest entry: if the target path exists on the friend's machine, **never overwrite**. Diff the proposed addition against existing content and report it for explicit approval.
- For each manifest entry: if the target path is absent, queue it for write.
- The friend approves the additive set; the loader writes only the approved subset.
- Existing files are **never touched** by the loader.

This makes minor framework upgrades safe: new template files appear in `wiki-skeleton/templates/`, the manifest gets bumped, and existing friend wikis can opt into the additions without losing content.

## How a contributor adds a new template file

1. Add the file under `wiki-skeleton/templates/<path>.md.tmpl` (or `wiki-skeleton/modules/<module>/<path>.md.tmpl` for an opt-in module).
2. Add the corresponding entry to `manifest.yaml` under the right profile, with the right `min_framework_version` (bump the manifest `schema_version` only when the contract changes).
3. Run `uv run python scripts/lint_no_dev_wiki_content.py` from the repo root to confirm no dev-wiki content snuck in.
4. Update the eval fixtures for `skills/install/` and `skills/bootstrap-project/` to cover the new file's presence.
