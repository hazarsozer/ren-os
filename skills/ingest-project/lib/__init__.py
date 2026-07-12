"""
skills.ingest-project library — internal implementation for /ren:ingest-project
(Task 4.4, RenOS 0.2 Phase 4).

Spec §3.1 L2: "a compact per-project page holding general project knowledge
plus an index of pointers — a map, not the territory." Spec §3.8 A-10: "the
first session produces a visible artifact." This module is where an EXISTING
repo becomes that artifact:

  1. `scan_repo` — read-only facts about the repo (carried `scan.py`: languages,
     entry points, deps, doc/git/size signals). Never writes, never raises on
     a non-project path.
  2. The LIVE SESSION (not this module — that's the LLM-shaped part) reads
     those facts and drafts `knowledge` (compact facts) + `pointers`
     (topic → wiki-path#anchor pointers).
  3. `assemble_l2` — pure, deterministic rendering of the frozen L2 schema
     from those drafted pieces. No LLM call happens inside this module.
  4. `ingest` — queues the assembled map through
     `lib.memory.queue.propose_and_apply` (never a direct write) and returns
     the first-session artifact text — exactly what
     `/ren:install`/`/ren:ingest-project` shows the friend at the end (exit
     criterion 6's "wow moment").

Scan-derived content is LLM-shaped (the live session synthesized it from raw
facts), so `ingest` always proposes with `writer="llm-auto"` — per spec
§3.10, that content is data-not-instruction until a human reviews it, and
`lib.memory.queue.apply_auto`/`apply` quarantine-mark it automatically for
exactly that reason. Per the v2.2 two-plane pivot, the map is a non-global
(data-plane) page, so it auto-applies immediately through
`propose_and_apply` — the first-session artifact tells the friend it's
already saved and one-step revertible, not that it's waiting on a human's
approval. `bootstrap` (sibling skill, `skills/bootstrap-project/lib`) is the
opposite case: an EMPTY map created directly by/for the human, so it proposes
with `writer="human"` and is never quarantined.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lib import ren_paths
from lib.memory import quarantine
from lib.memory.queue import Proposal, QueueEntry, propose_and_apply

from . import scan as _scan_module

FIRST_SESSION_LEAD = "I set up your project memory — here's what I captured:"


def scan_repo(repo_root: Path) -> dict:
    """Read-only facts about an existing repo (languages, entry points, deps,
    doc/git/size signals). Carried from donor `scan.py`; never writes, never
    raises on a bad/non-project path (see `scan.scan`'s own contract)."""
    return _scan_module.scan(str(repo_root))


def _map_page(project_slug: str) -> str:
    return f"projects/{project_slug}/map.md"


def assemble_l2(
    project_slug: str,
    knowledge: list[str],
    pointers: list[dict],
    log_line: str,
) -> str:
    """Render the FROZEN L2 pointer-map schema from already-drafted pieces.

    Pure and deterministic — no filesystem or LLM access. `pointers` entries
    are `{"topic": ..., "path": ..., "anchor": ..., "write_id": <str|None>}`;
    a `None`/falsy `write_id` renders as the literal `unstamped` (the pointer
    targets a page that hasn't been through the write-queue yet). `log_line`
    is the already-formatted one-line log entry (e.g. `"2026-01-01: bootstrapped"`)
    — this function only prefixes it with the bullet marker.
    """
    lines = [
        "---",
        "type: l2-map",
        f"project: {project_slug}",
        "---",
        f"# {project_slug} — knowledge map",
        "## Knowledge",
    ]
    for fact in knowledge:
        lines.append(f"- {fact}")
    lines.append("## Decision map")
    lines.append("_All pointer paths are relative to the wiki root, not this file._")
    for pointer in pointers:
        write_id = pointer.get("write_id") or "unstamped"
        anchor = pointer.get("anchor")
        target = f"{pointer['path']}#{anchor}" if anchor else pointer["path"]
        lines.append(f"- [{pointer['topic']}] → {target} ({write_id})")
    lines.append("## Log")
    lines.append(f"- {log_line}")
    return "\n".join(lines) + "\n"


def ingest(
    project_slug: str,
    knowledge: list[str],
    pointers: list[dict],
    session: str,
) -> dict:
    """Assemble and queue an L2 map from scan-derived (LLM-shaped) knowledge.

    ADD if `projects/<project_slug>/map.md` doesn't exist yet, else UPDATE
    (which will surface a `supersedes` conflict against the prior map via
    `lib.memory.semantics`, since the target already exists — `supersedes`
    doesn't hold the auto-apply, it's the normal shape of a changing map).
    Always `producer="ingest"`, `writer="llm-auto"` — the honest producer
    label for content pulled in from an existing repo (trust class
    `"foreign"`, per `lib.memory.provenance.trust_class`); quarantined on
    write until a human reviews it, per spec §3.10, but auto-applied
    immediately through the data-plane door (non-global page, v2.2 pivot).

    Returns `{"qid": <queue id>, "write_id": <write id or None if held>,
    "artifact": <first-session artifact text>}`. The artifact text is
    `FIRST_SESSION_LEAD` + a blank line + the assembled map body + a closing
    line telling the friend it's already saved and one-step revertible (or,
    on the rare held case — a detected contradiction — that it's waiting for
    review instead).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = assemble_l2(project_slug, knowledge, pointers, f"{today}: ingested from existing repository")

    instruction_shaped = [hit for fact in knowledge for hit in quarantine.detect_instruction_shaped(fact)]
    if instruction_shaped:
        content += f"\n> {len(instruction_shaped)} instruction-shaped fragment(s) detected at scan\n"

    page = _map_page(project_slug)
    page_abs = ren_paths.safe_join(ren_paths.wiki_root(), page)
    op = "UPDATE" if page_abs.exists() else "ADD"

    entry, _ = propose_and_apply(
        Proposal(
            op=op,
            page=page,
            content=content,
            reason="ingest-project",
            producer="ingest",
            writer="llm-auto",
            session=session,
            salience=False,
        )
    )

    write_id = entry.write_id
    if write_id:
        closing = f"This is saved (write {write_id}) — one step to revert, just say \"undo\" if it's wrong."
    else:
        closing = "This is held for review — a conflict was flagged that needs your input before it's saved."
    artifact = f"{FIRST_SESSION_LEAD}\n\n{content}\n\n{closing}"
    return {"qid": entry.qid, "write_id": write_id, "artifact": artifact, "instruction_shaped": instruction_shaped}


__all__ = ["FIRST_SESSION_LEAD", "scan_repo", "assemble_l2", "ingest"]
