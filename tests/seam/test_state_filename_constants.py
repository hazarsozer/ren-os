"""
Seam test: the state-file NAMES are duplicated in three modules and nothing
else pins them together (0.6.5 final-review finding 6, same seam as finding 3).

- `lib.memory.journal.JOURNAL_FILENAME` — the writer.
- `skills.wiki-health.lib.watermark.WATERMARK_FILENAME` — the lint's stamp.
- `hooks/wake-up/wakeup` re-declares BOTH, deliberately: the hook is
  stdlib-only and py3.9-safe and must not import skill packages, so it reads
  the two files directly.

That duplication is intentional; going unnoticed if someone renames one of
them is not. A rename on one side would silently mute the unlinted nudge (the
hook would read a file that no longer exists → count 0 → never nudge). This
test is the pin.

Run with: uv run pytest tests/seam/test_state_filename_constants.py -v
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from lib.memory import journal

watermark = importlib.import_module("skills.wiki-health.lib.watermark")

# `wakeup/` sits next to the dash-named ren-wake-up.py; add its parent dir to
# sys.path so `import wakeup` resolves the same way the hook script does it
# (same shim as tests/hooks/test_wakeup.py).
WAKE_UP_DIR = Path(__file__).resolve().parents[2] / "hooks" / "wake-up"
if str(WAKE_UP_DIR) not in sys.path:
    sys.path.insert(0, str(WAKE_UP_DIR))

import wakeup  # noqa: E402


def test_journal_filename_agrees_across_modules():
    assert wakeup.JOURNAL_FILENAME == journal.JOURNAL_FILENAME


def test_watermark_filename_agrees_across_modules():
    assert wakeup.WATERMARK_FILENAME == watermark.WATERMARK_FILENAME
