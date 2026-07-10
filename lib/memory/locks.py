"""
lib.memory.locks — G6 concurrency: coarse file lease/lock + lost-update detection
(Task 1.3, RenOS 0.2 Phase 1).

Spec §3.10 "Concurrency": coarse file lease/lock for mutable memory (L2, global),
lost-update detection, corruption detection. Multi-project means concurrent
sessions; silent lost updates violate the memory pillar directly.

Two independent primitives, both deliberately coarse (YAGNI — no checksum
manifests, no distributed-lock protocol):

- `lease(page, ttl_s)` — a context manager guarding exclusive access to one wiki
  page. Backed by a single lockfile per page under
  `ren_paths.state_dir() / "locks" / <sha1(page)>.lock`, containing JSON
  `{pid, session, ts}`. A non-stale existing lock raises `LeaseHeld`; a stale one
  (age > ttl_s) is broken (overwritten) and the break is appended to
  `locks/breaks.log` for later journal integration (Task 1.2). The lease is
  always released on exit, including on exception.

- `content_token` / `check_token` — the 0.2 corruption/lost-update primitive.
  `content_token` returns a sha256 hex digest of a page's bytes (or `""` if the
  page doesn't exist yet); `check_token` re-hashes and raises `LostUpdate` on any
  mismatch. Callers capture a token before editing and check it before writing,
  so a page that changed underneath them is caught instead of silently clobbered.

Session id: `os.environ.get("CLAUDE_SESSION_ID", "unknown")` — same env-var/
fallback convention `lib.memory.provenance` documents for the harness session id.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from lib import ren_paths

SESSION_ID_ENV = "CLAUDE_SESSION_ID"


class LeaseHeld(Exception):
    """Raised when acquiring a lease fails because a non-stale lock is already held."""


class LostUpdate(Exception):
    """Raised by `check_token` when a page's content differs from the captured token."""


def _session_id() -> str:
    return os.environ.get(SESSION_ID_ENV, "unknown")


def _locks_dir() -> Path:
    """`ren_paths.state_dir()/"locks"`, created on first use."""
    d = ren_paths.state_dir() / "locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _lock_path(page: str) -> Path:
    digest = hashlib.sha1(page.encode("utf-8")).hexdigest()
    return _locks_dir() / f"{digest}.lock"


def _breaks_log_path() -> Path:
    return _locks_dir() / "breaks.log"


def _read_holder(lock_path: Path) -> dict:
    """Best-effort read of an existing lockfile's JSON payload.

    A missing, empty, or corrupt lockfile is treated as an unknown holder (empty
    dict, age computed as infinite) rather than raising — a torn write to the
    lockfile itself must not wedge the lease forever.
    """
    try:
        raw = lock_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _append_break(page: str, lock_path: Path, holder: dict) -> None:
    entry = {
        "page": page,
        "lock_path": str(lock_path),
        "broken_at": time.time(),
        "prior_holder": holder,
    }
    with _breaks_log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


@contextmanager
def lease(page: str, ttl_s: int = 300) -> Iterator[None]:
    """Acquire an exclusive lease on `page` for the duration of the `with` block.

    Raises `LeaseHeld` if a non-stale lock (age <= ttl_s) already exists for this
    page. A stale lock (age > ttl_s, including a corrupt/unreadable one, which is
    treated as infinitely old) is broken: the break is appended to
    `locks/breaks.log` and the lease is acquired normally. Always released on
    exit, including when the body raises.
    """
    lock_path = _lock_path(page)
    payload = {"pid": os.getpid(), "session": _session_id(), "ts": time.time()}

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder = _read_holder(lock_path)
        ts = holder.get("ts")
        age = (time.time() - ts) if isinstance(ts, (int, float)) else float("inf")
        if age <= ttl_s:
            raise LeaseHeld(
                f"lease for page {page!r} is held by {holder!r} ({age:.1f}s old, ttl={ttl_s}s)"
            )
        _append_break(page, lock_path, holder)
        # Stale: remove the stale lockfile, then retry the atomic create
        # once. Another racer could win this retry too, in which case they
        # legitimately hold the fresh lease and we must fail rather than
        # clobber it.
        lock_path.unlink(missing_ok=True)
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = _read_holder(lock_path)
            ts = holder.get("ts")
            age = (time.time() - ts) if isinstance(ts, (int, float)) else float("inf")
            raise LeaseHeld(
                f"lease for page {page!r} is held by {holder!r} ({age:.1f}s old, ttl={ttl_s}s)"
            )

    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload))
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def content_token(page_abs: Path) -> str:
    """Return a sha256 hex digest of `page_abs`'s current bytes, or `""` if absent."""
    page_abs = Path(page_abs)
    if not page_abs.exists():
        return ""
    return hashlib.sha256(page_abs.read_bytes()).hexdigest()


def check_token(page_abs: Path, token: str) -> None:
    """Raise `LostUpdate` if `page_abs`'s current content doesn't match `token`."""
    current = content_token(page_abs)
    if current != token:
        raise LostUpdate(
            f"{page_abs} changed since the token was captured "
            f"(expected {token!r}, got {current!r})"
        )


__all__ = [
    "LeaseHeld",
    "LostUpdate",
    "lease",
    "content_token",
    "check_token",
]
