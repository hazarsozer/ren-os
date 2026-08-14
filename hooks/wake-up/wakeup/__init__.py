"""
ren-wake-up lib — composition layer for the SessionStart wake-up hook (Task 5.1,
RenOS 0.2 Phase 5).

Pure-logic functions for assembling the additionalContext payload:
  - detect_project(cwd, wiki_root) → project slug or None
  - read_l1(project_dir) → most recent L1 session page, quarantine banner intact
  - read_l2_map(project_dir) → the project's L2 pointer-map (projects/<slug>/map.md)
  - read_live_routines(wiki_root) → live-automations digest (carried from donor)
  - rank_extras(...) → heuristic-ranked additional pages, salience-boosted
  - estimate_tokens / truncate_text_to_tokens → the byte-budget mechanism
  - compose_wake_up_context(...) → orchestrator

Substrate CARRIED from donor `hooks/wake-up/wakeup/__init__.py` (per the harvest
map): the truncate-with-marker budget mechanism, project detection (cwd vs a
configurable dev root), and live-routine surfacing. What CHANGED (spec §3.1 +
§3.2):
  - Payload content: L1 (quarantine-bannered) + L2 map for the active project,
    NOT donor's master index + log-tail (that pair is dropped entirely).
  - Ranking: additional pages beyond L1/L2 are chosen by
    `skills.recall.lib.rank` (Task 4.3's heuristic — token overlap + recency +
    path-kind hints), reached via `importlib.import_module("skills.recall.lib")`
    per the hyphen-safe pattern noted in Task 4.4 (recall has no hyphen, but the
    pattern is used consistently everywhere the hook reaches into `skills/`).
  - Salience boost: pages behind an APPLIED queue entry whose proposal carried
    `salience=True` (Task 4.2's pin/correction verb) are moved to the front of
    the ranked extras.
  - Instrumentation: every composed payload calls
    `lib.instrument.miss_log.log_surface` (the pages actually surfaced) and
    `lib.instrument.collect.record(KIND_INJECTED_BYTES, ...)` — this is what
    makes G12's mechanical miss rate computable (Task 3.3).

Cache-line discipline (ADR-008, inviolable): this module only supplies TEXT for
`hookSpecificOutput.additionalContext` — it never touches the system-prompt
prefix. No LLM call anywhere in this module (verified by
`tests/hooks/test_wakeup.py`'s source-scan test).

RenOS 0.4.1 "trust hardening" (spec §4 L1-exemption amendment): extras (the
ranked "Related pages" section) exclude every page `lib.memory.quarantine`
considers quarantined — that channel is where foreign/ingested content
travels, so it gets the read-time exclusion.

RenOS 0.5.5 (spec §4.5 amendment): the L1 exemption is extended to two more
of RenOS's own structural artifacts — the project OVERVIEW (`overview.md`)
and the L2 KNOWLEDGE MAP (`map.md`). All three are RenOS's own
path-constrained structural writes (wrap/bootstrap `llm-auto` output at a
fixed, non-arbitrary path), not free-form foreign content — a quarantine
banner on any of them is a routine consequence of the ordinary llm-auto
write path, not a trust signal about the content itself. All three inject
WITH their quarantine banner intact when quarantined: the banner alone
(data-not-instruction) is the correct signal, and dropping the content from
context would break continuity for no trust benefit. The FOREIGN check is
unaffected by this amendment: a page stamped `ren_trust: "foreign"` (i.e.
`ingest-project`'s repo-scan writes) is still held out of all three
sections and counted in the "N quarantined page(s) held out" line
regardless of banner state — only the quarantine-withhold half of
`_withhold_untrusted` is lifted for these three sections, not the
foreign-stamp half. The IDENTITY section keeps the full `_withhold_untrusted`
check (quarantine AND foreign): `identity.md` is user-written, so a
quarantined identity is anomalous, not routine, and stays withheld. See
`read_l1`'s docstring for the same point at the call site.

Codex F1 (0.5.5 live drill, release-blocker): the extras discovery path
(`_discover_extra_candidates`/`rank_extras`) rediscovers every `*.md` wiki
page by raw path and injects it via `_read_text_safe`, entirely bypassing
the skeleton-suppression sections 1-4 apply via `read_identity`/
`read_overview` — a still-skeleton identity.md or overview.md leaked its
placeholder body into "## Possibly relevant now" for the whole pre-fill
period. Fixed two ways, both in the extras path: (1) `_is_skeleton_or_empty_page`
excludes any candidate whose frontmatter-stripped body is skeleton/empty
(reuses `_is_overview_skeleton_or_empty`, the same check `read_overview`
uses) — a general net, not scoped to any particular page; (2)
`compose_wake_up_context` excludes the exact rel-paths sections 1-4 look at
(`identity.md`, the active project's `overview.md`/`map.md`, every L1
session file) from the extras candidate pool regardless of whether that
section actually injected anything this compose — see `dedicated_paths` at
the call site. The two are independent and both needed: (1) alone misses a
FILLED overview (real body, not skeleton-shaped) that would otherwise
duplicate into extras; (2) alone misses a skeleton page reachable OUTSIDE
the four dedicated paths (e.g. a stray bootstrap-stamped template).

Codex F1 follow-up (0.5.5, live-reproduced against the 219f9d3 fix above):
that fix's `_is_overview_skeleton_or_empty` only recognized ONE skeleton
shape — a body reducing to a single heading line (overview.md's shape) —
so `index.md`/`LICENSES.md`/the venture module templates, which use a
DIFFERENT idiom (headings interleaved with whole-line ITALIC placeholder
prompts, identity.md's shape), still leaked verbatim. `_body_has_real_content`
(consolidated from identity's own heading+italic check) is now the ONE
shared predicate both `_is_overview_skeleton_or_empty` (and, through it,
`_is_skeleton_or_empty_page`) and `_identity_is_filled` call, so a
wholly-placeholder page of EITHER shape is excluded from the extras
candidate pool. That alone isn't sufficient for `index.md`/`LICENSES.md`
specifically — they mix real documentation prose with unanswered `_..._`
prompts, so `_body_has_real_content` correctly keeps them as candidates —
so every extras page now also runs through `_strip_extras_placeholder_lines`
at injection (mirrors `read_identity`'s own stripping) to remove just the
still-unanswered prompt lines, never the surrounding real content. Known
limitation, accepted: a user's genuine heading-only one-line stub, or a
real paragraph written as a single whole-line-italic line, may be treated
as placeholder — dropped from extras ELIGIBILITY in the first case, or
stripped from the injected text in the second. Both are low-harm (the page
stays reachable by name) and affect auto-surfacing only.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

import yaml

from .doctrine_card import (
    SECTION_DOCTRINE,
    render_doctrine_card,
    render_doctrine_card_compact,
    superpowers_installed,
)
from lib.instrument import collect, miss_log
from lib.instrument.calibration import PLAUSIBLE_RATIO_BAND
from lib.memory import archive, queue, quarantine
from lib.memory.provenance import read_frontmatter_provenance
from lib.ren_paths import DEFAULT_DEV_ROOT_REL, detect_project, resolve_dev_root, state_dir, wiki_root
from lib.skeleton import wiki_stamped

logger = logging.getLogger(__name__)


L1_DIRNAME: Final[str] = "l1"
L2_MAP_FILENAME: Final[str] = "map.md"
MASTER_ROUTINES_DIRNAME: Final[str] = "routines"
_SUGGESTION_LIST_CAP: Final[int] = 5
SALIENCE_WINDOW_DAYS: Final[int] = 30

# Token budget (ADR-008 heritage: 3-5K target, 5K hard cap)
DEFAULT_MAX_TOKENS: Final[int] = 5_000
CHARS_PER_TOKEN: Final[float] = 4.0  # rough heuristic; tiktoken-free for hook latency

# Per-section token allocations.
IDENTITY_BUDGET: Final[int] = 400
OVERVIEW_BUDGET: Final[int] = 600
L1_BUDGET: Final[int] = 1_200
L2_BUDGET: Final[int] = 1_200
ROUTINE_SPEC_BUDGET: Final[int] = 400
OPENWORK_BUDGET: Final[int] = 400
DOCTRINE_BUDGET: Final[int] = 500
# The doctrine card ships in the plugin rather than living in the wiki, so its
# `_inject_section` pointer names the source in prose instead of a page rel.
DOCTRINE_POINTER: Final[str] = "hooks/wake-up/wakeup/doctrine_card.py (in the installed ren plugin)"
EXTRAS_BUDGET: Final[int] = 1_600   # ranked additional pages, split across however many fit
EXTRA_PAGE_BUDGET: Final[int] = 400  # per-page cap within the extras budget
DEFAULT_EXTRAS_COUNT: Final[int] = 3

IDENTITY_FILENAME: Final[str] = "identity.md"
OVERVIEW_FILENAME: Final[str] = "overview.md"
OPENWORK_FILENAME: Final[str] = "open-work.md"

# `/ren:interview`'s `render_identity` (skills/interview/lib) ALWAYS writes
# this exact set of list fields to identity.md's frontmatter, non-empty only
# when the friend actually answered that question — see `_identity_is_filled`.
_IDENTITY_LIST_FIELDS: Final[tuple[str, ...]] = (
    "languages", "package_managers", "clouds", "databases", "strong_skills", "growth_areas",
)
# The four enum questions `/ren:interview` asks (skills/interview/lib
# QUESTIONS), mapped to their skeleton default — the exact literal each field
# holds in both `identity.md.tmpl` and `render_identity`'s `_DEFAULTS` when
# unanswered. See `_identity_is_filled` (Task 6c-2, 0.5.5 release-blocker):
# a friend who answers ONLY these four and skips every list/contact question
# was previously judged "not filled".
_IDENTITY_ENUM_DEFAULTS: Final[dict[str, str]] = {
    "working_style": "balanced",
    "communication_style": "balanced-with-emoji",
    "plans_before_code": "often",
    "tdd_attitude": "case-by-case",
}
# Every placeholder PROMPT line in identity.md.tmpl / render_identity's body
# is a single markdown line wrapped start-to-end in underscores (whole-line
# italic), e.g. "_One paragraph: who you are..._" — the invariant shared by
# both template variants regardless of their slightly different wording.
_IDENTITY_ITALIC_LINE_RE = re.compile(r"^_.+_$")

# Question-shaped section headers (spec §4.1) — exact strings, relied on by
# tests and Task 6's truncate-marker helper.
SECTION_IDENTITY: Final[str] = "## Who am I working with"
SECTION_OVERVIEW: Final[str] = "## What is this project"
SECTION_L1: Final[str] = "## What happened last session"
SECTION_OPENWORK: Final[str] = "## Open work"
SECTION_L2: Final[str] = "## Where to find project knowledge"
SECTION_ROUTINES: Final[str] = "## Active routines"
SECTION_PENDING: Final[str] = "## Waiting on you"
SECTION_EXTRAS: Final[str] = "## Possibly relevant now"

_GIT_TIMEOUT_S: Final[float] = 3.0

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    """Return `text` with a leading YAML frontmatter block removed, if present."""
    match = _FRONTMATTER_RE.match(text)
    return text[match.end():] if match else text


_MIN_CALIBRATION_SAMPLES: Final[int] = 5
_BUDGET_SHIFT_WARN_FRACTION: Final[float] = 0.25


def _calibrated_chars_per_token() -> float:
    """The calibrated chars-per-token ratio if `lib.instrument.calibration`'s
    loop (0.6.1 E5a) has persisted one, else `CHARS_PER_TOKEN`.

    One small stdlib JSON read of a single-line file — deliberately NOT a
    tokenizer call, so `estimate_tokens` keeps its no-deps/no-latency
    property. Anything unexpected (absent file, unreadable, malformed JSON,
    missing/non-numeric/non-positive ratio) falls back to the constant, same
    tolerance as `lib.instrument.estimator._load_ratio_state`.

    Fix round 3: a positive ratio isn't enough — it must also be plausible.
    `PLAUSIBLE_RATIO_BAND` (mirrored from `lib.instrument.calibration`, which
    already imports cleanly here) is the same band that module uses to reject
    calibration inputs it never measured; a corrupt or hand-edited
    estimator.json (0.5, 50.0, ...) would otherwise silently crush or
    10x-inflate every char budget this ratio now governs.

    Fix round 4 (#48): plausible still isn't enough — it must also be
    SEASONED. A single-sample ratio (the live 2026-08-03 estimator.json held
    exactly one: 2.1813929..., roughly halving every wake-up char budget)
    carries no statistical weight and must never displace the fallback
    constant; `_MIN_CALIBRATION_SAMPLES` is the floor. Once a ratio clears
    that floor and the plausibility band, it's allowed to govern — but if it
    still shifts every budget by more than `_BUDGET_SHIFT_WARN_FRACTION`
    (25%) vs `CHARS_PER_TOKEN`, that swing is logged at WARNING so a
    silently-halved (or doubled) injection budget is visible, not just
    "technically working as designed"."""
    try:
        path = state_dir() / "metrics" / "estimator.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        ratio = float(data["chars_per_token"])
        samples = int(data.get("samples", 0))
    except Exception:  # noqa: BLE001 - a calibration read must never break wake-up
        return CHARS_PER_TOKEN
    if samples < _MIN_CALIBRATION_SAMPLES:
        return CHARS_PER_TOKEN
    low, high = PLAUSIBLE_RATIO_BAND
    if not (low <= ratio <= high):
        return CHARS_PER_TOKEN
    shift = abs(ratio - CHARS_PER_TOKEN) / CHARS_PER_TOKEN
    if shift > _BUDGET_SHIFT_WARN_FRACTION:
        logger.warning(
            "calibrated chars-per-token %.3f shifts every wake-up budget %.0f%% "
            "vs the %.1f fallback", ratio, 100 * shift, CHARS_PER_TOKEN,
        )
    return ratio


def estimate_tokens(text: str) -> int:
    """Rough token count via a chars/ratio heuristic (no tiktoken dep for hook
    latency) — the calibrated ratio when one is stored, else `CHARS_PER_TOKEN`.

    For REPORTING/metrics. Budget arithmetic must use `_budget_tokens` — see
    its docstring."""
    return int(len(text) / _calibrated_chars_per_token())


def _budget_tokens(text: str, chars_per_token: float | None = None) -> int:
    """Token count for BUDGET DECISIONS.

    The decision and the cut must use ONE ratio: `truncate_text_to_tokens`
    converts `max_tokens` to a char cap, and if it converted with 4.0 while
    this said otherwise, a payload could be judged "in budget" while actually
    over it (or be truncated and still exceed the decision's own estimate).

    Fix round 2: that agreement is now reached on the CALIBRATED ratio, not on
    the constant. Round 1 standardized both sides on `CHARS_PER_TOKEN`, which
    made the whole calibration loop a no-op inside wake-up — the measured
    number was read but never acted on. `chars_per_token` is threaded in by
    `compose_wake_up_context`, which reads it ONCE per hook run (one small
    JSON read) and passes the same value to every cut. `None` means "read it
    yourself" (fallback `CHARS_PER_TOKEN` on absent/corrupt state)."""
    return int(len(text) / (chars_per_token or _calibrated_chars_per_token()))


def truncate_text_to_tokens(
    text: str, max_tokens: int, chars_per_token: float | None = None
) -> str:
    """Truncate `text` to fit within `max_tokens`, keeping the TAIL (most
    recent/relevant content) and prefixing a `[...truncated; N chars
    elided...]` marker when anything was cut — content is truncated, never
    silently dropped.

    `chars_per_token` defaults to the CALIBRATED ratio (`None` → read it),
    so the cut and the budget decision that authorized it always agree — see
    `_budget_tokens`."""
    if max_tokens <= 0:
        return ""
    max_chars = int(max_tokens * (chars_per_token or _calibrated_chars_per_token()))
    if len(text) <= max_chars:
        return text
    return f"[...truncated; first {len(text) - max_chars} chars elided...]\n" + text[-max_chars:]


def _inject_section(
    text: str,
    budget: int,
    pointer_rel: str | None = None,
    chars_per_token: float | None = None,
) -> str:
    """Truncate `text` to `budget` tokens via `truncate_text_to_tokens` and,
    when truncation actually removed content (output shorter than input —
    the truncation marker was added), append a
    "\\n*(continues in `{pointer_rel}`)*" pointer line naming the
    section's wiki-relative source file, so the user knows where to find
    the rest. No pointer line is appended when nothing was cut, or when
    `pointer_rel` isn't given (Task 6, 0.5.5 — does not change
    `truncate_text_to_tokens` itself, which has other callers)."""
    truncated = truncate_text_to_tokens(text, budget, chars_per_token)
    if pointer_rel and len(truncated) < len(text):
        truncated = f"{truncated}\n*(continues in `{pointer_rel}`)*"
    return truncated


def _inject_open_work(
    text: str,
    budget: int,
    pointer_rel: str,
    chars_per_token: float | None = None,
) -> str:
    """Budget the open-work ledger HEAD-first, naming what didn't fit.

    `truncate_text_to_tokens` keeps the TAIL, which for this section means an
    over-budget ledger silently drops the OLDEST open threads — the exact
    items most at risk of being forgotten, in the one artifact whose job is
    to not forget them. So this section cuts from the head instead (oldest
    lines survive) and always states how many items are not shown; silent
    loss is the thing being eliminated, not truncation itself.

    Section-local, by the same reasoning that produced the compact doctrine
    card: the shared `truncate_text_to_tokens` is untouched because its
    tail-keeping is correct for its other callers."""
    if budget <= 0:
        return ""
    max_chars = int(budget * (chars_per_token or _calibrated_chars_per_token()))
    if len(text) <= max_chars:
        return text

    lines = text.split("\n")
    kept: list[str] = []
    used = 0
    for line in lines:
        cost = len(line) + 1
        if used + cost > max_chars:
            break
        kept.append(line)
        used += cost

    dropped = len(lines) - len(kept)
    notice = f"*({dropped} more open item(s) not shown; full ledger in `{pointer_rel}`)*"
    return "\n".join(kept + [notice]) if kept else notice


# `resolve_dev_root` and `detect_project` now live in `lib.ren_paths` (codex
# D4 wiring) — imported above, re-exported here so existing callers of
# `wakeup.resolve_dev_root` / `wakeup.detect_project` keep working. Shared
# with `skills/wrap/lib` so wrap's write path and wake-up's read path can
# never resolve a cwd to two different project slugs.


def _read_text_safe(path: Path) -> str:
    """Read a file as text; return "" on any error (missing, permissions,
    binary garbage that doesn't decode as UTF-8, ...). Never raises."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("could not read %s: %s", path, exc)
        return ""


def _most_recent_l1_path(l1_dir: Path) -> Path | None:
    """Return the most recent `session-*.md` file under `l1_dir` (by mtime),
    or `None` if the dir is absent/unlistable or has no matching files.
    Factored out of `read_l1` (Task 6, 0.5.5) so the compose loop can name
    the pointer path for a truncated L1 section without re-deriving the
    same sort/selection logic."""
    if not l1_dir.is_dir():
        return None
    try:
        candidates = sorted(l1_dir.glob("session-*.md"), key=lambda p: _safe_mtime(p), reverse=True)
    except OSError as exc:
        logger.debug("could not list %s: %s", l1_dir, exc)
        return None
    return candidates[0] if candidates else None


def read_l1(project_dir: Path) -> str:
    """Return the most recent L1 session page's raw content (quarantine banner
    intact — it's data-not-instruction, and the hook must not strip that
    signal), or "" if there is no `l1/` dir or no `session-*.md` files, or the
    most recent page fails the stamp check below.

    L1 EXEMPTION (spec §4 amendment, 0.4.1): L1 pages are `llm-auto` and thus
    quarantined like any other unreviewed content, but they are deliberately
    exempt from the extras-side quarantine exclusion (`_discover_extra_candidates`)
    and are always injected here regardless. Rationale: L1 is RenOS's own
    summary of the user's OWN session — not foreign/ingested content — so the
    banner is sufficient signal (data-not-instruction) and the exclusion,
    which targets channels foreign content travels through, does not apply.

    Codex P5 hardening (0.5.1 Task 9): the exemption above previously trusted
    the L1 *path shape* alone — anything dropped at `l1/session-*.md` was
    injected raw, banner or not. That's no longer enough: this now verifies
    the page's OWN `ren_trust` stamp (Task 6) is `"model"` (a genuine RenOS
    write, not a foreign/human-planted file) before applying the exemption.
    A page that IS stamped `"model"` is injected raw regardless of the banner
    (the exemption, as before). A page that is unstamped OR stamped anything
    else (foreign, human, etc.) is held out (empty string) — never injected
    raw on path shape alone. Migration `trust-backfill-1` (Task 7) stamps
    `ren_trust` on every pre-0.5.1 page, so a legitimately old L1 page is
    stamped after migration; an unstamped file at this path post-migration
    has no legitimate explanation and gets the same held-out treatment as a
    foreign-stamped one.
    """
    path = _most_recent_l1_path(project_dir / L1_DIRNAME)
    if path is None:
        return ""
    text = _read_text_safe(path)
    if not text:
        return ""

    # `read_frontmatter_provenance` calls `yaml.safe_load` unguarded, so a page
    # with malformed frontmatter RAISES here — and this call sits outside any
    # try in `compose_wake_up_context`, which must never raise (0.6.5 fix
    # round 1). A page we cannot parse is not a verified model-class write:
    # degrade to held-out, same as an unstamped one.
    try:
        prov = read_frontmatter_provenance(text)
    except Exception:  # noqa: BLE001 - malformed frontmatter is untrusted, never fatal
        logger.debug("could not read L1 provenance from %s", path, exc_info=True)
        return ""
    if prov and prov.get("trust") == "model":
        return text

    # Not a verified model-class RenOS write — held out, whether foreign-
    # stamped or entirely unstamped. Never injected raw on path shape alone.
    return ""


def read_open_work(project_dir: Path) -> str:
    """Return the still-OPEN lines of the project's open-work ledger (0.6.5
    Task 6), or "" when the page is absent, untrusted, or has no open lines.

    Only lines under `## Open` that are still unchecked (`- [ ]`) surface:
    checked lines are done, and `## Archive` holds aged-out closed lines —
    neither is what the session needs at wake-up.

    Trust check follows `read_l1`'s pattern: the page's OWN stamp decides,
    path shape is never trusted. `ren_trust: "model"` is a genuine RenOS
    write (what `reconcile_open_work` produces) and surfaces; `"user"` is the
    template-stamped bootstrap page (`lib.skeleton` stamps skeleton writes
    `writer="human"`) or a friend's own hand-edit, and surfaces too — this
    ledger is explicitly a page humans write lines into, unlike L1. Anything
    else — `"foreign"` above all — is held out, as is an entirely unstamped
    file unless its frontmatter carries the template's own `type: open-work`.
    """
    text = _read_text_safe(project_dir / OPENWORK_FILENAME)
    if not text:
        return ""

    try:
        prov = read_frontmatter_provenance(text) or {}
    except Exception:  # noqa: BLE001 - malformed frontmatter is untrusted, never fatal
        logger.debug("could not read open-work provenance", exc_info=True)
        return ""
    trust = prov.get("trust")
    if trust not in ("model", "user"):
        if trust is not None:
            return ""
        if _parse_frontmatter_dict(text).get("type") != "open-work":
            return ""

    open_lines: list[str] = []
    in_open = False
    for line in _strip_frontmatter(text).splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_open = stripped == "## Open"
            continue
        if in_open and stripped.startswith("- [ ] "):
            open_lines.append(stripped)
    return "\n".join(open_lines)


def read_l2_map(project_dir: Path) -> str:
    """Return the project's L2 pointer-map content (`map.md`), or "" if absent.

    Quarantine banner intact — this function only reads the file. The
    foreign-stamp CHECK (and the decision to hold it out of the payload)
    happens in `compose_wake_up_context`: as of the spec §4.5 amendment, the
    L2 map gets the same structural-artifact exemption as L1 for the
    quarantine-withhold check (it's RenOS's own path-constrained write, not
    free-form foreign content) and injects with its banner intact — only a
    `ren_trust: "foreign"` stamp still holds it out.
    """
    return _read_text_safe(project_dir / L2_MAP_FILENAME)


def _parse_frontmatter_dict(text: str) -> dict:
    """Parse `text`'s leading YAML frontmatter block (if any) into a dict via
    `yaml.safe_load`. Returns {} on any parse failure, malformed YAML, or
    absent frontmatter — never raises. Distinct from
    `read_frontmatter_provenance`, which only surfaces the `ren_*` provenance
    subset: `/ren:interview`'s real answers land in plain (non-`ren_*`)
    frontmatter keys, which is what this reads."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _body_has_real_content(body: str) -> bool:
    """True if `body` (frontmatter already stripped) has at least one line
    that isn't blank, an HTML comment, a markdown heading, or a whole-line
    italic placeholder prompt (see `_IDENTITY_ITALIC_LINE_RE`) — i.e. a human
    actually wrote something, independent of whatever the frontmatter says.

    Shared by `_identity_is_filled`'s body-content fallback and the general
    extras skeleton/placeholder gate (`_is_overview_skeleton_or_empty`, and
    via it `_is_skeleton_or_empty_page`) — Codex F1 0.5.5 follow-up: the two
    were separate, heading-only-shaped checks (one recognized identity's
    heading+italic idiom, the other only overview's heading-only idiom)
    until this consolidation. `_is_skeleton_or_empty_page`'s predecessor
    only caught the heading-only shape, so a heading+italic-only page
    (index.md, LICENSES.md, the venture module templates) read as "has
    content" and leaked into extras — this is the general predicate both
    idioms now share."""
    without_comments = _OVERVIEW_HTML_COMMENT_RE.sub("", body)
    for line in without_comments.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _IDENTITY_ITALIC_LINE_RE.match(stripped):
            continue
        return True
    return False


