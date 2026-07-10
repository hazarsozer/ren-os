"""
lib.adapter.claude_md — hierarchical CLAUDE.md pointer layer (finalize-v0.2
agenda items 1+2).

This module is the DELIVERY MECHANISM for always-on doctrine — the consumer
`lib.doctrine.loader` was missing (the §3.3 gap found in the 2026-07-07
design review). Instead of injecting doctrine at wake-up, RenOS rides Claude
Code's NATIVE global→project CLAUDE.md hierarchy:

  - **Global tier** (`claude_user_dir()/CLAUDE.md`): a managed marker block
    holding (a) a compact behavioral core adapted from Andrej Karpathy's
    public CLAUDE.md guidelines, tailored to RenOS; (b) the recall doctrine
    (agenda item 2); (c) wiki navigation; (d) a doctrine index generated
    from `lib.doctrine.loader.load_all()` — always-on files get a standing
    pointer, glob-scoped files state their trigger glob, agent-pulled files
    state when to pull them.
  - **Project tier** (`<repo>/CLAUDE.md`): a thin pointer block at the
    project's L2 map. It never repeats global content — "point, don't
    duplicate" is the layer's design rule.

Behavioral rules must be INLINE (a model won't follow a rule it hasn't
read), so the behavioral core is embedded; everything retrievable is a
pointer. Three hard guarantees, mirrored by tests:

  1. **Additive, never overwrite**: `apply_block` only ever creates the file
     or rewrites the region between `MARKER_BEGIN`/`MARKER_END`. Content
     outside the markers is byte-for-byte preserved. A torn marker pair
     (begin without end) touches NOTHING and reports `"conflict"`.
  2. **Idempotent**: re-applying identical content reports `"unchanged"`.
  3. **Dedup-aware**: if the user's file already carries the Karpathy
     guidelines OUTSIDE our markers (the founder's own global CLAUDE.md
     does), the behavioral core is omitted so it never appears twice.

This file is native-harness glue by design — `lint_harness_neutral` does not
run over it (that lint covers AGENTS.md + l2-map pages only).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from lib import ren_paths
from lib.doctrine.loader import DoctrineFile, load_all

MARKER_BEGIN = "<!-- ren:begin -->"
MARKER_END = "<!-- ren:end -->"

KARPATHY_SENTINELS: tuple[str, ...] = (
    "reduce common LLM coding mistakes",
    "Think Before Coding",
)
"""Distinctive phrases from Karpathy's guidelines. Any of them appearing in a
CLAUDE.md OUTSIDE our managed block means the user already runs the original
(or a close derivative) — the generated block then omits the behavioral core."""

_MANAGED_BLOCK_RE = re.compile(
    re.escape(MARKER_BEGIN) + r".*?" + re.escape(MARKER_END), re.DOTALL
)

_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


# --- behavioral core (tailored Karpathy) -----------------------------------

_BEHAVIORAL_CORE = """\
## Behavioral core

Guidelines to reduce common LLM coding mistakes, tailored for RenOS sessions.
They bias toward caution over speed — for trivial tasks, use judgment.

### Think Before Coding
- State assumptions explicitly. If uncertain, ask. If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- Known territory? Check memory FIRST — trigger `/ren:recall` before deciding (see Memory & recall below).
- Before building anything new, brainstorm intent and design with the user before writing code (use a brainstorming skill if one is installed).

### Simplicity First
- Minimum code that solves the problem. No speculative features, abstractions, or configurability.
- For recurring or multi-agent work, use the lowest capability rung that fits (quick ask → skill → sub-agent → team → goal) — see the doctrine index below.
- Ask: "Would a senior engineer call this overcomplicated?" If yes, simplify.

### Surgical Changes
- Touch only what the request requires; match existing style; mention unrelated dead code, don't delete it.
- Remove only orphans YOUR change created.
- Never hand-edit inside `ren:`-managed marker blocks, and never edit governed wiki pages directly — durable wiki changes save automatically and revertibly through RenOS's memory write path.

