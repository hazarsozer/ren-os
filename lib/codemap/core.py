"""Orchestration: generate a CodeMap, render + cache it (digest + sidecar), check staleness."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib import sf_paths  # noqa: E402
from lib.codemap.adapter_leanctx import run_leanctx  # noqa: E402
from lib.codemap.digest import render_digest  # noqa: E402
from lib.codemap.model import CodeMap, Symbol  # noqa: E402
from lib.codemap.sources import enumerate_source_files  # noqa: E402
from lib.codemap.staleness import hash_files, is_stale  # noqa: E402


def _git_commit(project_root: Path) -> str:
    try:
        proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=str(project_root), capture_output=True, timeout=10)
        return proc.stdout.decode().strip() if proc.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _sidecar_path(project_name: str) -> Path:
    # The .md is the agent-facing digest; the .json sidecar carries the hashes
    # needed for staleness (keeps the digest clean — refinement of spec §6).
    return sf_paths.code_map_path(project_name).with_suffix(".json")


def _serialize(cm: CodeMap) -> str:
    return json.dumps({
        "project_path": cm.project_path, "generated_at": cm.generated_at,
        "git_commit": cm.git_commit, "file_hashes": cm.file_hashes,
        "symbols": [s.__dict__ for s in cm.symbols],
    }, indent=2)


def _deserialize(text: str) -> CodeMap:
    d = json.loads(text)
    return CodeMap(project_path=d["project_path"], generated_at=d["generated_at"],
                   git_commit=d.get("git_commit", ""), file_hashes=d.get("file_hashes", {}),
                   symbols=tuple(Symbol(**s) for s in d.get("symbols", [])))


def generate(project_root: Path, *, project_name: str) -> CodeMap:
    """Build the code-map for project_root; write the .md digest + .json sidecar."""
    project_root = Path(project_root).resolve()
    symbols = run_leanctx(project_root)
    cm = CodeMap(
        project_path=str(project_root),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_commit=_git_commit(project_root),
        file_hashes=hash_files(project_root, enumerate_source_files(project_root)),
        symbols=tuple(symbols),
    )
    out = sf_paths.code_map_path(project_name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_digest(cm))
    _sidecar_path(project_name).write_text(_serialize(cm))
    return cm


def load_cached(project_name: str) -> str | None:
    """Return the cached digest text, or None if absent."""
    p = sf_paths.code_map_path(project_name)
    return p.read_text() if p.is_file() else None


def load_cached_map(project_name: str) -> CodeMap | None:
    """Return the cached CodeMap from the sidecar, or None if absent."""
    p = _sidecar_path(project_name)
    return _deserialize(p.read_text()) if p.is_file() else None


def check_staleness(project_name: str, project_root) -> "StaleReport | None":
    """StaleReport for a cached map vs the current project, or None if no cache."""
    cm = load_cached_map(project_name)
    return is_stale(cm, Path(project_root)) if cm else None
