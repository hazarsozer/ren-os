"""
lib.memory.scrub — G7 secrets-scrub, fail-closed (Task 1.4, RenOS 0.2 Phase 1).

Spec §3.6 item 3: the memory-write path (transcripts → wiki → backup) is an
exfiltration chain if a pasted credential ever reaches a durable page. This
module is the standalone scanner: `write_apply` (Task 1.2, not yet built) will
import `scrub_or_raise` to gate every durable write. `doctor` and the push guard
(Phase 6) import the same `PATTERNS` list so there's exactly one denylist.

FAIL-CLOSED, never auto-redact: `scrub_or_raise` either returns the text
unchanged (nothing matched) or raises `SecretsFound` — it never silently
rewrites/masks the text and lets the write proceed. A refused write is a human
decision, not something this module papers over.

Pattern provenance: the donor's `scripts/publish.sh` DENYLIST (checked per Task
1.4 instructions) turned out to be a *path* denylist (wiki/, raw/, .claude/, ...
for the pruned-history publish guard), not a secret-regex list — there was no
regex-based secret scanner to salvage verbatim. The actual credential-shaped
patterns donor code already reasons about live in
`skills/insights/scripts/collect.py` (`_SECRET_PREFIXES`, `_AWS_KEY_RE`) — sk-/
ghp_/gho_/ghs_/github_pat_/xoxb-/xoxp- prefixes and the AKIA/ASIA AWS key shape.
This module generalizes that prefix list into full matchable regexes and adds
the kinds Task 1.4 explicitly asked for beyond what collect.py needed (PEM
blocks, password/secret/token assignment pairs) — see the deviations note in
the implementation report for the exact reasoning.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    kind: str                # e.g. "aws-access-key", "github-token", "openai-key", "pem-block", "password-pair"
    span: tuple[int, int]    # character offsets in the scanned text
    redacted_preview: str    # first 4 chars + "…" — NEVER the full secret


class SecretsFound(Exception):
    """Raised by `scrub_or_raise` when `scan` finds anything.

    The message lists only kinds + counts (e.g. "aws-access-key (1), github-token
    (2)") — never the secret material or even the redacted preview, so the
    exception itself can't leak into logs/tracebacks with anything sensitive.
    """

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        counts = Counter(f.kind for f in findings)
        summary = ", ".join(f"{kind} ({n})" for kind, n in sorted(counts.items()))
        super().__init__(f"secrets detected, write refused: {summary}")


# Module-level pattern registry — doctor and the Phase 6 push guard import this
# SAME list so there is exactly one denylist. Each entry is (kind, compiled_regex).
# Order matters only for iteration determinism, not correctness.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "aws-access-key",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ),
    (
        "github-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ),
    (
        "github-token",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    ),
    (
        "slack-token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]+\b"),
    ),
    (
        # sk- style keys (OpenAI, Anthropic, etc). Negative lookbehind on an
        # alnum/underscore guards against matching inside a longer word/token
        # (e.g. "desk-mounted" must NOT fire).
        "openai-key",
        re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}"),
    ),
    (
        "pem-block",
        re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|DSA\s+|OPENSSH\s+)?PRIVATE KEY-----"),
    ),
    (
        # `password:`/`db_password:`/`secret =`/`token: "..."`/`api_key=...`
        # assignment pairs. No leading `\b` — real-world identifiers are often
        # prefixed (`db_password`, `my_secret`), so we match the keyword as a
        # suffix of the identifier too. Requires an assignment operator (`:` or
        # `=`) right after the keyword so the bare word in prose ("enter your
        # password") never matches — only an actual key=value shape.
        "password-pair",
        re.compile(
            r"(?:password|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[^\s'\"]{4,}",
            re.IGNORECASE,
        ),
    ),
]


def scan(text: str) -> list[Finding]:
    """Scan `text` for anything matching `PATTERNS`. Returns [] when clean."""
    findings: list[Finding] = []
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            secret = match.group(0)
            findings.append(
                Finding(
                    kind=kind,
                    span=(start, end),
                    redacted_preview=secret[:4] + "…",
                )
            )
    return findings


def scrub_or_raise(text: str) -> str:
    """Return `text` unchanged if clean; raise `SecretsFound` otherwise.

    Fail-closed by design: this function NEVER redacts and returns a modified
    string. A durable write with a detected secret is refused outright — the
    caller (`write_apply`, once it exists) must surface `SecretsFound` to the
    human rather than attempt an automatic fix.
    """
    findings = scan(text)
    if not findings:
        return text
    raise SecretsFound(findings)


__all__ = ["Finding", "SecretsFound", "PATTERNS", "scan", "scrub_or_raise"]
