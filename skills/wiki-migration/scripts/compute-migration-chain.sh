#!/usr/bin/env bash
# compute-migration-chain.sh — given current page schemas + target framework version,
# compute the per-page-type chain of migrations to apply.
#
# Usage:
#   compute-migration-chain.sh <schemas.json path>
#     Reads page schema_versions from $SF_WIKI_ROOT by walking the file glob
#     patterns declared in schemas.json#page_types[*].path_pattern.
#     Outputs JSON to stdout:
#
#     {
#       "framework_target": "1.3.0",
#       "page_types": {
#         "identity": {
#           "current_schema": 3,
#           "your_schema": 1,
#           "chain": ["1-to-2", "2-to-3"],
#           "page_count": 1
#         },
#         ...
#       }
#     }
#
# Exit codes: 0 on success, 1 if any page is beyond deprecation (read-only), 2 on bad input.

set -uo pipefail

SCHEMAS_JSON="${1:-}"
if [[ -z "$SCHEMAS_JSON" || ! -f "$SCHEMAS_JSON" ]]; then
  echo "ERROR: usage: compute-migration-chain.sh <schemas.json>" >&2
  exit 2
fi

WIKI_ROOT="${SF_WIKI_ROOT:-${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}}"

if [[ ! -d "$WIKI_ROOT" ]]; then
  echo "ERROR: wiki root not found: $WIKI_ROOT" >&2
  exit 2
fi

exec python3 - "$SCHEMAS_JSON" "$WIKI_ROOT" <<'PYEOF'
import json, os, sys, re, glob

schemas_path, wiki_root = sys.argv[1], sys.argv[2]

with open(schemas_path) as f:
    registry = json.load(f)

frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def parse_frontmatter(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(8192)
    except OSError:
        return None
    m = frontmatter_re.match(text)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm

def files_for(pt):
    if pt == "identity":
        p = os.path.join(wiki_root, "identity.md")
        return [p] if os.path.isfile(p) else []
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
        p = os.path.join(wiki_root, "log.md")
        return [p] if os.path.isfile(p) else []
    if pt == "project-log-entry":
        return glob.glob(os.path.join(wiki_root, "projects", "*", "log.md"))
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

result = {"framework_target": registry["framework_version"], "page_types": {}}
any_beyond_deprecation = False

for pt, meta in registry["page_types"].items():
    files = files_for(pt)
    if not files:
        continue  # nothing to migrate

    current = meta["current"]
    supported_from = meta["supported_from"]
    available_migrations = meta["migrations"]  # ordered: e.g. ["1-to-2", "2-to-3"]

    # Collect per-file schemas (or assume 1 per ADR-027 fallback if absent)
    file_schemas = {}
    for fp in files:
        fm = parse_frontmatter(fp)
        if not fm:
            file_schemas[fp] = None
            continue
        sv = fm.get("schema_version")
        if sv is None:
            file_schemas[fp] = 1  # ADR-027 fallback
            continue
        try:
            file_schemas[fp] = int(sv)
        except (TypeError, ValueError):
            file_schemas[fp] = None

    # Group: which schema versions need which migration chains?
    # We compute the chain per starting-schema value.
    needed_by_start = {}
    for fp, start in file_schemas.items():
        if start is None or start == current:
            continue
        if start < supported_from:
            any_beyond_deprecation = True
            needed_by_start.setdefault("_beyond_deprecation", []).append(fp)
            continue
        if start > current:
            # Future schema — shouldn't happen unless friend hand-edited
            needed_by_start.setdefault("_future_schema", []).append(fp)
            continue
        # Build chain: from start to current, picking migrations sequentially
        chain = []
        v = start
        while v < current:
            mig_id = f"{v}-to-{v+1}"
            if mig_id not in available_migrations:
                # Gap in registry — this is a framework bug; we don't know how to bridge.
                chain = None
                break
            chain.append(mig_id)
            v += 1
        if chain is None:
            needed_by_start.setdefault("_chain_gap", []).append(fp)
        else:
            key = f"from_{start}"
            entry = needed_by_start.setdefault(key, {"chain": chain, "files": []})
            entry["files"].append(fp)

    if needed_by_start:
        result["page_types"][pt] = {
            "current_schema": current,
            "supported_from": supported_from,
            "page_count": len(files),
            "by_start_schema": needed_by_start
        }

print(json.dumps(result, indent=2))
sys.exit(1 if any_beyond_deprecation else 0)
PYEOF
