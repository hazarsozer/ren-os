#!/usr/bin/env bash
# check-context.sh — sf-doctor CONTEXT & TOKEN ECONOMICS section. READ-ONLY.
# Output: KEY|STATUS|VALUE|HINT  (STATUS ∈ ok|warn|skip)
set -uo pipefail
PLUGIN_DIR="${SF_PLUGIN_DIR:-${CLAUDE_PLUGIN_ROOT:-.}}"
PROJECT_CLAUDE_MD="${CLAUDE_PROJECT_CLAUDE_MD:-./CLAUDE.md}"
exec python3 - "$PLUGIN_DIR" "$HOME" "$PROJECT_CLAUDE_MD" <<'PYEOF'
import json, os, re, sys, glob
plugin_dir, home, project_md = sys.argv[1], sys.argv[2], sys.argv[3]
SKILL_LINE_WARN, CLAUDE_MD_LINE_WARN = 500, 200
REQUIRED_FM = ("name", "description", "version")
def emit(k, s, v="", h=""): print(f"{k}|{s}|{v}|{h}")
def linecount(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f: return sum(1 for _ in f)
    except OSError: return None
def parse_fm(p):
    try:
        with open(p, encoding="utf-8") as f: t = f.read(8192)
    except OSError: return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", t, re.DOTALL)
    if not m: return {}
    fm = {}
    for ln in m.group(1).splitlines():
        if ":" in ln and not ln.lstrip().startswith("#"):
            k, _, v = ln.partition(":"); fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm

# ── MCP servers + enabled plugins (from ~/.claude.json) ──
cj = os.path.join(home, ".claude.json"); mcp = plugins = None
if os.path.isfile(cj):
    try:
        d = json.load(open(cj)); mcp = len(d.get("mcpServers", {})); plugins = len(d.get("enabledPlugins", {}))
    except Exception: pass
emit("mcp_servers", "ok" if mcp is not None else "skip", mcp if mcp is not None else "(no ~/.claude.json)",
     "keys ≠ instructions — audit with /ren:doctor --permissions" if mcp else "")
emit("enabled_plugins", "ok" if plugins is not None else "skip", plugins if plugins is not None else "")

# ── framework skills + skill-size lint ──
skill_mds = sorted(glob.glob(os.path.join(plugin_dir, "skills", "*", "SKILL.md")))
emit("framework_skills", "ok" if skill_mds else "skip", len(skill_mds))
offenders = []
for p in skill_mds:
    name = os.path.basename(os.path.dirname(p)); lc = linecount(p) or 0; fm = parse_fm(p)
    missing = [k for k in REQUIRED_FM if not fm.get(k)]
    if lc > SKILL_LINE_WARN: offenders.append(f"{name}:{lc}L")
    if missing: offenders.append(f"{name}:missing[{','.join(missing)}]")
emit("skill_size_lint", "warn" if offenders else "ok",
     ", ".join(offenders[:8]) if offenders else "all skills < %dL + complete frontmatter" % SKILL_LINE_WARN,
     "trim or split oversized skills; complete YAML frontmatter" if offenders else "")

# ── CLAUDE.md sizes (loaded every session) ──
for key, path in (("claude_md_global", os.path.join(home, ".claude", "CLAUDE.md")),
                  ("claude_md_project", project_md)):
    lc = linecount(path)
    if lc is None: emit(key, "skip", "(none)")
    elif lc > CLAUDE_MD_LINE_WARN: emit(key, "warn", f"{lc} lines", "token-heavy; loaded every session — trim or move detail into skills")
    else: emit(key, "ok", f"{lc} lines")

# ── auto-mode safety posture ──
settings = os.path.join(home, ".claude", "settings.json"); mode = None
if os.path.isfile(settings):
    try: mode = (json.load(open(settings)).get("permissions", {}) or {}).get("defaultMode")
    except Exception: pass
if mode in ("bypassPermissions", "acceptEdits"):
    emit("auto_mode", "warn", mode, "broad auto-accept is the default — confirms are skipped; scope keys deliberately")
else:
    emit("auto_mode", "ok", mode or "default", "")
PYEOF