def _identity_is_filled(text: str, body: str) -> bool:
    """True if `/ren:interview` (or a hand edit) has actually populated this
    identity page.

    `skills.interview.lib.render_identity` ALWAYS writes the exact same
    placeholder BODY regardless of the answers given — the interview's real
    answers land only in frontmatter fields (`_IDENTITY_LIST_FIELDS`,
    `contact.timezone`, `contact.working_hours`, and the four enum fields in
    `_IDENTITY_ENUM_DEFAULTS`). A body-level skeleton check (the shape
    `read_overview` uses) would therefore suppress identity forever, even for
    a fully interviewed friend — so "filled" is judged from the frontmatter
    first, falling back to real body content only for a hand edit that
    bypassed the interview's frontmatter fields entirely.

    Task 6c-2 (0.5.5 release-blocker, codex-reported): the original version
    of this check only looked at the list fields and contact — a friend who
    answered ONLY the four enum questions (working_style, communication_style,
    plans_before_code, tdd_attitude) and skipped everything else was judged
    "not filled". The enum check below fixes that: a field present in
    frontmatter with a value other than its skeleton default counts as real
    signal. `skipped_questions` is deliberately NOT used as a signal here —
    the bootstrap-stamped skeleton and a fully-answered interview can both
    yield `skipped_questions: []`, so an empty list can't distinguish
    pristine-skeleton from fully-filled.

    Known limitation (acceptable, not fixed): if a friend's real answers
    happen to equal every enum default AND all lists are empty AND contact is
    empty AND the body is placeholder-only, identity is indistinguishable
    from a pristine skeleton and stays omitted — vanishingly unlikely, and
    low-harm since injecting all-default values would add no signal anyway.
    """
    fm = _parse_frontmatter_dict(text)
    for field in _IDENTITY_LIST_FIELDS:
        value = fm.get(field)
        if isinstance(value, list) and value:
            return True
    contact = fm.get("contact")
    if isinstance(contact, dict):
        timezone_ = str(contact.get("timezone") or "").strip()
        working_hours = str(contact.get("working_hours") or "").strip()
        if timezone_ or working_hours:
            return True
    for field, default in _IDENTITY_ENUM_DEFAULTS.items():
        if field in fm and fm.get(field) != default:
            return True
    return _body_has_real_content(body)


