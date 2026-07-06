"""
skills.code_map library — Graphify-backed code-map wrapper (Task 5.2, RenOS
0.2 Phase 5).

Spec §3.2 v2.1 D-4: the code-map is a THIN WRAPPER over Graphify (open-source,
MIT, tree-sitter/deterministic, pinned version) — not a hand-rolled engine.
Per the reuse doctrine, this DELETES the old carried `lib/codemap/` engine
(harvest map row flips ADAPT -> LEAVE); there is no donor code to port here.

What stays OURS:
  - Token instrumentation (the chairman ruling: Graphify's savings claims are
    marketing until they show up in OUR numbers — `consume()` records both
    the loaded graph's token count AND a baseline of the raw source it
    summarizes, so the win or its absence is measured, not asserted).
  - The staleness check (mtime of the newest source file under `repo_root`
    vs. `graph.json`'s mtime).
  - Doctor checks (installed? version-pinned? output fresh?) — `status()` is
    what a doctor check calls.

Boundaries (all load-bearing, not incidental):
  - Output lands in `state_dir()/derived/codemap/` — OUTSIDE the wiki page
    tree, the write-queue, integrity checks, and the backup-critical set.
    It's a regenerable cache, not memory. `build()` asserts this invariant in
    code rather than just documenting it.
  - Graphify's wiki/Obsidian EXPORT feature is NEVER invoked here — the SSOT
    stays queue-governed; this module only ever calls Graphify's code-mode
    (deterministic tree-sitter parsing), never its LLM media-extraction
    paths.
  - Graceful absence: graphify not installed -> `status()` reports it
    plainly (no raise), `build()`/`consume()` raise `CodeMapUnavailable` with
    an install pointer. No fallback engine, no second implementation.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from lib import ren_paths
from lib.instrument import collect, estimator

GRAPHIFY_PIN = "0.9"
DERIVED_DIR = "derived/codemap"
GRAPH_FILENAME = "graph.json"

_VERSION_RE = re.compile(r"\d+\.\d+(?:\.\d+)?")

_INSTALL_POINTER = (
    "graphify not installed — `uv tool install graphifyy` "
    "(optional companion; see doctrine/companions.md)"
)


class CodeMapUnavailable(Exception):
    """Raised when graphify isn't installed, a build/consume invocation
    fails, or (for `consume`) the graph is absent/stale. Always includes an
    actionable message — the missing-binary case always includes the install
    pointer."""


@dataclass(frozen=True)
class CodeMapStatus:
    installed: bool
    version: str | None
    pinned_ok: bool          # version.startswith(GRAPHIFY_PIN)
    graph_path: Path | None  # state_dir()/DERIVED_DIR/graph.json if it exists
    stale: bool              # newest source mtime > graph.json mtime (True if no graph)


def _derived_dir() -> Path:
    return ren_paths.state_dir() / DERIVED_DIR


def _graph_path() -> Path:
    return _derived_dir() / GRAPH_FILENAME


def _run_version(binary: str) -> str | None:
    """Tolerant `graphify --version` parse: find the first version-shaped
    substring in combined stdout+stderr. Returns None on any failure to
    launch, a timeout, or output with no recognizable version — never
    raises."""
    try:
        result = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    match = _VERSION_RE.search(combined)
    return match.group(0) if match else None


def _iter_repo_files(repo_root: Path):
    """Yield every real file under `repo_root`, skipping dot-directories
    (.git, .venv, etc.) and dotfiles — a cheap, good-enough source-file walk
    for staleness/baseline purposes (not a build system; no gitignore
    parsing)."""
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(repo_root).parts):
            continue
        yield path


def _newest_source_mtime(repo_root: Path) -> float | None:
    newest: float | None = None
    for path in _iter_repo_files(repo_root):
        mtime = path.stat().st_mtime
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def _concatenate_sources(repo_root: Path) -> str:
    """Concatenate every source file's text under `repo_root`, for the
    baseline token estimate `consume()` compares the graph against.
    Unreadable (binary/non-UTF-8) files are skipped, not fatal."""
    parts: list[str] = []
    for path in sorted(_iter_repo_files(repo_root)):
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(parts)


def status(repo_root: Path) -> CodeMapStatus:
    """Report graphify's install/version/pin state and the derived graph's
    freshness. Never raises — this is the doctor-check surface, and a doctor
    check that crashes on an absent optional companion defeats the point of
    "graceful absence"."""
    repo_root = Path(repo_root)
    binary = shutil.which("graphify")
    installed = binary is not None
    version = _run_version(binary) if installed else None
    pinned_ok = bool(version) and version.startswith(GRAPHIFY_PIN)

    graph_path = _graph_path()
    if graph_path.is_file():
        newest_src = _newest_source_mtime(repo_root)
        stale = newest_src is not None and newest_src > graph_path.stat().st_mtime
        resolved_graph_path: Path | None = graph_path
    else:
        stale = True
        resolved_graph_path = None

    return CodeMapStatus(
        installed=installed,
        version=version,
        pinned_ok=pinned_ok,
        graph_path=resolved_graph_path,
        stale=stale,
    )


def build(repo_root: Path, session: str) -> Path:
    """Run `graphify <repo_root> --output <state_dir()/derived/codemap>`
    headlessly. Raises `CodeMapUnavailable` if the binary is missing or exits
    nonzero. Records a `codemap_tokens` "build" metric (real byte size) on
    success. NEVER writes under the wiki page tree — asserted in code, not
    just documented.
    """
    repo_root = Path(repo_root)
    binary = shutil.which("graphify")
    if binary is None:
        raise CodeMapUnavailable(_INSTALL_POINTER)

    derived = _derived_dir()
    derived.mkdir(parents=True, exist_ok=True)
    assert derived.is_relative_to(ren_paths.state_dir()), (
        "code-map output must live under state_dir(), never the wiki page tree"
    )

    try:
        result = subprocess.run(
            [binary, str(repo_root), "--output", str(derived)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeMapUnavailable(f"{_INSTALL_POINTER} (invocation failed: {exc})") from exc

    if result.returncode != 0:
        raise CodeMapUnavailable(
            f"graphify exited with code {result.returncode}: {result.stderr.strip()}"
        )

    graph_path = _graph_path()
    if not graph_path.is_file():
        raise CodeMapUnavailable(
            f"graphify reported success but {graph_path} was not created"
        )

    collect.record(
        collect.KIND_CODEMAP_TOKENS,
        {"event": "build", "graph_bytes": graph_path.stat().st_size, "session": session},
    )
    return graph_path


def consume(repo_root: Path, session: str) -> dict:
    """Load the derived graph and return it alongside the chairman-ruling
    token instrumentation: `tokens_loaded` (the graph itself) vs.
    `tokens_baseline` (the raw source it summarizes) — the token win must
    show up in these numbers, not just in Graphify's own marketing.

    Raises `CodeMapUnavailable` if the graph is absent OR stale (mtime of the
    newest source file under `repo_root` is newer than `graph.json`) — the
    caller decides whether to `build()` again, this function never rebuilds
    silently.
    """
    repo_root = Path(repo_root)
    graph_path = _graph_path()
    if not graph_path.is_file():
        raise CodeMapUnavailable("code-map graph is absent; run build() first")

    newest_src = _newest_source_mtime(repo_root)
    if newest_src is not None and newest_src > graph_path.stat().st_mtime:
        raise CodeMapUnavailable("code-map graph is stale; run build() again")

    graph_text = graph_path.read_text(encoding="utf-8")
    tokens_loaded = estimator.estimate_tokens(graph_text)
    tokens_baseline = estimator.estimate_tokens(_concatenate_sources(repo_root))

    collect.record(
        collect.KIND_CODEMAP_TOKENS,
        {
            "event": "consume",
            "tokens_loaded": tokens_loaded,
            "tokens_baseline": tokens_baseline,
            "session": session,
        },
    )

    return {
        "graph": json.loads(graph_text),
        "tokens_loaded": tokens_loaded,
        "tokens_baseline": tokens_baseline,
    }


__all__ = [
    "GRAPHIFY_PIN",
    "DERIVED_DIR",
    "CodeMapStatus",
    "CodeMapUnavailable",
    "status",
    "build",
    "consume",
]
