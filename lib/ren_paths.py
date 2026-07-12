"""
lib.ren_paths — single source of truth for framework paths + handle + schema.

Ported from startup-framework's `lib/sf_paths.py` (ADR-031) for RenOS 0.2 (Task
0.2, docs/superpowers/plans/2026-07-06-renos-02-implementation.md). Every module
and skill that needs the framework root, the wiki path, the friend's handle, or
a schema-version check imports from here — the path convention lives in exactly
one place.

Resolution:
- Framework root: `REN_FRAMEWORK_ROOT` env override → `~/.renos/` default.
- Wiki root (Codex F1, 3-tier): `REN_WIKI_ROOT` → `CLAUDE_PLUGIN_OPTION_WIKIROOT`
  → `framework_root()/wiki`. Resolved INDEPENDENTLY of `framework_root()` so the
  advertised `wikiRoot` plugin option works on its own.

The friend's handle lives in YAML frontmatter at the top of `wiki/identity.md`
under the key `handle:` (ADR-022). We read that.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


# --- path constants (NOT to be reproduced elsewhere — import from here) ---

FRAMEWORK_ROOT_ENV = "REN_FRAMEWORK_ROOT"
"""Env-var override for the framework root path. Lets tests + distribution remap."""

DEFAULT_FRAMEWORK_ROOT = Path.home() / ".renos"
"""Default framework root (renamed from startup-framework's ~/.startup-framework)."""

WIKI_ROOT_ENV = "REN_WIKI_ROOT"
"""Explicit env-var override for the wiki path (highest-precedence F1 tier)."""

WIKI_ROOT_PLUGIN_OPTION = "CLAUDE_PLUGIN_OPTION_WIKIROOT"
"""Claude plugin option (`userConfig.wikiRoot`) exported as an env var by the host.
Honored on its own — independent of `REN_FRAMEWORK_ROOT` — so a friend who configures
only `wikiRoot` reads/writes the path they advertised (Codex F1)."""

FALLBACK_FRAMEWORK_VERSION = "0.5.2"
"""Fallback used when no installed-plugin metadata is reachable. Matches
plugin.json#version (the SSOT). Tests pinned to this. In a real install Layer 2
(plugin.json) wins, so this only stamps in bare-checkout/test contexts."""


def framework_version() -> str:
    """Return the installed framework version.

    Resolution order:
      1. CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION env var (cleanest interface)
      2. CLAUDE_PLUGIN_ROOT/.claude-plugin/plugin.json "version" field
      3. FALLBACK_FRAMEWORK_VERSION constant

    Never raises — falls back at each layer if a source is unreadable.
    """
    # Layer 1: explicit env var
    env_val = os.environ.get("CLAUDE_PLUGIN_OPTION_FRAMEWORK_VERSION", "").strip()
    if env_val:
        return env_val

    # Layer 2: plugin.json
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if plugin_root:
        plugin_json = Path(plugin_root) / ".claude-plugin" / "plugin.json"
        if plugin_json.exists():
            try:
                text = plugin_json.read_text(encoding="utf-8")
                # Minimal JSON parse for "version": "..." — avoid pulling json dep
                # for one field, since /ren:doctor and tests are perf-sensitive paths.
                m = re.search(r'"version"\s*:\s*"([^"]+)"', text)
                if m:
                    return m.group(1)
            except OSError:
                pass

    # Layer 3: fallback
    return FALLBACK_FRAMEWORK_VERSION


# Back-compat alias — referenced by older code; new code should call framework_version().
FRAMEWORK_VERSION = FALLBACK_FRAMEWORK_VERSION
"""Deprecated. Prefer `framework_version()`. Kept as a fallback string for code paths
that need a const literal at import time. The function form is authoritative; this
constant only matches when no env-var/plugin.json override applies."""

EXPECTED_IDENTITY_SCHEMA_VERSION = 1
"""Schema version this build expects on wiki/identity.md.
handle() asserts against this so a schema bump surfaces as a clear error instead of
a silent parse."""

REN_SCHEMA_VERSION: int = 1
"""General framework schema-version constant (Task 0.2 export). Distinct from
EXPECTED_IDENTITY_SCHEMA_VERSION, which is specific to the identity.md page type —
this is the SSOT downstream phases pin against for framework-wide schema checks."""


PLUGIN_DATA_ENV = "CLAUDE_PLUGIN_DATA"
# Mirrors the fallback the update/snapshot shell scripts already use.
DEFAULT_PLUGIN_DATA = Path.home() / ".claude" / "plugins" / "data" / "renos"


def plugin_data_dir() -> Path:
    """Return the plugin-data dir for regenerable artifacts (snapshots, code-maps).

    Honors CLAUDE_PLUGIN_DATA; falls back to the same path the shell scripts use.
    """
    override = os.environ.get(PLUGIN_DATA_ENV, "").strip()
    return Path(override).expanduser() if override else DEFAULT_PLUGIN_DATA


def code_map_cache_dir() -> Path:
    """Directory holding regenerable per-project code-maps."""
    return plugin_data_dir() / "code-maps"


def code_map_path(project_name: str) -> Path:
    """Cache file path for one project's code-map (kebab project name)."""
    return code_map_cache_dir() / f"{project_name}.md"


def framework_root() -> Path:
    """Return the framework root directory.

    Honors REN_FRAMEWORK_ROOT env var if set (for tests + distribution remapping);
    otherwise returns ~/.renos/.
    """
    override = os.environ.get(FRAMEWORK_ROOT_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_FRAMEWORK_ROOT


CLAUDE_DIR_ENV = "REN_CLAUDE_DIR"
"""Override for the user-level Claude config dir (tests + unusual homes)."""


def claude_user_dir() -> Path:
    """Return the user-level Claude config directory (`~/.claude` by default).

    Honors `REN_CLAUDE_DIR` if set — same override pattern as
    `REN_FRAMEWORK_ROOT`. This is where the global CLAUDE.md pointer layer
    (`lib.adapter.claude_md`) manages its marker block.
    """
    override = _resolve_path_env(CLAUDE_DIR_ENV)
    if override is not None:
        return override
    return Path.home() / ".claude"


def _resolve_path_env(name: str) -> Path | None:
    """Read env var `name` as a path; return None when unset or blank.

    Per tier: strip surrounding whitespace, then expand `${VAR}`/`$VAR` and a
    leading `~`. Whitespace-only values are treated as unset so an empty plugin
    option doesn't shadow a lower tier.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return Path(os.path.expanduser(os.path.expandvars(raw)))


def wiki_root() -> Path:
    """Return the friend's local wiki root (Codex F1, 3-tier).

    Precedence: `REN_WIKI_ROOT` → `CLAUDE_PLUGIN_OPTION_WIKIROOT` →
    `framework_root()/wiki`. Resolved independently of `framework_root()` so the
    advertised `wikiRoot` plugin option is honored on its own. Used by `handle()`
    to read `wiki/identity.md`, and by `state_dir()` for framework-internal state.
    """
    for env_name in (WIKI_ROOT_ENV, WIKI_ROOT_PLUGIN_OPTION):
        candidate = _resolve_path_env(env_name)
        if candidate is not None:
            return candidate
    return framework_root() / "wiki"


DEV_ROOT_ENV = "CLAUDE_PLUGIN_OPTION_DEVROOT"
"""Env override for the dev-projects root used by cwd-based project detection."""

DEFAULT_DEV_ROOT_REL = "Dev"
"""Default dev-projects root, relative to the user's home directory."""


def resolve_dev_root() -> Path:
    """Projects root for cwd-based project detection. `CLAUDE_PLUGIN_OPTION_DEVROOT`
    → `~/Dev`.

    Single source of truth for both the wake-up hook (`hooks/wake-up/wakeup`)
    and the wrap skill (`skills/wrap/lib`) — both need to agree on which
    project a given cwd belongs to, so this lives in the shared `lib/` layer
    rather than being duplicated in either consumer (codex D4 wiring)."""
    val = os.environ.get(DEV_ROOT_ENV, "").strip()
    if val:
        return Path(os.path.expanduser(os.path.expandvars(val)))
    return Path.home() / DEFAULT_DEV_ROOT_REL


def detect_project(cwd: Path, wiki_root_: Path, dev_root: Path | None = None) -> str | None:
    """cwd matches `<dev_root>/<X>/...` AND `wiki_root_/projects/<X>/` exists → X.

    Shared by the wake-up hook (project-scoped read) and the wrap skill
    (project-scoped write) so the two can never drift onto different paths
    for the "same" project (codex D4 wiring)."""
    if dev_root is None:
        dev_root = resolve_dev_root()
    try:
        rel = cwd.resolve().relative_to(dev_root.resolve())
    except (ValueError, OSError):
        return None
    if not rel.parts:
        return None
    candidate = rel.parts[0]
    if (wiki_root_ / "projects" / candidate).is_dir():
        return candidate
    return None


def state_dir() -> Path:
    """Return the framework's internal state directory, nested under the wiki root.

    Task 0.2 export: `wiki_root() / ".ren"`. Colocating state with the wiki keeps a
    single portable root per Obsidian-invariant (RenOS 0.2 scope v2.1) rather than
    splitting state across the framework root and the wiki root.
    """
    return wiki_root() / ".ren"


class PathTraversalError(ValueError):
    """Raised by `safe_join` when a relative path would escape its base directory."""


def safe_join(base: Path | str, rel: Path | str) -> Path:
    """Join `rel` onto `base`, raising `PathTraversalError` if the result would
    escape `base` (e.g. via `../../etc/passwd` or an absolute path override).

    Task 0.2 export. Generalizes the path-traversal guard `validate_handle()`
    already enforces on handle strings (M2/L7) into a reusable join primitive for
    any caller building filesystem paths from untrusted relative segments.
    """
    base_resolved = Path(base).expanduser().resolve()
    candidate = (base_resolved / rel).resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise PathTraversalError(
            f"{rel!r} escapes base directory {base_resolved} (resolved to {candidate})"
        )
    return candidate


# --- handle resolution (reads wiki/identity.md frontmatter `handle:` field) ---


class HandleNotConfiguredError(RuntimeError):
    """Raised when wiki/identity.md doesn't exist or doesn't have a `handle:` field.

    Indicates onboarding's identity-bootstrap hasn't run, OR the friend manually
    edited identity.md and broke the schema. Caller should surface a clear message
    pointing the user at /ren:interview.
    """


class InvalidHandleError(HandleNotConfiguredError):
    """Raised when a handle is present but malformed (doesn't match HANDLE_RE).

    A malformed handle is a path-traversal / malformed-commit-message risk (M2/L7): it
    flows into filesystem paths and git commit messages. /ren:interview validates the
    pattern at input; we enforce it at every use so a hand-edited identity.md can't
    escape into a traversal value.

    Subclasses HandleNotConfiguredError so existing `except HandleNotConfiguredError`
    handlers catch it with the same /ren:interview remediation.
    """


class SchemaVersionMismatchError(RuntimeError):
    """Raised when a file's `schema_version` frontmatter field doesn't match what
    this build expects (`EXPECTED_*_SCHEMA_VERSION`).

    Caller should surface to the user: "your wiki schema is at N but framework expects
    M; run /ren:update to migrate."

    Attributes:
        path: the file with the mismatched version
        found: the version observed in the file
        expected: the version this build expects
    """

    def __init__(self, path: Path, found: int, expected: int) -> None:
        self.path = path
        self.found = found
        self.expected = expected
        super().__init__(
            f"{path} has schema_version={found}; this framework expects {expected}. "
            "Run /ren:update to migrate."
        )


HANDLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
"""The handle contract: a lowercase letter followed by lowercase letters, digits, and
hyphens. Mirrors the pattern /ren:interview validates at input. Enforced at every use of
the handle (M2) so a hand-edited identity.md can't introduce a path-traversal value."""


def validate_handle(value: str) -> str:
    """Return `value` unchanged if it matches HANDLE_RE; otherwise raise InvalidHandleError.

    The handle is load-bearing for filesystem paths and git commit messages, so a
    malformed value is a path-traversal vector (M2/L7). We reject rather than
    sanitize-and-fall-back: the handle is identity and must be correct, not silently
    rewritten. Also caps length at 50 characters to bound path/commit-message growth.
    """
    if not isinstance(value, str) or len(value) > 50 or not HANDLE_RE.match(value):
        raise InvalidHandleError(
            f"handle {value!r} is invalid; it must match ^[a-z][a-z0-9-]*$ "
            "(a lowercase letter, then lowercase letters/digits/hyphens), max 50 characters. "
            "Run /ren:interview to set a valid handle."
        )
    return value


def handle(*, strict_schema: bool = True) -> str:
    """Return the friend's handle, read from wiki/identity.md frontmatter.

    Args:
        strict_schema: when True (default), also asserts the file's `schema_version`
            matches EXPECTED_IDENTITY_SCHEMA_VERSION and raises SchemaVersionMismatchError
            on drift. Set to False for repair-mode tooling that needs to read the handle
            from a stale-schema file.

    Raises:
        HandleNotConfiguredError: identity.md is missing or has no `handle:` field
        InvalidHandleError: handle is present but malformed (M2; subclass of the above)
        SchemaVersionMismatchError: schema_version frontmatter field doesn't match

    Reads from wiki_root()/identity.md, so it honors the F1 wiki-root resolution.
    """
    identity_md = wiki_root() / "identity.md"
    if not identity_md.exists():
        raise HandleNotConfiguredError(
            f"{identity_md} does not exist. Run /ren:interview to bootstrap your identity."
        )

    text = identity_md.read_text(encoding="utf-8")

    if strict_schema:
        observed_schema = _parse_schema_version_from_frontmatter(text)
        if observed_schema is not None and observed_schema != EXPECTED_IDENTITY_SCHEMA_VERSION:
            raise SchemaVersionMismatchError(
                identity_md, observed_schema, EXPECTED_IDENTITY_SCHEMA_VERSION,
            )

    parsed = _parse_handle_from_frontmatter(text)
    if not parsed:
        raise HandleNotConfiguredError(
            f"{identity_md} has no `handle:` field in YAML frontmatter. "
            "Run /ren:interview to repair, or hand-edit the frontmatter."
        )
    # M2: enforce the handle format at use (path-safety), independent of strict_schema —
    # a malformed handle is dangerous regardless of the file's schema_version.
    return validate_handle(parsed)


def _parse_schema_version_from_frontmatter(text: str) -> int | None:
    """Extract integer `schema_version` from YAML frontmatter. Returns None if absent."""
    value_str = _parse_field_from_frontmatter(text, "schema_version")
    if value_str is None:
        return None
    try:
        return int(value_str)
    except ValueError:
        return None


def _parse_field_from_frontmatter(text: str, field: str) -> str | None:
    """Generic frontmatter field reader. Returns the raw string value (sans quotes)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    prefix = f"{field}:"
    found: str | None = None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return found  # closing fence reached
        if found is None and stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            found = value or None
    # No closing fence: the block is unterminated, so any match was in the body.
    return None


def _parse_handle_from_frontmatter(text: str) -> str | None:
    """Extract the `handle:` value from YAML frontmatter at the top of a markdown file.

    Deliberately minimal — we don't pull in pyyaml just to read one field. Frontmatter
    format per onboarding's identity.md.tmpl:

        ---
        title: "..."
        type: identity
        schema_version: 1
        framework_version: "..."
        handle: hazar
        name: "..."
        ---

    Returns None if no frontmatter block, or frontmatter has no `handle:` line.
    """
    return _parse_field_from_frontmatter(text, "handle")


__all__ = [
    "FRAMEWORK_ROOT_ENV",
    "DEFAULT_FRAMEWORK_ROOT",
    "WIKI_ROOT_ENV",
    "WIKI_ROOT_PLUGIN_OPTION",
    "FALLBACK_FRAMEWORK_VERSION",
    "FRAMEWORK_VERSION",
    "framework_version",
    "EXPECTED_IDENTITY_SCHEMA_VERSION",
    "REN_SCHEMA_VERSION",
    "PLUGIN_DATA_ENV",
    "DEFAULT_PLUGIN_DATA",
    "plugin_data_dir",
    "code_map_cache_dir",
    "code_map_path",
    "framework_root",
    "CLAUDE_DIR_ENV",
    "claude_user_dir",
    "DEV_ROOT_ENV",
    "DEFAULT_DEV_ROOT_REL",
    "resolve_dev_root",
    "detect_project",
    "wiki_root",
    "state_dir",
    "PathTraversalError",
    "safe_join",
    "HANDLE_RE",
    "validate_handle",
    "handle",
    "HandleNotConfiguredError",
    "InvalidHandleError",
    "SchemaVersionMismatchError",
]
