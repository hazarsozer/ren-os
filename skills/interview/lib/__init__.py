"""
skills.interview library — internal implementation for /ren:interview
(Task 8.1, RenOS 0.2 Phase 8).

Spec §3.8: "identity + working-style profile... explicit question budget,
every question skippable, sane defaults for everything unanswered... the
system must work with ZERO user-authored doctrine." Donor `skills/interview/`
asks 18 identity questions (sections A-E) plus an optional 5-question venture
arc (section F). RenOS 0.2 caps the DEFAULT path at
`skills.install.lib.QUESTION_BUDGET` (10) and drops the venture arc entirely
from that path — the venture module templates still ship under
`wiki-skeleton/modules/venture/` for the friend who explicitly opts in later,
but this skill never offers them.

`QUESTIONS` below is a curated subset of donor's fields, chosen to fit the
budget: every entry's `key` is a real field in
`wiki-skeleton/templates/identity.md.tmpl`'s frontmatter (golden cross-check
in tests/skills/interview/test_profile.py), each with donor's own "sane
neutral default" carried over. Fields NOT asked here (package_managers,
clouds, databases) simply keep the template's default — the zero-doctrine
guarantee doesn't require asking about everything, only defaulting
everything not asked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from lib.memory.queue import Proposal, QueueEntry, propose_and_apply
from lib.ren_paths import safe_join, wiki_root

IDENTITY_PAGE = "identity.md"

FRAMEWORK_VERSION = "0.2.1"

# Sane, neutral defaults — never the framework developer's own preference
# (donor's own framing, carried verbatim as a design principle). Matches
# wiki-skeleton/templates/identity.md.tmpl's literal default values exactly.
_DEFAULTS: dict[str, Any] = {
    "name": "Friend",
    "handle": "friend",
    "languages": [],
    "package_managers": [],
    "clouds": [],
    "databases": [],
    "working_style": "balanced",
    "communication_style": "balanced-with-emoji",
    "plans_before_code": "often",
    "tdd_attitude": "case-by-case",
    "strong_skills": [],
    "growth_areas": [],
    "contact": {"timezone": "", "working_hours": ""},
}

QUESTIONS: list[dict] = [
    {
        "key": "name",
        "prompt": "What name should I use for you (display name, free-form)?",
        "options": None,
        "default": _DEFAULTS["name"],
    },
    {
        "key": "handle",
        "prompt": "What short handle do you prefer (lowercase, kebab-case, "
        "letters/digits/hyphens only)?",
        "options": None,
        "default": _DEFAULTS["handle"],
    },
    {
        "key": "languages",
        "prompt": "Which languages do you work in most? (comma-separated, or skip)",
        "options": None,
        "default": _DEFAULTS["languages"],
    },
    {
        "key": "working_style",
        "prompt": "How do you like to plan and work — structured, balanced, or exploratory?",
        "options": ["structured", "balanced", "exploratory"],
        "default": _DEFAULTS["working_style"],
    },
    {
        "key": "communication_style",
        "prompt": "How should I talk to you — concise, balanced-with-emoji, or detailed?",
        "options": ["concise", "balanced-with-emoji", "detailed"],
        "default": _DEFAULTS["communication_style"],
    },
    {
        "key": "plans_before_code",
        "prompt": "How much do you like to plan before writing code — always, often, "
        "case-by-case, or rarely?",
        "options": ["always", "often", "case-by-case", "rarely"],
        "default": _DEFAULTS["plans_before_code"],
    },
    {
        "key": "tdd_attitude",
        "prompt": "Your attitude toward test-driven development — strict, case-by-case, "
        "or rarely?",
        "options": ["strict", "case-by-case", "rarely"],
        "default": _DEFAULTS["tdd_attitude"],
    },
    {
        "key": "strong_skills",
        "prompt": "What are your strongest skill areas? (comma-separated, or skip)",
        "options": None,
        "default": _DEFAULTS["strong_skills"],
    },
    {
        "key": "growth_areas",
        "prompt": "What areas are you actively trying to grow in? (comma-separated, or skip)",
        "options": None,
        "default": _DEFAULTS["growth_areas"],
    },
    {
        "key": "contact",
        "prompt": "Your timezone and typical working hours? (both optional)",
        "options": None,
        "default": _DEFAULTS["contact"],
    },
]


def _yaml_scalar(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[" + ", ".join(f'"{item}"' for item in value) + "]"
    return str(value)


def render_identity(answers: dict) -> str:
    """Merge `answers` over `_DEFAULTS` and render the identity page content.

    Unanswered/skipped keys (absent from `answers`, or explicitly `None`) get
    the default AND are listed in the rendered `skipped_questions` field —
    THE zero-doctrine substrate: calling this with `answers={}` still
    produces a fully valid page.
    """
    answers = answers or {}
    merged = dict(_DEFAULTS)
    skipped: list[str] = []

    for question in QUESTIONS:
        key = question["key"]
        if key in answers and answers[key] is not None:
            merged[key] = answers[key]
        else:
            skipped.append(key)

    name = merged["name"]
    handle = merged["handle"]
    contact = merged["contact"] or {}
    timezone = contact.get("timezone", "")
    working_hours = contact.get("working_hours", "")
    today = date.today().isoformat()

    lines = [
        "---",
        f'title: "{name}\'s Identity"',
        "type: identity",
        "schema_version: 1",
        f'framework_version: "{FRAMEWORK_VERSION}"',
        f"handle: {handle}",
        f'name: "{name}"',
        f"created: {today}",
        f"updated: {today}",
        f"languages: {_yaml_scalar(merged['languages'])}",
        f"package_managers: {_yaml_scalar(merged['package_managers'])}",
        f"clouds: {_yaml_scalar(merged['clouds'])}",
        f"databases: {_yaml_scalar(merged['databases'])}",
        f"working_style: {merged['working_style']}",
        f"communication_style: {merged['communication_style']}",
        f"plans_before_code: {merged['plans_before_code']}",
        f"tdd_attitude: {merged['tdd_attitude']}",
        f"strong_skills: {_yaml_scalar(merged['strong_skills'])}",
        f"growth_areas: {_yaml_scalar(merged['growth_areas'])}",
        "contact:",
        f'  timezone: "{timezone}"',
        f'  working_hours: "{working_hours}"',
        f"skipped_questions: {_yaml_scalar(skipped)}",
        "---",
        "",
        f"# About {name}",
        "",
        "_This file is filled in by the interview during onboarding. You can re-run the "
        "interview anytime, or edit any field by hand. The YAML block above is read by "
        "other skills (wake-up, doctor, peer-aware tools); the markdown body is for you "
        "and your AI to share narrative context._",
        "",
        "## Background & current role",
        "",
        "_One paragraph: who you are, what you focus on, what brought you here._",
        "",
        "## Working style",
        "",
        "_How you prefer to communicate; how much planning before code; how you like "
        "feedback delivered._",
        "",
        "## Tech preferences",
        "",
        "_Languages, package managers, clouds, databases, other tools you live in. "
        "Free-form details that didn't fit the YAML enums above._",
        "",
        "## Strong opinions + non-goals",
        "",
        "_Things you want your AI to favour; explicit patterns you want it to AVOID._",
        "",
        "## What I contribute",
        "",
        "_What you typically bring to a friend-group project; the role you tend to "
        "land in._",
        "",
    ]
    return "\n".join(lines)


def save_identity(answers: dict, session: str) -> QueueEntry:
    """Queue the rendered identity page. The interview is human input, so
    `writer="human"`; `producer="promotion"` — there is no dedicated
    "interview" producer class (spec's producer list is fixed at
    wrap/pin/retrospective/routine/promotion), and an identity update is, in
    spirit, the friend promoting their own stated preferences into durable
    memory, same shape as `lib.memory.promotion`'s human-approved writes.

    `op` is `UPDATE` if `identity.md` already exists, else `ADD` — same
    exists-check pattern `skills.pin.lib.pin` uses. `identity.md` is a
    non-global (data-plane) page, so — like every other data-plane producer
    (v2.2 pivot) — this goes through `lib.memory.queue.propose_and_apply` and
    auto-applies immediately; the returned entry's `write_id` is set once
    applied.
    """
    content = render_identity(answers)
    op = "UPDATE" if _identity_exists() else "ADD"
    entry, _ = propose_and_apply(
        Proposal(
            op=op,
            page=IDENTITY_PAGE,
            content=content,
            reason="identity interview",
            producer="promotion",
            writer="human",
            session=session,
        )
    )
    return entry


def _identity_exists() -> bool:
    return safe_join(wiki_root(), IDENTITY_PAGE).is_file()


__all__ = ["QUESTIONS", "IDENTITY_PAGE", "render_identity", "save_identity"]
