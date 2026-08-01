#!/usr/bin/env python3
"""
migrations/project-knowledge-1/migrate.py — relocate flat per-project pages
into the sanctioned `projects/<slug>/knowledge/` subtree (issue #20, 0.6.2).

Shape decision (mirrors `migrations/trust-backfill-1/` and
`migrations/queue-governance-2-to-3/` — see those READMEs for the fuller
rationale): `skills/wiki-migration`'s chain machinery (`schemas.json` +
`migrate.sh <page_path>`, as used by `routine-spec-*`) is a per-page
frontmatter transform selected by an ALREADY-KNOWN page type at an
already-known path. Neither holds here: the pages this migration fixes are
exactly the ones with no sanctioned type and the wrong path, and the run has
to see a whole `projects/<slug>/` directory at once (to know what's flat, and
to rewrite the map's pointers to what moved). So this is a standalone
`migrate.py`, listed in `schemas.json`'s `global_migrations` for
discoverability only.

Why it exists: before 0.6.2 the per-project taxonomy defined only `map.md`,
`overview.md` and `l1/session-*.md`. A real ingest therefore dropped distilled
pages as loose `.md` files directly under `projects/<slug>/` — outside any
schema, invisible to `check_schema_versions`. 0.6.2 sanctions
`projects/<slug>/knowledge/` (`type: project-knowledge`, `schema_version: 1`)
as their home; this relocates the pages already on disk.

What it does, per `projects/<slug>/`:
  - every `*.md` DIRECTLY under it except `map.md` and `overview.md`
    (`l1/` is a subdirectory and is never walked) is moved to
    `knowledge/<name>.md`;
  - its frontmatter is normalized to `type: project-knowledge`,
    `schema_version: 1`, `project: <slug>` — every OTHER frontmatter line
    (including `ren_*` provenance/trust stamps) and the entire body are
    preserved byte-for-byte;
  - `## Decision map` pointer lines in any `type: l2-map` page that targeted
    the old path are rewritten to the new one.

Never overwrites: if `knowledge/<name>.md` already exists, the flat file is
left exactly where it is and reported as a collision (destructive-write
doctrine, `docs/audits/2026-07-destructive-writes.md`). Idempotent: a second
run finds nothing flat left to move.

Journal: every move is appended as one JSON line to
`state_dir()/migrations/project-knowledge-1.jsonl` (`{ts, slug, from, to}`).
The framework write journal is not used — nothing here goes through the write
queue, and inventing `write_id`s for a relocation would make the journal lie.

Contract:
  argv:   [] (DRY RUN, the default — reports what would move, writes nothing)
          | ["--apply"] (perform the moves)
  env:    honors whatever `lib.ren_paths.wiki_root()` resolves.
  stdout: one line per page, then one totals line.
  exit:   0 always (a page that can't be classified is left alone, which is
          always safe).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.ren_paths import state_dir, wiki_root  # noqa: E402

#: Files under `projects/<slug>/` that ARE part of the sanctioned taxonomy and
#: must never be relocated. `l1/` needs no entry — only top-level files are
#: considered.
SANCTIONED = frozenset({"map.md", "overview.md"})

PAGE_TYPE = "project-knowledge"
SCHEMA_VERSION = 1
KNOWLEDGE_DIRNAME = "knowledge"
JOURNAL_NAME = "project-knowledge-1.jsonl"

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_TYPE_RE = re.compile(r"^type:\s*(.+)$", re.MULTILINE)
_POINTER_RE = re.compile(r"^-\s*\[[^\]]*\]\s*→\s*([^\s#]+)")


def _frontmatter_type(text: str) -> str | None:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    tm = _TYPE_RE.search(m.group(1))
    return tm.group(1).strip().strip('"').strip("'") if tm else None


def normalize_frontmatter(text: str, slug: str) -> str:
    """Set `type`/`schema_version`/`project` on `text`'s frontmatter block,
    preserving every other line and the body byte-for-byte. Creates a
    frontmatter block if the page has none."""
    fields = {
        "type": PAGE_TYPE,
        "schema_version": str(SCHEMA_VERSION),
        "project": slug,
    }
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        header = "\n".join(f"{k}: {v}" for k, v in fields.items())
        return f"---\n{header}\n---\n" + text

    body = text[match.end():]
    lines = match.group(1).split("\n")
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        # Only a key at column 0 is top-level (0.6.2 review finding L2):
        # an indented `  type: x` is a nested YAML value and must be
        # preserved byte-for-byte, not rewritten.
        top_level = ":" in line and not line[:1].isspace()
        key = line.split(":", 1)[0].strip() if top_level else None
        if key in fields:
            if key in seen:
                continue  # drop a duplicate key rather than emit it twice
            out.append(f"{key}: {fields[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in fields.items():
        if key not in seen:
            out.append(f"{key}: {value}")
    return "---\n" + "\n".join(out) + "\n---\n" + body


def _flat_pages(project_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in project_dir.glob("*.md")
        if p.is_file() and p.name not in SANCTIONED and not p.name.startswith(".")
    )


def rewrite_pointers(wiki: Path, moves: dict[str, str], *, apply: bool) -> list[str]:
    """Rewrite `## Decision map` pointer targets in every `type: l2-map` page
    from the old wiki-relative path to the new one. `moves` maps old → new.
    Returns the list of `"<page>: <old> → <new>"` rewrites made (or that
    would be made under a dry run)."""
    rewritten: list[str] = []
    if not moves:
        return rewritten

    for md_path in sorted(wiki.rglob("*.md")):
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _frontmatter_type(text) != "l2-map":
            continue

        page = md_path.relative_to(wiki).as_posix()
        in_decision_map = False
        changed = False
        out_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("## "):
                in_decision_map = line.strip() == "## Decision map"
            elif in_decision_map:
                m = _POINTER_RE.match(line.strip())
                if m and m.group(1) in moves:
                    old, new = m.group(1), moves[m.group(1)]
                    line = line.replace(old, new, 1)
                    rewritten.append(f"{page}: {old} → {new}")
                    changed = True
            out_lines.append(line)

        if changed and apply:
            trailing = "\n" if text.endswith("\n") else ""
            md_path.write_text("\n".join(out_lines) + trailing, encoding="utf-8")
    return rewritten


def _journal(records: list[dict]) -> None:
    path = state_dir() / "migrations" / JOURNAL_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    apply = "--apply" in args

    wiki = wiki_root()
    projects_dir = wiki / "projects"
    if not projects_dir.is_dir():
        print("project-knowledge-1: no projects/ directory — nothing to do")
        return 0

    moved = 0
    collisions = 0
    path_moves: dict[str, str] = {}
    records: list[dict] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    schemaless = 0
    for project_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        slug = project_dir.name
        # Issue #20 amendment (hierarchical project wikis): every project
        # should carry its own SCHEMA document. REPORT-only — a migration
        # script cannot invent a taxonomy; the model/user writes schema.md
        # in a live session that can see the project.
        if not (project_dir / "schema.md").is_file():
            print(
                f"projects/{slug}: no schema.md — draft one (type: project-schema) "
                "declaring this project's knowledge/ taxonomy (not fabricated here)"
            )
            schemaless += 1
        for page in _flat_pages(project_dir):
            target = project_dir / KNOWLEDGE_DIRNAME / page.name
            rel_from = page.relative_to(wiki).as_posix()
            rel_to = target.relative_to(wiki).as_posix()

            if target.exists():
                print(f"{rel_from}: COLLISION — {rel_to} already exists, left in place")
                collisions += 1
                continue

            if apply:
                try:
                    text = page.read_text(encoding="utf-8")
                except OSError:
                    print(f"{rel_from}: unreadable, left in place")
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(normalize_frontmatter(text, slug), encoding="utf-8")
                page.unlink()
                print(f"{rel_from}: moved -> {rel_to}")
                # 0.6.2 review finding M2: journal each move IMMEDIATELY, not
                # in one batch at the end — a mid-run failure (e.g. a later
                # unlink raising) must not lose the record of files already
                # moved.
                record = {"ts": ts, "slug": slug, "from": rel_from, "to": rel_to}
                _journal([record])
                records.append(record)
            else:
                print(f"{rel_from}: WOULD MOVE -> {rel_to}")

            path_moves[rel_from] = rel_to
            moved += 1

    rewritten = rewrite_pointers(wiki, path_moves, apply=apply)
    for line in rewritten:
        print(("pointer rewritten " if apply else "pointer WOULD BE rewritten ") + line)

    verb = "moved" if apply else "would move"
    print(
        f"project-knowledge-1: {moved} page(s) {verb}, {len(rewritten)} pointer(s) "
        f"{'rewritten' if apply else 'would be rewritten'}, {collisions} collision(s), "
        f"{schemaless} project(s) missing schema.md"
        + ("" if apply else " — DRY RUN, re-run with --apply to write")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
