import subprocess
from pathlib import Path

SMOKE = Path(__file__).resolve().parents[2] / "scripts/seam/installed_plugin_smoke.sh"


def test_smoke_script_passes_from_repo():
    proc = subprocess.run(["bash", str(SMOKE)], capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
