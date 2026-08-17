"""Update-skill Python helpers (0.3.5).

The update flow's bash scripts own snapshot/restore/semver; this lib holds
the post-update conveniences. ``changelog_digest`` powers the "what changed
in your RenOS" report — best-effort by design: it returns "" rather than
raising, because the digest is a courtesy, never a gate.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from lib.ren_paths import framework_root, wiki_root

_HEADER_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)
_ANY_HEADER_RE = re.compile(r"^## \[", re.MULTILINE)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def changelog_digest(old: str, new: str, changelog_path: Path | str) -> str:
    """CHANGELOG.md sections for versions in (old, new], in file order.

    Accepts a `Path` or `str` path — the digest is a courtesy, never a
    gate, so an argument-type detail must not crash the closing flow.
    Returns "" when the range is empty, a bound is unparseable, or the
    file is missing/unreadable.
    """
    try:
        text = Path(changelog_path).read_text(encoding="utf-8")
        old_key, new_key = _version_key(old), _version_key(new)
    except (OSError, ValueError):
        return ""

    # Compute boundaries from ALL headers (including prerelease ones).
    boundaries = sorted(m.start() for m in _ANY_HEADER_RE.finditer(text))

    matches = list(_HEADER_RE.finditer(text))
    sections: list[str] = []
    for match in matches:
        try:
            key = _version_key(match.group(1))
        except ValueError:
            continue
        if old_key < key <= new_key:
            # Find the next boundary strictly greater than match.start().
            end = next((b for b in boundaries if b > match.start()), len(text))
            sections.append(text[match.start():end].strip())
    return "\n\n".join(sections)


_TRUST_BACKFILL_GATE = "0.5.1"


def should_run_trust_backfill(old: str, new: str) -> bool:
    """True when an update crosses the 0.5.1 boundary (old < 0.5.1 <= new).

    Gates ``migrations/trust-backfill-1/migrate.py`` (see that migration's
    README) the same way `changelog_digest`'s range check gates the digest:
    a pure version-tuple comparison, no chain machinery involved, because
    trust-backfill-1 is a standalone global migration (not part of
    `skills/wiki-migration`'s page-type chain — see
    `skills/wiki-migration/schemas.json`'s `global_migrations` note).
    """
    try:
        old_key, new_key, gate_key = (
            _version_key(old),
            _version_key(new),
            _version_key(_TRUST_BACKFILL_GATE),
        )
    except ValueError:
        return False
    return old_key < gate_key <= new_key


_PROJECT_KNOWLEDGE_GATE = "0.6.2"


def should_run_project_knowledge_1(old: str, new: str) -> bool:
    """True when an update crosses the 0.6.2 boundary (old < 0.6.2 <= new).

    Gates ``migrations/project-knowledge-1/migrate.py`` (see that migration's
    README) the same way ``should_run_trust_backfill`` gates its migration:
    a pure version-tuple comparison, no chain machinery, because
    project-knowledge-1 is a standalone global migration that walks whole
    ``projects/<slug>/`` directories rather than a schema_version-keyed
    page type.
    """
    try:
        old_key, new_key, gate_key = (
            _version_key(old),
            _version_key(new),
            _version_key(_PROJECT_KNOWLEDGE_GATE),
        )
    except ValueError:
        return False
    return old_key < gate_key <= new_key


_FOREIGN_REMINT_GATE = "0.6.3"


def should_run_foreign_remint_1(old: str, new: str) -> bool:
    """True when an update crosses the 0.6.3 boundary (old < 0.6.3 <= new).

    Gates ``migrations/foreign-remint-1/migrate.py`` (see that migration's
    README) the same way ``should_run_trust_backfill`` gates its migration:
    a pure version-tuple comparison, no chain machinery, because
    foreign-remint-1 is a standalone global migration (issue #22 — restamp
    mis-minted ``ren_trust: "foreign"`` ingest drafts to ``"model"``) that
    walks the whole wiki tree rather than a schema_version-keyed page type.
    """
    try:
        old_key, new_key, gate_key = (
            _version_key(old),
            _version_key(new),
            _version_key(_FOREIGN_REMINT_GATE),
        )
    except ValueError:
        return False
    return old_key < gate_key <= new_key


def should_run_folder_note_hubs_1(wiki_root_path: Path | None = None) -> bool:
    """True if any legacy knowledge-hub index.md remains (raw/, archive/, dot-dirs excluded).

    Unlike ``should_run_trust_backfill``/``should_run_project_knowledge_1``/
    ``should_run_foreign_remint_1``, this gate is idempotent-by-inspection
    rather than version-crossing: ``migrations/folder-note-hubs-1/migrate.py``
    (issue #56) renames `projects/*/knowledge/**/index.md` to
    `<parent-dir>.md`, so the gate just checks whether any such legacy hub
    still exists — same fail-safe reasoning as the migration's own verifier
    (`migrations/folder-note-hubs-1/verify.py`).
    """
    root = wiki_root_path or wiki_root()
    for knowledge in root.glob("projects/*/knowledge"):
        for p in knowledge.rglob("index.md"):
            rel = p.relative_to(root)
            if any(part.startswith(".") or part in ("raw", "archive") for part in rel.parts):
                continue
            return True
    return False


def rerender_all_project_claude_md() -> dict[str, str]:
    """#64 spec §3(b) trigger: `/ren:update`'s closing steps call this so
    every project's repo CLAUDE.md managed block reflects the CURRENT
    adapter/format after migrations land — the queue's post-apply hook and
    revert's post-revert hook only fire for the ONE project touched by a
    single write; an update can change how EVERY project's block renders
    (a format change, a doctrine index refresh) without touching any
    instructions.md at all.

    For every registered project slug whose wiki carries a
    `projects/<slug>/instructions.md` (same detection
    `skills/doctor/lib/check_standing_instructions_drift` uses), calls
    `write_project_claude_md`. Returns `{slug: "ok"}` on success or
    `{slug: "error: <msg>"}` on failure — never raises, so one broken repo
    path never stops the rest of the run."""
    from lib import ren_paths
    from lib.adapter import claude_md

    wiki = wiki_root()
    results: dict[str, str] = {}
    for slug, entry in sorted(ren_paths.load_project_registry().items()):
        if not (wiki / "projects" / slug / "instructions.md").is_file():
            continue
        try:
            claude_md.write_project_claude_md(Path(entry["repo_path"]), slug, wiki_root=wiki)
            results[slug] = "ok"
        except Exception as exc:  # noqa: BLE001 - never stop the run over one slug
            results[slug] = f"error: {exc}"
    return results


def _plugin_cache_versions_root() -> Path | None:
    """Parent of the versioned plugin cache dir, resolved the same way
    `skills.install.lib._repo_root()` and doctor's checks read
    `$CLAUDE_PLUGIN_ROOT` — that env var points AT the currently-running
    version dir (`~/.claude/plugins/cache/ren-os/ren/<version>/`), so its
    parent (`.../ren-os/ren/`) lists every version dir the cache still has.
    Returns None when the env var is unset (bare dev checkout, no installed
    plugin) — callers must treat that as "unresolvable", never as "no live
    versions"."""
    val = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if not val:
        return None
    return Path(os.path.expanduser(os.path.expandvars(val))).parent


def gc_stale_envs() -> list[str]:
    """Remove `framework_root()/.envs/<v>` dirs whose version `<v>` has no
    corresponding dir in the plugin cache (#40) — GCs the per-version uv
    project environments `ren_paths.envs_dir()` points invocations at, once
    that version is no longer installed. Returns the removed version
    strings, in sorted order.

    Never raises: an unresolvable cache root is a no-op (nothing removed —
    we never guess and delete everything just because we can't confirm
    what's live), a missing `.envs` dir is a no-op, and a per-directory
    `OSError` (permissions, a concurrent deletion) just skips that one
    directory rather than aborting the sweep."""
    cache_versions_root = _plugin_cache_versions_root()
    if cache_versions_root is None or not cache_versions_root.is_dir():
        return []

    live_versions = {p.name for p in cache_versions_root.iterdir() if p.is_dir()}

    envs_root = framework_root() / ".envs"
    if not envs_root.is_dir():
        return []

    removed: list[str] = []
    for entry in sorted(envs_root.iterdir()):
        if not entry.is_dir() or entry.name in live_versions:
            continue
        try:
            shutil.rmtree(entry)
        except OSError:
            continue
        removed.append(entry.name)
    return removed
