"""
skills.wiki-migration library — minimal schema registry + thin verify/apply
primitive (Task 7.3, RenOS 0.2 Phase 7).

Spec §7.1: donor's heavy chain-computer/registry-template machinery is
PRE-EXCLUDED for 0.2. This module is deliberately thin:

  - `load_registry()` — reads `schemas.json` (page_type → current version +
    ordered migration-directory-name chain). Enumerates only page types
    actually stamped by something in this repo (identity, l2-map,
    routine-spec) — not a speculative full taxonomy.
  - `migration_chain(page_type, from_version)` — the subset of a page type's
    chain that still needs to run for a page currently at `from_version`.
  - `run_migration(migration_dir, page_path, wiki_root, snapshot_dir)` — runs
    one migration directory's `migrate.sh` against one page. Sets BOTH the
    `SF_*` and `REN_*` env var names (the env-mapping shim) so the SAME
    runner works against `migrations/routine-spec-1-to-2/` (carried verbatim
    from donor, expects `SF_WIKI_ROOT`/`SF_SNAPSHOT_DIR`) and
    `migrations/routine-spec-2-to-3/` (written fresh for this repo, expects
    `REN_WIKI_ROOT`/`REN_SNAPSHOT_DIR`) without the caller needing to know
    which convention a given `migrate.sh` reads.
  - `verify_page(verify_json_path, page_path)` — a minimal predicate checker
    for `verify.json` files: `yaml.valid`, `yaml.equals`, `yaml.present`,
    `yaml.in` against the page's frontmatter (dotted-path field lookup, so
    `allowlist.paths` works). `snapshot.body-identical` is intentionally NOT
    implemented here — it needs a snapshot path this thin signature doesn't
    carry; a caller wanting that check compares bodies directly (both
    migration test suites in this repo already do exactly that).

Donor's full `verify-page.sh` + JSON-schema validation + the chain-computer
script + doctor's schema-drift integration are NOT carried — see the module
docstring's PRE-EXCLUDED note. This is enough to actually run and verify the
two migration directories that exist in this repo, nothing more.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_DIR_RE = re.compile(r"^(?P<type>.+)-(?P<from>\d+)-to-(?P<to>\d+)$")


def _default_registry_path() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas.json"


def load_registry(registry_path: Path | None = None) -> dict[str, Any]:
    """Load `schemas.json`. Returns `{}` if missing/malformed rather than
    raising — a registry-reading failure shouldn't crash `/ren:doctor`'s
    other checks."""
    path = registry_path or _default_registry_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def migration_chain(page_type: str, from_version: int, registry: dict[str, Any] | None = None) -> list[str]:
    """The ordered subset of `page_type`'s migration-directory chain that
    still needs to run for a page currently at `from_version`. Directory
    names are expected to look like `<page_type>-<from>-to-<to>`."""
    registry = registry if registry is not None else load_registry()
    all_dirs = registry.get("page_types", {}).get(page_type, {}).get("migrations", [])
    chain: list[str] = []
    for name in all_dirs:
        m = _DIR_RE.match(name)
        if not m:
            continue
        if int(m.group("from")) >= from_version:
            chain.append(name)
    return chain


@dataclass(frozen=True)
class MigrationRunResult:
    returncode: int
    stdout: str
    stderr: str
    skipped: bool     # True if migrate.sh reported "SKIP: ..." (already at target schema)


def run_migration(migration_dir: Path, page_path: Path, wiki_root: Path, snapshot_dir: Path) -> MigrationRunResult:
    """Run `<migration_dir>/migrate.sh <page_path>`, with BOTH `SF_*` and
    `REN_*` env var names set to the same `wiki_root`/`snapshot_dir` (the
    env-mapping shim — see module docstring). Never raises on the script's
    own failure; the caller inspects `returncode`."""
    migrate_script = Path(migration_dir) / "migrate.sh"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "SF_WIKI_ROOT": str(wiki_root),
        "SF_SNAPSHOT_DIR": str(snapshot_dir),
        "REN_WIKI_ROOT": str(wiki_root),
        "REN_SNAPSHOT_DIR": str(snapshot_dir),
    }
    proc = subprocess.run(
        ["bash", str(migrate_script), str(page_path)],
        capture_output=True, text=True, env=env,
    )
    return MigrationRunResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        skipped="SKIP" in proc.stdout,
    )


def _parse_frontmatter(text: str) -> dict[str, Any]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    import yaml
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _get_field(data: dict[str, Any], dotted_path: str) -> tuple[Any, bool]:
    """Dotted-path lookup (e.g. `allowlist.paths`) into a nested dict.
    Returns `(value, found)`."""
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def verify_page(verify_json_path: Path, page_path: Path) -> tuple[bool, list[str]]:
    """Check `page_path`'s frontmatter against `verify_json_path`'s
    assertions. Supports `yaml.valid`, `yaml.equals`, `yaml.present`,
    `yaml.in`; `snapshot.body-identical` is a no-op here (see module
    docstring). Returns `(all_passed, [failure descriptions])`.
    """
    spec = json.loads(Path(verify_json_path).read_text(encoding="utf-8"))
    text = Path(page_path).read_text(encoding="utf-8")
    frontmatter = _parse_frontmatter(text)

    failures: list[str] = []
    for assertion in spec.get("assertions", []):
        predicate = assertion["predicate"]
        assertion_id = assertion.get("id", predicate)

        if predicate == "yaml.valid":
            if not text.startswith("---"):
                failures.append(f"{assertion_id}: no frontmatter fence")
        elif predicate == "yaml.equals":
            value, found = _get_field(frontmatter, assertion["field"])
            if not found or value != assertion["value"]:
                failures.append(
                    f"{assertion_id}: {assertion['field']} == {value!r}, expected {assertion['value']!r}"
                )
        elif predicate == "yaml.present":
            _, found = _get_field(frontmatter, assertion["field"])
            if not found:
                failures.append(f"{assertion_id}: {assertion['field']} missing")
        elif predicate == "yaml.in":
            value, found = _get_field(frontmatter, assertion["field"])
            if not found or value not in assertion["values"]:
                failures.append(
                    f"{assertion_id}: {assertion['field']} = {value!r} not in {assertion['values']}"
                )
        elif predicate == "snapshot.body-identical":
            continue  # not implemented in the thin runner — see docstring
        else:
            failures.append(f"{assertion_id}: unknown predicate {predicate!r}")

    return (not failures, failures)


__all__ = [
    "load_registry",
    "migration_chain",
    "MigrationRunResult",
    "run_migration",
    "verify_page",
]
