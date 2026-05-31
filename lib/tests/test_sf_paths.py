"""
Tests for lib.sf_paths — the framework-wide path/handle/schema core (ADR-031).

Two concerns:
  1. Handle validation / schema / frontmatter parsing — ported from the former
     feed/tests/test_handle_validation.py (the non-feed half; the feed writer-guard
     cases move out with the feed module in Commit 2).
  2. The Codex F1 fix: 3-tier wiki-path resolution
     (SF_WIKI_ROOT → CLAUDE_PLUGIN_OPTION_WIKIROOT → framework_root()/wiki), resolved
     independently of framework_root() so the advertised `wikiRoot` option works alone.

Run with: python3 -m pytest lib/tests/test_sf_paths.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lib import sf_paths
from lib.sf_paths import (
    EXPECTED_IDENTITY_SCHEMA_VERSION,
    HandleNotConfiguredError,
    InvalidHandleError,
    SchemaVersionMismatchError,
    framework_root,
    handle,
    validate_handle,
    wiki_path,
)


VALID_HANDLES = ["hazar", "friend-b", "hazar-new", "self", "a", "x1", "a-b-c", "abc123"]
INVALID_HANDLES = [
    "", "../etc", "a/b", "..", "Hazar", "1x", "-x", "a_b", "a.b", "a b", "héllo", "x/../y",
]

# Wiki-root env vars the F1 resolver consults, plus the framework-root override.
_WIKI_ENV_VARS = ("SF_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "SF_FRAMEWORK_ROOT")


@pytest.fixture
def clean_path_env(monkeypatch):
    """Start from a known-empty env so ambient wiki/framework overrides can't leak in."""
    for var in _WIKI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def temp_wiki(clean_path_env):
    """A temp framework root whose wiki/ is reachable via tier-3 (SF_FRAMEWORK_ROOT)."""
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("SF_FRAMEWORK_ROOT", tmp)
        wiki = Path(tmp) / "wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        yield wiki


# --- validate_handle unit ---------------------------------------------------


@pytest.mark.parametrize("h", VALID_HANDLES)
def test_validate_handle_accepts_valid(h):
    assert validate_handle(h) == h


@pytest.mark.parametrize("h", INVALID_HANDLES)
def test_validate_handle_rejects_invalid(h):
    with pytest.raises(InvalidHandleError):
        validate_handle(h)


def test_invalid_handle_subclasses_not_configured():
    """Existing `except HandleNotConfiguredError` handlers (sf-recall/sf-wrap) must
    still catch the malformed-handle error with the same /sf:interview remediation."""
    assert issubclass(InvalidHandleError, HandleNotConfiguredError)
    with pytest.raises(HandleNotConfiguredError):
        validate_handle("../../etc/passwd")


# --- handle() enforcement ---------------------------------------------------


def test_handle_raises_when_identity_missing(temp_wiki):
    with pytest.raises(HandleNotConfiguredError) as exc:
        handle()
    assert "/sf:interview" in str(exc.value)


def test_handle_raises_when_no_handle_field(temp_wiki):
    (temp_wiki / "identity.md").write_text(
        "---\nschema_version: 1\nname: \"x\"\n---\n", encoding="utf-8"
    )
    with pytest.raises(HandleNotConfiguredError):
        handle()


def test_handle_raises_on_malformed_identity_handle(temp_wiki):
    (temp_wiki / "identity.md").write_text(
        "---\nschema_version: 1\nhandle: ../../etc\n---\n", encoding="utf-8"
    )
    with pytest.raises(InvalidHandleError) as exc:
        handle()
    assert "/sf:interview" in str(exc.value)


def test_handle_validates_even_when_strict_schema_false(temp_wiki):
    """Path-safety is independent of schema version: repair-mode (strict_schema=False)
    must still reject a traversal handle."""
    (temp_wiki / "identity.md").write_text(
        "---\nschema_version: 42\nhandle: ../evil\n---\n", encoding="utf-8"
    )
    with pytest.raises(InvalidHandleError):
        handle(strict_schema=False)


def test_handle_accepts_valid_identity_handle(temp_wiki):
    (temp_wiki / "identity.md").write_text(
        "---\nschema_version: 1\nhandle: friend-b\n---\n", encoding="utf-8"
    )
    assert handle() == "friend-b"


# --- schema-version enforcement ---------------------------------------------


def test_handle_raises_on_schema_mismatch(temp_wiki):
    bad = EXPECTED_IDENTITY_SCHEMA_VERSION + 1
    (temp_wiki / "identity.md").write_text(
        f"---\nschema_version: {bad}\nhandle: hazar\n---\n", encoding="utf-8"
    )
    with pytest.raises(SchemaVersionMismatchError) as exc:
        handle()
    assert exc.value.found == bad
    assert exc.value.expected == EXPECTED_IDENTITY_SCHEMA_VERSION
    assert "/sf:update" in str(exc.value)


