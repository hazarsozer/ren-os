"""
lib.portability.agents_surface — G13 AGENTS.md canonical surface (Task 7.2,
RenOS 0.2 Phase 7).

Spec §3.9 A-9 (load-bearing, exit criterion 5): "knowledge-layer files contain
ZERO Claude-specific structure (harness glue lives in a separate adapter dir);
the canonical markdown IS the AGENTS.md surface (shared/canonical, not
generated copies — thin pointer files at most); 0.2 ships one working proof:
Codex reads the project context from the same files. Write gates remain
OS-side; foreign harnesses are read-only in 0.2."

This module owns two things:
  1. `render_agents_md`/`write_agents_md` — the THIN POINTER file. It is NOT a
     copy of wiki content (that would be a second, drifting source of truth)
     — it's a short orientation doc plus links into the real wiki pages.
     Written directly to `repo_root/AGENTS.md` (bypassing the memory write
     path): it's a repo-side, regenerable pointer file, not durable memory.
  2. `lint_harness_neutral`/`lint_generated_surfaces` — the enforcement half
     of A-9. Any text WE generate for a foreign harness to read must contain
     zero Claude-Code-specific tokens. Human-authored wiki prose is exempt
     (a friend's own notes mentioning "Claude" are their content, not ours to
     scrub) — the lint only runs over generated surfaces: AGENTS.md itself,
     and pages typed `l2-map` (machine-assembled knowledge maps), never over
     arbitrary human pages like `lessons/` or `decisions/`.
"""

from __future__ import annotations

import re
from pathlib import Path

# Harness-coupling markers. Any of these appearing (case-insensitively) in a
# GENERATED surface (AGENTS.md, l2-map pages) is a portability violation —
# "/ren:" counts because slash-commands are Claude-Code-specific surface,
# not something a foreign harness like Codex would understand.
CLAUDE_TOKENS: tuple[str, ...] = (
    "claude",
    "anthropic",
    "CLAUDE_PLUGIN",
    "SessionStart",
    "hookSpecificOutput",
    "/ren:",
)

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_L2_MAP_TYPE = "l2-map"


def _frontmatter_type(text: str) -> str | None:
    """Minimal frontmatter `type:` reader (same small local shape used
    elsewhere in this codebase — see provenance.py/semantics.py/quarantine.py/
    promotion.py/lib.doctrine.loader for the running Phase-9-hygiene note)."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("type:"):
            value = stripped[len("type:"):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            return value or None
    return None


def render_agents_md(wiki_root: Path, project_slug: str | None = None) -> str:
    """Render the thin AGENTS.md pointer file's content.

    Links to the project's L2 map (`projects/<project_slug>/map.md`) when
    `project_slug` is given, else the master wiki index (`index.md`) — plus
    the global doctrine/preferences tier, and a read-only note explaining
    that durable changes save themselves through RenOS's memory write path,
    never a direct edit.

    ZERO Claude-specific tokens by construction — `lint_harness_neutral`
    is expected to return `[]` for this output; that's the golden test for
    exit criterion 5's substrate.
    """
    wiki_root = Path(wiki_root).resolve()

    if project_slug:
        map_path = wiki_root / "projects" / project_slug / "map.md"
        map_label = f"{project_slug} project map"
    else:
        map_path = wiki_root / "index.md"
        map_label = "master wiki index"

    global_path = wiki_root / "global"

    lines = [
        "# AGENTS.md",
        "",
        "This project's canonical context lives in the wiki — start at the map below.",
        "",
        "## Start here",
        "",
        f"- [{map_label}]({map_path}) — the knowledge map: what this project is, "
        "key facts, and pointers to deeper pages.",
        f"- [global doctrine and preferences]({global_path}) — durable rules and "
        "preferences shared across every project.",
        "",
        "## Read-only note for any coding agent reading this file",
        "",
        "An append-only journal (with snapshots) governs every durable change to "
        "this wiki. Treat every page under the wiki as read-only. Do not edit wiki "
        "pages directly — durable changes save themselves through RenOS's memory "
        "write path, never a direct file edit.",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_agents_md(repo_root: Path, wiki_root: Path, project_slug: str | None = None) -> Path:
    """Write the rendered AGENTS.md at `repo_root/AGENTS.md` (direct write —
    this is a repo-side, regenerable pointer file, not wiki memory, so it
    bypasses the memory write path). Idempotent: re-running overwrites
    the prior content rather than appending or erroring."""
    repo_root = Path(repo_root)
    content = render_agents_md(wiki_root, project_slug)
    path = repo_root / "AGENTS.md"
    path.write_text(content, encoding="utf-8")
    return path


def lint_harness_neutral(text: str) -> list[str]:
    """Return the `CLAUDE_TOKENS` entries found in `text` (case-insensitive
    substring match). `[]` means clean."""
    lowered = text.lower()
    return [token for token in CLAUDE_TOKENS if token.lower() in lowered]


def lint_generated_surfaces(wiki_root: Path, repo_root: Path) -> dict[str, list[str]]:
    """Lint every GENERATED surface for harness-coupling tokens: `AGENTS.md`
    at `repo_root` (if present) and every wiki page whose frontmatter `type`
    is `l2-map`. Human-authored pages (lessons/, decisions/, etc.) are never
    linted — this only enforces the surfaces WE generate.

    Returns `{path: [offending tokens]}` for offenders only; a page/file that
    passes (or a missing AGENTS.md) simply doesn't appear in the dict.
    """
    wiki_root = Path(wiki_root)
    repo_root = Path(repo_root)
    report: dict[str, list[str]] = {}

    agents_md = repo_root / "AGENTS.md"
    if agents_md.is_file():
        offenders = lint_harness_neutral(agents_md.read_text(encoding="utf-8"))
        if offenders:
            report[str(agents_md)] = offenders

    if wiki_root.is_dir():
        for md_path in sorted(wiki_root.rglob("*.md")):
            text = md_path.read_text(encoding="utf-8")
            if _frontmatter_type(text) != _L2_MAP_TYPE:
                continue
            offenders = lint_harness_neutral(text)
            if offenders:
                report[str(md_path)] = offenders

    return report


__all__ = [
    "CLAUDE_TOKENS",
    "render_agents_md",
    "write_agents_md",
    "lint_harness_neutral",
    "lint_generated_surfaces",
]
