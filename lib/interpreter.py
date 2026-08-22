"""The single validity predicate for the wake-up hook's fast-path interpreter.

`hooks/wake-up/ren-wake-up.py` re-execs under an interpreter recorded by
`skills.install.lib.warm_environment` to avoid a cold-`uv` resolution that
trips its `_REEXEC_TIMEOUT_S` (#11 §4). Two consumers must agree on whether a
given record is usable: the hook, which acts on it, and
`skills.doctor.lib.check_interpreter_freshness`, which reports on it. They
used to implement that test twice and were required by comment to "stay in
step" — which is exactly the drift this module exists to make impossible.

Stdlib-only by contract: the hook imports this from bare `python3` before any
self-heal has run, so nothing here may import a third-party package.

Machine identity (0.8.3): the record lives in `ren_paths.machine_state_dir()`,
OUTSIDE the git-synced wiki, so it cannot travel between machines. The old
location was `state_dir()/interpreter.json` — under the wiki, which is backed
up to a remote — and the resulting cross-machine collision risk was guarded by
comparing `platform.node()`. That guard was itself broken: `platform.node()`
returns an IP-derived name on macOS depending on the network (observed:
`192.168.1.17` one moment, `Hazars-MacBook-Air.local` another, same laptop),
so a valid record read as foreign whenever the network changed and the fast
path degraded silently and permanently. Storing the record where it cannot
be synced removes the need for the check rather than making the check
cleverer, so no machine comparison happens here at all.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

__all__ = ["recorded_interpreter", "recorded_interpreter_status", "REASONS"]

#: Every rejection reason this predicate can return, plus "ok".
REASONS = ("ok", "never-warmed", "gone", "not-python", "not-executable")


def recorded_interpreter_status(record_path: Path | str | None = None) -> tuple[Path | None, str]:
    """Return `(interpreter, reason)` for the recorded fast-path interpreter.

    `interpreter` is None unless `reason == "ok"`. `reason` is one of
    `REASONS`; the caller decides what to do with it — the hook falls through
    to `uv run` on anything but "ok", doctor turns it into a message.

    Never raises: an unreadable, absent, or malformed record is
    "never-warmed", the same as no record at all.
    """
    if record_path is None:
        from lib.ren_paths import interpreter_record_path

        record_path = interpreter_record_path()

    try:
        data = json.loads(Path(record_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "never-warmed"
    # A top-level non-dict record (`null`, a number, a list) parses fine but
    # has no `.get`; treat it as never-warmed rather than raising.
    if not isinstance(data, dict):
        return None, "never-warmed"

    recorded = str(data.get("interpreter") or "")
    if not recorded:
        return None, "never-warmed"

    p = Path(recorded)
    if not p.is_file():
        return None, "gone"
    if not p.name.startswith("python"):
        return None, "not-python"
    if not os.access(p, os.X_OK):
        return None, "not-executable"
    return p, "ok"


def recorded_interpreter(record_path: Path | str | None = None) -> Path | None:
    """The hook's view: the usable interpreter, or None to fall back to `uv run`."""
    return recorded_interpreter_status(record_path)[0]
