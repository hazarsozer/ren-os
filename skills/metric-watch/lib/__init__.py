"""
skills.metric-watch library — the §3.5 minimal metric-watch routine (Task 6.3,
RenOS 0.2 Phase 6).

Spec §3.5: "minimal metric-watch: one routine watches budget ceiling, memory
growth rate, classifier fail-closed events, backup unconfigured and writes
findings to the journal for the next wake-up."

Four independent checks, each isolated (a crashing check produces a
`"check-error"` finding instead of killing the others):

  - `_check_budget` — is the latest `injected_bytes` wake-up payload
    unusually large vs. recent history (> 1.5x the median of the last 10)?
  - `_check_memory_growth` — has the wiki's page count or total bytes grown
    > 20% since the LAST metric-watch run? (persists a snapshot in
    `state_dir()/"metric-watch.json"` across runs — this is the one check
    that needs cross-run memory.)
  - `_check_classifier_fail_closed` — any NEW `classifier_event` entries with
    `event == "fail_closed"` since the last run?
  - `_check_backup` — is there neither a configured `backup` git remote NOR a
    tarball newer than 7 days in the plugin's backups dir?

Findings are written to the JOURNAL (`lib.memory.journal.append`, a
`routine`-writer `Provenance` with `op="NOOP"`, `page="_metric-watch"`,
`extra={"findings": [...]}`) — NEVER to a wiki page. Wake-up already surfaces
live routine state (Task 5.1's `read_live_routines`); the journal is the
spec's notify channel, not another page to maintain.
"""

from __future__ import annotations

import json
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from lib import ren_paths
from lib.instrument import collect
from lib.memory import journal
from lib.memory.provenance import new_provenance

STATE_FILENAME = "metric-watch.json"
INJECTION_GROWTH_THRESHOLD = 1.5
MEMORY_GROWTH_THRESHOLD = 0.20
BACKUP_REMOTE_NAME = "backup"
BACKUP_TARBALL_MAX_AGE_DAYS = 7
_GIT_TIMEOUT_S = 5.0


def _state_path() -> Path:
    return ren_paths.state_dir() / STATE_FILENAME


def _load_state() -> dict:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def _check_budget(state: dict) -> dict | None:
    """Latest injected_bytes payload > 1.5x the median of the preceding
    history (last 10 entries total). Needs at least 2 recorded entries."""
    entries = collect.read(kind=collect.KIND_INJECTED_BYTES)
    if len(entries) < 2:
        return None
    recent = entries[-10:]
    latest = recent[-1]["bytes"]
    history = [e["bytes"] for e in recent[:-1]]
    if not history:
        return None
    median = statistics.median(history)
    if median > 0 and latest > INJECTION_GROWTH_THRESHOLD * median:
        return {"kind": "injection-budget-growth", "latest_bytes": latest, "median_bytes": median}
    return None


def _check_memory_growth(wiki_root: Path, state: dict) -> dict | None:
    """Wiki *.md count/bytes vs. the snapshot from the LAST watch() run.
    Always updates the snapshot (side effect on `state`); returns a finding
    only when growth since that prior snapshot exceeds the threshold. The
    first-ever run (no prior snapshot) never fires — there's nothing to
    compare against yet."""
    md_files = [p for p in wiki_root.rglob("*.md") if p.is_file()]
    count = len(md_files)
    total_bytes = sum(p.stat().st_size for p in md_files)

    last = state.get("memory_snapshot")
    state["memory_snapshot"] = {"count": count, "bytes": total_bytes}

    if not last:
        return None
    last_count = last.get("count", 0)
    last_bytes = last.get("bytes", 0)
    if last_count <= 0 or last_bytes <= 0:
        return None

    count_growth = (count - last_count) / last_count
    bytes_growth = (total_bytes - last_bytes) / last_bytes
    if count_growth > MEMORY_GROWTH_THRESHOLD or bytes_growth > MEMORY_GROWTH_THRESHOLD:
        return {
            "kind": "memory-growth",
            "count_growth": round(count_growth, 3),
            "bytes_growth": round(bytes_growth, 3),
        }
    return None


def _check_classifier_fail_closed(state: dict) -> dict | None:
    """Any classifier_event entries with event=="fail_closed" newer than the
    last run's high-water mark (persisted in `state`)."""
    entries = collect.read(kind=collect.KIND_CLASSIFIER_EVENT)
    fail_closed = [e for e in entries if e.get("event") == "fail_closed"]

    last_ts = state.get("last_classifier_ts")
    new_events = [e for e in fail_closed if not last_ts or e.get("ts", "") > last_ts]
    if fail_closed:
        state["last_classifier_ts"] = fail_closed[-1].get("ts", last_ts)

    if new_events:
        return {"kind": "classifier-fail-closed", "count": len(new_events)}
    return None


def _git_remote_configured(wiki_root: Path, remote_name: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(wiki_root), "remote", "get-url", remote_name],
            capture_output=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _has_recent_tarball(backups_dir: Path, max_age_days: float) -> bool:
    if not backups_dir.is_dir():
        return False
    now = datetime.now(timezone.utc).timestamp()
    for tarball in backups_dir.glob("*.tar.gz"):
        try:
            age_days = (now - tarball.stat().st_mtime) / 86400.0
        except OSError:
            continue
        if age_days <= max_age_days:
            return True
    return False


def _check_backup(wiki_root: Path) -> dict | None:
    """Neither a configured `backup` git remote NOR a tarball newer than 7
    days in the plugin's backups dir → "backup-unconfigured"."""
    if _git_remote_configured(wiki_root, BACKUP_REMOTE_NAME):
        return None
    backups_dir = ren_paths.plugin_data_dir() / "backups"
    if _has_recent_tarball(backups_dir, BACKUP_TARBALL_MAX_AGE_DAYS):
        return None
    return {"kind": "backup-unconfigured"}


_CHECKS: tuple[tuple[str, str], ...] = (
    ("budget", "_check_budget"),
    ("memory_growth", "_check_memory_growth"),
    ("classifier", "_check_classifier_fail_closed"),
    ("backup", "_check_backup"),
)


def watch(session: str) -> list[dict]:
    """Run all four checks; write findings to the journal (never a wiki
    page). Each check is isolated: a crash in one produces a `"check-error"`
    finding for that check and never prevents the others from running.
    Returns the list of findings (may be empty).
    """
    wiki_root = ren_paths.wiki_root()
    state = _load_state()
    findings: list[dict] = []

    # Plain name references (not bound closures over a specific function
    # object) — each is looked up in this module's globals() at CALL time, so
    # a test that does `monkeypatch.setattr(metric_watch, "_check_backup", ...)`
    # is honored here, not shadowed by an early-bound reference.
    checks = [
        ("budget", lambda: _check_budget(state)),
        ("memory_growth", lambda: _check_memory_growth(wiki_root, state)),
        ("classifier", lambda: _check_classifier_fail_closed(state)),
        ("backup", lambda: _check_backup(wiki_root)),
    ]

    for name, check in checks:
        try:
            result = check()
            if result is not None:
                findings.append(result)
        except Exception as exc:  # noqa: BLE001 - one crashing check must never kill the others
            findings.append({"kind": "check-error", "check": name, "error": str(exc)})

    _save_state(state)

    prov = new_provenance(writer="routine", session=session, op="NOOP", page="_metric-watch")
    journal.append(prov, extra={"findings": findings})

    return findings


__all__ = ["watch", "STATE_FILENAME"]
