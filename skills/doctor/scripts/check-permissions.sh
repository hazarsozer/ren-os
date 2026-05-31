#!/usr/bin/env bash
# check-permissions.sh — sf-doctor PERMISSION AUDIT ("/sf:doctor --permissions")
#
# Unlike the four KEY|STATUS|VALUE|HINT section scripts, this emits a SELF-CONTAINED
# human-readable "KEYS ON YOUR RING" report. It is a standalone, on-demand audit
# surface (not one of the always-on doctor sections), so it owns its own framing.
#
# What it reports (all read-only):
#   - MCP servers by NAME + TRANSPORT (stdio/http/sse), with granted tool-key counts
#     (global ~/.claude.json#mcpServers + per-project projects.*.mcpServers)
#   - permissions.{allow,deny,ask} tallied by tool prefix
#   - BROAD GRANTS flagged (bare `Bash`, wildcard MCP like `mcp__*`)
#   - enabledPlugins (a DICT keyed by "<plugin>@<marketplace>")
#   - configured hooks (by event name)
#
# Framing: "keys != instructions" — granting a tool hands Claude a key; it does NOT
# tell Claude to use it. This audit lists the keys on the ring, nothing more.
#
# Side effects: NONE. No writes, no network.
# SECURITY: config files are mode 0600 and contain secrets (mcpServers.*.env values,
#   oauth/userID, http headers). This script reads STRUCTURE ONLY — it prints server
#   names, transports, rule counts, and tool prefixes. It NEVER prints any env value,
#   header value, command, arg, or token. (See test_check_permissions.sh: a seeded
#   fake token is asserted ABSENT from the output.)
# Requires: python3 (JSON parsing — bash is unsafe for arbitrary nested config).

set -uo pipefail

# Input sources. Honor explicit overrides (used by the hermetic test + power users);
# otherwise resolve under $HOME. Absence of any file is tolerated downstream.
CLAUDE_JSON="${SF_CLAUDE_JSON:-${HOME}/.claude.json}"
SETTINGS_JSON="${SF_SETTINGS_JSON:-${HOME}/.claude/settings.json}"
SETTINGS_LOCAL_JSON="${SF_SETTINGS_LOCAL_JSON:-${HOME}/.claude/settings.local.json}"

exec python3 - "$CLAUDE_JSON" "$SETTINGS_JSON" "$SETTINGS_LOCAL_JSON" <<'PYEOF'
import json
import os
import sys

claude_json_path, settings_path, settings_local_path = sys.argv[1], sys.argv[2], sys.argv[3]


