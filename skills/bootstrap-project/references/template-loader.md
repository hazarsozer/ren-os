# Template Loader — shared procedure

This is the **single source of truth** for how the framework expands template files into a friend's wiki. Used by:

- `skills/sf-bootstrap-project/SKILL.md` — to stamp `~/.startup-framework/wiki/projects/<name>/`
- `skills/sf-install/SKILL.md` Stage 5 — to stamp `~/.startup-framework/wiki/` itself (via `wiki-skeleton/manifest.yaml` profile `master`)

Anything that needs to write template files into a friend's wiki MUST follow this procedure. Do not reimplement.

## Inputs

Every invocation takes:

1. **Template root** — directory holding `.tmpl` files and a `templates/` subtree
2. **Target root** — directory on the friend's machine where output goes
3. **Manifest** — either a `manifest.yaml` (preferred for long-lived contracts like the master skeleton) OR an inline file list with explicit write rules (for self-contained skills like sf-bootstrap-project)
4. **Placeholder bindings** — map of `{{var}}` → string value

## The procedure

### Step 1: Verify target root

- If target root doesn't exist, create it (`mkdir -p`).
- If target root exists AND any of the planned files exist, switch to **Additive-diff mode** (see below). Otherwise, continue.

### Step 2: For each manifest entry

In manifest order:

1. **Resolve the source path**: `template_root/<entry.template>` (for files) or `entry.path` (for directories).
2. **Resolve the target path**: `target_root/<entry.path>`.
3. **Check the write rule**:
   - `copy_if_missing` (files): if target exists, skip with info log. If absent, continue.
   - `create_if_missing` (directories): `mkdir -p target_path`. Idempotent. Place an empty `.gitkeep` inside if the template had one.
   - `never_write` (reserved): record presence in summary, never write.
4. **For files**, read the source template content.
5. **Expand placeholders**: substitute each `{{var}}` with its bound value. If a placeholder appears in the file but isn't in the bindings map, leave the literal `{{var}}` in the output and emit a warning. Never silently substitute empty string.
6. **Write the expanded content** to the target path.
7. **Record outcome** in the run summary: `wrote | skipped | warned | refused`.

### Step 3: Report

Emit a per-entry summary to the friend:

```
Bootstrapping <target_root>:
  wrote   PROJECT.md
  wrote   REQUIREMENTS.md
  wrote   ROADMAP.md
  wrote   STATE.md
  wrote   CONTEXT.md
  wrote   index.md
  wrote   log.md
  created research/
  created decisions/
  created patterns/

Done. 7 files written, 3 directories created.
```

## Placeholder expansion rules

- Single pattern: `{{var}}` (exactly two curly braces, no spaces inside).
- Variable names: `[a-z][a-z0-9_]*` (lowercase, snake_case, leading letter).
- Substitution is literal text replacement. No shell expansion, no nested templates, no conditionals.
- The bindings map MUST include every required placeholder for the template set. The skill calling the loader is responsible for assembling the map. If the loader encounters an unbound placeholder, it leaves the literal `{{var}}` in the output AND emits a warning line in the summary: `WARN: <file> contains unbound {{var}} at line <n>; left literal`.
- This is intentional: the friend should be able to grep `{{` in their wiki and find any unfilled holes.

## Additive-diff mode

Triggered when the target root already contains some (or all) of the planned files. Per the team-lead's Stage-5 pushback + ADR-027's MINOR-bump migration pattern:

1. For each manifest entry, compute its planned status: `would_write` (file absent + has template content) | `already_present` (file exists) | `would_create` (dir absent).
2. Render a diff summary to the friend:

   ```
   Target <target_root> already exists. Proposed additive changes:
     would_write   patterns/.gitkeep          (new in framework v1.2.0)
     would_create  alternatives/              (new in framework v1.1.0)
     already_present  PROJECT.md
     already_present  REQUIREMENTS.md
     ...
   ```

3. Prompt: `Apply additive changes? [y/N]` — default NO.
4. If yes: write only the `would_write` / `would_create` entries.
5. If no: exit clean, write nothing, log "additive diff declined by friend".

**Never overwrite an existing file under any circumstance.** No flag, no force mode, no implicit upgrade. This is the load-bearing safety rule from team-lead's P2 pushback.

## Error handling

| Condition | Loader behavior |
|---|---|
| Template source path missing | Refuse the whole run; print path + skill name; exit non-zero. Not the friend's fault — this is a framework bug. |
| Target path is not writable | Refuse the whole run; print path + remediation (e.g. "check permissions on ~/.startup-framework/wiki/"). |
| Manifest YAML malformed | Refuse the whole run; print parser error + path. |
| Unbound placeholder | Continue with literal `{{var}}` + warning (per § "Placeholder expansion rules"). |
| Disk full mid-write | Stop at the failing entry; do NOT roll back already-written entries; surface the partial state with explicit "re-run to resume" guidance. The friend can clean up manually. |

## Why a single loader

Two skills (sf-install Stage 5, sf-bootstrap-project) and one future skill (sf-install's `/sf:migrate-wiki`) need the same write semantics. Diverging implementations cause subtle drift — additive-diff turning into overwrite, placeholder pattern changes, write-rule meanings drifting. One spec, one set of fixtures, one set of eval assertions.

When the loader's contract changes, bump `wiki-skeleton/manifest.yaml`'s `schema_version` and document the change in this file's "Revision history" below.

## Revision history

- v1 (2026-05-28) — initial loader spec. Two write rules (`copy_if_missing`, `create_if_missing`). Additive-diff mode for existing targets. Single-brace `{{var}}` placeholder syntax. Warning-on-unbound behavior.
