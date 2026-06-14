#!/usr/bin/env python3
"""
statusline.py — Claude Code statusLine hook

Claude Code calls this after every assistant response in an interactive session,
piping a JSON blob to stdin:

  {
    "rate_limits": {
      "five_hour": {
        "resets_at": 1749876543,
        "used_percentage": 85.3
      }
    }
  }

This script:
  1. Caches the reset Unix timestamp to ~/.claude/next-reset-time
     (read by scheduler.py to know when to schedule the claim job)
  2. Outputs one status-bar line to stdout, e.g.:
       claude: 72% [███████░░░] -1h22m

rate_limits is absent before the first API response and absent for
non-Pro/Max subscribers — the script handles that gracefully.

Configure in ~/.claude/settings.json:
  { "statusLine": { "type": "command", "command": "/path/to/statusline.py" } }
"""

import json
import os
import sys
import time

RESET_CACHE = os.path.expanduser("~/.claude/next-reset-time")


def read_stdin_json():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def cache_reset_time(ts: int) -> None:
    os.makedirs(os.path.dirname(RESET_CACHE), exist_ok=True)
    with open(RESET_CACHE, "w") as f:
        f.write(f"{ts}\n")


def bar(pct: float) -> str:
    filled = round(pct / 10)
    filled = max(0, min(10, filled))
    return "█" * filled + "░" * (10 - filled)


def main() -> None:
    data = read_stdin_json()

    try:
        five_hour = data["rate_limits"]["five_hour"]
        resets_at = int(five_hour["resets_at"])
        used_pct = float(five_hour["used_percentage"])
    except (KeyError, TypeError, ValueError):
        print("claude: --")
        return

    cache_reset_time(resets_at)

    now = int(time.time())
    remaining = resets_at - now

    if remaining <= 0:
        print("claude: window open ✓")
        return

    h = remaining // 3600
    m = (remaining % 3600) // 60
    time_left = f"{h}h{m}m" if h > 0 else f"{m}m"
    pct_int = round(used_pct)

    print(f"claude: {pct_int}% [{bar(used_pct)}] -{time_left}")


if __name__ == "__main__":
    main()
