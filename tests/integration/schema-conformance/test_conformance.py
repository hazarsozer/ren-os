"""
pytest wrapper for the schema-conformance harness.

CI integration: this runs in the `validate.yml` workflow's schemas job once
we expand it. For now, the workflow runs conformance.py directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add this directory to sys.path so `import conformance` works. The previous
# importlib.util.spec_from_file_location pattern broke pytest collection because
# the @dataclass decorator's introspection of cls.__module__ can't recover the
# module dict when loaded via spec. Plain sys.path + normal import is the
# minimum-friction fix.
HERE = Path(__file__).parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import conformance  # noqa: E402


def test_schema_conformance() -> None:
    """All strict-mode files must conform to the registry contract."""
    registry = conformance.load_registry()
    report = conformance.walk_targets(registry)

    strict_fails = [r for r in report.by_status["fail"] if r.mode == "strict"]

    if strict_fails:
        msg_lines = ["Schema conformance failures (strict mode):"]
        for r in strict_fails:
            msg_lines.append(f"  {r.path}")
            msg_lines.append(f"    type: {r.type_claimed!r}, schema_version: {r.schema_version!r}")
            msg_lines.append(f"    reason: {r.detail}")
        raise AssertionError("\n".join(msg_lines))


def test_all_registered_types_have_conformant_example() -> None:
    """Surface as XFAIL if a registered page-type has zero conformant examples.

    This is informational at v1.0 — not all 16 types will have shipped templates yet.
    Marked xfail; flip to a hard assertion once all peers have shipped their templates.
    """
    import pytest

    registry = conformance.load_registry()
    report = conformance.walk_targets(registry)
    missing = [
        ptype for ptype in registry["page_types"]
        if ptype not in report.type_coverage
    ]
    if missing:
        pytest.xfail(f"Page-types without a conformant example yet: {missing}")


# ──────────────────────────────────────────────────────────────────────
# framework_version semver-regex pin tests (lifecycle-2 coord 2026-05-28)
# ──────────────────────────────────────────────────────────────────────
import tempfile  # noqa: E402


def _write_test_file(content: str) -> Path:
    """Write content to a temp file; return Path."""
    tmpdir = tempfile.mkdtemp(prefix="conformance-")
    p = Path(tmpdir) / "test-page.md"
    p.write_text(content, encoding="utf-8")
    return p


def test_semver_regex_accepts_valid_versions() -> None:
    """The SEMVER_RE must accept canonical semver triples + pre-release + build metadata."""
    valid = [
        "1.0.0",
        "0.0.1",
        "10.20.30",
        "1.0.0-rc.1",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-rc.10",
        "2.0.0-rc.final",
        "1.0.0+build.123",
        "1.0.0-rc.1+exp.sha.5114f85",
    ]
    for v in valid:
        assert conformance.SEMVER_RE.match(v), f"SEMVER_RE rejected valid: {v!r}"


def test_semver_regex_rejects_invalid_versions() -> None:
    """The SEMVER_RE must reject malformed values that would silently break the consumer."""
    invalid = [
        "",
        "1",          # too few components
        "1.0",        # two-component (would YAML-parse as float in some configs)
        "1.0.0.0",    # too many components
        "v1.0.0",     # leading 'v' prefix
        "1.0.a",      # non-numeric patch
        "abc",
        "1.0.0 ",     # trailing space
        "1.0.0-",     # empty pre-release
    ]
    for v in invalid:
        assert not conformance.SEMVER_RE.match(v), f"SEMVER_RE accepted invalid: {v!r}"


def test_conformance_fails_on_unquoted_float_framework_version(tmp_path: Path) -> None:
    """A YAML doc with `framework_version: 1.0` (no quotes) parses as float 1.0 — must FAIL."""
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: identity\n"
        "schema_version: 1\n"
        "framework_version: 1.0\n"
        "handle: test\n"
        "name: Test\n"
        "phase: ideation\n"
        "---\n"
        "\nbody\n",
        encoding="utf-8",
    )
    registry = conformance.load_registry()
    result = conformance.check_file(p, "test", "strict", registry)
    assert result.status == "fail", f"expected fail; got {result.status}: {result.detail}"
    assert "framework_version" in result.detail
    assert "semver" in result.detail.lower()


def test_conformance_passes_on_quoted_semver_framework_version(tmp_path: Path) -> None:
    """A YAML doc with `framework_version: \"1.0.0\"` parses as string — must PASS."""
    p = tmp_path / "page.md"
    p.write_text(
        '---\n'
        'type: identity\n'
        'schema_version: 1\n'
        'framework_version: "1.0.0"\n'
        'handle: test\n'
        'name: Test\n'
        'phase: ideation\n'
        '---\n'
        '\nbody\n',
        encoding="utf-8",
    )
    registry = conformance.load_registry()
    result = conformance.check_file(p, "test", "strict", registry)
    assert result.status == "pass", f"expected pass; got {result.status}: {result.detail}"


def test_conformance_passes_on_unquoted_canonical_semver(tmp_path: Path) -> None:
    """A canonical three-component version (e.g. 1.0.0 with no quotes) parses correctly
    in YAML as a string when it matches the semver pattern. Test catches regression in
    PyYAML parsing or the regex itself.
    """
    p = tmp_path / "page.md"
    p.write_text(
        "---\n"
        "type: identity\n"
        "schema_version: 1\n"
        "framework_version: 1.0.0\n"  # unquoted 3-component — YAML keeps as string
        "handle: test\n"
        "name: Test\n"
        "phase: ideation\n"
        "---\n"
        "\nbody\n",
        encoding="utf-8",
    )
    registry = conformance.load_registry()
    result = conformance.check_file(p, "test", "strict", registry)
    assert result.status == "pass", f"expected pass; got {result.status}: {result.detail}"
