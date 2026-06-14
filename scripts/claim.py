#!/usr/bin/env python3
"""
claim.py — one-shot window claimer

Runs `claude -p "hey"` and writes a provisional next-reset timestamp.
Invoked by the transient systemd unit scheduled by scheduler.py.

Exit codes: 0 = success (window claimed), 1 = failure.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time

LOG_FILE = os.path.expanduser("~/.claude/claim-claude-window.log")
RESET_CACHE = os.path.expanduser("~/.claude/next-reset-time")
DUMMY_PROMPT = os.environ.get("DUMMY_PROMPT", "hey")
LEAD_SECONDS = int(os.environ.get("LEAD_SECONDS", "45"))

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    if log.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [claim] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stderr),
        ],
    )


def find_claude() -> str:
    explicit = os.environ.get("CLAUDE_BIN", "")
    if explicit and os.path.isfile(explicit) and os.access(explicit, os.X_OK):
        return explicit
    found = shutil.which("claude")
    if found:
        return found
    local = os.path.expanduser("~/.local/bin/claude")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    raise RuntimeError("claude binary not found; set CLAUDE_BIN or ensure it is on PATH")


def write_provisional_reset() -> int:
    # 5 hours + 10 minutes buffer from now
    ts = int(time.time()) + 5 * 3600 + 600
    os.makedirs(os.path.dirname(RESET_CACHE), exist_ok=True)
    with open(RESET_CACHE, "w") as f:
        f.write(f"{ts}\n")
    return ts


def main() -> int:
    _setup_logging()
    log.info(f"running claude -p \"{DUMMY_PROMPT}\"")

    try:
        claude = find_claude()
    except RuntimeError as e:
        log.error(str(e))
        return 1

    try:
        result = subprocess.run(
            [claude, "-p", DUMMY_PROMPT, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        log.error("claude timed out after 120s")
        return 1
    except Exception as e:
        log.error(f"failed to run claude: {e}")
        return 1

    raw = result.stdout.strip()
    is_error = True
    reply_text = ""

    try:
        envelope = json.loads(raw)
        is_error = envelope.get("is_error", True)
        reply_text = envelope.get("result", "")
    except (json.JSONDecodeError, AttributeError):
        # No jq equivalent — check raw text
        is_error = '"is_error": false' not in raw and '"is_error":false' not in raw

    if result.returncode == 0 and not is_error and reply_text:
        provisional_ts = write_provisional_reset()
        provisional_human = time.strftime(
            "%Y-%m-%d %H:%M:%S UTC", time.gmtime(provisional_ts)
        )
        log.info(f"success — provisional next reset: {provisional_human}")
        log.info(f"reply: {reply_text[:120].replace(chr(10), ' ')}")
        return 0
    else:
        reason = "claude-error"
        combined = (reply_text + raw).lower()
        if any(k in combined for k in ("limit", "exhaust", "rate", "quota")):
            reason = "usage-limit"
        log.error(
            f"FAIL reason={reason} rc={result.returncode} is_error={is_error}"
        )
        log.error(f"envelope: {raw[:200]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
