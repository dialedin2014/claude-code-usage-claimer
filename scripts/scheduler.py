#!/usr/bin/env python3
"""
scheduler.py — 10-minute timer payload

Reads ~/.claude/next-reset-time and schedules (or re-schedules) a transient
systemd one-shot unit to run claim.py at reset_time + 45 seconds.

Rules:
  - Cache missing or more than 1 hour in the past → do nothing (stale)
  - Already-scheduled claim within ±5 minutes of target → do nothing
  - Otherwise: cancel any existing claim unit, schedule a new one

Invoked every 10 minutes by claim-claude-window.timer.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import time

RESET_CACHE = os.path.expanduser("~/.claude/next-reset-time")
LOG_FILE = os.path.expanduser("~/.claude/claim-claude-window.log")
LEAD_SECONDS = int(os.environ.get("LEAD_SECONDS", "45"))
STALE_THRESHOLD = 3600      # 1 hour past reset → treat as stale
SCHEDULE_TOLERANCE = 300    # ±5 min — don't reschedule within this window
UNIT_PREFIX = "claim-claude-window"

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    if log.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [scheduler] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stderr),
        ],
    )


def read_reset_ts() -> int | None:
    if not os.path.isfile(RESET_CACHE):
        return None
    try:
        raw = open(RESET_CACHE).read().strip()
        return int(raw)
    except (ValueError, OSError):
        return None


def list_claim_timers() -> list[str]:
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "list-units", "--plain", "--no-legend",
             f"{UNIT_PREFIX}-*.timer"],
            text=True, stderr=subprocess.DEVNULL,
        )
        return [line.split()[0] for line in out.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        return []


def timer_fire_ts(unit: str) -> int | None:
    """Parse the next-elapse timestamp out of systemctl show output."""
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "show", unit, "--property=NextElapseUSecRealtime"],
            text=True, stderr=subprocess.DEVNULL,
        )
        # Value is microseconds since epoch
        match = re.search(r"NextElapseUSecRealtime=(\d+)", out)
        if match:
            return int(match.group(1)) // 1_000_000
    except (subprocess.CalledProcessError, ValueError):
        pass
    return None


def cancel_timers(timers: list[str]) -> None:
    for unit in timers:
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", unit],
                check=False, stderr=subprocess.DEVNULL,
            )
            log.info(f"cancelled {unit}")
        except Exception:
            pass


def find_claim_py() -> str:
    lib = os.path.expanduser("~/.local/lib/claim-claude-window/claim.py")
    if os.path.isfile(lib):
        return lib
    here = os.path.join(os.path.dirname(__file__), "claim.py")
    if os.path.isfile(here):
        return here
    raise RuntimeError("claim.py not found; expected at ~/.local/lib/claim-claude-window/claim.py")


def schedule_claim(fire_ts: int, claim_py: str) -> None:
    calendar = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(fire_ts))
    python = shutil.which("python3") or sys.executable
    unit_name = f"{UNIT_PREFIX}-{fire_ts}"

    subprocess.run(
        [
            "systemd-run", "--user",
            f"--on-calendar={calendar}",
            "--timer-property=AccuracySec=1s",
            f"--unit={unit_name}",
            f"--description=claim-claude-window claim job",
            python, claim_py,
        ],
        check=True,
        stderr=subprocess.PIPE,
    )
    human = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(fire_ts))
    log.info(f"claim job scheduled for {human} (unit: {unit_name}.timer)")


def main() -> int:
    _setup_logging()
    now = int(time.time())

    reset_ts = read_reset_ts()
    if reset_ts is None:
        log.info("no reset cache — nothing to do")
        return 0

    if reset_ts < now - STALE_THRESHOLD:
        human = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(reset_ts))
        log.info(f"cache is stale (reset was {human}) — nothing to do")
        return 0

    fire_ts = reset_ts + LEAD_SECONDS
    human_reset = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(reset_ts))

    existing = list_claim_timers()
    for unit in existing:
        scheduled_ts = timer_fire_ts(unit)
        if scheduled_ts is not None and abs(scheduled_ts - fire_ts) <= SCHEDULE_TOLERANCE:
            human_fire = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(scheduled_ts))
            log.info(f"next reset: {human_reset} — claim already scheduled for {human_fire} — no action")
            return 0

    cancel_timers(existing)

    if fire_ts <= now:
        log.info(f"fire time {fire_ts} is already past — skipping (will retry after next statusline update)")
        return 0

    try:
        claim_py = find_claim_py()
    except RuntimeError as e:
        log.error(str(e))
        return 1

    try:
        schedule_claim(fire_ts, claim_py)
    except subprocess.CalledProcessError as e:
        log.error(f"systemd-run failed: {e.stderr.decode().strip() if e.stderr else e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
