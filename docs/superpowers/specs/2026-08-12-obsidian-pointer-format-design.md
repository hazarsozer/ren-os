# Obsidian-native pointer format (#53) — design

**Date:** 2026-08-12 · **Issue:** [#53](https://github.com/hazarsozer/ren-os/issues/53) · **Target version:** 0.7.0 (ships with #54, #55; #56 deferred to MAJOR)

## Problem

The L2 decision-map pointer grammar `- [topic] → <path> (<write_id>)` is plain
text to Obsidian and every other markdown-graph tool. On the dogfood wiki this
leaves all 29 map pointers edge-less: 40 of 94 vault pages are full orphans and
the graph splits into 43 components, even though the knowledge trees themselves
have zero unresolved links. The maps are the designed hubs; their spokes are
invisible. Fix the grammar at the source and migrate existing wikis atomically
with the parser change — hand-conversion ahead of the version is unsupported.

## Decisions already made (with Hazar)

- 0.7.0 bundles #53 + #54 + #55; #56 (hub renames, folder-note convention)
  waits for a MAJOR bump.
- Only wiki-file targets become links; `repo:<name>:<path>` external refs keep
  the arrow form (a fake link would reintroduce lying edges).
- write_id stays as the trailing paren group (greppable, matches what
  `remember` already strips; not hidden in a link title).
- Paths stay wiki-root-relative (Obsidian resolves vault-absolute paths; wiki
  path-math unchanged).
- Legacy arrow form with a wiki path stays parse-accepted until the #56 MAJOR
  bump, but is never emitted again.
- No Graphify impact: the code-map integration is code-mode only, never reads
  the wiki, and its output lives outside the wiki tree by asserted invariant.
  Standard links only improve future Obsidian-ecosystem compatibility.

## 1. Pointer grammar (the contract)

A decision-map pointer line is one of two shapes:

```
- [<topic>](<wiki-root-relative-path>.md[#anchor]) (<write_id|unstamped>)   ← wiki target (new canonical)
- [<topic>] → repo:<name>:<path> (<write_id|unstamped>)                     ← external repo ref (unchanged)
```

Schema: `l2-map` goes `1 → 2`; version 2 means "wiki-target pointers are
link-form." Master `index.md` is `type: l2-map` and is covered like any
project map.

## 2. Shared parser: `lib/pointer.py`

New module — the single place the grammar lives.

```python
@dataclass(frozen=True)
class PointerLine:
    topic: str
    target: str          # "projects/x/page.md#anchor" or "repo:name:path"
    path: str            # target without anchor ("" for repo refs)
    anchor: str | None
    write_id: str | None # None when "(unstamped)" or absent
    form: Literal["link", "arrow"]

def parse_pointer_line(line: str) -> PointerLine | None:  # None = not a pointer line
```

Accepts both grammars. Consumers rewire onto it:

| Consumer | Today | Change |
|---|---|---|
| `skills/wiki-health/lib/__init__.py:88` `_POINTER_RE` | own regex + `_REPO_REF_PREFIX` skip | delete regex; `_dangling_pointers` uses `parse_pointer_line`, skips `repo:` targets via the parser's classification |
| `skills/doctor/lib/__init__.py:226` | duplicate regex | same replacement |
| `skills/remember/lib/__init__.py:37` `_POINTER_RE` + `_TRAILING_PAREN_RE` | regex + trailing-paren strip | render `topic`/`path` from the dataclass; kills the two-paren-group hazard |

The cross-module regex drift test in `tests/skills/wiki_health/test_sweep.py`
is replaced by an import-identity assertion (all three consume `lib.pointer`).

## 3. Producer: `assemble_l2`

`skills/ingest-project/lib/__init__.py` (pointer line at ~110) branches on
target shape: wiki `.md` path → link form; `repo:` prefix → arrow form.
Emitted maps stamp `schema_version: 2`. The `_All pointer paths are relative
to the wiki root…_` caption stays. SKILL.md examples in ingest-project,
bootstrap-project, remember, and wiki-health update to the new line shape so
live sessions hand-writing map lines (wrap flow) copy the right grammar.

## 4. Migration: `migrations/l2-map-1-to-2/`

Same three-file shape and contract as `routine-spec-2-to-3` (`$1` = page path,
`REN_WIKI_ROOT`/`REN_SNAPSHOT_DIR`, stdout `OK`/`SKIP:`, exit 0/2/1,
idempotent, bounded to `$1`). **This is the repo's first body-rewriting
migration** — existing ones are frontmatter-only — which drives two choices:

- `migrate.sh` keeps the guard boilerplate in shell but hands the body
  transform to an inline Python step (uv-run), not sed: the anchor/unstamped/
  `repo:`-exclusion logic is regex-group work that BSD sed makes fragile (the
  reference script already needs a 10-line BSD-vs-GNU comment for mere
  frontmatter inserts).
- Transform scope: only lines under `## Decision map`; only arrow-form lines
  whose target is a wiki-relative path. `repo:` lines and prose arrows
  elsewhere in the body are untouched. Then bump `schema_version: 1 → 2`.
- **Self-verification**: after rewriting, the transform re-parses every
  Decision-map line with `lib/pointer.py`; any failure → exit 1, page
  untouched (write-temp-then-rename). The migration cannot emit a line its
  own consumers can't read.
- `verify.json`: `yaml.valid`, `schema_version == 2`, `type == l2-map`.
  (`snapshot.body-identical` is deliberately absent — body changes are the
  point; body correctness is covered by self-verification + tests.)
- `schemas.json`: `"l2-map": {"current": 2, "migrations": ["l2-map-1-to-2"]}`.
- Driver: `/ren:update` runs it over all `type: l2-map` pages under the
  existing snapshot/rollback. `/ren:doctor` flags l2-maps still at 1.

Non-goal: pointer-shaped lines on non-l2-map pages are never converted
(knowledge hubs already use real markdown links).

## 5. Error handling

- `parse_pointer_line` → `None` on anything malformed: consumers degrade to
  "not a pointer," identical to today's regex non-match. `(unstamped)` →
  `write_id=None`.
- Migration: temp-write + rename; self-verify failure exits 1 with the page
  byte-identical; batch failure covered by `/ren:update` snapshot/rollback;
  re-run SKIPs at schema 2.
- Pages without frontmatter or with another `type` are never touched.

## 6. Testing

- `lib/pointer.py`: both grammars, anchors, `unstamped`, `repo:` refs,
  malformed lines, emit→parse round-trip.
- `assemble_l2`: golden output with mixed wiki/`repo:` pointers;
  `schema_version: 2` stamped.
- Consumers: wiki-health/doctor/remember suites run fixtures in BOTH formats —
  dual-format acceptance is a tested contract. Drift test → import-identity.
- Migration: v1 fixtures modeled on the dogfood maps (flux's 15 pointers,
  genshin's dangling targets, index.md's placeholder section) → migrate →
  verify.json passes, every line re-parses, `repo:` untouched, second run
  SKIPs, injected-malformed-line run exits 1 with page unchanged.
- Doctor: l2-map at version 1 → warn fixture.

## Out of scope

- Producer link duties (#54) and wiki-wide orphan detection (#55) — own specs,
  same 0.7.0.
- Hub renames / folder-note convention, dropping arrow parsing (#56, MAJOR).
- Any hand-edit of the dogfood wiki — it converts via `/ren:update` only.