### Goal-Driven Execution
- Turn tasks into verifiable goals ("fix the bug" → "write a failing test, make it pass"); state a brief step → verify plan for multi-step work.
- Loop until verified — evidence before claiming done.
- End substantial sessions with `/ren:wrap` so learnings persist; never game recall/miss metrics — an honest miss is signal, a faked hit poisons the memory.
"""

_BEHAVIORAL_CORE_OMITTED = """\
## Behavioral core

Omitted — behavioral coding guidelines already present in this file outside
the managed block; RenOS never duplicates them. The sections below carry only
RenOS-specific doctrine.
"""


def _recall_section(wiki: Path) -> str:
    return f"""\
## Memory & recall (the recall doctrine)

- When a topic touches known territory — a past decision, a project already in the wiki, a person, a preference — trigger `/ren:recall` yourself. Recall is agent-initiated; do not wait to be asked.
- NEVER raw-Read wiki pages to answer memory questions. Recall goes through `/ren:recall` so misses are measured honestly; a raw Read is an unrecorded hit and poisons the metrics.
- Durable facts learned mid-session: `/ren:pin` them. End-of-session consolidation: `/ren:wrap`.
- Durable wiki writes save themselves — revertible via provenance/journal/snapshot underneath. The only human gate is promotion into standing instructions or skills, asked in chat; contradictions are model-resolved with recorded reasoning. Direct edits to governed pages are forbidden.
"""


def _navigation_section(wiki: Path) -> str:
    return f"""\
## Wiki navigation

- Master wiki root: `{wiki}` — start at `index.md`; chronology in `log.md`; who the user is in `identity.md`.
- Per-project knowledge maps live at `{wiki / "projects"}/<slug>/map.md` (L2 maps: compact facts + pointers). Follow pointers instead of scanning the tree.
- Durable rules and preferences shared across projects: `{wiki / "global"}`.
- Project repos carry a thin `CLAUDE.md` pointer block into their map — the wiki is the single source of truth; pointer files never hold content of their own.
"""


def _doctrine_index(docs: list[DoctrineFile]) -> str:
    lines = [
        "## Doctrine index",
        "",
        "Framework doctrine files and when they apply:",
        "",
    ]
    if not docs:
        lines.append("- (no doctrine files found)")
    for doc in docs:
        match = _HEADING_RE.search(doc.body)
        title = match.group(1).strip() if match else doc.path.stem
        path = doc.path.resolve()
        if doc.activation == "always-on":
            directive = "always applies — read it before any non-trivial work in its area"
        elif doc.activation == "glob-scoped":
            directive = f"applies when the working set matches `{doc.scope_glob}` — read it then"
        else:  # agent-pulled
            directive = "pull on demand — read it only when doing the work it covers"
        lines.append(f"- **{title}** (`{path}`): {directive}.")
    lines.append("")
    return "\n".join(lines)


def render_global_block(
    *,
    existing_text: str = "",
    doctrine_root: Path | None = None,
    wiki_root: Path | None = None,
) -> str:
    """Render the global-tier managed block content (WITHOUT markers —
    `apply_block` owns those).

    `existing_text` is the current content of the target CLAUDE.md (or ""):
    used for dedup-awareness. Sentinels inside a previous ren-managed block
    are ignored — only content the USER authored counts as "already has it".
    """
    wiki = (Path(wiki_root) if wiki_root is not None else ren_paths.wiki_root()).resolve()
    user_text = _MANAGED_BLOCK_RE.sub("", existing_text)
    already_has_core = any(s in user_text for s in KARPATHY_SENTINELS)

    parts = [
        "# RenOS — global doctrine",
        "",
        "Generated by RenOS install. This block is re-rendered on update —",
        "hand edits inside the markers are overwritten; everything outside",
        "them is never touched.",
        "",
        _BEHAVIORAL_CORE_OMITTED if already_has_core else _BEHAVIORAL_CORE,
        _recall_section(wiki),
        _navigation_section(wiki),
        _doctrine_index(load_all(doctrine_root)),
        "---",
        "",
        "Behavioral core adapted from Andrej Karpathy's public CLAUDE.md",
        "guidelines, tailored for RenOS.",
    ]
    return "\n".join(parts)


def render_project_block(project_slug: str, *, wiki_root: Path | None = None) -> str:
    """Render the project-tier pointer block (WITHOUT markers). Thin by
    design: it points at the project's L2 map and defers everything else to
    the global tier — never duplicating its content."""
    wiki = (Path(wiki_root) if wiki_root is not None else ren_paths.wiki_root()).resolve()
    map_path = wiki / "projects" / project_slug / "map.md"
    return f"""\
