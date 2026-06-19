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
def eval_sandbox():
    root = Path(tempfile.mkdtemp(prefix="ren-c5a-eval-"))
    wiki_root = root / "wiki"
    plugin_data = root / "plugin-data"
    wiki_root.mkdir(parents=True)
    plugin_data.mkdir(parents=True)
    env = dict(os.environ)
    env["SF_WIKI_ROOT"] = str(wiki_root)
    env["CLAUDE_PLUGIN_DATA"] = str(plugin_data)
    try:
        yield SandboxEnv(env=env, cwd=root, wiki_root=wiki_root, plugin_data=plugin_data)
    finally:
        shutil.rmtree(root, ignore_errors=True)
