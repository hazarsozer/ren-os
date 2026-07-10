"""
lib.memory.provenance — G2 provenance module (Task 1.1, RenOS 0.2 Phase 1).

Spec §3.1 "Provenance" (council A-2): every memory write carries a writer class,
source session, timestamp, and op (ADD / UPDATE / DELETE / NOOP) — the substrate
§3.10 (Memory Integrity & Recovery) needs for reverts, decay, and trust decisions.
This module is the one place that builds a `Provenance` record and stamps/reads
it in a wiki page's YAML frontmatter as `ren_*` keys.

The interface below is FROZEN — downstream phases (the write queue, wrap gate,
retrospective engine) import these exact names.

Frontmatter strategy: `stamp_frontmatter` does a TARGETED line-level rewrite of
just the `ren_*` keys rather than a full YAML parse+dump round-trip. A full
round-trip through PyYAML would lose comments, key ordering, and quoting style
on every OTHER frontmatter key (title, type, custom fields, ...) — unacceptable
since those keys must survive byte-for-byte. `read_frontmatter_provenance` DOES
use `yaml.safe_load` (only on the isolated frontmatter block) since reading is
naturally lossy-tolerant and pyyaml correctly type-converts quoted scalars back
to str.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, get_args

import yaml
from ulid import ULID

WriterClass = Literal["human", "llm-auto", "retrospective", "routine"]
Op = Literal["ADD", "UPDATE", "DELETE", "NOOP"]

_WRITER_CLASSES: tuple[str, ...] = get_args(WriterClass)
_OPS: tuple[str, ...] = get_args(Op)

# Trust taxonomy (0.5.1, Task 6): every write's trust class is derived
# MECHANICALLY from writer/producer at the single door, never classified by a
# model. "user" = a human wrote it directly; "foreign" = ingested from outside
# the session (untrusted provenance, e.g. an existing repo scan); "model" =
# everything else the session itself produced (llm-auto, retrospective, routine).
TRUST_CLASSES: tuple[str, ...] = ("user", "model", "foreign")


def trust_class(writer: str, producer: str) -> str:
    """Mechanically derive the trust class for a write from its writer and
    producer. `writer == "human"` always wins (a human-authored write is
    trusted regardless of producer); otherwise `producer == "ingest"` marks
    content pulled in from outside the session as `"foreign"`; everything
    else is `"model"`."""
    if writer == "human":
        return "user"
    if producer == "ingest":
        return "foreign"
    return "model"


# Frontmatter keys this module owns, in the fixed order they're (re)written.
_REN_KEYS: tuple[str, ...] = (
    "ren_write_id",
    "ren_ts",
    "ren_writer",
    "ren_op",
    "ren_supersedes",
    "ren_trust",
)

# Matches a leading YAML frontmatter block: opening `---` fence, content, closing
# `---` fence. Anchored to the start of the string (frontmatter must be the very
# first thing in the file, per convention elsewhere in this codebase).
_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


@dataclass(frozen=True)
class Provenance:
    write_id: str            # "w-" + ULID
    ts: str                  # ISO-8601 UTC, e.g. "2026-07-06T12:00:00Z"
    writer: WriterClass
    session: str             # harness session id or "unknown"
    op: Op
    page: str                # wiki-relative path
    supersedes: str | None   # write_id of superseded entry
    trust: str = "model"     # one of TRUST_CLASSES — derived via trust_class()

    def __post_init__(self) -> None:
        if self.writer not in _WRITER_CLASSES:
            raise ValueError(
                f"writer {self.writer!r} is invalid; must be one of {_WRITER_CLASSES}"
            )
        if self.op not in _OPS:
            raise ValueError(f"op {self.op!r} is invalid; must be one of {_OPS}")
        if self.trust not in TRUST_CLASSES:
            raise ValueError(f"trust {self.trust!r} is invalid; must be one of {TRUST_CLASSES}")


def new_provenance(
    writer: WriterClass,
    session: str,
    op: Op,
    page: str,
    supersedes: str | None = None,
    trust: str | None = None,
) -> Provenance:
    """Build a new `Provenance` record: fresh write_id (ULID) + current UTC ts.

    When `trust` is not given it derives from the writer alone
    (`trust_class(writer, producer="")`): human → "user", else "model".
    Callers that know the producer (the queue) pass trust explicitly — the
    only path that can yield "foreign". This default closes the rev-t6 gap
    where human-driven paths with no producer in scope (revert, install
    founding pages) were silently stamped "model".

    Raises ValueError if `writer`, `op`, or `trust` aren't one of the frozen
    values (enforced by `Provenance.__post_init__`, so direct dataclass
    construction is validated the same way).
    """
    if trust is None:
        trust = trust_class(writer, "")
    write_id = f"w-{ULID()}"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Provenance(
        write_id=write_id,
        ts=ts,
        writer=writer,
        session=session,
        op=op,
        page=page,
        supersedes=supersedes,
        trust=trust,
    )


def _render_ren_lines(prov: Provenance) -> list[str]:
    """Render the `ren_*` key: value lines for `prov`, quoted so PyYAML always
    reads them back as `str` (an unquoted ISO-8601 `ren_ts` would otherwise be
    silently resolved to a `datetime` object by PyYAML's implicit timestamp tag)."""
    lines = [
        f'ren_write_id: "{prov.write_id}"',
        f'ren_ts: "{prov.ts}"',
        f'ren_writer: "{prov.writer}"',
        f'ren_op: "{prov.op}"',
        f'ren_trust: "{prov.trust}"',
    ]
    if prov.supersedes is not None:
        lines.append(f'ren_supersedes: "{prov.supersedes}"')
    return lines


def stamp_frontmatter(md_text: str, prov: Provenance) -> str:
    """Upsert `prov`'s `ren_*` keys into `md_text`'s YAML frontmatter.

    - If frontmatter exists: any existing `ren_*` lines are replaced in place
      (no duplicates); every other line (other keys, blank lines, comments) and
      the body are left untouched, byte-for-byte.
    - If no frontmatter exists (or it's malformed/unterminated): a new
      frontmatter block containing only the `ren_*` keys is prepended, and the
      original `md_text` is kept as the body, byte-for-byte.
    """
    match = _FRONTMATTER_RE.match(md_text)
    new_lines = _render_ren_lines(prov)

    if match is None:
        fence = "---\n" + "\n".join(new_lines) + "\n---\n"
        return fence + md_text

    fm_content = match.group(1)
    body = md_text[match.end():]

    ren_key_re = re.compile(r"^(" + "|".join(_REN_KEYS) + r"):")
    kept_lines = [
        line for line in fm_content.split("\n") if not ren_key_re.match(line)
    ]
    # Drop a single trailing blank line so we don't accumulate blank lines across
    # repeated stampings (kept_lines may end with "" if the old ren_* block was
    # the last thing before the closing fence).
    if kept_lines and kept_lines[-1] == "":
        kept_lines.pop()

    rebuilt_content = "\n".join(kept_lines + new_lines)
    return f"---\n{rebuilt_content}\n---\n{body}"


def read_frontmatter_provenance(md_text: str) -> dict | None:
    """Read the `ren_*` provenance keys from `md_text`'s YAML frontmatter.

    Returns a dict with keys `write_id`, `ts`, `writer`, `op`, `supersedes`
    (`supersedes` is `None` when absent), or `None` if there's no frontmatter or
    no `ren_write_id` key in it (i.e. the page has never been stamped).
    """
    match = _FRONTMATTER_RE.match(md_text)
    if match is None:
        return None

    data = yaml.safe_load(match.group(1))
    if not isinstance(data, dict) or "ren_write_id" not in data:
        return None

    return {
        "write_id": data.get("ren_write_id"),
        "ts": data.get("ren_ts"),
        "writer": data.get("ren_writer"),
        "op": data.get("ren_op"),
        "supersedes": data.get("ren_supersedes"),
        "trust": data.get("ren_trust"),
    }


__all__ = [
    "WriterClass",
    "Op",
    "TRUST_CLASSES",
    "trust_class",
    "Provenance",
    "new_provenance",
    "stamp_frontmatter",
    "read_frontmatter_provenance",
]
