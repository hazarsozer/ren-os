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
    nlines = len(text.splitlines())
    if nlines > PAGE_LINE_WARN: heavy.append(f"{rel}:{nlines}L")
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
    emit(key, "warn" if items else "ok", f"{len(items)} ({', '.join(items[:5])}{'…' if len(items)>5 else ''})" if items else f"0 {noun}")
line("dead_links", dead, "dead links"); line("stale_pages", stale, f"pages > {STALE_DAYS}d"); line("heavy_pages", heavy, f"pages > {PAGE_LINE_WARN}L")
issues = len(dead) + len(stale) + len(heavy)
emit("health_score", "ok" if issues == 0 else ("warn" if issues <= 5 else "error"),
     f"{issues} issue(s) across {len(md_files)} pages", "GOOD" if issues == 0 else "review flagged pages above")
PYEOF
