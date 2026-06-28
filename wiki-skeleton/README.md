# wiki-skeleton/

**Audience:** framework contributors. **Not shipped to a friend's installed wiki as-is.**

## What this is

`wiki-skeleton/` holds the empty templates the framework's `/ren:install` skill (Stage 5) and `/ren:bootstrap-project` skill stamp into a friend's machine when they run the framework for the first time (or bootstrap a new project).

It is **the plugin's shipping payload** for the wiki layer — not a copy of the framework's own development wiki. Per ADR-017, the friend's wiki starts EMPTY of any framework-developer content. The skeleton provides structure + page-format conventions; the friend fills in content through their own work.

## What this is NOT

- **Not the framework's development wiki.** That lives at `wiki/` (peer of this directory). Our 16+ ADRs and research pages are how WE designed the framework. They never ship to users.
- **Not a content seed.** No example research entries, no example decisions, no founder names, no project-history references. The CI lint at `tests/lint_no_dev_wiki_content.py` enforces this.

## Layout

```
wiki-skeleton/
├── README.md                    # this file
├── manifest.yaml                # file set + per-file rules (consumed by Stage 5 + bootstrap-project)
├── templates/
│   ├── index.md.tmpl            # master wiki index — empty section headers
│   ├── log.md.tmpl              # master log — single init entry
│   ├── identity.md.tmpl         # frontmatter stub; /ren:interview populates it
│   ├── LICENSES.md.tmpl         # plugin-license summary; written at Stage 6
│   ├── research/.gitkeep        # ingested-source pages live here once friend ingests
│   ├── decisions/.gitkeep       # friend's own ADRs live here
│   ├── alternatives/.gitkeep    # friend's rejected options live here
│   ├── patterns/.gitkeep        # friend's reusable patterns live here
│   └── projects/.gitkeep        # per-project sub-wikis live here
└── tests/
    ├── lint_no_dev_wiki_content.py   # CI guard; see ADR-017 R4 risk
    ├── forbidden-substrings.txt      # curated forbidden-content list
    └── README.md                     # how to run the lint
```

## Template variables

Templates use a tiny `{{var}}` placeholder syntax. The Stage 5 / bootstrap-project loader substitutes these at write time:

| Placeholder         | Source                                          |
| ------------------- | ----------------------------------------------- |
| `{{handle}}`        | friend's kebab-case handle (from `/ren:interview`)  |
| `{{name}}`          | friend's display name (from `/ren:interview`)       |
| `{{today}}`         | ISO date (YYYY-MM-DD) of install / bootstrap       |
| `{{framework_version}}` | framework semver from the plugin registry      |

If a placeholder is encountered with no available value, the loader writes the literal placeholder back and logs a warning (so the friend can fill it in by hand). No silent dropping.

## Stage-5 contract (additive-only migration)

Per ADR-027 §"MINOR" and team-lead pushback on the plan:

- Stage 5 reads `manifest.yaml` to learn the expected file set.
- For each manifest entry: if the target path exists on the friend's machine, **never overwrite**. Diff the proposed addition against existing content and report it for explicit approval.
- For each manifest entry: if the target path is absent, queue it for write.
- The friend approves the additive set; loader writes only the approved subset.
- Existing files are **never touched** by the loader.

This makes minor framework upgrades safe: new template files appear in `wiki-skeleton/templates/`, the manifest gets bumped, and existing friend wikis can opt into the additions without losing content.

## How a contributor adds a new template file

1. Add the file under `wiki-skeleton/templates/<path>.md.tmpl`.
2. Add the corresponding entry to `manifest.yaml` with the right `min_schema_version` (bump the manifest `schema_version` only when the contract changes).
3. Run `python tests/lint_no_dev_wiki_content.py` from inside `wiki-skeleton/` to confirm no dev-wiki content snuck in.
4. Update the eval fixtures for `skills/sf-install/` and `skills/sf-bootstrap-project/` to cover the new file's presence.

## Related ADRs

- ADR-004 — page format conventions the templates follow
- ADR-014 — per-project taxonomy that `skills/sf-bootstrap-project/` instantiates
- ADR-015 — Stage 5 of `/ren:install`
- ADR-017 — load-bearing: skeleton ships, dev wiki does not
- ADR-022 — `identity.md` frontmatter shape (this template reflects it)
- ADR-027 — schema versioning + additive migration pattern
