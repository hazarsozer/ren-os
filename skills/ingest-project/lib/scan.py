#!/usr/bin/env python3
"""
scan.py — read-only project scanner for /ren:ingest-project (Task 4.4, RenOS
0.2 Phase 4).

Carried near-verbatim from donor `skills/ingest-project/scripts/scan.py`
(`~/Dev/startup-framework`) — only the `_framework_version` import path was
adjusted for this repo's layout (`lib.ren_paths` instead of `lib.sf_paths`,
default fallback bumped to "0.2.0"). The ADR-014 7-file taxonomy this facts
JSON used to feed is DEAD for 0.2; here the facts feed `assemble_l2` (this
skill's `lib/__init__.py`) instead, which renders the L2 pointer-map schema.

Walks an existing project directory and emits a bounded, structured facts JSON
on stdout. The live session (not this script) turns those facts into L2 map
knowledge/pointers; this script only collects facts.

INVARIANTS:
  - NO writes. Every file is opened read-only; nothing in the project is
    created, modified, or deleted.
  - NO network. Pure local filesystem + read-only git subprocess reads.
  - Bounded. Tree depth/entry caps, git summarized, code-skim capped, large
    and sensitive files never read.
  - Tolerant. A project with no git, no README, or no manifest still scans.

Usage:
    python3 scan.py [PATH] [--depth standard|light|deep]

Exit codes:
    0 — scan succeeded (a non-project path is still success: looks_like_project=false)
    2 — invocation error (bad args / path missing)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

SCHEMA_VERSION = 1

MAX_READ_BYTES = 256 * 1024  # never open a file larger than this

SKIP_DIRS = frozenset(
    {
        ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
        "target", "vendor", ".next", "coverage", ".idea", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".gradle", ".tox", "site-packages",
    }
)

# Never read these (secret/credential/binary-ish), even if tracked.
NEVER_READ_GLOBS = (
    ".env", ".env.*", "*.pem", "*.key", "id_rsa", "id_rsa.*", "id_ed25519",
    "credentials", "credentials.*", "*.sqlite", "*.sqlite3", "*.db",
    "*.p12", "*.pfx", "*.keystore", "*.jks",
)


def _framework_version() -> str:
    """Best-effort framework version for page frontmatter. Imports lib.ren_paths
    from the repo root; falls back to the pinned literal below in a bare checkout. Read-only."""
    try:
        plugin_root = Path(__file__).resolve().parents[3]  # lib→ingest-project→skills→<repo root>
        if str(plugin_root) not in sys.path:
            sys.path.insert(0, str(plugin_root))
        from lib.ren_paths import framework_version
        return framework_version()
    except Exception:
        return "0.5.4"


def _is_never_read(name: str) -> bool:
    return any(fnmatch.fnmatch(name, g) for g in NEVER_READ_GLOBS)


def _safe_size(path: Path) -> bool:
    """Return True if path's size is within MAX_READ_BYTES; False on stat error."""
    try:
        return path.stat().st_size <= MAX_READ_BYTES
    except OSError:
        return False


def _git_tracked_files(root: Path) -> list[Path] | None:
    """Return tracked files via `git ls-files`, or None if not a git repo."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(root), capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", errors="replace")
    rels = [r for r in out.split("\0") if r]
    # A git repo with ZERO commits returns rc=0 + EMPTY stdout here. Return None
    # (→ enumerate_files falls back to _walk_files), NOT [] ("no files") — else a
    # freshly `git init`-ed, uncommitted project scans as empty.
    # Bare repos also return rc=0 + empty output -> None -> walk fallback; walking
    # a bare repo's object store is noisy but harmless (looks_like_project handles it).
    if not rels:
        return None
    return [root / r for r in rels]


def _walk_files(root: Path) -> list[Path]:
    """Fallback enumeration for non-git dirs: os.walk with skip-dir pruning."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            found.append(Path(dirpath) / fn)
    return found


