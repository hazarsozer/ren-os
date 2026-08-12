"""
skills.wrap.lib.links — #54's link duties as pure text transforms.

Wrap is where pages are born, so wrap is where they get woven into the
graph: L1s link the pages the session touched, log.md links the L1, the
project map links recent sessions and every new durable page, and the
master index links the map. Each function here is text-in/text-out (or
returns None for "no write needed") so `wrap_session` can drive every
write through the queue and tests can hammer the transforms directly.

D1/D3 deliberately emit PLAIN markdown links (no write_id) — they are
narrative links, not decision-map pointers; only `add_map_pointer` /
`ensure_index_spine` emit pointer lines, via lib.pointer.
"""
from __future__ import annotations

import re
from pathlib import Path

from lib.pointer import render_pointer_line

_SESSIONS_HEADER = "## Sessions"
_DECISION_HEADER = "## Decision map"
_LOG_HEADER = "## Log"
_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)


def page_title(wiki_root: Path, page: str) -> str:
    try:
        text = (wiki_root / page).read_text(encoding="utf-8", errors="replace")
        body = _FRONTMATTER_RE.sub("", text)
        m = _HEADING_RE.search(body)
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    return Path(page).stem


def touched_section(wiki_root: Path, pages: list[str]) -> str:
    unique = sorted(set(pages))
    if not unique:
        return ""
    lines = ["## Touched pages"]
    for page in unique:
        lines.append(f"- [{page_title(wiki_root, page)}]({page})")
    return "\n".join(lines) + "\n"


def log_entry_line(date_iso: str, project: str | None, l1_page: str, session: str) -> str:
    scope = project or "global"
    return f"## [{date_iso}] session | {scope} — [session-{session}]({l1_page})"


def append_log_entry(log_text: str, entry_line: str) -> str:
    return log_text.rstrip("\n") + "\n\n" + entry_line + "\n"


def _split_section(text: str, header: str) -> tuple[str, list[str], str] | None:
    """(before, section_lines_without_header, after) or None if absent.

    `before` ends with the header line + its trailing newline; `after`
    starts at the next "## " header (or is "" at EOF) — splicing back
    together as before + body + after always reconstructs the original
    bytes around the section, so frontmatter/banner content elsewhere in
    the page is never touched.
    """
    lines = text.splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if l.rstrip("\n") == header), None)
    if start is None:
        return None
    end = next(
        (
            i for i in range(start + 1, len(lines))
            # A later "## " section header ends the body as before; a "# "
            # H1 (a fresh top-level heading, e.g. a page's own title
            # re-asserted mid-body) also ends it — without this, a splice
            # could run past an H1 and corrupt content that belongs to a
            # different logical page section.
            if lines[i].startswith("## ") or lines[i].startswith("# ")
        ),
        len(lines),
    )
    return "".join(lines[: start + 1]), [l.rstrip("\n") for l in lines[start + 1 : end]], "".join(lines[end:])


def upsert_sessions_section(page_text: str, l1_page: str, session: str, cap: int = 10) -> str | None:
    entry = f"- [session-{session}]({l1_page})"
    split = _split_section(page_text, _SESSIONS_HEADER)
    if split is None:
        block = f"{_SESSIONS_HEADER}\n{entry}\n"
        log_split = _split_section(page_text, _LOG_HEADER)
        if log_split is None:
            return page_text.rstrip("\n") + "\n" + block
        # Insert the new section immediately before the "## Log" header,
        # i.e. at the start of `before` up through the header's own line.
        before, section_lines, after = log_split
        log_header_line = before.splitlines(keepends=True)[-1]
        head = before[: -len(log_header_line)]
        rest = log_header_line + "".join(l + "\n" for l in section_lines) + after
        return head + block + rest
    before, section_lines, after = split
    if entry in section_lines:
        return None
    # The section is session-entries-first by convention: session lines get
    # the cap/trim treatment (oldest dropped on overflow), while every other
    # line in the body (including blank lines separating placeholder prose)
    # stays exactly where it is — only TRAILING blank lines, right before
    # the newly appended entry, are ever dropped.
    session_indices = [i for i, l in enumerate(section_lines) if l.startswith("- [session-")]
    overflow = len(session_indices) + 1 - cap
    drop = set(session_indices[: max(overflow, 0)])
    kept_lines = [l for i, l in enumerate(section_lines) if i not in drop]
    while kept_lines and not kept_lines[-1].strip():
        kept_lines.pop()
    kept_lines.append(entry)
    body = "".join(l + "\n" for l in kept_lines)
    return before + body + after


def _append_pointer(page_text: str, topic: str, path: str, write_id: str | None) -> str | None:
    if path in page_text:
        return None
    line = render_pointer_line(topic, path, write_id)
    split = _split_section(page_text, _DECISION_HEADER)
    if split is None:
        return page_text.rstrip("\n") + f"\n{_DECISION_HEADER}\n{line}\n"
    before, section_lines, after = split
    # Keep the section body verbatim (placeholder prose, blank lines and
    # all) — only trailing blank lines right before the append point are
    # dropped, so the splice never reflows or discards existing content.
    section_lines = list(section_lines)
    while section_lines and not section_lines[-1].strip():
        section_lines.pop()
    section_lines.append(line)
    body = "".join(l + "\n" for l in section_lines)
    return before + body + after


def add_map_pointer(page_text: str, topic: str, path: str, write_id: str | None) -> str | None:
    return _append_pointer(page_text, topic, path, write_id)


def ensure_index_spine(index_text: str, slug: str, map_page: str, map_write_id: str | None) -> str | None:
    return _append_pointer(index_text, slug, map_page, map_write_id)