# RenOS — project memory pointer

- This project's knowledge map: `{map_path}` — recall its contents via `/ren:recall` (agent-initiated); never raw-Read wiki pages to answer memory questions.
- Global RenOS doctrine (behavioral core, recall rules, wiki navigation) lives in the user-level CLAUDE.md — it is not repeated here.
- Durable changes to the wiki save themselves (revertible), never a direct file edit."""


def spliced_text(existing_text: str, content: str) -> str:
    """Pure: the full file text `apply_block` WOULD write for `content`,
    given `existing_text` as the file's current contents (`""` standing in
    for "file doesn't exist yet", the same convention `write_global_claude_md`
    already uses).

    Extracted so producers (Gate-0 finding a: `doctrine_shaping`) can predict
    what a refresh would produce and compare it to disk WITHOUT writing
    anything — `apply_block` itself uses this for the actual write, so the
    two can never drift apart. Doesn't distinguish added/updated/unchanged/
    conflict (that's `apply_block`'s contract); for torn markers (begin
    without end, or vice versa) this returns `existing_text` unchanged,
    mirroring `apply_block`'s "conflict" refusal to touch the file.
    """
    block = f"{MARKER_BEGIN}\n{content.rstrip()}\n{MARKER_END}\n"

    if not existing_text:
        return block

    has_begin = MARKER_BEGIN in existing_text
    has_end = MARKER_END in existing_text

    if has_begin and has_end:
        return _MANAGED_BLOCK_RE.sub(lambda _m: block.rstrip("\n"), existing_text, count=1)

    if has_begin or has_end:
        return existing_text

    separator = "" if existing_text.endswith("\n\n") else ("\n" if existing_text.endswith("\n") else "\n\n")
    return existing_text + separator + block


def apply_block(path: Path, content: str) -> str:
    """Create or update the managed marker block in `path`.

    Returns `"added"` (file created, or block appended to an existing file),
    `"updated"` (block content replaced), `"unchanged"` (identical content),
    or `"conflict"` (torn markers — file left byte-for-byte untouched).
    Everything outside the markers is always preserved.
    """
    path = Path(path)

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, spliced_text("", content))
        return "added"

    text = path.read_text(encoding="utf-8")
    has_begin = MARKER_BEGIN in text
    has_end = MARKER_END in text

    if has_begin and has_end:
        new_text = spliced_text(text, content)
        if new_text == text:
            return "unchanged"
        _atomic_write(path, new_text)
        return "updated"

    if has_begin or has_end:
        return "conflict"

    new_text = spliced_text(text, content)
    _atomic_write(path, new_text)
    return "added"


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_global_claude_md(
    *,
    claude_dir: Path | None = None,
    doctrine_root: Path | None = None,
    wiki_root: Path | None = None,
) -> tuple[Path, str]:
    """Render + apply the global block at `claude_user_dir()/CLAUDE.md`.
    Returns `(path, apply_block result)`."""
    target_dir = Path(claude_dir) if claude_dir is not None else ren_paths.claude_user_dir()
    path = target_dir / "CLAUDE.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    content = render_global_block(
        existing_text=existing, doctrine_root=doctrine_root, wiki_root=wiki_root
    )
    return path, apply_block(path, content)


def write_project_claude_md(
    repo_root: Path,
    project_slug: str,
    *,
    wiki_root: Path | None = None,
) -> tuple[Path, str]:
    """Render + apply the project pointer block at `<repo_root>/CLAUDE.md`.
    Returns `(path, apply_block result)`."""
    path = Path(repo_root) / "CLAUDE.md"
    return path, apply_block(path, render_project_block(project_slug, wiki_root=wiki_root))


__all__ = [
    "MARKER_BEGIN",
    "MARKER_END",
    "KARPATHY_SENTINELS",
    "render_global_block",
    "render_project_block",
    "spliced_text",
    "apply_block",
    "write_global_claude_md",
    "write_project_claude_md",
]