def enumerate_files(root: Path) -> list[Path]:
    """Enumerate readable project files, respecting .gitignore (in git repos),
    skip-dirs, never-read globs, and the size cap. Read-only.
    """
    candidates = _git_tracked_files(root)
    if candidates is None:
        candidates = _walk_files(root)
    out: list[Path] = []
    for p in candidates:
        # Any path component in SKIP_DIRS → drop (covers git submodule edge cases).
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        if _is_never_read(p.name):
            continue
        if not p.is_file():
            continue
        if not _safe_size(p):
            continue
        out.append(p)
    return out


# manifest filename → language. Order matters only for readability;
# detection is set-based (seen_langs dedup below).
_MANIFEST_LANG = {
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "setup.py": "Python",
    "setup.cfg": "Python",
    "Pipfile": "Python",
    "package.json": "JavaScript",  # upgraded to TypeScript if tsconfig present
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "build.gradle.kts": "Kotlin",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "pubspec.yaml": "Dart",
}

# lockfile / marker → package manager
_PM_MARKERS = {
    "uv.lock": "uv",
    "poetry.lock": "poetry",
    "Pipfile.lock": "pipenv",
    "requirements.txt": "pip",
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "bun.lockb": "bun",
    "Cargo.lock": "cargo",
    "go.sum": "go modules",
    "Gemfile.lock": "bundler",
    "composer.lock": "composer",
}

# framework name → substrings that, if present in a manifest's text, imply it.
# Loose single-word substrings cause false positives (e.g. "react" in
# "reactive", "rails" in "guardrails-ai" — a real Python AI dep, "next" in
# "next-auth", "torch" in "torchlight"), so the high-collision entries use
# anchored/quoted forms — the same pattern the "spring" entry already follows.
# Goal: fewer false positives, not fewer true positives.
_FRAMEWORK_HINTS = {
    "fastapi": ("fastapi",),
    "django": ("django",),
    "flask": ("flask",),
    "pytorch": ("import torch", '"torch"', "'torch'", "torch>=", "torch==", "pytorch"),
    "next": ('"next"', '"nextjs"', "next.js"),
    "react": ('"react"', "'react'", "react-dom", "react-scripts"),
    "vue": ('"vue"', "'vue'", "vue.js"),
    "svelte": ("svelte",),
    "express": ('"express"', "'express'"),
    "spring": ("spring-boot", "springframework"),
    "rails": ("rails/all", "rails/application", "gem 'rails'", 'gem "rails"'),
    "laravel": ("laravel",),
    "axum": ("axum",),
    "actix": ("actix",),
}


def detect_stack(root: Path, files: list[Path]) -> dict:
    """Detect languages, package managers, and frameworks from manifest presence
    + a bounded substring scan of manifest contents. Read-only."""
    names = {p.name for p in files}
    manifests = sorted(n for n in names if n in _MANIFEST_LANG)

    languages: list[dict] = []
    seen_langs: set[str] = set()
    for m in manifests:
        lang = _MANIFEST_LANG[m]
        # package.json → TypeScript if a tsconfig is present.
        if m == "package.json" and "tsconfig.json" in names:
            lang = "TypeScript"
        if lang not in seen_langs:
            seen_langs.add(lang)
            languages.append({"name": lang, "evidence": m, "confidence": "high"})

    package_managers = sorted({pm for marker, pm in _PM_MARKERS.items() if marker in names})

    # Framework hints: read manifest texts (bounded by MAX_READ_BYTES already).
    blob = ""
    # dict.fromkeys dedups: a manifest already in `manifests` (e.g. pyproject.toml
    # on a Python project) must not be read twice. (review-correction dedup fix)
    for m in dict.fromkeys(manifests + ["package.json", "pyproject.toml"]):
        fp = root / m
        if fp.is_file() and _safe_size(fp):
            try:
                blob += "\n" + fp.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
    frameworks = sorted(
        fw for fw, hints in _FRAMEWORK_HINTS.items() if any(h in blob for h in hints)
    )

    return {
        "languages": languages,
        "package_managers": package_managers,
        "frameworks": frameworks,
        "manifests": manifests,
    }