def _strip_placeholder_lines(body: str) -> str:
    """Remove every whole-line italic placeholder prompt (see
    `_IDENTITY_ITALIC_LINE_RE`) from `body`, preserving everything else —
    headings, blank lines, and any real hand-written line — byte-for-byte.

    Originally identity-only ("once identity is judged 'filled'
    (`_identity_is_filled`), the ~370 placeholder tokens in the untouched
    body would otherwise crowd the real signal — the frontmatter — out of
    `IDENTITY_BUDGET`"). Generalized (Codex F1 0.5.5 follow-up) for
    `_strip_extras_placeholder_lines`: a page mixing real prose with
    unanswered `_..._` prompts (index.md, LICENSES.md) correctly stays an
    extras candidate — `_body_has_real_content` finds the real prose — but
    its still-unanswered prompt lines must not leak verbatim into the
    payload either."""
    lines = body.splitlines(keepends=True)
    kept = [line for line in lines if not _IDENTITY_ITALIC_LINE_RE.match(line.strip())]
    return "".join(kept)


def _strip_extras_placeholder_lines(text: str) -> str:
    """Frontmatter-preserving `_strip_placeholder_lines` for the extras
    injection path (Codex F1 0.5.5 follow-up): every page surfaced via
    "## Possibly relevant now" is run through this before injection, not
    just the ones the general skeleton gate (`_is_skeleton_or_empty_page`)
    excludes outright — a page can legitimately clear that gate (it has
    SOME real content) while still carrying whole-line italic placeholder
    prompts alongside it (index.md, LICENSES.md ship exactly this shape:
    real documentation prose interleaved with per-section `_..._` prompts).
    Frontmatter itself is never touched — only the body past it."""
    match = _FRONTMATTER_RE.match(text)
    frontmatter_prefix = text[: match.end()] if match else ""
    body = text[match.end() :] if match else text
    return frontmatter_prefix + _strip_placeholder_lines(body)


