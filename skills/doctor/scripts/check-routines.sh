#!/usr/bin/env bash
# check-routines.sh — sf-doctor ROUTINES section (ADR-034)
#
# Output: `KEY|STATUS|VALUE|HINT`
# Keys: routines (skip), routine-net / routine-net:<name> (network-tier audit),
#       routine-quota (defined cron routines vs plan cap).
#
# Side effects: NONE. Reads wiki/routines/*.md frontmatter.
# Plan tier: SF_PLAN_TIER (pro|max|team|enterprise); defaults to max.
set -uo pipefail
emit() { printf '%s|%s|%s|%s\n' "$1" "$2" "${3:-}" "${4:-}"; }

WIKI_ROOT="${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}"
ROUTINES_DIR="$WIKI_ROOT/routines"
PLAN_TIER="$(printf '%s' "${SF_PLAN_TIER:-max}" | tr '[:upper:]' '[:lower:]')"

if [[ ! -d "$ROUTINES_DIR" ]]; then
  emit "routines" "skip" "no routines defined" "→ /ren:routine-init scaffolds a cadence routine (ADR-034)"
  exit 0
fi

exec python3 - "$ROUTINES_DIR" "$PLAN_TIER" <<'PYEOF'
import os, sys, re, glob

routines_dir, plan_tier = sys.argv[1], sys.argv[2]
CAPS = {"pro": 5, "max": 15, "team": 25, "enterprise": 25}
cap = CAPS.get(plan_tier, 15)

frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def parse_fm(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(8192)  # frontmatter is at the top; 8K is plenty
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

def emit(key, status, value="", hint=""):
    print(f"{key}|{status}|{value}|{hint}")

specs = []
for fp in sorted(glob.glob(os.path.join(routines_dir, "*.md"))):
    fm = parse_fm(fp)
    if fm.get("type") != "routine-spec":
        continue
    specs.append((os.path.splitext(os.path.basename(fp))[0], fm))

if not specs:
    emit("routines", "skip", "no routine-spec pages", "→ /ren:routine-init scaffolds one")
    sys.exit(0)

# Network-tier audit — flag any routine on the 'full' (unrestricted egress) tier.
full_tier = [name for name, fm in specs if fm.get("network_tier", "trusted") == "full"]
if full_tier:
    for name in full_tier:
        emit(f"routine-net:{name}", "warn", "network tier = full",
             "→ 'full' = unrestricted egress = a prompt-injection exfiltration surface. "
             "Prefer 'trusted' (Anthropic allowlist) unless this routine genuinely needs arbitrary domains.")
else:
    emit("routine-net", "ok", f"{len(specs)} routine(s), none on 'full' tier", "")

# Quota / headroom audit — counts DEFINED cron routines (not live runs) vs the plan cap.
scheduled = [name for name, fm in specs if fm.get("trigger_type", "") == "cron"]
used = len(scheduled)
if used >= cap:
    emit("routine-quota", "warn", f"{used}/{cap} scheduled ({plan_tier} cap)",
         f"→ at/over the {plan_tier} cap of {cap} scheduled routines/day; consolidate or upgrade. "
         "(Counts DEFINED cron routines, not live runs consumed today.)")
else:
    emit("routine-quota", "ok", f"{used}/{cap} scheduled ({plan_tier} cap)",
         "(Counts defined cron routines — not live runs consumed today.)")
PYEOF
