"""Invariant: no wiki-skeleton template may be born behind its own page
type's current schema version (#53 review finding — `index.md.tmpl` shipped
`schema_version: 1` while the l2-map registry entry was already at 2, so
every fresh install failed `/ren:doctor` on day one). Walks every `.md.tmpl`
under `wiki-skeleton/` (both `templates/` and the `modules/` add-ons) and,
for any template stamping BOTH `type:` and `schema_version:` in its
frontmatter, checks it against `skills/wiki-migration/lib`'s registry —
types the registry doesn't know about (e.g. `log-entry`, `licenses`) are
skipped, since they carry no schema chain to be behind."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import yaml

SKELETON_ROOT = Path(__file__).resolve().parents[2] / "wiki-skeleton"

_wiki_migration_lib = importlib.import_module("skills.wiki-migration.lib")
load_registry = _wiki_migration_lib.load_registry


def _frontmatter(template_path: Path) -> dict:
    text = template_path.read_text(encoding="utf-8")
    # Unrendered `{{placeholder}}` tokens (e.g. `updated: {{today}}`) aren't
    # valid YAML scalars — stub them out with a harmless string, same as
    # test_manifest.py's binding-substitution approach for the fields this
    # test actually reads (`type`, `schema_version`, both always literal).
    text = re.sub(r"\{\{\w+\}\}", "placeholder", text)
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    data = yaml.safe_load(match.group(1))
    return data if isinstance(data, dict) else {}


def test_every_template_schema_version_matches_registry_current():
    registry = load_registry()
    page_types = registry["page_types"]
    assert page_types, "registry loaded empty — invariant would vacuously pass"

    checked = 0
    for template_path in sorted(SKELETON_ROOT.rglob("*.md.tmpl")):
        frontmatter = _frontmatter(template_path)
        page_type = frontmatter.get("type")
        schema_version = frontmatter.get("schema_version")
        if page_type is None or schema_version is None:
            continue
        if page_type not in page_types:
            continue
        checked += 1
        expected = page_types[page_type]["current"]
        assert schema_version == expected, (
            f"{template_path.relative_to(SKELETON_ROOT)}: type={page_type!r} "
            f"stamps schema_version={schema_version!r}, but registry current "
            f"is {expected!r}"
        )

    assert checked > 0, "no template exercised the invariant — check the glob/registry types"
