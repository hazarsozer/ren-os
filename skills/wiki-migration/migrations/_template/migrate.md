# `<Page-type>` v`<from>` → v`<to>` — LLM prompt

> Replace this entire file with the actual prompt when you author a real migration. Delete this file entirely if your migration mode is "scripted" (script-only).

## When this prompt runs

This prompt is invoked by `/sf:update`'s MIGRATING state when the migration mode (declared in `README.md`) is `LLM-driven` or `hybrid`. The driver passes:

- `${page_path}` — absolute path to the current page (post-script if hybrid; pre-anything if LLM-only)
- `${snapshot_path}` — absolute path to the pre-migration snapshot of the same page
- `${page_type}` — the registered page-type identifier
- `${from_schema}` and `${to_schema}` — version integers

The model output replaces the file contents. No body text printed outside the file.

---

## Prompt body

You are migrating a wiki page from schema version `${from_schema}` to schema version `${to_schema}`. The page type is `${page_type}`.

### Inputs

- The current file contents (after any scripted preprocessing): `<contents of ${page_path}>`
- The pre-migration snapshot (read-only reference): `<contents of ${snapshot_path}>`

### Rules

1. **Preserve everything except what this migration explicitly changes.** Untouched frontmatter keys: keep their values byte-identical. Untouched body sections: keep their text byte-identical.
2. **Set `schema_version: ${to_schema}` in the frontmatter.**
3. **Set `framework_version: ${framework_version}`** (the env var the driver passes).
4. **Apply the semantic changes specific to this migration.** Replace this sentence with a numbered list of what to do. Be specific. For each transformation, name the source field/section, the target field/section, and the rule for value mapping.
5. **No code fences, no commentary.** Output ONLY the new file contents. The driver writes them verbatim to disk.
6. **Preserve YAML formatting.** Same indentation, same quote style, same key order (unless this migration reorders keys).
7. **If the snapshot has a key/section your transformation depends on, use the SNAPSHOT value as the source of truth.** The current file may have been touched by a preceding scripted step in a hybrid migration; the snapshot is the original.

### What this migration changes (FILL THIS IN)

Replace this list with the actual transformations. Be precise. The verify.json assertions will catch deviations.

- (transformation 1)
- (transformation 2)
- ...

### Output format

Emit the full new file contents starting with `---` (the frontmatter delimiter) and ending with the page's final character. No additional output before or after.
