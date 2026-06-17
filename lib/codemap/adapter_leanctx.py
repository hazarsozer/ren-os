"""The only lean-ctx-aware unit. Per-file `lean-ctx read -m signatures` (text) -> Symbol[]."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.codemap.model import Symbol  # noqa: E402

LEANCTX_BIN = "lean-ctx"
TIMEOUT = 60
SOURCE_GLOBS = ("*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.go", "*.rs", "*.java")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
             "build", "target", "vendor", ".next", ".mypy_cache", ".pytest_cache"}

# A lean-ctx `-m signatures` line, e.g. "fn pub framework_version() → str @L49-82"
# or "class pub Foo @L1-40" or indented "  fn __init__(self) → None @L5-9".
_SIG_RE = re.compile(
    r'^(?P<indent>\s*)(?P<kind>fn|class)\s+(?:pub\s+)?(?P<name>\w+)'
    r'(?:\((?P<params>.*?)\))?\s*(?:→\s*(?P<ret>.*?))?\s*@L(?P<start>\d+)-(?P<end>\d+)\s*$'
)
_KIND = {"fn": "function", "class": "class"}


class EngineUnavailable(RuntimeError):
    """lean-ctx is not installed or not runnable."""


def _symbols_from_signatures(text: str, file_rel: str) -> list[Symbol]:
    out: list[Symbol] = []
    for line in text.splitlines():
        m = _SIG_RE.match(line)
        if not m:
            continue  # file-header ("name.py [322L]") or unparseable -> skip
        kind = _KIND.get(m.group("kind"), m.group("kind"))
        if m.group("indent") and kind == "function":
            kind = "method"
        params = m.group("params")
        ret = (m.group("ret") or "").strip()
        sig = m.group("name") + (f"({params})" if params is not None else "") + (f" → {ret}" if ret else "")
        out.append(Symbol(name=m.group("name"), kind=kind, file=file_rel,
                          start_line=int(m.group("start")), end_line=int(m.group("end")),
                          signature=sig))
    return out


def _iter_source_files(project_root: Path):
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if any(p.match(g) for g in SOURCE_GLOBS):
                yield p


def run_leanctx(project_root: Path) -> list[Symbol]:
    """Per-file `lean-ctx read -m signatures` over project_root -> Symbol[].

    Read-only on the project (lean-ctx writes only to its XDG cache; spike-verified).
    Raises EngineUnavailable if the binary is missing.
    """
    project_root = Path(project_root).resolve()
    symbols: list[Symbol] = []
    for fp in _iter_source_files(project_root):
        try:
            proc = subprocess.run([LEANCTX_BIN, "read", str(fp), "-m", "signatures"],
                                  capture_output=True, timeout=TIMEOUT)
        except (FileNotFoundError, OSError) as e:
            raise EngineUnavailable(str(e)) from e
        except subprocess.TimeoutExpired:
            continue  # one slow file shouldn't fail the whole map
        if proc.returncode != 0:
            continue  # skip a file lean-ctx can't parse; don't abort the whole map
        rel = str(fp.relative_to(project_root))
        symbols.extend(_symbols_from_signatures(proc.stdout.decode("utf-8", errors="replace"), rel))
    return symbols
