# l2-map v1 → v2

Task 6 (#53). The repo's first BODY-rewriting migration — see `migrations/README.md`'s portability doctrine (issue #9) for why this is Python (`transform.py`) rather than sed: rewriting a regex-captured group back into a different line shape needs real parsing, not text substitution, and `lib/pointer.py` (Task 1) is already the single home of that grammar.

**What it converts:** arrow-form pointer lines (`- [Topic] → target (write_id)`) under a page's `## Decision map` section, where `target` is a wiki-root-relative path, into the canonical markdown-link form (`- [Topic](target) (write_id)`) — Obsidian renders links, not bare arrows, as navigable. `schema_version` is stamped to `2`, inserted right after the `type:` line when absent (the dogfood maps predate schema stamping — issue #20) or overwritten in place when a stale value is already present.

**What it never touches:** `repo:` refs (canonical arrow form stays arrow form — `render_pointer_line` renders those as arrows on purpose), prose elsewhere in the page (a `→` inside a sentence is not a pointer line and `parse_pointer_line` returns `None` for it), any section other than `## Decision map`, and any page whose `type` isn't `l2-map`. Every rewritten line is re-parsed with `lib/pointer.py` before the file is replaced (write-temp-then-rename); if a line doesn't round-trip, the page is left byte-identical and the migration exits 1 rather than emit a line its own consumers can't read.

**How it's driven:** `/ren:update` runs this over every `type: l2-map` page in the wiki, including the master `index.md`, under the usual snapshot/rollback machinery (`REN_SNAPSHOT_DIR`). Idempotent — a page already at `schema_version: 2` is skipped (`SKIP: already at schema 2`).