def test_handle_strict_schema_false_reads_stale_schema(temp_wiki):
    (temp_wiki / "identity.md").write_text(
        f"---\nschema_version: {EXPECTED_IDENTITY_SCHEMA_VERSION + 9}\nhandle: hazar\n---\n",
        encoding="utf-8",
    )
    assert handle(strict_schema=False) == "hazar"


def test_handle_no_schema_version_field_is_tolerated(temp_wiki):
    """Absent schema_version → no mismatch raised; handle still resolves."""
    (temp_wiki / "identity.md").write_text(
        "---\nhandle: hazar\n---\n", encoding="utf-8"
    )
    assert handle() == "hazar"


# --- frontmatter parsing ----------------------------------------------------


def test_parse_handle_strips_quotes():
    assert sf_paths._parse_handle_from_frontmatter('---\nhandle: "hazar"\n---\n') == "hazar"
    assert sf_paths._parse_handle_from_frontmatter("---\nhandle: 'hazar'\n---\n") == "hazar"


def test_parse_handle_no_frontmatter_returns_none():
    assert sf_paths._parse_handle_from_frontmatter("no frontmatter here\nhandle: x\n") is None


def test_parse_schema_version_non_integer_returns_none():
    assert sf_paths._parse_schema_version_from_frontmatter("---\nschema_version: x\n---\n") is None


# --- F1: 3-tier wiki_path() resolution --------------------------------------


def test_wiki_path_default_is_framework_root_wiki(clean_path_env):
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("SF_FRAMEWORK_ROOT", tmp)
        assert wiki_path() == framework_root() / "wiki"
        assert wiki_path() == Path(tmp) / "wiki"


def test_wiki_path_honors_plugin_option_when_sf_wiki_root_unset(clean_path_env):
    """The advertised `wikiRoot` plugin option is honored on its own (the F1 fix)."""
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", tmp)
        assert wiki_path() == Path(tmp)


def test_wiki_path_sf_wiki_root_takes_precedence(clean_path_env):
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        clean_path_env.setenv("SF_WIKI_ROOT", a)
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", b)
        assert wiki_path() == Path(a)


def test_wiki_path_is_independent_of_framework_root(clean_path_env):
    """Plugin option alone must win even when SF_FRAMEWORK_ROOT points elsewhere —
    wiki_path() is not derived from framework_root() (the F1 latent split)."""
    with tempfile.TemporaryDirectory() as fw, tempfile.TemporaryDirectory() as wiki:
        clean_path_env.setenv("SF_FRAMEWORK_ROOT", fw)
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", wiki)
        assert wiki_path() == Path(wiki)
        assert wiki_path() != framework_root() / "wiki"


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_wiki_path_blank_value_treated_as_unset(clean_path_env, blank):
    """Whitespace-only SF_WIKI_ROOT must not shadow the lower tiers."""
    with tempfile.TemporaryDirectory() as plugin:
        clean_path_env.setenv("SF_WIKI_ROOT", blank)
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", plugin)
        assert wiki_path() == Path(plugin)


def test_wiki_path_blank_falls_through_to_default(clean_path_env):
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("SF_FRAMEWORK_ROOT", tmp)
        clean_path_env.setenv("SF_WIKI_ROOT", "   ")
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", "")
        assert wiki_path() == Path(tmp) / "wiki"


def test_wiki_path_expands_tilde(clean_path_env):
    clean_path_env.setenv("SF_WIKI_ROOT", "~/custom-wiki")
    assert wiki_path() == Path.home() / "custom-wiki"


def test_wiki_path_expands_env_var(clean_path_env):
    clean_path_env.setenv("SF_WIKI_ROOT", "${HOME}/env-wiki")
    assert wiki_path() == Path.home() / "env-wiki"


def test_wiki_path_strips_surrounding_whitespace(clean_path_env):
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("SF_WIKI_ROOT", f"  {tmp}  ")
        assert wiki_path() == Path(tmp)


def test_unterminated_frontmatter_handle_in_body_rejected():
    """A `handle:` line in a truncated body with NO closing --- must not be accepted."""
    assert sf_paths._parse_handle_from_frontmatter(
        "---\ntitle: x\nhandle: evil\nmore body\n"
    ) is None

def test_terminated_frontmatter_still_parses():
    assert sf_paths._parse_handle_from_frontmatter(
        "---\nhandle: good\n---\nbody\n"
    ) == "good"

def test_validate_handle_rejects_overlong():
    with pytest.raises(InvalidHandleError):
        validate_handle("a" * 50_000)

def test_validate_handle_accepts_50_char_boundary():
    validate_handle("a" + "b" * 49)  # exactly 50 chars
