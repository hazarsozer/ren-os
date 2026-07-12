# trust-backfill-1

0.5.1 Task 7. Backfills `ren_trust` (the trust taxonomy stamped by
`lib.memory.provenance` at the single write door since 156e0c0..500bf3c,
0.5.1 Task 6) onto every pre-0.5.1 wiki page that doesn't carry it yet.

## Shape decision: standalone script, not the wiki-migration chain

`migrations/routine-spec-1-to-2/` and `-2-to-3/` follow
`skills/wiki-migration`'s chain shape: a `schemas.json` registry keyed by
**page type**, and a `migrate.sh <page_path>` invoked once per matching page
of that type. `ren_trust` is not a per-page-type `schema_version` field — it
is stamped on EVERY page regardless of type — so there is no page type to
register a `<type>-N-to-M` chain entry under, and no natural
"invoked once per page of type X" dispatch. This mirrors the shape decision
`migrations/queue-governance-2-to-3/` made for queue state; here the walked
state is the wiki tree instead.

`skills/wiki-migration/schemas.json` gets a `global_migrations` note listing
this migration for discoverability (so `/ren:doctor` and a friend reading
the registry can find it), but it is **not** driven by `migration_chain()` —
that function is page-type-keyed and would never select a migration with no
page type.

## What it does

Walks every `*.md` under the wiki root (skipping dot-prefixed path
components, e.g. `.ren/`). For each page lacking `ren_trust`:

- `ren_writer == "human"` → `"user"`
- `quarantine.is_quarantined(text)` → `"foreign"`
- else → `"model"` (the spec's conservative default — 0.5.1's trust
  taxonomy treats unclassified pre-0.5.1 content as model-produced, not
  user-authored, until proven otherwise)

Only the `ren_trust: "<value>"` line is inserted into frontmatter (right
after `ren_op:` when present, else appended); every other frontmatter line
and the entire body are left byte-for-byte untouched. A page with no
frontmatter at all gets a new frontmatter block containing only `ren_trust`.

## Idempotent

A page that already carries `ren_trust` (checked via
`provenance.read_frontmatter_provenance(text)["trust"]`) is skipped. A
second run always finds the same (possibly empty) set of unstamped pages
and is a clean no-op.

## Usage

```sh
# report only, no writes:
uv run python migrations/trust-backfill-1/migrate.py --check

# apply:
uv run python migrations/trust-backfill-1/migrate.py
```

Honors whatever `lib.ren_paths.wiki_root()` already resolves
(`REN_WIKI_ROOT` / `CLAUDE_PLUGIN_OPTION_WIKIROOT` / `REN_FRAMEWORK_ROOT`) —
this script does not read wiki-root env vars itself.

Prints one summary line per stamped page, then one totals line.

## Rollback

Each stamp is a single inserted frontmatter line; a friend who wants to
undo it can restore from the pre-update wiki snapshot `/ren:update` already
takes, same as any other migration in this directory.
