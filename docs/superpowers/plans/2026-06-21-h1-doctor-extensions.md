# H1 — Doctor Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `/ren:doctor` with two new read-only sections — **CONTEXT & TOKEN ECONOMICS** (skill-size lint + context-budget counts + auto-mode safety posture) and **WIKI HEALTH** (dead links + stale pages + token-heavy pages + a health score) — taking the report from seven sections to nine.

**Architecture:** Two new check-scripts (`check-context.sh`, `check-wiki-health.sh`) follow the established doctor pattern exactly — a `bash` wrapper that `exec`s an embedded `python3` heredoc for all parsing, emitting `KEY|STATUS|VALUE|HINT` pipe-delimited fragments to stdout, strictly read-only and side-effect-free. The `SKILL.md` body (the LLM renderer + parallel-fanout orchestrator) gains two render sections; `reference.md` gains the format + `--json` schema entries; `eval/eval.json` gains binary assertions. No new ADRs, no new page-types, no schema changes.

**Tech Stack:** Bash + embedded `python3` (stdlib only — `json`, `os`, `re`, `glob`, `datetime`). Hermetic shell tests in the existing `scripts/tests/test_check_*.sh` style.

## Global Constraints

- **Doctor is READ-ONLY and side-effect-free.** New scripts MUST NOT write, create, or delete anything (`contract.permissions.write: []`, `files_written: 0`). No network calls.
- **Per-script budget:** each check runs under a **10s** orchestrator timeout and the whole report under **60s**. Read frontmatter only (cap reads at 8192 bytes/file, like `check-schemas.sh`); never load whole wikis into memory.
- **Pattern fidelity:** mirror `skills/doctor/scripts/check-schemas.sh` (bash→`python3` heredoc, `emit()` helper, env-var inputs, `_error` fragment + `exit 1` on missing critical inputs) and `check-env.sh` (hermetic test style).
- **Tolerate all absence:** missing wiki, missing CLAUDE.md, missing `~/.claude.json`, empty config — render a clean fragment and **exit 0** (never crash the report). Only a genuinely-broken plugin install (`schemas.json` absent etc.) may `_error`.
- **CI gates that apply:** `bash -n` on every `.sh` (must pass), `shellcheck --severity=warning` (keep clean), `claude plugin validate ./ --strict`. The python embedded in `.sh` is not separately linted but must be correct.
- **Inputs (env), matching existing scripts:** `WIKI_ROOT` ← `CLAUDE_PLUGIN_OPTION_WIKIROOT` (default `$HOME/.startup-framework/wiki`); plugin dir ← `SF_PLUGIN_DIR`/`CLAUDE_PLUGIN_ROOT`. Tests override these to point at fixtures.
- **Naming:** sections render as `▶ CONTEXT & TOKEN ECONOMICS` and `▶ WIKI HEALTH`. Keep `/ren:` command spelling everywhere.

---

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `skills/doctor/scripts/check-context.sh` | **Create** | Emits CONTEXT & TOKEN ECONOMICS fragments: MCP-server count, enabled-plugin count, framework-skill count, global+project `CLAUDE.md` size, skill-size lint, auto-mode safety posture. |
| `skills/doctor/scripts/check-wiki-health.sh` | **Create** | Emits WIKI HEALTH fragments: dead links, stale pages, token-heavy pages, and an aggregate health score. |
| `skills/doctor/scripts/tests/test_check_context.sh` | **Create** | Hermetic fixtures + assertions for `check-context.sh`. |
| `skills/doctor/scripts/tests/test_check_wiki_health.sh` | **Create** | Hermetic fixtures + assertions for `check-wiki-health.sh`. |
| `skills/doctor/SKILL.md` | **Modify** | Seven→nine sections everywhere (description, contract, flags, fan-out table, output example, `--section`, permissions.execute, eval list). Add render instructions for the two new sections. |
| `skills/doctor/reference.md` | **Modify** | Add format spec + `--json` schema entries for the two new sections. |
| `skills/doctor/eval/eval.json` | **Modify** | Add binary assertions for the two new sections. |
| `CHANGELOG.md`, `wiki/log.md`, `wiki/index.md`, `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md` | **Modify** | Wire-up (Task 4). |

