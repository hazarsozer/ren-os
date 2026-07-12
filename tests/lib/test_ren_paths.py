"""
Tests for lib.ren_paths — the framework-wide path/handle/schema core.

Ported from startup-framework's `lib/tests/test_sf_paths.py` (ADR-031) for RenOS
0.2 (Task 0.2). Two concerns:
  1. Handle validation / schema / frontmatter parsing.
  2. The Codex F1 fix: 3-tier wiki-root resolution
     (REN_WIKI_ROOT → CLAUDE_PLUGIN_OPTION_WIKIROOT → framework_root()/wiki), resolved
     independently of framework_root() so the advertised `wikiRoot` option works alone.

Plus new coverage for the four names Task 0.2 requires downstream phases to import:
wiki_root(), state_dir(), safe_join(), REN_SCHEMA_VERSION.

Run with: uv run pytest tests/lib/test_ren_paths.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lib import ren_paths
from lib.ren_paths import (
    EXPECTED_IDENTITY_SCHEMA_VERSION,
    REN_SCHEMA_VERSION,
    HandleNotConfiguredError,
    InvalidHandleError,
    PathTraversalError,
    SchemaVersionMismatchError,
    claude_user_dir,
    framework_root,
    handle,
    safe_join,
    state_dir,
    validate_handle,
    wiki_root,
)


VALID_HANDLES = ["hazar", "friend-b", "hazar-new", "self", "a", "x1", "a-b-c", "abc123"]
INVALID_HANDLES = [
    "", "../etc", "a/b", "..", "Hazar", "1x", "-x", "a_b", "a.b", "a b", "héllo", "x/../y",
]

# Wiki-root env vars the F1 resolver consults, plus the framework-root override.
_WIKI_ENV_VARS = ("REN_WIKI_ROOT", "CLAUDE_PLUGIN_OPTION_WIKIROOT", "REN_FRAMEWORK_ROOT")


@pytest.fixture
def clean_path_env(monkeypatch):
    """Start from a known-empty env so ambient wiki/framework overrides can't leak in.

    Also never touches the real ~/.renos — every test that needs a root sets
    REN_FRAMEWORK_ROOT or REN_WIKI_ROOT to a tempdir before calling any resolver.
    """
    for var in _WIKI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def temp_wiki(clean_path_env):
    """A temp framework root whose wiki/ is reachable via tier-3 (REN_FRAMEWORK_ROOT)."""
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("REN_FRAMEWORK_ROOT", tmp)
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
    """Existing `except HandleNotConfiguredError` handlers must still catch the
    malformed-handle error with the same /ren:interview remediation."""
    assert issubclass(InvalidHandleError, HandleNotConfiguredError)
    with pytest.raises(HandleNotConfiguredError):
        validate_handle("../../etc/passwd")


# --- handle() enforcement ---------------------------------------------------


def test_handle_raises_when_identity_missing(temp_wiki):
    with pytest.raises(HandleNotConfiguredError) as exc:
        handle()
    assert "/ren:interview" in str(exc.value)


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
    assert "/ren:interview" in str(exc.value)


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
    assert "/ren:update" in str(exc.value)


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


def test_ren_schema_version_is_a_positive_int():
    assert isinstance(REN_SCHEMA_VERSION, int)
    assert REN_SCHEMA_VERSION >= 1


# --- frontmatter parsing ----------------------------------------------------


def test_parse_handle_strips_quotes():
    assert ren_paths._parse_handle_from_frontmatter('---\nhandle: "hazar"\n---\n') == "hazar"
    assert ren_paths._parse_handle_from_frontmatter("---\nhandle: 'hazar'\n---\n") == "hazar"


def test_parse_handle_no_frontmatter_returns_none():
    assert ren_paths._parse_handle_from_frontmatter("no frontmatter here\nhandle: x\n") is None


def test_parse_schema_version_non_integer_returns_none():
    assert ren_paths._parse_schema_version_from_frontmatter("---\nschema_version: x\n---\n") is None


# --- F1: 3-tier wiki_root() resolution --------------------------------------


def test_wiki_root_default_is_framework_root_wiki(clean_path_env):
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("REN_FRAMEWORK_ROOT", tmp)
        assert wiki_root() == framework_root() / "wiki"
        assert wiki_root() == Path(tmp) / "wiki"


def test_wiki_root_honors_plugin_option_when_ren_wiki_root_unset(clean_path_env):
    """The advertised `wikiRoot` plugin option is honored on its own (the F1 fix)."""
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", tmp)
        assert wiki_root() == Path(tmp)


def test_wiki_root_ren_wiki_root_takes_precedence(clean_path_env):
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        clean_path_env.setenv("REN_WIKI_ROOT", a)
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", b)
        assert wiki_root() == Path(a)


def test_wiki_root_is_independent_of_framework_root(clean_path_env):
    """Plugin option alone must win even when REN_FRAMEWORK_ROOT points elsewhere —
    wiki_root() is not derived from framework_root() (the F1 latent split)."""
    with tempfile.TemporaryDirectory() as fw, tempfile.TemporaryDirectory() as wiki:
        clean_path_env.setenv("REN_FRAMEWORK_ROOT", fw)
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", wiki)
        assert wiki_root() == Path(wiki)
        assert wiki_root() != framework_root() / "wiki"


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_wiki_root_blank_value_treated_as_unset(clean_path_env, blank):
    """Whitespace-only REN_WIKI_ROOT must not shadow the lower tiers."""
    with tempfile.TemporaryDirectory() as plugin:
        clean_path_env.setenv("REN_WIKI_ROOT", blank)
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", plugin)
        assert wiki_root() == Path(plugin)


def test_wiki_root_blank_falls_through_to_default(clean_path_env):
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("REN_FRAMEWORK_ROOT", tmp)
        clean_path_env.setenv("REN_WIKI_ROOT", "   ")
        clean_path_env.setenv("CLAUDE_PLUGIN_OPTION_WIKIROOT", "")
        assert wiki_root() == Path(tmp) / "wiki"


def test_wiki_root_expands_tilde(clean_path_env):
    clean_path_env.setenv("REN_WIKI_ROOT", "~/custom-wiki")
    assert wiki_root() == Path.home() / "custom-wiki"


def test_wiki_root_expands_env_var(clean_path_env):
    clean_path_env.setenv("REN_WIKI_ROOT", "${HOME}/env-wiki")
    assert wiki_root() == Path.home() / "env-wiki"


def test_wiki_root_strips_surrounding_whitespace(clean_path_env):
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("REN_WIKI_ROOT", f"  {tmp}  ")
        assert wiki_root() == Path(tmp)


def test_unterminated_frontmatter_handle_in_body_rejected():
    """A `handle:` line in a truncated body with NO closing --- must not be accepted."""
    assert ren_paths._parse_handle_from_frontmatter(
        "---\ntitle: x\nhandle: evil\nmore body\n"
    ) is None


def test_terminated_frontmatter_still_parses():
    assert ren_paths._parse_handle_from_frontmatter(
        "---\nhandle: good\n---\nbody\n"
    ) == "good"


def test_only_opening_fence_returns_none():
    assert ren_paths._parse_handle_from_frontmatter("---\nhandle: x\n") is None


def test_validate_handle_rejects_overlong():
    with pytest.raises(InvalidHandleError):
        validate_handle("a" * 50_000)


def test_validate_handle_accepts_50_char_boundary():
    validate_handle("a" + "b" * 49)  # exactly 50 chars


# --- Task 0.2: state_dir() --------------------------------------------------


def test_state_dir_is_dot_ren_under_wiki_root(clean_path_env):
    with tempfile.TemporaryDirectory() as tmp:
        clean_path_env.setenv("REN_WIKI_ROOT", tmp)
        assert state_dir() == Path(tmp) / ".ren"
        assert state_dir() == wiki_root() / ".ren"


def test_state_dir_follows_wiki_root_tier_precedence(clean_path_env):
    with tempfile.TemporaryDirectory() as fw, tempfile.TemporaryDirectory() as wiki:
        clean_path_env.setenv("REN_FRAMEWORK_ROOT", fw)
        clean_path_env.setenv("REN_WIKI_ROOT", wiki)
        assert state_dir() == Path(wiki) / ".ren"


# --- Task 0.2: safe_join() traversal guard ----------------------------------


def test_safe_join_returns_path_within_base(tmp_path):
    result = safe_join(tmp_path, "sub/dir/file.md")
    assert result == (tmp_path / "sub" / "dir" / "file.md").resolve()


def test_safe_join_allows_base_itself(tmp_path):
    assert safe_join(tmp_path, ".") == tmp_path.resolve()


@pytest.mark.parametrize(
    "rel",
    ["..", "../etc/passwd", "sub/../../escape", "../../../../etc/shadow"],
)
def test_safe_join_raises_on_traversal(tmp_path, rel):
    with pytest.raises(PathTraversalError):
        safe_join(tmp_path, rel)


def test_safe_join_raises_on_absolute_escape(tmp_path):
    with pytest.raises(PathTraversalError):
        safe_join(tmp_path, "/etc/passwd")


def test_safe_join_accepts_string_base(tmp_path):
    result = safe_join(str(tmp_path), "child.md")
    assert result == (tmp_path / "child.md").resolve()


# --- Gate-0 Finding 1: claude_user_dir() precedence -------------------------
# REN_CLAUDE_DIR > CLAUDE_CONFIG_DIR > ~/.claude


@pytest.fixture
def clean_claude_env(monkeypatch):
    monkeypatch.delenv("REN_CLAUDE_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return monkeypatch


def test_claude_user_dir_defaults_to_home_dot_claude(clean_claude_env):
    assert claude_user_dir() == Path.home() / ".claude"


def test_claude_user_dir_honors_claude_config_dir_when_ren_unset(clean_claude_env, tmp_path):
    """Gate-0 shape: CLAUDE_CONFIG_DIR set (sandboxed profile), REN_CLAUDE_DIR
    unset — writes must land under CLAUDE_CONFIG_DIR, not the real ~/.claude."""
    clean_claude_env.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert claude_user_dir() == tmp_path


def test_claude_user_dir_ren_claude_dir_takes_precedence_over_claude_config_dir(
    clean_claude_env, tmp_path
):
    ren_dir = tmp_path / "ren-override"
    config_dir = tmp_path / "config-dir"
    clean_claude_env.setenv("REN_CLAUDE_DIR", str(ren_dir))
    clean_claude_env.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    assert claude_user_dir() == ren_dir


def test_claude_user_dir_ren_claude_dir_alone_still_works(clean_claude_env, tmp_path):
    clean_claude_env.setenv("REN_CLAUDE_DIR", str(tmp_path))
    assert claude_user_dir() == tmp_path
