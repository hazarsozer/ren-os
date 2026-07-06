"""
lib.instrument.estimator — calibrated token estimator (Task 3.2, RenOS 0.2 Phase 3).

Spec §3.9 + exit criterion 3: "token estimator calibrated against the real
tokenizer." `estimate_tokens` is a cheap chars/ratio approximation used
wherever a full tokenizer call would be too expensive (e.g. sizing a
candidate wake-up injection before committing to it); `calibrate` is how that
ratio gets corrected against REAL usage data (harvested via
`lib.instrument.collect.harvest_session_usage`, which reports real
`input_tokens`/`output_tokens` from the harness) instead of staying a
guessed constant forever.

State: one JSON file, `state_dir()/"metrics"/estimator.json`, shaped
`{"chars_per_token": float, "samples": int, "updated": iso-ts}`. Absent or
corrupt state falls back to `DEFAULT_CHARS_PER_TOKEN` with zero recorded
samples — `estimate_tokens` never raises on a missing/bad calibration file.

Blending: `calibrate` folds a new batch of (text, reported_tokens) pairs into
the stored ratio as a running average, weighted by sample COUNT (not chars or
tokens) — the stored ratio counts as `stored_samples` "votes" and the new
batch counts as `len(samples)` "votes":

    batch_ratio = sum(len(text) for text, _ in samples) / sum(tokens for _, tokens in samples)
    blended = (stored_ratio * stored_samples + batch_ratio * len(samples))
              / (stored_samples + len(samples))

so a large body of prior calibration data isn't swamped by one small new
batch, and repeated calibration converges rather than oscillating.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from lib import ren_paths

DEFAULT_CHARS_PER_TOKEN = 4.0
ESTIMATOR_FILENAME = "estimator.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _estimator_path() -> Path:
    return ren_paths.state_dir() / "metrics" / ESTIMATOR_FILENAME


def _load_ratio_state() -> tuple[float, int]:
    """Return `(chars_per_token, samples)`. Falls back to
    `(DEFAULT_CHARS_PER_TOKEN, 0)` on a missing file, unreadable/malformed
    JSON, or an internally inconsistent value (non-positive ratio, negative
    sample count) — never raises."""
    path = _estimator_path()
    if not path.exists():
        return DEFAULT_CHARS_PER_TOKEN, 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ratio = float(data["chars_per_token"])
        samples = int(data["samples"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return DEFAULT_CHARS_PER_TOKEN, 0
    if ratio <= 0 or samples < 0:
        return DEFAULT_CHARS_PER_TOKEN, 0
    return ratio, samples


def estimate_tokens(text: str) -> int:
    """Estimate `text`'s token count as `ceil(len(text) / chars_per_token)`,
    using the calibrated ratio if one is stored, else `DEFAULT_CHARS_PER_TOKEN`."""
    ratio, _samples = _load_ratio_state()
    return math.ceil(len(text) / ratio)


def calibrate(samples: list[tuple[str, int]]) -> float:
    """Fold `samples` (real `(text, reported_tokens)` pairs) into the stored
    ratio as a sample-count-weighted running average (see module docstring).
    Persists the result atomically and returns the new blended ratio.

    Raises `ValueError` if `samples` is empty or any pair's `reported_tokens`
    is `<= 0` (a non-positive token count can't be divided into meaningfully).
    """
    if not samples:
        raise ValueError("calibrate requires at least one (text, reported_tokens) sample")
    for text, reported_tokens in samples:
        if reported_tokens <= 0:
            raise ValueError(f"reported_tokens must be > 0, got {reported_tokens!r} for {text!r}")

    total_chars = sum(len(text) for text, _ in samples)
    total_tokens = sum(reported_tokens for _, reported_tokens in samples)
    batch_ratio = total_chars / total_tokens
    batch_weight = len(samples)

    stored_ratio, stored_samples = _load_ratio_state()
    new_samples = stored_samples + batch_weight
    blended_ratio = (stored_ratio * stored_samples + batch_ratio * batch_weight) / new_samples

    path = _estimator_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"chars_per_token": blended_ratio, "samples": new_samples, "updated": _now_iso()}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)

    return blended_ratio


__all__ = ["DEFAULT_CHARS_PER_TOKEN", "estimate_tokens", "calibrate"]
