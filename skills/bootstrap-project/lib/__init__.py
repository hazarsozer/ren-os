"""
skills.bootstrap-project library — internal implementation for
/ren:bootstrap-project (Task 4.4, RenOS 0.2 Phase 4).

Spec §3.1 L2 + §3.8 A-10 (first-session artifact), the FRESH-project half of
the pair: `/ren:ingest-project` (sibling skill) is for an EXISTING repo with
real content to scan; this skill is for a brand-new project with nothing to
scan yet. It does two things:

  1. Stamps the shared wiki skeleton (`lib/skeleton.py` + `wiki-skeleton/`)
     into the wiki root — additive, never-overwrite, so running this against
     an already-onboarded wiki touches nothing that exists.
  2. Queues an EMPTY L2 map at `projects/<slug>/map.md` — same frozen schema
     `skills/ingest-project/lib/assemble_l2` renders, just with no knowledge
     or pointers yet (the friend or a later `/ren:ingest-project`/`/ren:wrap`
     fills it in) — but ONLY when that page doesn't exist yet. If it already
     exists, the map write is skipped entirely: bootstrap only SEEDS an empty
     map once, it never re-touches a map that's since been grown with real
     content by other writers.

Always `producer="promotion"`, `writer="human"` (a human explicitly asked to
start this project — nothing here is LLM-drafted), so it's never quarantined,
unlike `ingest`'s scan-derived `writer="llm-auto"` maps. Like every other
data-plane producer (v2.2 pivot), this goes through
`lib.memory.queue.propose_and_apply` — a non-global page write auto-applies,
so `bootstrap` lands `applied` immediately, not pending for human approval.

The directory name `bootstrap-project` isn't a valid Python identifier
segment, so `assemble_l2` is reached via `importlib.import_module` (the same
mechanism donor skills used for hyphenated skill dirs) rather than a `from
skills.ingest_project.lib import ...`-style dotted import, which would fail
to parse.
"""

from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from lib import ren_paths
from lib.adapter.claude_md import write_project_claude_md
from lib.memory.queue import Proposal, QueueEntry, propose_and_apply
from lib.portability.agents_surface import write_agents_md
from lib.skeleton import stamp_skeleton

_LOGGER = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]  # lib -> bootstrap-project -> skills -> repo root
_SKELETON_ROOT = _REPO_ROOT / "wiki-skeleton"

_ingest_lib = importlib.import_module("skills.ingest-project.lib")
assemble_l2 = _ingest_lib.assemble_l2


def _map_page(project_slug: str) -> str:
    return f"projects/{project_slug}/map.md"


def bootstrap(project_slug: str, session: str, repo_root: Path | None = None) -> QueueEntry | None:
    """Stamp the shared skeleton (additive) and seed an empty L2 map for
    `project_slug`.

    ADD only, and only if `projects/<project_slug>/map.md` doesn't exist yet.
    If it already exists, the map write is skipped entirely — no proposal is
    queued, the existing map (and whatever real content other writers have
    since grown it with) is left completely untouched — and `None` is
    returned instead of a `QueueEntry`. bootstrap seeds a map once; it never
    re-touches one that already exists.

    Always human-provenance — never quarantined. Auto-applies through the
    data-plane door (v2.2); the returned entry's `write_id` is set once
    applied.

    When `repo_root` is given (the project repo the user is bootstrapping
    from, e.g. `Path.cwd()`), also writes `<repo_root>/AGENTS.md` (the
    portability pointer surface, Codex D5) and `<repo_root>/CLAUDE.md` (the
    project-tier pointer block, per `lib.adapter.claude_md`). `None`
    (default) skips both, full backward compatibility. A failure writing
    either file never breaks bootstrap itself.
    """
    stamp_skeleton(
        skeleton_root=_SKELETON_ROOT,
        target_root=ren_paths.wiki_root(),
        profile="master",
        placeholders={
            "handle": "friend",
            "name": "friend",
            "framework_version": ren_paths.framework_version(),
        },
    )

    # 0.5.5 Task 2: also stamp the `project` manifest profile (overview.md —
    # the guaranteed wake-up orientation page) under projects/<slug>/.
    # target_root stays wiki_root() (write_apply always resolves against it
    # internally, per lib/skeleton.py's module docstring); path_prefix nests
    # the profile's manifest-relative paths under this project's slug.
    stamp_skeleton(
        skeleton_root=_SKELETON_ROOT,
        target_root=ren_paths.wiki_root(),
        profile="project",
        placeholders={
            "handle": "friend",
            "name": "friend",
            "framework_version": ren_paths.framework_version(),
        },
        path_prefix=f"projects/{project_slug}/",
    )

    page = _map_page(project_slug)
    page_abs = ren_paths.safe_join(ren_paths.wiki_root(), page)

    entry: QueueEntry | None = None
    if not page_abs.exists():
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        content = assemble_l2(project_slug, [], [], f"{today}: project bootstrapped")
        entry, _ = propose_and_apply(
            Proposal(
                op="ADD",
                page=page,
                content=content,
                reason="bootstrap-project",
                producer="promotion",
                writer="human",
                session=session,
                salience=False,
            )
        )

    if repo_root is not None:
        try:
            write_agents_md(Path(repo_root), ren_paths.wiki_root(), project_slug)
        except OSError:
            _LOGGER.exception("bootstrap-project: failed to write AGENTS.md at %s", repo_root)

        try:
            write_project_claude_md(Path(repo_root), project_slug)
        except OSError:
            _LOGGER.exception("bootstrap-project: failed to write CLAUDE.md at %s", repo_root)

    return entry


__all__ = ["bootstrap", "assemble_l2"]
