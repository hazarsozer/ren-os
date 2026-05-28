# schema-conformance — load-bearing drift-catcher

Per Task #42. Asserts that every file claiming a registered page-type conforms to `skills/wiki-migration/schemas.json` and to a minimum required-field contract.

## Why this exists

Cross-team drift catches schemas-vs-templates mismatches that look fine in isolation but break composition. Real example caught: onboarding-2's template named `type: project` when the registry expected `project-main`. This harness reproduces that catch automatically.

## What it checks

For every `.md` / `.md.tmpl` file in `SCAN_TARGETS`:

1. Parse YAML frontmatter (template placeholders rendered with synthetic values first).
2. If no `type:` field → mark "free-form" (legitimate per ADR-027 § opt-in semantics).
3. If `type:` is set:
   - Must be a registered key in `schemas.json#page_types`. Unknown type → FAIL.
   - `schema_version:` must be an integer in `[supported_from, current]`. Outside range → FAIL.
   - All required fields per `REQUIRED_FIELDS_BY_TYPE` must be present. Missing → FAIL.

## What it surfaces

- **Strict-mode failures** (block CI): template files in `wiki-skeleton/` and `skills/sf-bootstrap-project/templates/`. These are user-facing templates and MUST conform.
- **Informational fails** (do not block CI): files in `wiki/research/`, `wiki/decisions/`, etc. — the framework's dev wiki. These predate ADR-027 and aren't part of the shipped/installed wiki per ADR-017. They're scanned to surface drift but don't fail the harness.
- **Type coverage** report: every registered page-type listed; any without at least one conformant example tagged `⚠️ no conformant example (TODO)`.

## Run

```bash
# Direct
python3 tests/integration/schema-conformance/conformance.py

# Or via pytest (test_conformance.py wraps the harness in a pytest case)
pytest tests/integration/schema-conformance/
```

## Exit codes

- `0` — all strict-mode files conform
- `1` — at least one strict-mode failure (block ship)
- `2` — registry malformed or missing

## How to remediate a failure

Each failure line names:
- The file path
- The claimed `type` value
- The claimed `schema_version` value
- A concrete reason (e.g., `missing required field: ['project_name']`)

Three remediation paths:
1. **Wrong `type:` value** (typo) → fix the template's frontmatter
2. **Page-type missing from registry** → PR to `schemas.json` adding the entry, then re-run
3. **Out-of-range schema_version** → align with registry (forward drift means template is at a future version; backward beyond N+3 means deprecated)

## Required-fields contract

`REQUIRED_FIELDS_BY_TYPE` in `conformance.py` defines the minimum frontmatter keys per page-type. Universal triple (`type`, `schema_version`, `framework_version`) is mandatory for every typed page. Per-type extensions add fields specific to that type.

v1.1 plan: move `REQUIRED_FIELDS_BY_TYPE` into the schemas.json registry itself (e.g., a `required_fields: []` property per page-type) so the contract is self-describing.

## When to update this harness

- Adding a new page-type to schemas.json → also add an entry to `REQUIRED_FIELDS_BY_TYPE` (or leave the set empty for universal-only)
- Adding a new SCAN_TARGET location → append to `SCAN_TARGETS`
- Bumping a placeholder convention → update `TEMPLATE_PLACEHOLDERS`