TREE_DEPTH_CAP = 4
TREE_ENTRY_CAP = 500

_ENTRY_POINT_CANDIDATES = (
    "main.py", "src/main.py", "app.py", "src/app.py", "__main__.py",
    "manage.py", "index.js", "src/index.js", "index.ts", "src/index.ts",
    "main.go", "cmd/main.go", "src/main.rs", "src/lib.rs", "Main.java",
)

_DOC_PATTERNS = (
    ("readme", ("readme.md", "readme.rst", "readme.txt", "readme")),
    ("changelog", ("changelog.md", "changelog")),
    ("contributing", ("contributing.md",)),
)


def build_tree_digest(root: Path, files: list[Path]) -> dict:
    """Summarize the directory shape: top-level dirs, entry count, truncation."""
    top_dirs: set[str] = set()
    notable: set[str] = set()
    truncated = False
    for p in files:
        rel = p.relative_to(root)
        parts = rel.parts
        if len(parts) > 1:
            top_dirs.add(parts[0])
        if len(parts) > TREE_DEPTH_CAP:
            truncated = True
        name = parts[-1]
        if name in ("README.md", "pyproject.toml", "package.json", "Cargo.toml",
                    "go.mod", "Makefile", "Dockerfile", "docker-compose.yml"):
            notable.add(str(rel))
    if len(files) > TREE_ENTRY_CAP:
        truncated = True
    return {
        "depth_cap": TREE_DEPTH_CAP,
        "entry_count": len(files),
        "truncated": truncated,
        "top_dirs": sorted(top_dirs),
        "notable_files": sorted(notable),
    }


def detect_entry_points(root: Path, files: list[Path]) -> list[str]:
    """Return entry-point paths (relative strings) that exist in the file list."""
    rels = {str(p.relative_to(root)) for p in files}
    return [c for c in _ENTRY_POINT_CANDIDATES if c in rels]


def _doc_kind(rel: str) -> str | None:
    """Classify a relative path string as a doc kind, or return None."""
    low = rel.lower()
    base = low.rsplit("/", 1)[-1]
    if "/adr/" in "/" + low or "/decisions/" in "/" + low:
        if low.endswith(".md"):
            return "adr"
    for kind, names in _DOC_PATTERNS:
        if base in names:
            return kind
    if low.startswith("docs/") and low.endswith((".md", ".rst")):
        return "doc"
    return None


def build_doc_inventory(root: Path, files: list[Path]) -> list[dict]:
    """Return a sorted list of {path, kind, bytes} for recognised doc files."""
    inv: list[dict] = []
    for p in files:
        rel = str(p.relative_to(root))
        kind = _doc_kind(rel)
        if kind is None:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        inv.append({"path": rel, "kind": kind, "bytes": size})
    inv.sort(key=lambda d: d["path"])
    return inv


GIT_TIMEOUT = 30
RECENT_COMMITS = 10


