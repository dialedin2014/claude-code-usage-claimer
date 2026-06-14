#!/usr/bin/env python3
"""
uninstall.py — remove everything install.py created
"""

import json
import os
import shutil
import subprocess
import sys

LIB_DIR = os.path.expanduser("~/.local/lib/claim-claude-window")
STATUSLINE_DEST = os.path.expanduser("~/.claude/statusline.py")
SETTINGS_FILE = os.path.expanduser("~/.claude/settings.json")
SYSTEMD_USER_DIR = os.path.expanduser("~/.config/systemd/user")
CLAUDE_DIR = os.path.expanduser("~/.claude")
RESET_CACHE = os.path.join(CLAUDE_DIR, "next-reset-time")
LOG_FILE = os.path.join(CLAUDE_DIR, "claim-claude-window.log")
UNIT_NAME = "claim-claude-window"


def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def info(msg: str) -> None:
    print(f"  {msg}")


def systemctl_user(*args: str) -> None:
    subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
    )


def stop_and_disable_timer() -> None:
    systemctl_user("stop", f"{UNIT_NAME}.timer")
    systemctl_user("disable", f"{UNIT_NAME}.timer")

    # Cancel any transient claim job units
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "list-units", "--plain", "--no-legend",
             f"{UNIT_NAME}-*.timer"],
            text=True, stderr=subprocess.DEVNULL,
        )
        for line in out.splitlines():
            unit = line.split()[0] if line.strip() else ""
            if unit:
                systemctl_user("stop", unit)
    except Exception:
        pass

    ok("systemd timer stopped and disabled")


def remove_systemd_units() -> None:
    for name in (f"{UNIT_NAME}.timer", f"{UNIT_NAME}.service"):
        path = os.path.join(SYSTEMD_USER_DIR, name)
        if os.path.isfile(path):
            os.remove(path)
    systemctl_user("daemon-reload")
    ok("systemd unit files removed")


def remove_lib_dir() -> None:
    if os.path.isdir(LIB_DIR):
        shutil.rmtree(LIB_DIR)
        ok(f"removed {LIB_DIR}/")
    else:
        info(f"{LIB_DIR}/ not found — skipping")


def remove_statusline() -> None:
    if os.path.isfile(STATUSLINE_DEST):
        os.remove(STATUSLINE_DEST)
        ok(f"removed {STATUSLINE_DEST}")
    else:
        info(f"{STATUSLINE_DEST} not found — skipping")


def remove_data_files() -> None:
    for path in (RESET_CACHE, LOG_FILE):
        if os.path.isfile(path):
            os.remove(path)
            ok(f"removed {path}")
        else:
            info(f"{path} not found — skipping")


def unpatch_settings() -> None:
    if not os.path.isfile(SETTINGS_FILE):
        info("settings.json not found — skipping")
        return
    try:
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        info("Could not parse settings.json — skipping statusLine removal")
        return

    changed = False
    sl = settings.get("statusLine")
    if isinstance(sl, dict) and sl.get("command") == STATUSLINE_DEST:
        del sl["command"]
        if not sl:
            del settings["statusLine"]
        changed = True
    elif isinstance(sl, str) and sl == STATUSLINE_DEST:
        del settings["statusLine"]
        changed = True

    if changed:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
            f.write("\n")
        ok("removed statusLine.command from settings.json")
    else:
        info("statusLine.command in settings.json not ours — not modified")


def main() -> None:
    print("\nclaim-claude-window uninstaller\n" + "=" * 32)

    print("\n[1] Stopping systemd timer")
    stop_and_disable_timer()

    print("\n[2] Removing systemd unit files")
    remove_systemd_units()

    print("\n[3] Removing library scripts")
    remove_lib_dir()

    print("\n[4] Removing statusline hook")
    remove_statusline()

    print("\n[5] Patching settings.json")
    unpatch_settings()

    print("\n[6] Removing data files")
    remove_data_files()

    print("\n\033[32mUninstall complete.\033[0m\n")


if __name__ == "__main__":
    main()
