"""lib.memory.page_types — the ONE table mapping a wiki page's path to its
frontmatter `type:` (spec 2026-08-21 §2.2).

Two consumers share this module so the write door and the backfill migration
can never disagree about what a page's type should be:

  1. `lib.memory.queue.propose()` — fills a missing `type:` on new content
  2. `migrations/frontmatter-type-1/` — the one-shot backfill

`skills.wiki-health.lib.lint`'s `missing-frontmatter-type` rule checks only
that a `type:` is PRESENT, never what it should be, so it does not import
this module today. It is the natural third consumer if a rule ever validates
the value.

`skills.wrap.lib._ensure_l1_type` overlaps benignly: it stamps `type: l1` on
an L1 narrative before the proposal reaches the door, and I1 means whatever
it set wins. Both agree on `l1`, so there is nothing to reconcile — but if
the two ever disagree, THIS module is the source of truth.

Two invariants (spec §2.3):

  I1 — never override an existing `type:`. Derivation fills a MISSING value
       only, so a human's hand-set type is never renamed out from under them.
  I2 — an unmapped path gets no stamp and raises no error. It stays untyped
       and the lint still flags it as a judgment call. Without I2 the rule
       becomes dead code and a novel path shape lands mistyped forever.

WHERE this is called matters as much as what it returns: `propose()` applies
it UPSTREAM of `_normalize_body()`. A `type:` added downstream (i.e. in
`provenance.stamp_frontmatter`) would sit outside the duplicate-comparison
boundary, and every idempotent re-write would register as a real change.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Final

# NOTE the `^` and re.MULTILINE, and that group(1) KEEPS its trailing
# newline. The obvious `r"\A---\n(.*?)\n---\n"` does NOT match an EMPTY
# frontmatter fence ("---\n---\n"), because there is no `\n` before the
# closing `---`. With that regex `ensure_type` would treat an empty fence as
# "no frontmatter" and prepend a SECOND fence, emitting malformed output.
# This is the same shape a reviewer already caught once in wrap's
# `_ensure_l1_type` (see `test_l1_empty_frontmatter_gains_type`).
_FRONTMATTER_RE: Final[re.Pattern[str]] = re.compile(
    r"\A---\n(.*?)^---\n", re.DOTALL | re.MULTILINE
)
_FM_TYPE_RE: Final[re.Pattern[str]] = re.compile(r"^type:\s*(.+)$", re.MULTILINE)

# Detects an OPENING fence only ("does this text claim to have frontmatter at
# all"), tolerant of CRLF. Deliberately looser than `_FRONTMATTER_RE` — it is
# the fail-safe guard `ensure_type` uses to tell "no frontmatter" apart from
# "frontmatter this module's stricter regex could not confidently parse".
_OPENING_FENCE_RE: Final[re.Pattern[str]] = re.compile(r"\A---\r?\n")

_ROOT_FILES: Final[dict[str, str]] = {
    "identity.md": "identity",
    "log.md": "log-entry",
    "LICENSES.md": "licenses",
    "index.md": "l2-map",
}

_PROJECT_FILES: Final[dict[str, str]] = {
    "map.md": "l2-map",
    "overview.md": "overview",
    "schema.md": "project-schema",
    "open-work.md": "open-work",
    "instructions.md": "project-instructions",
}

_HUB_EXCLUDED_PARTS: Final[frozenset[str]] = frozenset({"raw", "archive"})


def _is_folder_note_hub(parts: tuple[str, ...]) -> bool:
    """`<dir>/<dirname>.md` under a project knowledge tree.

    THE folder-note predicate (#76) — `skills.wiki-health.lib.lint._is_hub_page`
    imports this rather than re-deriving it. Note the lint ALSO treats any
    `index.md` as a hub; that is a different question (should hub-entry
    maintenance run?) from this module's (what `type:` does the page carry?),
    and root index.md is a correct `l2-map` here and a correct hub there.

    String-scoped so a project literally NAMED "knowledge"
    (projects/knowledge/notes/notes.md) cannot false-positive.
    """
    if len(parts) <= 2:
        return False
    if parts[-1] != f"{parts[-2]}.md":
        return False
    if parts[0] != "projects" or "knowledge" not in parts[2:-1]:
        return False
    return not any(p.startswith(".") or p in _HUB_EXCLUDED_PARTS for p in parts)


def derive_type(page: str) -> str | None:
    """The `type:` for `page`, or `None` when no rule matches (I2).

    Rules are ordered; first match wins. Rule 2 precedes rule 3 so a
    `lessons.md` folder note is a `hub`, not a `lesson`. Rule 3 precedes
    rule 5 so a project-scoped lesson is a `lesson` — kind wins over
    location (spec §2.4).
    """
    parts = PurePosixPath(page).parts
    if not parts:
        return None
    name = parts[-1]

    # Rule 1 — a project's own top-level files. Direct children ONLY: exactly
    # three segments. `projects/<slug>/knowledge/schema.md` is four and must
    # fall through to rule 5.
    if len(parts) == 3 and parts[0] == "projects" and name in _PROJECT_FILES:
        return _PROJECT_FILES[name]

    # Rule 2 — folder-note hubs.
    if _is_folder_note_hub(parts):
        return "hub"

    # Rule 2b — the root-level `lessons/` folder note (#76.3). Deliberately a
    # narrow rule rather than widening `_is_folder_note_hub` past its
    # `projects/` scoping: that predicate is now shared with the lint, so
    # widening it would change which pages the lint treats as hubs. The
    # scoping is also load-bearing — it exists so a project literally named
    # "knowledge" cannot false-positive. See spec 2026-08-21 (0.8.2) §3.3.
    if len(parts) == 2 and parts[0] == "lessons" and name == "lessons.md":
        return "hub"

    # Rule 3 — lessons, global or project-scoped (kind wins over location).
    if len(parts) >= 2 and parts[-2] == "lessons":
        return "lesson"

    # Rule 4 — session narratives, including archived ones. Anchored to the
    # file's IMMEDIATE parent (spec §2.4's `**/l1/*.md` glob), matching how
    # rules 3 and 5 anchor to a fixed position rather than "anywhere in the
    # path" — `archive/l1/sub/session-z.md` is not a direct child of `l1/`
    # and must fall through to I2.
    if len(parts) >= 2 and parts[-2] == "l1":
        return "l1"

    # Rule 5 — everything else under a project knowledge tree.
    if len(parts) > 3 and parts[0] == "projects" and parts[2] == "knowledge":
        return "project-knowledge"

    # Rule 6 — the wiki root's own files.
    if len(parts) == 1 and name in _ROOT_FILES:
        return _ROOT_FILES[name]

    return None


def ensure_type(md_text: str, page: str) -> str:
    """Return `md_text` with a derived `type:` present in its frontmatter.

    Returns the text UNCHANGED when it already declares a `type:` (I1) or
    when no rule matches `page` (I2). Otherwise inserts `type: <derived>` as
    the first frontmatter line, creating a frontmatter block if there is none.
    """
    match = _FRONTMATTER_RE.match(md_text)
    if match is not None and _FM_TYPE_RE.search(match.group(1)):
        return md_text  # I1

    if match is None and _OPENING_FENCE_RE.match(md_text):
        # `md_text` claims to have frontmatter (it opens with a `---` fence)
        # but `_FRONTMATTER_RE` — deliberately stricter than
        # `provenance.py`'s/`lint.py`'s, so it correctly handles an EMPTY
        # fence rather than mistaking it for "no frontmatter" — could not
        # parse it with confidence (e.g. a trailing space or missing
        # newline after the closing fence, or CRLF line endings). Do not
        # guess: prepending a second fence here would emit a page with two
        # frontmatter blocks and could duplicate an already-set `type:`,
        # violating I1. The safe action is to leave the text untouched and
        # let wiki-health lint flag the malformed frontmatter for a human.
        return md_text

    derived = derive_type(page)
    if derived is None:
        return md_text  # I2

    if match is None:
        return f"---\ntype: {derived}\n---\n{md_text}"
    # group(1) keeps its own trailing newline (or is "" for an empty fence),
    # so there is deliberately no `\n` between it and the closing fence here.
    return f"---\ntype: {derived}\n{match.group(1)}---\n{md_text[match.end():]}"


__all__ = ["derive_type", "ensure_type"]