def read_identity(wiki_root: Path) -> str:
    """Return the top-level `identity.md`'s content, or "" if absent, empty,
    or still unfilled — skeleton-default frontmatter (never answered via
    `/ren:interview` or by hand) with a placeholder body — a friend who
    skipped onboarding should not have placeholder boilerplate injected as if
    it were real identity signal. See `_identity_is_filled` for why this
    check reads the frontmatter rather than the body.

    When filled, the placeholder body's italic prompt lines are stripped
    before returning (`_strip_placeholder_lines`) so they don't crowd the
    real frontmatter signal out of the token budget; any real, hand-written
    body content is preserved untouched.
    """
    text = _read_text_safe(wiki_root / IDENTITY_FILENAME)
    if not text:
        return ""
    body = _strip_frontmatter(text)
    if not body.strip():
        return ""
    if not _identity_is_filled(text, body):
        return ""

    match = _FRONTMATTER_RE.match(text)
    frontmatter_prefix = text[:match.end()] if match else ""
    return frontmatter_prefix + _strip_placeholder_lines(body)


_OVERVIEW_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _is_overview_skeleton_or_empty(body: str) -> bool:
    """True if `body` (frontmatter already stripped) carries no real content
    of its own — i.e. it's a shipped skeleton (headings, HTML comments,
    and/or whole-line italic placeholder prompts only, per
    `_body_has_real_content`) or genuinely empty/whitespace.

    Was heading-only-shaped (`len(lines) == 1 and lines[0].startswith("#")`)
    to mirror `skills.wrap.lib._is_skeleton_or_empty_body` exactly, which is
    all `overview.md.tmpl` (heading + HTML comment) needs. Widened (Codex F1
    0.5.5 follow-up) to `_body_has_real_content` so the SAME check also
    recognizes the heading + whole-line-italic-prompt idiom used by
    index.md/LICENSES.md/identity.md/the venture module templates — see
    `_is_skeleton_or_empty_page`, the general extras-candidate gate this
    function backs. Still NOT imported from `skills.wrap.lib` (hooks must
    not import skills; see module docstring's layering note) — replicated,
    now with the wider shape."""
    return not _body_has_real_content(body)


def read_overview(project_dir: Path) -> str:
    """Return the project's `overview.md` content, or "" if absent, empty, or
    still the shipped skeleton (a heading plus an HTML comment — never
    replaced because wrap's `maintain_overview` has never judged a session's
    narrative a material change) — same "no placeholder injected as real
    signal" doctrine as `read_identity`, applied at the body level since,
    unlike identity, overview's skeleton body IS the entire unfilled signal
    (there's no separate frontmatter fields an interview populates).

    Foreign-trust CHECK happens in `compose_wake_up_context` (via
    `_is_foreign`), same pattern as `read_l2_map` — spec §4.5 amendment:
    a quarantined-but-not-foreign overview injects with its banner intact.
    """
    text = _read_text_safe(project_dir / OVERVIEW_FILENAME)
    if not text:
        return ""
    if _is_overview_skeleton_or_empty(_strip_frontmatter(text)):
        return ""
    return text


