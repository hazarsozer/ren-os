#!/usr/bin/env python3
"""Assert the wake-up hook's observable contract (issue #11 §1 item 1).

Contract: exit 0; stdout is JSON; additionalContext is a non-empty string;
degraded environments must say so loudly, never return silent-empty.
Runs on any python3 >= 3.6 by design (the cold-machine job pins 3.9).
"""
import argparse, json, shlex, subprocess, sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hook-cmd", required=True, help="command that runs the hook")
    args = ap.parse_args()
    proc = subprocess.run(
        shlex.split(args.hook_cmd), input='{"hook_event_name":"SessionStart","source":"startup"}',
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        print(f"CONTRACT FAIL: hook exit {proc.returncode}\nstderr: {proc.stderr[-2000:]}")
        return 1
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"CONTRACT FAIL: stdout is not JSON: {proc.stdout[:500]!r}")
        return 1
    ctx = (payload.get("hookSpecificOutput") or {}).get("additionalContext")
    if not isinstance(ctx, str) or not ctx.strip():
        print("CONTRACT FAIL: silent-empty additionalContext")
        return 1
    print("CONTRACT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