def load(path):
    """Load a JSON object tolerantly. Missing / unreadable / malformed -> {}."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def transport_of(cfg):
    """Classify an MCP server entry as stdio / http / sse / unknown.

    Never inspects values that could be secret — only key presence + the `type` tag.
    """
    if not isinstance(cfg, dict):
        return "unknown"
    declared = cfg.get("type")
    if isinstance(declared, str) and declared.lower() in ("stdio", "http", "sse"):
        return declared.lower()
    if "command" in cfg:
        return "stdio"
    if "url" in cfg:
        return "http"  # http vs sse is indistinguishable without the (secret-bearing) value
    return "unknown"


def prefix_of(rule):
    """Tool prefix of a `Tool(arg)` / `mcp__server__tool` permission rule.

    `Bash(git *)` -> `Bash`;  `mcp__resend__send-email` -> `mcp__resend`;  `Read` -> `Read`.
    """
    if not isinstance(rule, str):
        return "?"
    head = rule.split("(", 1)[0].strip()
    if head.startswith("mcp__"):
        parts = head.split("__")
        if len(parts) >= 3 and parts[2] not in ("", "*"):
            return "mcp__" + parts[1]  # server-scoped grouping
        if len(parts) >= 2 and parts[1] not in ("", "*"):
            return "mcp__" + parts[1]
        return "mcp__*"
    return head or "?"


def is_bare_bash(rule):
    return isinstance(rule, str) and rule.strip() in ("Bash", "Bash()", "Bash(*)", "Bash(:*)")


def is_global_mcp_wildcard(rule):
    return isinstance(rule, str) and rule.strip() in ("mcp__*", "mcp__")


def mcp_server_of(rule):
    """Return (server, is_server_wildcard) for an `mcp__server__...` rule, else (None, False)."""
    if not isinstance(rule, str):
        return None, False
    head = rule.split("(", 1)[0].strip()
    if not head.startswith("mcp__"):
        return None, False
    parts = head.split("__")
    if len(parts) < 2 or parts[1] in ("", "*"):
        return None, False
    server = parts[1]
    is_wild = len(parts) >= 3 and parts[2] == "*"
    return server, is_wild


def tally_prefixes(rules):
    counts = {}
    for r in rules:
        p = prefix_of(r)
        counts[p] = counts.get(p, 0) + 1
    return counts


def fmt_tally(counts):
    if not counts:
        return ""
    return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))


# ── Load all sources ─────────────────────────────────────────────────
claude = load(claude_json_path)
settings = load(settings_path)
settings_local = load(settings_local_path)

out = []
W = out.append

# Collect every allow-list rule (global settings + local override) so MCP grant
# counts and broad-grant flags see the whole picture.
def perms_of(blob):
    p = blob.get("permissions") if isinstance(blob.get("permissions"), dict) else {}
    allow = p.get("allow") if isinstance(p.get("allow"), list) else []
    deny = p.get("deny") if isinstance(p.get("deny"), list) else []
    ask = p.get("ask") if isinstance(p.get("ask"), list) else []
    return allow, deny, ask


g_allow, g_deny, g_ask = perms_of(settings)
l_allow, l_deny, l_ask = perms_of(settings_local)

projects = claude.get("projects") if isinstance(claude.get("projects"), dict) else {}
# Per-project allowedTools also grant MCP keys.
project_allow = []
for cfg in projects.values():
    if isinstance(cfg, dict) and isinstance(cfg.get("allowedTools"), list):
        project_allow.extend(cfg["allowedTools"])

all_allow = list(g_allow) + list(l_allow) + project_allow

# Global wildcard short-circuits every server's key count.
global_mcp_wildcard = any(is_global_mcp_wildcard(r) for r in all_allow)

# Per-server granted-tool-key counts + server wildcards from the allow rules.
server_grant_count = {}
server_wildcard = set()
for r in all_allow:
    server, is_wild = mcp_server_of(r)
    if server is None:
        continue
    if is_wild:
        server_wildcard.add(server)
    else:
        server_grant_count[server] = server_grant_count.get(server, 0) + 1


def grant_note(name):
    if global_mcp_wildcard:
        return "ALL tools (via mcp__* wildcard)"
    if name in server_wildcard:
        return f"ALL tools (via mcp__{name}__* wildcard)"
    n = server_grant_count.get(name, 0)
    if n == 0:
        return "0 tool-key(s) granted  (no explicit grants; gated by approval prompts)"
    return f"{n} tool-key(s) granted"


# ── Header ───────────────────────────────────────────────────────────
W("==================================================================")
W("  KEYS ON YOUR RING  -  permission audit  (read-only)")
W("==================================================================")
W("")
W("  Keys != instructions. Granting a tool hands Claude a key; it does")
W("  NOT tell Claude to use it. This audit lists the keys on your ring,")
W("  not what Claude will do with them.")
W("")
W("  Read-only: server names, transports, rule counts, and tool prefixes")
W("  only. No secret / env / token / header values are read or printed.")
W("")

# ── MCP servers (global) ─────────────────────────────────────────────
W("> MCP SERVERS (global)   ~/.claude.json : mcpServers")
g_mcp = claude.get("mcpServers") if isinstance(claude.get("mcpServers"), dict) else {}
if not g_mcp:
    W("    (none configured globally)")
else:
    for name in sorted(g_mcp):
        tr = transport_of(g_mcp[name])
        W(f"    {name:<22} {tr:<7} {grant_note(name)}")
    W(f"    -- {len(g_mcp)} server(s) configured globally")
W("")

# ── MCP servers (per-project) ────────────────────────────────────────
W("> MCP SERVERS (per-project)   ~/.claude.json : projects.*.mcpServers")
proj_with_mcp = []
for path, cfg in projects.items():
    if isinstance(cfg, dict) and isinstance(cfg.get("mcpServers"), dict) and cfg["mcpServers"]:
        proj_with_mcp.append((path, cfg["mcpServers"]))
if not proj_with_mcp:
    W(f"    (no project-scoped MCP servers in {len(projects)} project(s))")
else:
    for path, servers in proj_with_mcp:
        label = os.path.basename(path.rstrip("/")) or "(root)"
        for name in sorted(servers):
            tr = transport_of(servers[name])
            W(f"    {label}: {name} ({tr}) {grant_note(name)}")
    W(f"    -- scanned {len(projects)} project(s); {len(proj_with_mcp)} with project-scoped server(s)")
W("")

# ── Permission rules tally ───────────────────────────────────────────
W("> PERMISSION RULES   ~/.claude/settings.json : permissions.{allow,deny,ask}")
W(f"    allow: {len(g_allow)} rule(s)   {fmt_tally(tally_prefixes(g_allow))}".rstrip())
W(f"    deny:  {len(g_deny)} rule(s)   {fmt_tally(tally_prefixes(g_deny))}".rstrip())
W(f"    ask:   {len(g_ask)} rule(s)   {fmt_tally(tally_prefixes(g_ask))}".rstrip())
if settings_local:
    W(f"    settings.local.json overlay: allow {len(l_allow)}, deny {len(l_deny)}, ask {len(l_ask)}")
if project_allow:
    W(f"    per-project allowedTools: {len(project_allow)} rule(s) across {len(projects)} project(s)")
W("")

# ── Broad grants ─────────────────────────────────────────────────────
W("> BROAD GRANTS   wide-open keys worth a second look")
flags = []
# Bare Bash / global MCP wildcard, attributed to the list they came from.
for label, rules in (("allow", g_allow), ("allow:local", l_allow), ("allow:project", project_allow)):
    for r in rules:
        if is_bare_bash(r):
            flags.append((f"BROAD GRANT ({label})",
                          "bare `Bash` grants EVERY shell command (no argument filter)",
                          "-> scope it, e.g. Bash(git *), Bash(npm run *)"))
        elif is_global_mcp_wildcard(r):
            flags.append((f"BROAD GRANT ({label})",
                          "`mcp__*` grants EVERY tool on EVERY MCP server",
                          "-> grant per server/tool, e.g. mcp__resend__send-email"))
# Server-scoped wildcards are noted (lower severity).
for name in sorted(server_wildcard):
    flags.append(("NOTE",
                  f"`mcp__{name}__*` grants every tool on the '{name}' server",
                  "-> fine if intentional; tighten to specific tools if not"))
if not flags:
    W("    (none found -- no bare Bash, no wildcard MCP grants)")
else:
    for head, body, hint in flags:
        W(f"    {head}: {body}")
        W(f"        {hint}")
W("")

# ── Enabled plugins ──────────────────────────────────────────────────
W("> ENABLED PLUGINS   ~/.claude/settings.json : enabledPlugins")
enabled = settings.get("enabledPlugins")
if isinstance(enabled, dict) and enabled:
    for key in sorted(enabled):
        W(f"    {key}")
    W(f"    -- {len(enabled)} enabled")
else:
    W("    (none enabled)")
W("")

# ── Hooks ────────────────────────────────────────────────────────────
W("> HOOKS   ~/.claude/settings.json : hooks")
hooks = settings.get("hooks")
if isinstance(hooks, dict) and hooks:
    W(f"    events: {', '.join(hooks.keys())}")
    W(f"    -- {len(hooks)} event(s) wired")
else:
    W("    (no hooks configured)")
W("")

# ── Footer ───────────────────────────────────────────────────────────
W("------------------------------------------------------------------")
W("  Nothing was modified (read-only). Keys != instructions --")
W("  audit your ring now and then, and revoke keys you don't recognize.")

print("\n".join(out))
PYEOF