def _git(root: Path, args: list[str]) -> str | None:
    """Run a read-only git command; return stdout text or None on any failure."""
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=str(root),
            capture_output=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def collect_git_facts(root: Path) -> dict:
    """Collect bounded, read-only git history facts. Monthly timeline buckets;
    tags annotated; recent commits capped. Returns {'is_repo': False} for non-repos."""
    inside = _git(root, ["rev-parse", "--is-inside-work-tree"])
    if inside is None or inside.strip() != "true":
        return {"is_repo": False}

    facts: dict = {"is_repo": True}

    # Zero-commit repo: `rev-parse --is-inside-work-tree` is "true" but there is no
    # HEAD yet, so rev-list/status would emit misleading facts (dirty=True from
    # untracked-only). Report it honestly and return early.
    head = _git(root, ["rev-parse", "--verify", "-q", "HEAD"])
    if head is None or not head.strip():
        facts["commit_count"] = 0
        facts["branch"] = (_git(root, ["symbolic-ref", "--short", "-q", "HEAD"]) or "").strip()
        facts["dirty"] = False
        facts["first_commit"] = ""
        facts["last_commit"] = ""
        facts["timeline"] = []
        facts["tags"] = []
        facts["recent"] = []
        facts["no_commits"] = True
        return facts

    count = _git(root, ["rev-list", "--count", "HEAD"])
    facts["commit_count"] = int(count.strip()) if count and count.strip().isdigit() else 0

    branch = _git(root, ["symbolic-ref", "--short", "HEAD"])
    if branch is None:
        # detached HEAD: abbrev-ref returns "HEAD" — treat as no branch
        branch = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
        if branch and branch.strip() == "HEAD":
            branch = ""
    facts["branch"] = branch.strip() if branch else ""

    dirty = _git(root, ["status", "--porcelain"])
    facts["dirty"] = bool(dirty and dirty.strip())

    # First/last commit dates (ISO short).
    first = _git(root, ["log", "--reverse", "--date=format:%Y-%m-%d",
                        "--pretty=%ad", "--max-parents=0"])
    facts["first_commit"] = first.splitlines()[0].strip() if first and first.strip() else ""
    last = _git(root, ["log", "-1", "--date=format:%Y-%m-%d", "--pretty=%ad"])
    facts["last_commit"] = last.strip() if last else ""

    # Monthly timeline buckets (single algorithm, per spec §7).
    months_out = _git(root, ["log", "--date=format:%Y-%m", "--pretty=%ad"])
    bucket: Counter = Counter()
    if months_out:
        for line in months_out.splitlines():
            m = line.strip()
            if m:
                bucket[m] += 1
    facts["timeline"] = [
        {"month": mth, "count": cnt} for mth, cnt in sorted(bucket.items())
    ]

    # Tags with their commit date (annotated into the timeline by the LLM later).
    tags_out = _git(root, ["tag", "--sort=creatordate",
                           "--format=%(refname:short)\t%(creatordate:short)"])
    tags: list[dict] = []
    if tags_out:
        for line in tags_out.splitlines():
            if "\t" in line:
                nm, dt = line.split("\t", 1)
                if nm.strip():
                    tags.append({"name": nm.strip(), "date": dt.strip()})
    facts["tags"] = tags

    # Recent commits (capped).
    recent_out = _git(root, [
        "log", f"-{RECENT_COMMITS}", "--date=format:%Y-%m-%d", "--pretty=%ad\t%s",
    ])
    recent: list[dict] = []
    if recent_out:
        for line in recent_out.splitlines():
            if "\t" in line:
                dt, subj = line.split("\t", 1)
                recent.append({"date": dt.strip(), "subject": subj.strip()[:120]})
    facts["recent"] = recent

    return facts


_KEBAB_RE = re.compile(r"[^a-z0-9]+")
SUBAGENT_FILE_THRESHOLD = 800
SUBAGENT_LOC_THRESHOLD = 50_000


def _kebabify(name: str) -> str:
    s = _KEBAB_RE.sub("-", name.strip().lower()).strip("-")
    return s or "project"


def _read_small(path: Path) -> str:
    if not path.is_file() or not _safe_size(path):
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _manifest_name(root: Path, manifests: list[str]) -> str | None:
    """Best-effort project name from a manifest. Bounded, tolerant."""
    if "pyproject.toml" in manifests:
        txt = _read_small(root / "pyproject.toml")
        m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', txt)
        if m:
            return m.group(1)
    if "package.json" in manifests:
        txt = _read_small(root / "package.json")
        m = re.search(r'"name"\s*:\s*"([^"]+)"', txt)
        if m:
            return m.group(1)
    if "Cargo.toml" in manifests:
        txt = _read_small(root / "Cargo.toml")
        m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', txt)
        if m:
            return m.group(1)
    return None


