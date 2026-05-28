#!/usr/bin/env bash
# check-schemas.sh — sf-doctor SCHEMA VERSIONS section
#
# Output format: lines of `KEY|STATUS|VALUE|HINT|FILES_FOUND|CURRENT|YOURS|SUPPORTED_FROM`
# where the trailing fields describe per-page-type counts and version state.
#
# Inputs:
#   - $1 = path to schemas.json (defaults to ${SF_PLUGIN_DIR}/skills/wiki-migration/schemas.json)
#   - env: WIKI_ROOT (from CLAUDE_PLUGIN_OPTION_WIKIROOT) — friend's wiki location
#   - env: ACTIVITY_FEED_LOCAL (from CLAUDE_PLUGIN_OPTION_ACTIVITYFEEDLOCALCLONE)
#
# Side effects: NONE. Reads schemas.json + walks wiki frontmatter.
# Requires: python3 (for YAML frontmatter parsing — bash regex is too brittle).

set -uo pipefail

emit() { printf '%s|%s|%s|%s|%s|%s|%s|%s\n' "$1" "$2" "${3:-}" "${4:-}" "${5:-}" "${6:-}" "${7:-}" "${8:-}"; }

SCHEMAS_JSON="${1:-${SF_PLUGIN_DIR:-${CLAUDE_PLUGIN_ROOT:-.}}/skills/wiki-migration/schemas.json}"
WIKI_ROOT="${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}"
FEED_LOCAL="${CLAUDE_PLUGIN_OPTION_ACTIVITYFEEDLOCALCLONE:-$HOME/.startup-framework/activity-feed}"

if [[ ! -f "$SCHEMAS_JSON" ]]; then
  emit "_error" "error" "schemas.json not found at $SCHEMAS_JSON" "→ The plugin install is broken. Reinstall via /sf:install."
  exit 1
fi

if [[ ! -d "$WIKI_ROOT" ]]; then
  emit "_error" "error" "wiki not found at $WIKI_ROOT" "→ Run /sf:install to bootstrap; or /sf:install --restore."
  exit 1
fi

# All YAML/JSON parsing in Python — bash regex is unsafe for arbitrary content.
exec python3 - "$SCHEMAS_JSON" "$WIKI_ROOT" "$FEED_LOCAL" <<'PYEOF'
import json, os, sys, re, glob

schemas_path, wiki_root, feed_local = sys.argv[1], sys.argv[2], sys.argv[3]

with open(schemas_path) as f:
    registry = json.load(f)

page_types = registry["page_types"]

# Glob patterns per page-type → list of files to scan
def globs_for(pt: str) -> list[str]:
    pattern = page_types[pt]["path_pattern"]
    if pt == "identity":
        return [os.path.join(wiki_root, "identity.md")]
    if pt == "project-main":
        return glob.glob(os.path.join(wiki_root, "projects", "*", "PROJECT.md"))
    if pt == "project-state":
        return glob.glob(os.path.join(wiki_root, "projects", "*", "STATE.md"))
    if pt == "project-roadmap":
        return glob.glob(os.path.join(wiki_root, "projects", "*", "ROADMAP.md"))
    if pt == "project-requirements":
        return glob.glob(os.path.join(wiki_root, "projects", "*", "REQUIREMENTS.md"))
    if pt == "project-context":
        return glob.glob(os.path.join(wiki_root, "projects", "*", "CONTEXT.md"))
    if pt == "research":
        return glob.glob(os.path.join(wiki_root, "research", "*.md"))
    if pt == "decision":
        return glob.glob(os.path.join(wiki_root, "decisions", "*.md"))
    if pt == "pattern":
        return glob.glob(os.path.join(wiki_root, "patterns", "*.md"))
    if pt == "log-entry":
        return [os.path.join(wiki_root, "log.md")]
    if pt == "project-log-entry":
        return glob.glob(os.path.join(wiki_root, "projects", "*", "log.md"))
    if pt == "feed-entry":
        if not os.path.isdir(feed_local):
            return []
        return glob.glob(os.path.join(feed_local, "*.log.md"))
    if pt == "skill":
        return glob.glob(os.path.join(wiki_root, "skills", "*", "SKILL.md"))
    if pt == "master-index":
        p = os.path.join(wiki_root, "index.md")
        return [p] if os.path.isfile(p) else []
    if pt == "project-index":
        return glob.glob(os.path.join(wiki_root, "projects", "*", "index.md"))
    if pt == "licenses":
        p = os.path.join(wiki_root, "LICENSES.md")
        return [p] if os.path.isfile(p) else []
    return []

frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def parse_frontmatter(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(8192)  # frontmatter is always at the top; 8K is plenty
    except OSError:
        return {}
    m = frontmatter_re.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm

def emit(key, status, value="", hint="", files_found="", current="", yours="", supported_from=""):
    print(f"{key}|{status}|{value}|{hint}|{files_found}|{current}|{yours}|{supported_from}")

for pt, meta in page_types.items():
    files = globs_for(pt)
    files_found = len(files)
    current = meta["current"]
    supported_from = meta["supported_from"]
    deprecated_below = meta.get("deprecated_below")

    if files_found == 0:
        # Page-type registered but no instance present. Not an error — most friends won't have every type at v1.
        emit(pt, "skip", "(no files of this type)", "", "0", str(current), "-", str(supported_from))
        continue

    # Collect schema_version values across all files of this type.
    # Per REVIEW.md D1: track per-FILE presence explicitly so we don't undercount
    # files-with-schema when multiple files share the same schema_version value
    # (which is the NORMAL case for a healthy wiki).
    yours_set = set()
    files_without_fm = 0
    files_without_schema_field = 0
    files_with_schema = 0
    files_at_wrong_type = 0

    for fp in files:
        fm = parse_frontmatter(fp)
        if not fm:
            files_without_fm += 1
            continue
        # Check `type:` matches the registered identifier (when present)
        ftype = fm.get("type", "")
        if ftype and ftype != pt:
            files_at_wrong_type += 1
        sv_raw = fm.get("schema_version", "")
        if sv_raw == "" or sv_raw is None:
            # Genuine absence — ADR-027 fallback applies for THIS file specifically.
            files_without_schema_field += 1
            continue
        files_with_schema += 1
        try:
            yours_set.add(int(sv_raw))
        except (TypeError, ValueError):
            yours_set.add(sv_raw)  # keep as string for reporting

    # Sanity: counts must sum (defensive — catches future logic bugs).
    assert files_found == files_without_fm + files_without_schema_field + files_with_schema, \
        f"count mismatch for {pt}: found={files_found} fm_missing={files_without_fm} sv_missing={files_without_schema_field} sv_present={files_with_schema}"

    # Determine status:
    # - missing frontmatter on any file: warn
    # - any file with schema below supported_from: error (deprecated)
    # - any file with schema below current but >= supported_from: warn (migration available)
    # - any file with schema in (deprecated_below ... supported_from-1) early-deprecation warning
    # - all files at current: ok

    numeric_yours = {y for y in yours_set if isinstance(y, int)}
    string_yours = yours_set - numeric_yours

    status = "ok"
    hint = ""
    annotation = ""

    if files_without_fm > 0 or string_yours:
        status = "warn"
        hint = f"{files_without_fm} file(s) lack valid frontmatter; {len(string_yours)} have non-integer schema_version"

    elif files_without_schema_field == files_found and files_found > 0:
        # All files have frontmatter but NONE declare schema_version — legacy pre-v1 pages.
        # Per ADR-027 § Pages without schema_version: assume schema_version: 1.
        # Don't error; just note. Friend's first /sf:update will add the field via migration 1→2.
        status = "warn"
        hint = (f"no schema_version field in any file (legacy pre-v1 frontmatter). "
                f"Assuming schema_version: 1 per ADR-027 fallback. "
                f"Next migration will add the field explicitly.")
        # Synthesise yours so downstream rendering is consistent
        numeric_yours = {1}

    elif files_without_schema_field > 0:
        status = "warn"
        hint = f"{files_without_schema_field}/{files_found} file(s) missing schema_version field. Assuming schema_version: 1 for those per ADR-027 fallback."
        numeric_yours.add(1)

    elif any(y < supported_from for y in numeric_yours):
        status = "error"
        worst = min(numeric_yours)
        hint = (f"schema v{worst} is now beyond the N+3 deprecation window — page is READ-ONLY.\n"
                f"  → Recovery options:\n"
                f"    (a) Restore from snapshot at ${{CLAUDE_PLUGIN_DATA}}/wiki-snapshots/ and step-migrate via /sf:update\n"
                f"    (b) Edit the file(s) manually to schema v{current} (see docs/RECOVERY.md 'Schema beyond deprecation')\n"
                f"    (c) Discard if not valuable")
    elif any(y < current for y in numeric_yours):
        status = "warn"
        worst = min(numeric_yours)
        hint = f"migration available (v{worst} → v{current}) — Run /sf:update to apply (see CHANGELOG for schema changes)"
    elif deprecated_below is not None and any(y < deprecated_below for y in numeric_yours):
        status = "warn"
        hint = "schema approaches deprecation — will become read-only in next MAJOR"

    if files_at_wrong_type > 0:
        status = "warn" if status == "ok" else status
        hint = (hint + " | " if hint else "") + f"{files_at_wrong_type} file(s) have `type:` mismatching registered page-type"

    # Value column for human display
    if numeric_yours:
        if len(numeric_yours) == 1:
            yours_display = str(next(iter(numeric_yours)))
        else:
            yours_display = f"mixed ({sorted(numeric_yours)})"
    else:
        yours_display = "?"

    # File count annotation for project-* etc
    if pt.startswith("project-") or pt in ("research", "decision", "pattern", "skill"):
        names = []
        for fp in files:
            if pt.startswith("project-"):
                names.append(os.path.basename(os.path.dirname(fp)))
            elif pt == "skill":
                names.append(os.path.basename(os.path.dirname(fp)))
            else:
                names.append(os.path.splitext(os.path.basename(fp))[0])
        annotation = f"({files_found} files: {', '.join(sorted(set(names))[:6])}{'...' if files_found > 6 else ''})"

    emit(pt, status, annotation, hint, str(files_found), str(current), yours_display, str(supported_from))

PYEOF
