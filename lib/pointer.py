"""
lib.pointer — the single home of the L2 decision-map pointer grammar (#53).

Two accepted line shapes:

  - [<topic>](<wiki-root-relative-path>[#anchor]) (<write_id|unstamped>)   ← link form (canonical for wiki targets)
  - [<topic>] → <target> (<write_id|unstamped>)                            ← arrow form (canonical for repo: refs;
                                                                              legacy for wiki targets, parse-accepted
                                                                              until the next MAJOR bump)

Every producer (skills.ingest-project's assemble_l2, the l2-map-1-to-2
migration) and every consumer (wiki-health, doctor, remember) goes through
this module — the old per-module regexes needed a drift test to stay in
sync, which was the code asking to be one function.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

REPO_REF_PREFIX = "repo:"

# Strict whole-line match is deliberate (#53 review): a malformed pointer is
# a non-pointer, never a half-parsed one. Trailing prose, an extra paren
# group, or a space in the target all fail the match rather than partially
# extract — wiki-health/doctor then treat the line as prose, same as any
# other non-pointer bullet. Do not loosen these to "helpfully" tolerate
# near-miss shapes; that trades a clean miss for a silently wrong parse.
_LINK_RE = re.compile(
    r"^-\s*\[(?P<topic>[^\]]*)\]\((?P<target>[^)\s]+)\)(?:\s*\((?P<wid>[^)]*)\))?\s*$"
)
_ARROW_RE = re.compile(
    r"^-\s*\[(?P<topic>[^\]]*)\]\s*→\s*(?P<target>\S+)(?:\s*\((?P<wid>[^)]*)\))?\s*$"
)


@dataclass(frozen=True)
class PointerLine:
    topic: str
    target: str          # "projects/x/page.md#anchor" or "repo:name:path"
    path: str            # target without anchor; "" for repo refs
    anchor: str | None
    write_id: str | None  # None when "(unstamped)" or absent
    form: str            # "link" | "arrow"


def parse_pointer_line(line: str) -> PointerLine | None:
    """Parse one decision-map line. Returns None for anything that isn't a
    pointer line — consumers degrade exactly as they did on regex non-match."""
    stripped = line.strip()
    for form, rx in (("link", _LINK_RE), ("arrow", _ARROW_RE)):
        m = rx.match(stripped)
        if not m:
            continue
        target = m.group("target")
        wid = m.group("wid")
        write_id = wid if wid and wid != "unstamped" else None
        if target.startswith(REPO_REF_PREFIX):
            path, anchor = "", None
        else:
            path, _, frag = target.partition("#")
            anchor = frag or None
        return PointerLine(
            topic=m.group("topic"), target=target, path=path,
            anchor=anchor, write_id=write_id, form=form,
        )
    return None


def render_pointer_line(topic: str, target: str, write_id: str | None) -> str:
    """Render the canonical line for `target` (anchor included in `target`):
    link form for wiki paths, arrow form for repo: refs."""
    wid = write_id or "unstamped"
    if target.startswith(REPO_REF_PREFIX):
        return f"- [{topic}] → {target} ({wid})"
    return f"- [{topic}]({target}) ({wid})"