**Scope cuts (documented, intentional — simplicity-first):** the spec lists "stable-ID-rehydration flag" and "MCP-vs-CLI" under doctor extensions. Both require heuristic static analysis of skill bodies (detecting repeated MCP discovery calls) that is speculative and high-false-positive; they are **explicitly deferred** to a future H-slice and noted in `reference.md` § Deferred. "Network tiers" is already covered by the existing ROUTINES section — not duplicated here.

---

## Task 1: `check-context.sh` — CONTEXT & TOKEN ECONOMICS

**Files:**
- Create: `skills/doctor/scripts/check-context.sh`
- Test: `skills/doctor/scripts/tests/test_check_context.sh`

**Interfaces:**
- Consumes (env): `SF_PLUGIN_DIR`/`CLAUDE_PLUGIN_ROOT` (framework root, for skill enumeration), `HOME` (for `~/.claude.json`, `~/.claude/settings.json`, `~/.claude/CLAUDE.md`), `CLAUDE_PROJECT_CLAUDE_MD` (optional override of the project `CLAUDE.md` path; default `./CLAUDE.md`).
- Produces: stdout fragments `KEY|STATUS|VALUE|HINT`, one per line. STATUS ∈ `ok|warn|skip|error`. Keys: `mcp_servers`, `enabled_plugins`, `framework_skills`, `claude_md_global`, `claude_md_project`, `skill_size_lint`, `auto_mode`. Exit 0 always (no `_error` case — every input is optional).

**Thresholds (constants at top of the python block):** `SKILL_LINE_WARN = 500`, `CLAUDE_MD_LINE_WARN = 200`, `REQUIRED_FM = ("name", "description", "version")`.

- [ ] **Step 1: Write the failing test**