def _is_foreign(content: str) -> bool:
    """True if `content` is `ren_trust: "foreign"`-stamped. Shared by every
    section, exempt or not — the foreign-stamp check is never lifted, only
    the quarantine-withhold check is (spec §4.5 amendment; see module
    docstring). Never raises: any provenance-read failure degrades to "not
    foreign" (never silently drops legitimate content).
    """
    if not content:
        return False
    try:
        prov = read_frontmatter_provenance(content)
        return bool(prov and prov.get("trust") == "foreign")
    except Exception:  # noqa: BLE001 - provenance parse failure must never abort wake-up
        logger.debug("read_frontmatter_provenance failed", exc_info=True)
        return False


def _withhold_untrusted(content: str) -> bool:
    """True if `content` should be held out of the wake-up payload: either
    banner-quarantined or `ren_trust: foreign`-stamped. Used by sections that
    do NOT get the structural-artifact exemption (identity only, as of the
    spec §4.5 amendment — L1, overview, and the L2 map inject quarantined
    content with the banner intact and only withhold on the foreign-stamp
    check via `_is_foreign`; see module docstring). Never raises: any
    quarantine/provenance-read failure degrades to "not withheld" (never
    silently drops legitimate content, per hook failure doctrine).
    """
    if not content:
        return False
    quarantined = False
    try:
        quarantined = quarantine.is_quarantined(content)
    except Exception:  # noqa: BLE001 - quarantine check failure must never abort wake-up
        logger.debug("quarantine.is_quarantined failed", exc_info=True)
    return quarantined or _is_foreign(content)


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


_ROUTINE_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_routine_fields(content: str) -> dict[str, str]:
    """Tiny dependency-free frontmatter field reader (no PyYAML at hook runtime)."""
    m = _ROUTINE_FM_RE.match(content)
    if not m:
        return {}
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip().strip('"').strip("'")
    return fields


def read_live_routines(wiki_root: Path) -> str:
    """Scan `wiki/routines/` for routine-spec pages; one-line-per-routine
    digest. Returns "" if no routines/ dir or no routine-spec pages. Carried
    from donor (ADR-034 heritage)."""
    routines_dir = wiki_root / MASTER_ROUTINES_DIRNAME
    if not routines_dir.is_dir():
        return ""
    try:
        paths = sorted(routines_dir.glob("*.md"))
    except OSError as exc:
        logger.debug("could not scan routines dir %s: %s", routines_dir, exc)
        return ""
    rows: list[str] = []
    for path in paths:
        fm = _parse_routine_fields(_read_text_safe(path))
        if fm.get("type") != "routine-spec":
            continue
        name = fm.get("name", path.stem)
        trigger = fm.get("trigger_type", "?")
        repo = fm.get("linked_repo", "?")
        rows.append(f"- **{name}** · {trigger} · {repo}")
    return "\n".join(rows)


def suggestion_line() -> str:
    """Multi-line block announcing pending queue entries (v2.2: suggestions are
    conversational, not a queue verb — Task 8). Lists up to `_SUGGESTION_LIST_CAP`
    pending items with their page and reason; returns "" when nothing is pending,
    so the payload gains nothing on the common case.

    Counts only suggestion-classified entries (a `global/` target, or
    produced by `"retrospective"`, WITHOUT a `contradicts` conflict) toward
    "N suggestion(s)" — a contradiction hold is not a suggestion (matches
    `skills.wrap.lib.render_wrap_screen`'s classification order: contradicts
    wins first). If any contradiction holds exist, appends a second count.

    Returns a multi-line block with: count line + up to _SUGGESTION_LIST_CAP item
    lines (qid → page — reason) + overflow line if needed. This replaces the old
    bare count announcement so the user can see what they're answering without
    scrolling."""
    try:
        entries = queue.pending()
    except Exception:  # noqa: BLE001 - never let this abort the wake-up payload
        logger.debug("queue.pending() failed", exc_info=True)
        entries = []

    lines: list[str] = []

    if entries:
        held = 0
        suggested = 0
        for entry in entries:
            if any(c.get("kind") == "contradicts" for c in (entry.conflicts or [])):
                held += 1
            else:
                suggested += 1

        parts = []
        if suggested:
            plural = "" if suggested == 1 else "s"
            parts.append(f"{suggested} suggestion{plural}")
        if held:
            plural = "" if held == 1 else "s"
            parts.append(f"{held} contradiction hold{plural}")

        if parts:
            lines.append(f"{' and '.join(parts)} waiting — answer in chat or ignore:")
            for entry in entries[:_SUGGESTION_LIST_CAP]:
                reason = entry.proposal.reason or ""
                lines.append(f"- {entry.qid} → {entry.proposal.page} — {reason}")
            overflow = len(entries) - _SUGGESTION_LIST_CAP
            if overflow > 0:
                lines.append(f"- …and {overflow} more — ask me to list them")

    store_line = _suggestions_store_line()
    if store_line:
        lines.append(store_line)

    return "\n".join(lines)


def _suggestions_store_line() -> str:
    """Pointer line for `lib.suggestions` (Task 14's separate suggestion
    store, distinct from the queue) — announces its own pending count when
    non-empty. Never raises: any store-read failure degrades to ""."""
    try:
        from lib import suggestions

        entries = suggestions.pending_suggestions()
    except Exception:  # noqa: BLE001 - never let this abort the wake-up payload
        logger.debug("lib.suggestions.pending_suggestions() failed", exc_info=True)
        return ""
    if not entries:
        return ""
    n = len(entries)
    return f"{n} instruction suggestion(s) pending — run /ren:suggestions to review."


JOURNAL_FILENAME: Final[str] = "journal.jsonl"
WATERMARK_FILENAME: Final[str] = "wiki_lint_watermark.json"


def _unlinted_count() -> int:
    """Number of append-only journal lines past the wiki-lint watermark —
    i.e. how many recorded wiki writes no lint pass has looked at yet (0.6.5
    Task 5).

    Deliberately reads `state_dir()/journal.jsonl` and
    `state_dir()/wiki_lint_watermark.json` DIRECTLY with stdlib rather than
    calling `skills.wiki-health.lib.watermark.unlinted()`: the wake-up hook is
    py3.9-safe, stdlib-only and latency-sensitive, and must not import skill
    packages (see the layering note in `_is_overview_skeleton_or_empty`). The
    file shapes are Task 2's contract — one JSON object per journal line, and
    a flat `{"journal_lines_seen": int, "clean": bool, "stamped_at": str}`
    stamp.

    Keyed on the COUNT, never on the stamp's `clean` flag: `clean` is
    wiki-global, so a single unresolved finding anywhere would otherwise make
    this a permanent nudge.

    Never raises: an absent/unreadable/corrupt journal or watermark yields 0
    (no nudge), same failure doctrine as every other producer here."""
    try:
        with (state_dir() / JOURNAL_FILENAME).open(encoding="utf-8") as handle:
            # Blank lines are skipped, matching how the journal's own reader
            # (`lib.memory.journal.entries`) counts entries — the watermark is
            # stamped in THOSE units, so the two must agree.
            lines = sum(1 for line in handle if line.strip())
    except (OSError, UnicodeDecodeError):
        logger.debug("could not count journal lines", exc_info=True)
        return 0

    seen = 0
    try:
        data = json.loads((state_dir() / WATERMARK_FILENAME).read_text(encoding="utf-8"))
        seen = int(data["journal_lines_seen"])
    except Exception:  # noqa: BLE001 - a missing/corrupt stamp means "lint everything"
        logger.debug("could not read lint watermark", exc_info=True)
        seen = 0

    return max(0, lines - seen)


def unlinted_nudge_line() -> str:
    """The wake-up nudge naming the shipped `ren-wiki-lint` agent, or "" when
    the lint watermark is caught up. Appended only alongside REAL content —
    it must never make an otherwise-empty compose look non-empty (the
    loud-notice contract); see `compose_wake_up_context`."""
    n = _unlinted_count()
    if n <= 0:
        return ""
    plural = "y" if n == 1 else "ies"
    return f"{n} journal entr{plural} unlinted — spawn the ren-wiki-lint agent or run /ren:wrap."


def _quarantine_backlog_count() -> int:
    """Non-l1 quarantined pages — the screen's worklist size. Never raises
    (same discipline as _unlinted_count): any error reads as 0, wake-up
    must not die over a nudge."""
    try:
        from pathlib import PurePosixPath

        pages = quarantine.quarantined_rel_pages(wiki_root())
        return sum(1 for rel in pages if "l1" not in PurePosixPath(rel).parts)
    except Exception:  # noqa: BLE001
        return 0


