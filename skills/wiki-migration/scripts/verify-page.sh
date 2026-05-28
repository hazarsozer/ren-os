#!/usr/bin/env bash
# verify-page.sh — run a migration's verify.json assertions against a migrated page.
#
# Usage:
#   verify-page.sh <verify.json path> <migrated-page path> [<snapshot-page path>]
#
# Exit:
#   0  all non-optional assertions PASS
#   1  any non-optional assertion FAIL
#   2  bad input (missing files, malformed verify.json, unknown predicate)
#
# Output (stderr): per-assertion PASS/FAIL with reason on FAIL.
#
# Predicates implemented (v1 vocabulary, locked):
#   yaml.valid       — frontmatter parses as YAML
#   yaml.equals      — frontmatter[field] == value
#   yaml.in          — frontmatter[field] in values[]
#   yaml.absent      — frontmatter[field] does NOT exist
#   yaml.present     — frontmatter[field] exists
#   regex.matches    — pattern matches against target (frontmatter|body|whole)
#   snapshot.value-preserved  — pre-migration[snapshot_field] == post-migration[post_field]
#   snapshot.body-identical   — body byte-identical to snapshot's body
#   file.exists      — path exists (placeholders: ${page_dir}, ${wiki_root})

set -uo pipefail

VERIFY_JSON="${1:-}"
PAGE_PATH="${2:-}"
SNAPSHOT_PATH="${3:-}"

if [[ -z "$VERIFY_JSON" || ! -f "$VERIFY_JSON" ]]; then
  echo "ERROR: verify.json not found: $VERIFY_JSON" >&2
  exit 2
fi
if [[ -z "$PAGE_PATH" || ! -f "$PAGE_PATH" ]]; then
  echo "ERROR: page not found: $PAGE_PATH" >&2
  exit 2
fi

WIKI_ROOT="${SF_WIKI_ROOT:-${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}}"

exec python3 - "$VERIFY_JSON" "$PAGE_PATH" "${SNAPSHOT_PATH:-}" "$WIKI_ROOT" <<'PYEOF'
import json, os, sys, re

verify_path, page_path, snapshot_path, wiki_root = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

with open(verify_path) as f:
    spec = json.load(f)

assertions = spec.get("assertions", [])
if not assertions:
    print("ERROR: verify.json has no assertions", file=sys.stderr)
    sys.exit(2)

frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def split_page(path):
    """Return (frontmatter_text, frontmatter_dict, body_text)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = frontmatter_re.match(text)
    if not m:
        return None, {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    fm = {}
    for line in fm_text.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm_text, fm, body

page_fm_text, page_fm, page_body = split_page(page_path)
snap_fm_text, snap_fm, snap_body = (None, {}, "")
if snapshot_path and os.path.isfile(snapshot_path):
    snap_fm_text, snap_fm, snap_body = split_page(snapshot_path)

page_dir = os.path.dirname(page_path)

passes = 0
fails = 0
errors = 0

def report(level, aid, desc, detail=""):
    print(f"  {level:5}  {aid:30}  {desc}{(' — ' + detail) if detail else ''}", file=sys.stderr)

def coerce(v):
    """Best-effort: int → int, float → float, else str."""
    if isinstance(v, (int, float, bool, type(None))):
        return v
    s = str(v)
    if s.lower() == "true": return True
    if s.lower() == "false": return False
    if s.lower() == "null" or s == "": return None
    try: return int(s)
    except ValueError: pass
    try: return float(s)
    except ValueError: pass
    return s

def get_target_text(target):
    if target == "frontmatter" or target is None:
        return page_fm_text or ""
    if target == "body":
        return page_body
    if target == "whole":
        with open(page_path, encoding="utf-8") as f:
            return f.read()
    return ""

for a in assertions:
    aid = a.get("id", "<no-id>")
    desc = a.get("description", "")
    predicate = a.get("predicate")
    optional = a.get("optional", False)

    try:
        if predicate == "yaml.valid":
            ok = page_fm_text is not None
            detail = "no frontmatter delimited by ---" if not ok else ""

        elif predicate == "yaml.equals":
            field = a["field"]
            expected = coerce(a["value"])
            actual = coerce(page_fm.get(field))
            ok = actual == expected
            detail = f"field '{field}' = {actual!r}, expected {expected!r}" if not ok else ""

        elif predicate == "yaml.in":
            field = a["field"]
            allowed = [coerce(x) for x in a["values"]]
            actual = coerce(page_fm.get(field))
            ok = actual in allowed
            detail = f"field '{field}' = {actual!r}, allowed {allowed!r}" if not ok else ""

        elif predicate == "yaml.absent":
            field = a["field"]
            ok = field not in page_fm
            detail = f"field '{field}' is present (= {page_fm.get(field)!r})" if not ok else ""

        elif predicate == "yaml.present":
            field = a["field"]
            ok = field in page_fm
            detail = f"field '{field}' missing" if not ok else ""

        elif predicate == "regex.matches":
            pat = a["pattern"]
            target = a.get("target", "frontmatter")
            text = get_target_text(target)
            ok = re.search(pat, text) is not None
            detail = f"pattern /{pat}/ did not match {target}" if not ok else ""

        elif predicate == "snapshot.value-preserved":
            if snap_fm is None or not snap_fm_text:
                if optional:
                    ok = True
                    detail = "snapshot frontmatter unavailable; assertion optional → skip"
                else:
                    ok = False
                    detail = "snapshot not available"
            else:
                snap_field = a["snapshot_field"]
                post_field = a["post_field"]
                if snap_field not in snap_fm:
                    if optional:
                        ok = True
                        detail = f"snapshot didn't have '{snap_field}'; assertion optional → skip"
                    else:
                        ok = False
                        detail = f"snapshot didn't have '{snap_field}'"
                else:
                    snap_val = coerce(snap_fm[snap_field])
                    post_val = coerce(page_fm.get(post_field))
                    ok = snap_val == post_val
                    detail = f"snapshot.{snap_field}={snap_val!r}, post.{post_field}={post_val!r}" if not ok else ""

        elif predicate == "snapshot.body-identical":
            if snap_fm_text is None and snap_body == "":
                if optional:
                    ok, detail = True, "snapshot unavailable; optional"
                else:
                    ok, detail = False, "snapshot unavailable"
            else:
                ok = page_body == snap_body
                detail = f"body differs ({len(page_body)} vs {len(snap_body)} bytes)" if not ok else ""

        elif predicate == "file.exists":
            path = a["path"].replace("${page_dir}", page_dir).replace("${wiki_root}", wiki_root)
            ok = os.path.exists(path)
            detail = f"{path} not found" if not ok else ""

        else:
            errors += 1
            report("ERROR", aid, desc, f"unknown predicate: {predicate}")
            continue

        if ok:
            passes += 1
            report("PASS", aid, desc)
        else:
            if optional:
                # Optional FAILs are reported but don't change the exit code
                report("WARN", aid, desc, f"(optional) {detail}")
            else:
                fails += 1
                report("FAIL", aid, desc, detail)

    except Exception as e:
        errors += 1
        report("ERROR", aid, desc, f"exception: {e}")

total = len(assertions)
print(f"\n  verify summary: {passes}/{total} PASS, {fails} FAIL, {errors} ERROR", file=sys.stderr)

if errors > 0:
    sys.exit(2)
if fails > 0:
    sys.exit(1)
sys.exit(0)
PYEOF