Create `skills/doctor/scripts/tests/test_check_context.sh` (mirror `test_check_env.sh`'s harness):

```bash
#!/usr/bin/env bash
# test_check_context.sh — hermetic tests for the /ren:doctor CONTEXT & TOKEN ECONOMICS section.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$(cd "$SCRIPT_DIR/.." && pwd)/check-context.sh"
PASS=0; FAIL=0
pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }

# Fixture: a fake framework root with two skills — one oversized, one missing a frontmatter field.
FX="$(mktemp -d)"; trap 'rm -rf "$FX"' EXIT
mkdir -p "$FX/skills/big/" "$FX/skills/small/"
{ echo "---"; echo "name: big"; echo "description: x"; echo "version: 0.1.0"; echo "---"; \
  for i in $(seq 1 600); do echo "line $i"; done; } > "$FX/skills/big/SKILL.md"
{ echo "---"; echo "name: small"; echo "description: y"; echo "---"; echo body; } > "$FX/skills/small/SKILL.md"   # missing version
mkdir -p "$FX/home/.claude"
printf '%s\n' '{"mcpServers":{"resend":{},"canva":{}},"enabledPlugins":{"superpowers@x":true}}' > "$FX/home/.claude.json"
{ for i in $(seq 1 250); do echo "claude md line $i"; done; } > "$FX/home/.claude/CLAUDE.md"   # > 200 → token-heavy
printf '%s\n' '{"permissions":{"defaultMode":"bypassPermissions"}}' > "$FX/home/.claude/settings.json"

echo "▶ Scenario A — counts, lint, sizes, auto-mode"
OUT="$(SF_PLUGIN_DIR="$FX" HOME="$FX/home" CLAUDE_PROJECT_CLAUDE_MD="$FX/none/CLAUDE.md" bash "$CHECK" 2>&1)"; RC=$?
[ "$RC" = "0" ] && pass "exits 0" || fail "exit was $RC"
grep -q '^mcp_servers|ok|2' <<<"$OUT" && pass "counts 2 MCP servers" || fail "mcp_servers: $(grep '^mcp_servers' <<<"$OUT")"
grep -q '^framework_skills|ok|2' <<<"$OUT" && pass "counts 2 skills" || fail "framework_skills"
grep -Eq '^skill_size_lint\|warn\|' <<<"$OUT" && pass "lint warns (oversized + missing field)" || fail "skill_size_lint"
grep -q 'big' <<<"$OUT" && pass "names the oversized skill" || fail "no oversized skill name"
grep -Eq '^claude_md_global\|warn\|' <<<"$OUT" && pass "flags token-heavy global CLAUDE.md" || fail "claude_md_global"
grep -q '^claude_md_project|skip' <<<"$OUT" && pass "absent project CLAUDE.md → skip" || fail "claude_md_project"
grep -Eq '^auto_mode\|warn\|' <<<"$OUT" && pass "warns bypassPermissions default" || fail "auto_mode"

echo "▶ Scenario B — all absent → clean, exit 0"
EMPTY="$(mktemp -d)"; trap 'rm -rf "$FX" "$EMPTY"' EXIT
OUT2="$(SF_PLUGIN_DIR="$EMPTY" HOME="$EMPTY" CLAUDE_PROJECT_CLAUDE_MD="$EMPTY/none" bash "$CHECK" 2>&1)"; RC2=$?
[ "$RC2" = "0" ] && pass "exits 0 with empty env" || fail "empty exit $RC2"
grep -q '^auto_mode|ok' <<<"$OUT2" && pass "no settings → auto_mode ok (safe default)" || fail "auto_mode empty"

echo ""; echo "context: $PASS passed, $FAIL failed"; [ "$FAIL" = "0" ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash skills/doctor/scripts/tests/test_check_context.sh`
Expected: FAIL — `check-context.sh` does not exist yet (`bash: …/check-context.sh: No such file`).

- [ ] **Step 3: Write minimal implementation**

Create `skills/doctor/scripts/check-context.sh`. Use `check-schemas.sh` as the structural template (shebang, `set -uo pipefail`, `exec python3 - <<'PYEOF'`). Core logic:

```bash
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash skills/doctor/scripts/tests/test_check_context.sh`
Expected: PASS — `context: N passed, 0 failed`. Also run `bash -n skills/doctor/scripts/check-context.sh` (clean) and `shellcheck --severity=warning skills/doctor/scripts/check-context.sh` (clean).

- [ ] **Step 5: Commit**

```bash
git add skills/doctor/scripts/check-context.sh skills/doctor/scripts/tests/test_check_context.sh
git commit -m "feat(h1): add check-context.sh — CONTEXT & TOKEN ECONOMICS doctor section"
```

---

## Task 2: `check-wiki-health.sh` — WIKI HEALTH

**Files:**
- Create: `skills/doctor/scripts/check-wiki-health.sh`
- Test: `skills/doctor/scripts/tests/test_check_wiki_health.sh`

**Interfaces:**
- Consumes (env): `WIKI_ROOT` ← `CLAUDE_PLUGIN_OPTION_WIKIROOT` (default `$HOME/.startup-framework/wiki`); `DOCTOR_TODAY` (optional `YYYY-MM-DD` override for deterministic stale-date tests; default = system date).
- Produces: fragments `KEY|STATUS|VALUE|HINT`. Keys: `dead_links`, `stale_pages`, `heavy_pages`, `health_score`. If `WIKI_ROOT` is absent → single `health_score|skip|(no wiki)` + exit 0 (a friend may run doctor pre-install).

**Thresholds:** `STALE_DAYS = 90`, `PAGE_LINE_WARN = 500`.
**Link detection:** wikilinks `\[\[([^\]\|]+?)(\|[^\]]*)?\]\]` (strip any `|alias`), resolved by basename/slug against all `*.md` under `WIKI_ROOT`; relative markdown links `\]\(([^)]+?\.md)(#[^)]*)?\)` resolved against the containing file's dir. A link is **dead** if no target file exists. Ignore external `http(s)://` links.

- [ ] **Step 1: Write the failing test**

Create `skills/doctor/scripts/tests/test_check_wiki_health.sh`:

```bash
#!/usr/bin/env bash
# test_check_wiki_health.sh — hermetic tests for the /ren:doctor WIKI HEALTH section.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$(cd "$SCRIPT_DIR/.." && pwd)/check-wiki-health.sh"
PASS=0; FAIL=0
pass() { printf '\033[32m  ✓ PASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '\033[31m  ✗ FAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }

W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
mkdir -p "$W/research"
# index links to one existing + one missing page (dead wikilink)
printf '%s\n' '---' 'title: i' 'updated: 2099-01-01' '---' 'See [[real-page]] and [[ghost-page]].' > "$W/index.md"
printf '%s\n' '---' 'title: r' 'updated: 2099-01-01' '---' 'fresh' > "$W/research/real-page.md"
# a stale page (old updated) and a heavy page (>500 lines)
printf '%s\n' '---' 'title: s' 'updated: 2000-01-01' '---' 'old' > "$W/research/stale.md"
{ echo "---"; echo "title: h"; echo "updated: 2099-01-01"; echo "---"; for i in $(seq 1 600); do echo "L$i"; done; } > "$W/research/heavy.md"

echo "▶ Scenario A — one dead link, one stale, one heavy"
OUT="$(CLAUDE_PLUGIN_OPTION_WIKIROOT="$W" DOCTOR_TODAY="2099-06-01" bash "$CHECK" 2>&1)"; RC=$?
[ "$RC" = "0" ] && pass "exits 0" || fail "exit $RC"
grep -Eq '^dead_links\|warn\|1\b' <<<"$OUT" && pass "finds 1 dead link" || fail "dead_links: $(grep '^dead_links' <<<"$OUT")"
grep -q 'ghost-page' <<<"$OUT" && pass "names the dead target" || fail "no dead target name"
grep -Eq '^stale_pages\|warn\|1\b' <<<"$OUT" && pass "finds 1 stale page" || fail "stale_pages"
grep -Eq '^heavy_pages\|warn\|1\b' <<<"$OUT" && pass "finds 1 heavy page" || fail "heavy_pages"
grep -Eq '^health_score\|(warn|error)\|' <<<"$OUT" && pass "emits a score" || fail "health_score"

echo "▶ Scenario B — no wiki → skip, exit 0"
OUT2="$(CLAUDE_PLUGIN_OPTION_WIKIROOT="$W/nonexistent" bash "$CHECK" 2>&1)"; RC2=$?
[ "$RC2" = "0" ] && pass "exits 0 without wiki" || fail "exit $RC2"
grep -q '^health_score|skip' <<<"$OUT2" && pass "no wiki → skip" || fail "no-wiki skip"

echo ""; echo "wiki-health: $PASS passed, $FAIL failed"; [ "$FAIL" = "0" ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bash skills/doctor/scripts/tests/test_check_wiki_health.sh`
Expected: FAIL — script does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create `skills/doctor/scripts/check-wiki-health.sh` (template: `check-schemas.sh`). Core python logic:

```bash
#!/usr/bin/env bash
# check-wiki-health.sh — sf-doctor WIKI HEALTH section. READ-ONLY.
set -uo pipefail
WIKI_ROOT="${CLAUDE_PLUGIN_OPTION_WIKIROOT:-$HOME/.startup-framework/wiki}"
exec python3 - "$WIKI_ROOT" "${DOCTOR_TODAY:-}" <<'PYEOF'
import os, re, sys, glob, datetime
wiki_root, today_override = sys.argv[1], sys.argv[2]
STALE_DAYS, PAGE_LINE_WARN = 90, 500
def emit(k, s, v="", h=""): print(f"{k}|{s}|{v}|{h}")
if not os.path.isdir(wiki_root):
    emit("health_score", "skip", "(no wiki)", "run /ren:install to bootstrap"); sys.exit(0)
today = datetime.date.fromisoformat(today_override) if today_override else datetime.date.today()
md_files = glob.glob(os.path.join(wiki_root, "**", "*.md"), recursive=True)
# index of existing pages by basename-without-ext (for wikilink resolution) + by relpath
by_slug = {}
for p in md_files: by_slug.setdefault(os.path.splitext(os.path.basename(p))[0], p)
wikilink = re.compile(r"\[\[([^\]\|]+?)(?:\|[^\]]*)?\]\]")
mdlink = re.compile(r"\]\(([^)]+?\.md)(?:#[^)]*)?\)")
def fm_field(text, key):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m: return None
    mm = re.search(rf"^{key}:\s*(.+)$", m.group(1), re.MULTILINE)
    return mm.group(1).strip().strip('"').strip("'") if mm else None

dead, stale, heavy = [], [], []
for p in md_files:
    try:
        with open(p, encoding="utf-8", errors="replace") as f: text = f.read()
    except OSError: continue
    rel = os.path.relpath(p, wiki_root)
    if text.count("\n") + 1 > PAGE_LINE_WARN: heavy.append(f"{rel}:{text.count(chr(10))+1}L")
    # stale
    upd = fm_field(text[:8192], "updated") or fm_field(text[:8192], "created")
    if upd:
        try:
            d = datetime.date.fromisoformat(upd[:10])
            if (today - d).days > STALE_DAYS: stale.append(f"{rel}:{(today-d).days}d")
        except ValueError: pass
    # links
    for tgt in wikilink.findall(text):
        if tgt.strip() not in by_slug: dead.append(f"{rel}→[[{tgt.strip()}]]")
    for tgt in mdlink.findall(text):
        if tgt.startswith(("http://", "https://")): continue
        if not os.path.isfile(os.path.normpath(os.path.join(os.path.dirname(p), tgt))): dead.append(f"{rel}→{tgt}")

def line(key, items, noun):
    emit(key, "warn" if items else "ok", f"{len(items)}  ({', '.join(items[:5])}{'…' if len(items)>5 else ''})" if items else f"0 {noun}")
line("dead_links", dead, "dead links"); line("stale_pages", stale, f"pages > {STALE_DAYS}d"); line("heavy_pages", heavy, f"pages > {PAGE_LINE_WARN}L")
issues = len(dead) + len(stale) + len(heavy)
emit("health_score", "ok" if issues == 0 else ("warn" if issues <= 5 else "error"),
     f"{issues} issue(s) across {len(md_files)} pages", "GOOD" if issues == 0 else "review flagged pages above")
PYEOF
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bash skills/doctor/scripts/tests/test_check_wiki_health.sh`
Expected: PASS — `wiki-health: N passed, 0 failed`. Then `bash -n` + `shellcheck --severity=warning` on the new script (clean).

- [ ] **Step 5: Commit**

```bash
git add skills/doctor/scripts/check-wiki-health.sh skills/doctor/scripts/tests/test_check_wiki_health.sh
git commit -m "feat(h1): add check-wiki-health.sh — WIKI HEALTH doctor section"
```

---

## Task 3: Integrate both sections into SKILL.md + reference.md + eval.json

`SKILL.md` is the **LLM renderer + orchestrator** (prose, not code) — integration means editing its instructions, not writing render logic.

**Files:**
- Modify: `skills/doctor/SKILL.md`
- Modify: `skills/doctor/reference.md`
- Modify: `skills/doctor/eval/eval.json`

- [ ] **Step 1 (RED): Extend eval.json with the two new assertions.** Add binary assertions (match the existing eval.json shape) asserting that: (a) the report contains the headers `CONTEXT & TOKEN ECONOMICS` and `WIKI HEALTH`; (b) `--section context` runs only that section; (c) `--section wiki-health` runs only that section; (d) the permission-safety note never prints a secret. Read the current `eval/eval.json` first and append in-style.

- [ ] **Step 2: Update `SKILL.md` — all seven→nine references:**
  - Frontmatter `description`: add the two sections to the parenthesized list.
  - `contract.required_outputs[0]`: "seven sections (…)" → "nine sections (…, CONTEXT & TOKEN ECONOMICS, WIKI HEALTH)".
  - `contract.permissions.execute`: add `scripts/check-context.sh`, `scripts/check-wiki-health.sh`.
  - `contract.permissions.read`: add `~/.claude/CLAUDE.md`, `./CLAUDE.md` (context check reads them).
  - `completion_conditions`: "All seven status sections" → "All nine status sections".
  - Flags table: add `--section context` and `--section wiki-health` to the `--section` row's value list.
  - "Seven scripts run in parallel" table → add the two new rows (Side effects: **None**).
  - Output-format TL;DR: add `▶ CONTEXT & TOKEN ECONOMICS` and `▶ WIKI HEALTH` example blocks (with a sample line each).
  - Add a short **render instructions** subsection per section: how to turn each `KEY|STATUS|VALUE|HINT` fragment into a report line (icon by STATUS: `ok→✅ warn→⚠️ skip→·(dim) error→❌`), and that WIKI HEALTH ends with the `health_score` summary line.
  - `## Eval` bullet list: add the two new section headers to the "Output contains all … section headers" bullet.

- [ ] **Step 3: Update `reference.md`** — add the full format spec for both sections, their fragment keys, and extend the **`--json` output schema** with `context` and `wiki_health` objects (mirroring how existing sections are represented). Add a `§ Deferred` note recording the stable-ID-rehydration + MCP-vs-CLI scope cut.

- [ ] **Step 4 (GREEN): Run the full doctor gate.**

Run:
```bash
for t in skills/doctor/scripts/tests/test_check_*.sh; do bash "$t" >/dev/null 2>&1 && echo "✓ $(basename "$t")" || { echo "✗ $(basename "$t")"; FAILED=1; }; done; [ -z "${FAILED:-}" ]
bash -n skills/doctor/scripts/check-context.sh skills/doctor/scripts/check-wiki-health.sh
python3 -c "import json; json.load(open('skills/doctor/eval/eval.json')); print('eval.json valid JSON')"
claude plugin validate ./ --strict
```
Expected: all doctor shell tests pass (8 files now), `bash -n` clean, eval.json valid JSON, plugin validate ✔.

- [ ] **Step 5: Commit**

```bash
git add skills/doctor/SKILL.md skills/doctor/reference.md skills/doctor/eval/eval.json
git commit -m "feat(h1): wire CONTEXT & TOKEN ECONOMICS + WIKI HEALTH into doctor (7→9 sections)"
```

---

## Task 4: Wire-up (CHANGELOG + roadmap + wiki)

**Files:** `CHANGELOG.md`, `docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md`, `wiki/log.md`, `wiki/index.md`.

- [ ] **Step 1:** `CHANGELOG.md` — add an entry under the working version: "H1 — `/ren:doctor` gains CONTEXT & TOKEN ECONOMICS (skill-size lint, context-budget counts, auto-mode posture) + WIKI HEALTH (dead links, stale + token-heavy pages, health score)."
- [ ] **Step 2:** Roadmap — flip the **H1** Status cell from `Not started` to `✅ DONE 2026-06-21 — …` with the plan path; update the critical-path note if it references H1 as pending.
- [ ] **Step 3:** `wiki/log.md` — append a chronological milestone entry (append-only; do not rewrite earlier days) recording H1 shipped + the two sections + the scope cut decision (stable-ID/MCP-vs-CLI deferred).
- [ ] **Step 4:** `wiki/index.md` — if it summarizes doctor's sections or capabilities, update to nine sections.
- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md docs/superpowers/plans/2026-06-11-agentic-os-rebuild-roadmap.md wiki/log.md wiki/index.md
git commit -m "docs(h1): wire-up — CHANGELOG, roadmap status, wiki log + index"
```

---

## Self-Review

**Spec coverage:** spec line 64 = "token-economics + safety audits (auto-mode posture, network tiers, skill-size lint, …) + wiki health-score (dead links, stale files, token-heavy CLAUDE.md)". → auto-mode posture = `auto_mode` (T1); skill-size lint = `skill_size_lint` (T1); token-heavy CLAUDE.md = `claude_md_*` (T1); dead links/stale/heavy = T2; health-score = `health_score` (T2); network tiers = already in ROUTINES (noted, not duplicated); stable-ID/MCP-vs-CLI = deferred + documented. Covered.

**Placeholder scan:** test bodies + implementation + thresholds are concrete; no TBD/"handle appropriately". Boilerplate (bash→python wrapper) references the in-repo template `check-schemas.sh` rather than re-pasting — this is DRY-with-codebase, not a placeholder.

**Type/name consistency:** fragment keys used in tests (`mcp_servers`, `framework_skills`, `skill_size_lint`, `claude_md_global/project`, `auto_mode`, `dead_links`, `stale_pages`, `heavy_pages`, `health_score`) match the implementations and the SKILL.md/reference.md render instructions. STATUS vocabulary `ok|warn|skip|error` is consistent across both scripts and the icon mapping.