def _build_name_candidates(root: Path, manifests: list[str]) -> dict:
    dir_name = _kebabify(root.name)
    manifest_name = _manifest_name(root, manifests)
    chosen = _kebabify(manifest_name) if manifest_name else dir_name
    return {
        "dir": dir_name,
        "manifest": _kebabify(manifest_name) if manifest_name else None,
        "chosen": chosen,
    }


def _estimate_loc(files: list[Path]) -> int:
    """Bounded line-count estimate over text-ish files (skips huge/binary)."""
    total = 0
    text_ext = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
                ".kt", ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".cs",
                ".md", ".rst", ".toml", ".yaml", ".yml", ".json", ".sh")
    for p in files:
        if p.suffix.lower() not in text_ext:
            continue
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                for _ in fh:
                    total += 1
        except OSError:
            continue
    return total


def _build_size_signals(files: list[Path]) -> dict:
    file_count = len(files)
    loc = _estimate_loc(files)
    return {
        "file_count": file_count,
        "loc_estimate": loc,
        "recommend_subagents": file_count > SUBAGENT_FILE_THRESHOLD
        or loc > SUBAGENT_LOC_THRESHOLD,
    }


def scan(path: str, *, depth: str = "standard") -> dict:
    """Scan a project directory and return the facts dict. Never writes."""
    root = Path(path).expanduser().resolve()
    facts: dict = {
        "schema_version": SCHEMA_VERSION,
        "scanned_path": str(root),
        "looks_like_project": False,
        "warnings": [],
    }
    if not root.is_dir():
        # Return a COMPLETE facts dict (all contract keys present) so the LLM
        # consumer never KeyErrors on a bad path.
        facts["warnings"].append(f"path is not a directory: {root}")
        facts["framework_version"] = _framework_version()
        facts["name_candidates"] = {"dir": "", "manifest": None, "chosen": "project"}
        facts["stack"] = {"languages": [], "package_managers": [],
                          "frameworks": [], "manifests": []}
        facts["tree_digest"] = {"depth_cap": TREE_DEPTH_CAP, "entry_count": 0,
                                "truncated": False, "top_dirs": [], "notable_files": []}
        facts["entry_points"] = []
        facts["doc_inventory"] = []
        facts["git"] = {"is_repo": False}
        facts["size_signals"] = {"file_count": 0, "loc_estimate": 0,
                                 "recommend_subagents": False}
        return facts

    files = enumerate_files(root)
    stack = detect_stack(root, files)
    git = collect_git_facts(root)
    doc_inventory = build_doc_inventory(root, files)

    has_manifest = bool(stack["manifests"])
    has_readme = any(d["kind"] == "readme" for d in doc_inventory)
    looks_like_project = has_manifest or git.get("is_repo", False) or has_readme

    facts["looks_like_project"] = looks_like_project
    facts["name_candidates"] = _build_name_candidates(root, stack["manifests"])
    facts["stack"] = stack
    facts["tree_digest"] = build_tree_digest(root, files)
    facts["entry_points"] = detect_entry_points(root, files)
    facts["doc_inventory"] = doc_inventory
    facts["git"] = git
    facts["size_signals"] = _build_size_signals(files)
    facts["framework_version"] = _framework_version()

    if not has_readme:
        facts["warnings"].append("no README found")
    if not git.get("is_repo", False):
        facts["warnings"].append("not a git repository; timeline will be skipped")
    if not has_manifest:
        facts["warnings"].append("no recognized package manifest found")

    return facts


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scan.py",
        description="Read-only project scanner for /ren:ingest-project.",
    )
    p.add_argument("path", nargs="?", default=".", help="project directory (default: cwd)")
    p.add_argument(
        "--depth",
        choices=["light", "standard", "deep"],
        default="standard",
        help="extraction depth (default: standard)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    target = Path(args.path).expanduser()
    if not target.exists():
        sys.stderr.write(f"scan.py: path does not exist: {target}\n")
        return 2
    facts = scan(str(target), depth=args.depth)
    try:
        sys.stdout.write(json.dumps(facts, indent=2) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