def quarantine_backlog_nudge_line() -> str:
    """One nudge line when quarantined pages await screening; "" otherwise.
    Appended only alongside REAL content — it must never make an otherwise-
    empty compose look non-empty (the loud-notice contract); see
    `compose_wake_up_context`."""
    n = _quarantine_backlog_count()
    if n <= 0:
        return ""
    return (
        f"{n} page(s) in quarantine backlog — the ren-wiki-lint agent screens "
        f"them at /ren:wrap; run /ren:suggestions for ones already held for you."
    )


def _git(cwd: Path, args: list[str]) -> str:
    """Read-only, bounded git subprocess call. Returns "" on ANY failure
    (not a repo, git absent, timeout, non-zero exit) — never raises."""
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=str(cwd), capture_output=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="replace").strip()


def _build_rank_query(project: str | None, cwd: Path) -> str:
    """Heuristic query for `rank`: project slug words + current git branch +
    recent commit subject words. Every source is best-effort; an empty query
    is a valid (if degraded) outcome — see `rank`'s own empty-query behavior."""
    parts: list[str] = []
    if project:
        parts.append(project.replace("-", " ").replace("_", " "))

    branch = _git(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch and branch != "HEAD":
        parts.append(branch.replace("-", " ").replace("_", " "))

    recent = _git(cwd, ["log", "-3", "--pretty=%s"])
    if recent:
        parts.append(recent.replace("\n", " "))

    return " ".join(parts).strip()


def _is_foreign_stamped(path: Path) -> bool:
    """True if `path`'s own `ren_trust` frontmatter stamp is `"foreign"` —
    Task 9b: the banner-only exclusion (`quarantine.quarantined_rel_pages`)
    misses a foreign-stamped page whose banner has since been released, so
    this checks the durable stamp (Task 6) independently of banner state.
    Unstamped pages are NOT foreign (deliberate scope decision — see module
    docstring / Task 9b brief: "foreign" only ever arrives via an explicit
    stamp — post-#22 no producer mints it, ingest drafts are "model" — and
    ordinary hand-written pages carry no `ren_*` stamps at all). Never
    raises: any read/parse failure degrades to "not foreign".
    """
    text = _read_text_safe(path)
    if not text:
        return False
    try:
        prov = read_frontmatter_provenance(text)
    except Exception:  # noqa: BLE001 - provenance parse failure must never abort wake-up
        logger.debug("read_frontmatter_provenance failed for %s", path, exc_info=True)
        return False
    return bool(prov and prov.get("trust") == "foreign")


def _is_skeleton_or_empty_page(path: Path) -> bool:
    """True if `path`'s frontmatter-stripped body is skeleton-or-empty per
    `_is_overview_skeleton_or_empty` (Codex F1, 0.5.5 live drill).

    `_discover_extra_candidates` previously rediscovered every `*.md` page
    by raw path and injected it via `_read_text_safe`, bypassing the
    skeleton-suppression `read_overview` (and, via frontmatter,
    `read_identity`) apply to their own dedicated sections — a still-skeleton
    overview.md (or any other bootstrap-stamped skeleton page reachable
    outside the dedicated identity/overview/L1/L2 paths, e.g. a sibling
    project's untouched overview) leaked its placeholder body into
    "## Possibly relevant now" for the entire pre-fill period. This is a
    general safety net alongside the dedicated-path exclusion added in
    `compose_wake_up_context` (Part B) — the two are independent: this catches
    ANY skeleton-shaped page regardless of path, that one catches the exact
    paths already covered by sections 1-4 for THIS compose regardless of
    their skeleton state.

    Never raises: any read failure degrades to True (an unreadable file has
    nothing worth surfacing either).
    """
    text = _read_text_safe(path)
    return _is_overview_skeleton_or_empty(_strip_frontmatter(text))


def _is_own_project_knowledge(rel: str, project: str | None) -> bool:
    """True if `rel` is a page under `projects/<project>/knowledge/` for the
    session's DETECTED project (issue #20).

    Such pages are the friend's own distilled project knowledge, written by
    `/ren:ingest-project` from their own repo — so `ren_trust: "foreign"`
    alone must not exile them from that project's own sessions forever. This
    exempts them from the `_is_foreign_stamped` extras exclusion ONLY (see
    `_discover_extra_candidates`); the quarantine BANNER exclusion is
    untouched, so a knowledge page still stays out of context until a human
    releases it (`skills.wiki-health.lib.release_page`). Nothing outside this exact
    path prefix — not other projects, not the project's own map/overview, not
    root-tier pages — is affected.
    """
    if not project:
        return False
    # A bare startswith on the prefix: nested paths
    # (knowledge/entities/characters/x.md) are covered by construction —
    # the hierarchical-wiki amendment (issue #20) relies on exactly that.
    return rel.startswith(f"projects/{project}/knowledge/")


def _is_project_raw(rel: str) -> bool:
    """True if `rel` sits under any `projects/<slug>/raw/` — immutable
    source material (issue #20 amendment). Never a wake-up candidate: raw
    holds sources, not distilled knowledge, so it is skipped outright (and
    NOT counted as held-out — there is no withheld trust signal, the page
    was never eligible)."""
    parts = rel.split("/")
    return len(parts) >= 3 and parts[0] == "projects" and parts[2] == "raw"


def _discover_extra_candidates(
    wiki_root: Path, exclude: set[str], project: str | None = None
) -> tuple[list[str], int]:
    """Every `*.md` under `wiki_root`, excluding dotdirs, `exclude` (the pages
    already surfaced as L1/L2, so they aren't offered twice), quarantined
    pages (0.4.1 trust hardening — see module docstring for the L1 exemption,
    which does NOT apply here since L1 is never routed through this extras
    path), `ren_trust: foreign`-stamped pages (Task 9b — closes the gap
    where a foreign page's released banner let it surface raw; unstamped
    pages remain included, per the deliberate scope decision in `_is_foreign_stamped`),
    `archive/`-prefixed pages (Task 16, 0.5.3 — archived pages are held
    out of ranking, same as quarantined/foreign, since they're no longer
    live), every `projects/<slug>/instructions.md` (#63 — already injected
    into every session via the repo's CLAUDE.md managed block, so surfacing
    it here would be a duplicate; not counted in held_count, nothing is
    withheld), and skeleton/empty-body pages (Codex F1, 0.5.5 live drill — see
    `_is_skeleton_or_empty_page`). Skeleton/empty exclusions are NOT counted
    in `held_count` — that count and its "N quarantined page(s) held out"
    message describe withheld TRUST signal; an empty/placeholder page has no
    content to withhold or show on request.

    Returns `(candidates, held_count)` where `held_count` is the number of
    otherwise-eligible pages dropped for being quarantined, foreign-stamped,
    or archived.
    Quarantine-scan failure degrades to no exclusion (never raises) — logged
    at debug level.
    """
    if not wiki_root.is_dir():
        return [], 0
    try:
        held_pages = quarantine.quarantined_rel_pages(wiki_root)
    except Exception:  # noqa: BLE001 - quarantine scan failure must never abort wake-up
        logger.debug("quarantined_rel_pages failed", exc_info=True)
        held_pages = set()

    candidates = []
    held_count = 0
    for path in wiki_root.rglob("*.md"):
        rel = path.relative_to(wiki_root).as_posix()
        if any(part.startswith(".") for part in path.relative_to(wiki_root).parts):
            continue
        if rel in exclude:
            continue
        if _is_project_raw(rel):
            continue
        rel_parts = rel.split("/")
        if len(rel_parts) == 3 and rel_parts[0] == "projects" and rel_parts[2] == "instructions.md":
            # #63: standing instructions are already in every session via the
            # repo's CLAUDE.md managed block — surfacing them here would spend
            # extras budget on a duplicate. Not counted in held_count: nothing
            # is being withheld, the content is injected by another channel.
            continue
        if archive.is_archived(rel):
            held_count += 1
            continue
        if rel in held_pages:
            held_count += 1
            continue
        if _is_foreign_stamped(path) and not _is_own_project_knowledge(rel, project):
            held_count += 1
            continue
        if _is_skeleton_or_empty_page(path):
            continue
        candidates.append(rel)
    return candidates, held_count


def _salient_pages() -> set[str]:
    """Wiki-relative pages with ANY applied queue entry that carried
    `proposal.salience=True` (Task 4.2's pin/correction verb sets this).
    Boosts expire after SALIENCE_WINDOW_DAYS — re-pin to refresh.
    Reads via `queue.all_entries()` (public read API, 0.4.0) instead of
    parsing `state_dir()/queue/*.json` raw."""
    try:
        entries = queue.all_entries()
    except Exception:  # noqa: BLE001 - never let this abort the wake-up payload
        logger.debug("queue.all_entries() failed", exc_info=True)
        return set()

    now = datetime.now(timezone.utc)
    result = set()
    for e in entries:
        if not (e.status == "applied" and e.proposal.salience and e.proposal.page):
            continue

        # Parse ts and check if within window. Unparsable ts → treat as fresh (never raise).
        try:
            entry_time = datetime.strptime(e.ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age = now - entry_time
            if age <= timedelta(days=SALIENCE_WINDOW_DAYS):
                result.add(e.proposal.page)
        except (ValueError, TypeError):
            # Unparsable ts → treat as fresh, never raise
            logger.debug("could not parse ts %r; treating as fresh", e.ts)
            result.add(e.proposal.page)

    return result


def rank_extras(
    query: str,
    wiki_root: Path,
    exclude: set[str],
    *,
    count: int = DEFAULT_EXTRAS_COUNT,
    project: str | None = None,
) -> tuple[list[str], int]:
    """Rank candidate pages (excluding `exclude` and quarantined pages) via
    `skills.recall.lib.rank`, then move any salience-boosted page (Task 4.2
    pins) to the front of its tier — i.e. all salient pages first (in their
    relative rank order among themselves), then the rest — and return
    `(top count pages, held_count)`, where `held_count` is the number of
    quarantined pages excluded (see `_discover_extra_candidates`).

    `project` (the session's detected project slug, or `None`) narrowly
    exempts `projects/<project>/knowledge/` pages from the foreign-stamp
    exclusion — see `_is_own_project_knowledge` (issue #20).

    `rank` is reached via `importlib.import_module("skills.recall.lib")`, the
    hyphen-safe pattern documented in Task 4.4 (kept here for consistency even
    though `recall` itself has no hyphen).
    """
    import importlib

    candidates, held_count = _discover_extra_candidates(wiki_root, exclude, project)
    if not candidates:
        return [], held_count

    recall_lib = importlib.import_module("skills.recall.lib")
    ranked = recall_lib.rank(query, candidates, wiki_root)

    salient = _salient_pages()
    boosted = [p for p in ranked if p in salient] + [p for p in ranked if p not in salient]
    return boosted[:count], held_count


def compose_wake_up_context(
    *,
    cwd: Path,
    wiki_root: Path,
    source: str = "startup",
    session: str = "unknown",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    dev_root: Path | None = None,
) -> str:
    """Compose the additionalContext payload for the SessionStart hook.

    Injects the active project's L1, overview, and L2 map with their
    quarantine banner intact when quarantined (spec §4.5 structural-artifact
    exemption — see module docstring); each is still held out and counted in
    the "N quarantined page(s) held out" line if `ren_trust: "foreign"`-
    stamped. Also injects live routines and a small set of heuristically-
    ranked + salience-boosted extra pages — all
    within a hard token budget (oversized sections are truncated with a
    marker, never silently dropped; identity/overview/L1/L2 additionally
    get a "*(continues in `{rel_path}`)*" pointer line when truncation
    actually occurred, per `_inject_section` — Task 6, 0.5.5). The
    `SECTION_PENDING` header is emitted immediately before
    `suggestion_line()`'s output when it is non-empty, and omitted
    entirely (no bare header) when nothing is pending — same omission
    rule as every other section. Records every surfaced page via
    `miss_log.log_surface` and the payload's byte size via
    `collect.record(KIND_INJECTED_BYTES, ...)` — this instrumentation is
    unconditional, not optional.

    Returns "" if the wiki is inaccessible OR not stamped (`index.md` absent
    — an existing but empty/unrelated directory is NOT a wiki, issue #12), and
    also when nothing real was gathered: a payload consisting only of the
    "## RenOS wake-up context" header is silent-empty in disguise, and the
    hook's caller relies on "" to fire the loud uninitialized notice. Graceful
    degradation; the hook still exits 0. NEVER raises — any per-section failure degrades that
    section to empty rather than aborting the whole payload.
    """
    if not wiki_stamped(wiki_root):
        logger.info("no stamped wiki at %s; emitting empty context", wiki_root)
        return ""

    # ONE ratio for this entire compose: read the calibrated chars-per-token
    # once (fix round 2) and hand the SAME value to every truncation and to
    # the final budget guard, so the loop's measured number actually governs
    # the cuts and decision/cut can never disagree. One JSON read per hook run.
    chars_per_token = _calibrated_chars_per_token()

    sections: list[str] = [f"## RenOS wake-up context (source={source})\n"]
    surfaced_pages: list[str] = []
    held_count = 0

    # Codex F1 (0.5.5 live drill), Part B: the pages injected by sections
    # 1-4 (identity, overview, L2 map — L1 is handled separately below, same
    # doctrine) must be excluded from the extras candidate pool for THIS
    # compose regardless of whether their content actually ends up injected.
    # `surfaced_pages` alone isn't enough for that — it only gains an entry
    # when a section's read function returns non-empty content, so a
    # SKELETON identity/overview (read_identity/read_overview correctly
    # return "" for those) left its path off `surfaced_pages`, free to
    # re-enter raw via "Possibly relevant now". `dedicated_paths` names the
    # exact rel-paths sections 1-4 look at, independent of what they find.
    dedicated_paths: set[str] = {IDENTITY_FILENAME}

    identity_text = read_identity(wiki_root)
    if identity_text:
        if _withhold_untrusted(identity_text):
            held_count += 1
        else:
            sections.append(SECTION_IDENTITY)
            sections.append(_inject_section(identity_text, IDENTITY_BUDGET, IDENTITY_FILENAME, chars_per_token))
            surfaced_pages.append(IDENTITY_FILENAME)

    project = None
    try:
        project = detect_project(cwd, wiki_root, dev_root=dev_root)
    except Exception:  # noqa: BLE001 - never let project detection abort the payload
        logger.debug("detect_project failed", exc_info=True)

    project_dir = wiki_root / "projects" / project if project is not None else None

    if project_dir is not None:
        overview_rel = f"projects/{project}/{OVERVIEW_FILENAME}"
        l2_rel = f"projects/{project}/{L2_MAP_FILENAME}"
        openwork_rel = f"projects/{project}/{OPENWORK_FILENAME}"
        dedicated_paths.add(overview_rel)
        dedicated_paths.add(l2_rel)
        dedicated_paths.add(openwork_rel)

        overview_text = read_overview(project_dir)
        if overview_text:
            if _is_foreign(overview_text):
                held_count += 1
            else:
                sections.append(SECTION_OVERVIEW)
                sections.append(_inject_section(overview_text, OVERVIEW_BUDGET, overview_rel, chars_per_token))
                surfaced_pages.append(overview_rel)

    # L1 continuity is GLOBAL (issue #21): the read below runs whether or not
    # a project was detected — project-local `l1/` first when there is one,
    # with the global `l1/` dir (codex D4) always reachable as the fallback.
    # Only overview and the L2 map stay project-gated.
    #
    # Codex P5 (as hardened by the 0.5.1 drill, Leg 4): whether or not
    # read_l1 ultimately injects a given candidate, NO file under an L1
    # dir may leak back in via the extras ("Related pages") discovery
    # path, which excludes only banner-quarantined or foreign-stamped
    # pages. L1 content may only enter wake-up context through
    # read_l1's stamp-verified injection path (see read_l1's own
    # docstring) — path-shape under `l1/` is never trusted for
    # INCLUSION, but excluding every file at that path shape from the
    # separate extras channel is safe and correct: it can only ever
    # cause the module to under-surface (fall back to nothing there),
    # never to leak an unvetted L1 file raw. The drill found that
    # excluding only `candidate_files[0]` (the single most-recent file)
    # left older, bannerless/unstamped hostile files in the same `l1/`
    # dir free to re-enter once a newer legitimate L1 file existed —
    # so every file, not just the newest, is excluded here.
    l1_dirs = [project_dir, wiki_root] if project_dir is not None else [wiki_root]
    for candidate_dir in l1_dirs:
        for l1_file in (candidate_dir / L1_DIRNAME).glob("session-*.md"):
            surfaced_pages.append(str(l1_file.relative_to(wiki_root).as_posix()))

    l1_text = ""
    l1_source_dir = wiki_root
    for candidate_dir in l1_dirs:
        l1_text = read_l1(candidate_dir)
        if l1_text:
            l1_source_dir = candidate_dir
            break

    if l1_text:
        sections.append(SECTION_L1)
        l1_path = _most_recent_l1_path(l1_source_dir / L1_DIRNAME)
        l1_rel = l1_path.relative_to(wiki_root).as_posix() if l1_path else None
        sections.append(_inject_section(l1_text, L1_BUDGET, l1_rel, chars_per_token))

    # Open work sits between "what happened last session" and "where to find
    # knowledge": it is the other half of continuity — what is still open.
    # Real content, so it is appended BEFORE the emptiness verdict below
    # (unlike the nudge/doctrine card, which ride real content).
    if project_dir is not None:
        open_work_text = read_open_work(project_dir)
        if open_work_text:
            sections.append(SECTION_OPENWORK)
            sections.append(
                _inject_open_work(open_work_text, OPENWORK_BUDGET, openwork_rel, chars_per_token)
            )
            surfaced_pages.append(openwork_rel)

    if project_dir is not None:
        l2_text = read_l2_map(project_dir)
        if l2_text:
            if _is_foreign(l2_text):
                # spec §4.5: the L2 map now gets the structural-artifact
                # exemption for quarantine (banner-intact injection below),
                # but a `ren_trust: "foreign"` stamp (ingest-project's
                # repo-scan writes) still holds it out and counts it in the
                # held-out line — that check is unaffected by the amendment.
                held_count += 1
            else:
                sections.append(SECTION_L2)
                sections.append(_inject_section(l2_text, L2_BUDGET, l2_rel, chars_per_token))
                surfaced_pages.append(l2_rel)

    live_routines = read_live_routines(wiki_root)
    if live_routines:
        sections.append(SECTION_ROUTINES)
        sections.append(truncate_text_to_tokens(live_routines, ROUTINE_SPEC_BUDGET, chars_per_token))

    suggestion = suggestion_line()
    if suggestion:
        sections.append(SECTION_PENDING)
        sections.append(suggestion)

    extras: list[str] = []
    extras_held_count = 0
    try:
        query = _build_rank_query(project, cwd)
        if query:
            extras, extras_held_count = rank_extras(
                query, wiki_root, exclude=set(surfaced_pages) | dedicated_paths, project=project
            )
        else:
            # Issue #23: no project and no git signal — the query is empty,
            # so ranking would just surface whatever happens to be released,
            # presented with unearned confidence. Inject nothing, not noise.
            # Dogfood-2 M3: still run the cheap candidate discovery so the
            # "N quarantined page(s) held out" transparency line survives —
            # suppressing ranking must not also suppress the withheld-trust
            # signal (no-project sessions are exactly where it matters).
            logger.info("empty rank query; suppressing extras")
            _, extras_held_count = _discover_extra_candidates(
                wiki_root, set(surfaced_pages) | dedicated_paths, project
            )
    except Exception:  # noqa: BLE001 - ranking failure degrades to no extras
        logger.debug("rank_extras failed", exc_info=True)
        extras, extras_held_count = [], 0
    held_count += extras_held_count

    if extras:
        per_page_budget = max(EXTRA_PAGE_BUDGET, EXTRAS_BUDGET // max(len(extras), 1))
        extra_blocks: list[str] = []
        for rel in extras:
            text = _read_text_safe(wiki_root / rel)
            if not text:
                continue
            extra_blocks.append(f"#### {rel}")
            extra_blocks.append(truncate_text_to_tokens(_strip_extras_placeholder_lines(text), per_page_budget, chars_per_token))
            surfaced_pages.append(rel)
        # Same no-bare-header rule as every other section: when every ranked
        # extra reads empty, the header alone must not be emitted.
        if extra_blocks:
            sections.append(SECTION_EXTRAS)
            sections.extend(extra_blocks)

    if held_count > 0:
        sections.append(
            f"{held_count} quarantined page(s) held out of this context — "
            "ask to see them explicitly."
        )

    # `sections[0]` is the seed header; anything after it is real content.
    # With nothing real gathered, return "" rather than a header-only payload
    # (issue #12) so the hook emits its loud uninitialized notice instead.
    if not [s for s in sections[1:] if s.strip()]:
        logger.info("nothing to inject from %s; emitting empty context", wiki_root)
        return ""

    # Same rule as the doctrine card below: the unlinted-journal nudge rides
    # real content and is appended only AFTER the emptiness verdict above, so
    # journal lines alone can never turn an empty wiki's compose into a
    # non-empty payload and suppress the loud uninitialized notice.
    nudge = unlinted_nudge_line()
    if nudge:
        sections.append(nudge)

    backlog_nudge = quarantine_backlog_nudge_line()
    if backlog_nudge:
        sections.append(backlog_nudge)

    # Doctrine rides real content; empty compose stays "" (loud notice) —
    # the emptiness decision above is made before the card is ever added.
    full_card = render_doctrine_card(superpowers_installed())
    # Pointer (not None): if a band-low calibration ratio forces a cut, the
    # loss must be VISIBLE rather than silently eating doctrine text.
    card = _inject_section(full_card, DOCTRINE_BUDGET, DOCTRINE_POINTER, chars_per_token)
    if card != full_card:
        # The full card doesn't fit. `truncate_text_to_tokens` keeps the TAIL,
        # which would elide the header and gates 1-3 — the card's whole point.
        # Swap in the head-preserving compact variant instead (card-local fix;
        # the shared truncator is untouched because it has other callers).
        compact = render_doctrine_card_compact()
        card = truncate_text_to_tokens(compact, DOCTRINE_BUDGET, chars_per_token)
        card = f"{card}\n*(continues in `{DOCTRINE_POINTER}`)*"
    card = card or full_card
    sections.insert(1, card)

    # #48: the generic truncator keeps the TAIL, which would silently elide
    # the seed header (sections[0]) and doctrine card (sections[1]) — the
    # exact content this guard exists to protect. Split head from body so
    # ANY over-budget payload truncates only the content sections, never the
    # head, and logs the loss instead of eating it silently.
    head = "\n\n".join(s for s in sections[:2] if s.strip())   # seed header + doctrine card
    body = "\n\n".join(s for s in sections[2:] if s.strip())
    composed = f"{head}\n\n{body}" if body else head

    final_tokens = _budget_tokens(composed, chars_per_token)
    if final_tokens > max_tokens:
        head_tokens = _budget_tokens(head, chars_per_token)
        body_budget = max(0, max_tokens - head_tokens)
        truncated_body = truncate_text_to_tokens(body, body_budget, chars_per_token)
        logger.warning(
            "wake-up payload over budget (%d > %d tokens); elided %d chars from "
            "content sections — doctrine card preserved",
            final_tokens, max_tokens, len(body) - len(truncated_body),
        )
        composed = f"{head}\n\n{truncated_body}" if truncated_body else head

    try:
        if surfaced_pages:
            miss_log.log_surface(surfaced_pages, session)
        collect.record(collect.KIND_INJECTED_BYTES, {"bytes": len(composed.encode("utf-8")), "session": session})
    except Exception:  # noqa: BLE001 - instrumentation failure must never break wake-up
        logger.debug("instrumentation recording failed", exc_info=True)

    return composed


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "CHARS_PER_TOKEN",
    "DEFAULT_DEV_ROOT_REL",
    "IDENTITY_BUDGET",
    "OVERVIEW_BUDGET",
    "IDENTITY_FILENAME",
    "OVERVIEW_FILENAME",
    "L1_BUDGET",
    "L2_BUDGET",
    "ROUTINE_SPEC_BUDGET",
    "OPENWORK_BUDGET",
    "DOCTRINE_BUDGET",
    "DOCTRINE_POINTER",
    "EXTRAS_BUDGET",
    "EXTRA_PAGE_BUDGET",
    "SALIENCE_WINDOW_DAYS",
    "SECTION_DOCTRINE",
    "SECTION_IDENTITY",
    "SECTION_OVERVIEW",
    "SECTION_L1",
    "SECTION_OPENWORK",
    "SECTION_L2",
    "SECTION_ROUTINES",
    "SECTION_PENDING",
    "SECTION_EXTRAS",
    "estimate_tokens",
    "truncate_text_to_tokens",
    "resolve_dev_root",
    "detect_project",
    "read_identity",
    "read_overview",
    "read_l1",
    "read_l2_map",
    "read_live_routines",
    "suggestion_line",
    "unlinted_nudge_line",
    "rank_extras",
    "compose_wake_up_context",
]
