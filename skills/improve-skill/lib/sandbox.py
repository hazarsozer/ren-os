"""Eval sandbox: run a skill with wiki/plugin-data writes redirected to a tmp tree,
so the real wiki/project is left byte-identical. We build an env COPY (passed to the
subprocess) rather than mutating os.environ — keeps the orchestrator process clean."""
from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxEnv:
    env: dict
    cwd: Path
    wiki_root: Path
    plugin_data: Path


@contextmanager
def eval_sandbox(skill_cwd: Path | None = None):
    """Run a skill with wiki/plugin-data WRITES redirected to a throwaway tmp tree.

    `skill_cwd`, when given, is the working directory handed to the subprocess
    (the plugin-active worktree root, so the worktree's own skills load and the
    eval scores the iteration's edits). When None, the cwd is the tmp root —
    the legacy isolated behavior. Teardown removes ONLY the tmp root; the
    skill_cwd (the real repo) is never touched.
    """
    root = Path(tempfile.mkdtemp(prefix="ren-c5a-eval-"))
    wiki_root = root / "wiki"
    plugin_data = root / "plugin-data"
    wiki_root.mkdir(parents=True)
    plugin_data.mkdir(parents=True)
    env = dict(os.environ)
    env["SF_WIKI_ROOT"] = str(wiki_root)
    env["CLAUDE_PLUGIN_DATA"] = str(plugin_data)
    cwd = skill_cwd if skill_cwd is not None else root
    try:
        yield SandboxEnv(env=env, cwd=cwd, wiki_root=wiki_root, plugin_data=plugin_data)
    finally:
        shutil.rmtree(root, ignore_errors=True)
