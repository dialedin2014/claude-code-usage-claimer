#!/usr/bin/env python3
"""
install.py — claim-claude-window installer

Steps:
  1. Verify python3 (already running, so trivially true)
  2. Verify claude is on PATH and authenticated
  3. Copy scripts/ to ~/.local/lib/claim-claude-window/
  4. Copy statusline.py to ~/.claude/statusline.py
  5. Patch ~/.claude/settings.json (statusLine.command)
  6. Install systemd user units
  7. systemctl --user daemon-reload
  8. systemctl --user enable --now claim-claude-window.timer
  9. Detect and offer loginctl enable-linger if needed
 10. Run claim.py once to bootstrap the cache
 11. Run scheduler.py once to schedule the first claim job
 12. Print confirmation
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_SRC = os.path.join(BASE_DIR, "scripts")
SYSTEMD_SRC = os.path.join(BASE_DIR, "systemd")

LIB_DIR = os.path.expanduser("~/.local/lib/claim-claude-window")
CLAUDE_DIR = os.path.expanduser("~/.claude")
STATUSLINE_DEST = os.path.join(CLAUDE_DIR, "statusline.py")
SETTINGS_FILE = os.path.join(CLAUDE_DIR, "settings.json")
SYSTEMD_USER_DIR = os.path.expanduser("~/.config/systemd/user")
RESET_CACHE = os.path.join(CLAUDE_DIR, "next-reset-time")

UNIT_NAME = "claim-claude-window"


def info(msg: str) -> None:
    print(f"  {msg}")


def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def err(msg: str) -> None:
    print(f"  \033[31m✗\033[0m {msg}", file=sys.stderr)


def die(msg: str) -> None:
    err(msg)
    sys.exit(1)


def step(n: int, title: str) -> None:
    print(f"\n[{n}] {title}")


# ── Prereq checks ─────────────────────────────────────────────────────────────

def check_linux() -> None:
    if platform.system() != "Linux":
        die(
            f"This installer targets Linux (systemd). "
            f"Detected: {platform.system()}. "
            f"See windows/README.md for Windows instructions."
        )
    ok("Linux detected")


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
    die(
        "'claude' not found on PATH. Install Claude Code CLI first:\n"
        "  https://docs.anthropic.com/en/docs/claude-code"
    )


def check_claude_version(claude: str) -> None:
    try:
        result = subprocess.run(
            [claude, "--version"], capture_output=True, text=True, timeout=10
        )
        ver = (result.stdout + result.stderr).strip().splitlines()[0]
        ok(f"claude found: {ver}")
    except Exception as e:
        die(f"Failed to run 'claude --version': {e}")


def check_claude_auth(claude: str) -> None:
    info("Checking Claude Code authentication (sending test prompt)…")
    try:
        result = subprocess.run(
            [claude, "-p", ".", "--output-format", "json"],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        die("Authentication check timed out after 60s.")
    except Exception as e:
        die(f"Failed to run claude: {e}")

    raw = result.stdout.strip()
    try:
        envelope = json.loads(raw)
        is_error = envelope.get("is_error", True)
        subtype = envelope.get("subtype", "")
    except (json.JSONDecodeError, AttributeError):
        is_error = True
        subtype = ""

    if is_error and any(k in (raw + subtype).lower() for k in ("auth", "login", "unauthenticated")):
        die(
            "Claude Code is not authenticated. Run 'claude' interactively to log in first."
        )
    ok("Claude Code is authenticated")


# ── Reinstall detection ────────────────────────────────────────────────────────

def is_reinstall() -> bool:
    return os.path.isdir(LIB_DIR)


def note_overwrite(path: str) -> None:
    info(f"overwriting existing {path}")


# ── File installation ──────────────────────────────────────────────────────────

def install_lib_scripts(reinstall: bool) -> None:
    if reinstall:
        note_overwrite(LIB_DIR + "/")
    os.makedirs(LIB_DIR, exist_ok=True)
    for name in ("scheduler.py", "claim.py"):
        src = os.path.join(SCRIPTS_SRC, name)
        dst = os.path.join(LIB_DIR, name)
        shutil.copy2(src, dst)
        os.chmod(dst, 0o755)
    ok(f"scripts installed to {LIB_DIR}/")


def install_statusline(reinstall: bool) -> None:
    if reinstall and os.path.isfile(STATUSLINE_DEST):
        note_overwrite(STATUSLINE_DEST)
    os.makedirs(CLAUDE_DIR, exist_ok=True)
    src = os.path.join(SCRIPTS_SRC, "statusline.py")
    shutil.copy2(src, STATUSLINE_DEST)
    os.chmod(STATUSLINE_DEST, 0o755)
    ok(f"statusline.py installed to {STATUSLINE_DEST}")


def check_settings_conflict() -> None:
    if not os.path.isfile(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    sl = settings.get("statusLine", {})
    if not isinstance(sl, dict):
        return
    existing_cmd = sl.get("command")
    if existing_cmd and existing_cmd != STATUSLINE_DEST:
        die(
            f"settings.json already has statusLine.command pointing to:\n"
            f"    {existing_cmd}\n"
            f"  This installer will not overwrite a statusLine hook it did not create.\n"
            f"  Remove or relocate that hook first, then re-run the installer."
        )
    ok("settings.json statusLine is clear for install")


def patch_settings(reinstall: bool) -> None:
    os.makedirs(CLAUDE_DIR, exist_ok=True)
    settings: dict = {}
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE) as f:
                settings = json.load(f)
        except (json.JSONDecodeError, OSError):
            info("Could not parse existing settings.json — starting fresh merge")

    status_line = settings.get("statusLine", {})
    if not isinstance(status_line, dict):
        status_line = {}

    if reinstall and status_line.get("command") == STATUSLINE_DEST:
        note_overwrite("statusLine.command in settings.json")

    # Set only the command field; leave all other statusLine fields untouched
    status_line["command"] = STATUSLINE_DEST
    settings["statusLine"] = status_line

    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")
    ok(f"settings.json patched (statusLine.command → {STATUSLINE_DEST})")


def stop_timer() -> None:
    subprocess.run(
        ["systemctl", "--user", "stop", f"{UNIT_NAME}.timer"],
        capture_output=True,
    )
    subprocess.run(
        ["systemctl", "--user", "disable", f"{UNIT_NAME}.timer"],
        capture_output=True,
    )


def install_systemd_units(reinstall: bool) -> None:
    if reinstall:
        note_overwrite(f"{UNIT_NAME}.timer and {UNIT_NAME}.service")
        stop_timer()
    os.makedirs(SYSTEMD_USER_DIR, exist_ok=True)
    for name in (f"{UNIT_NAME}.timer", f"{UNIT_NAME}.service"):
        src = os.path.join(SYSTEMD_SRC, name)
        dst = os.path.join(SYSTEMD_USER_DIR, name)
        shutil.copy2(src, dst)
    ok(f"systemd units installed to {SYSTEMD_USER_DIR}/")


# ── systemd wiring ─────────────────────────────────────────────────────────────

def systemctl_user(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True, text=True,
    )


def check_linger() -> None:
    user = os.environ.get("USER", "")
    try:
        result = subprocess.run(
            ["loginctl", "show-user", user, "--property=Linger"],
            capture_output=True, text=True,
        )
        if "Linger=yes" not in result.stdout:
            print()
            print(
                "  NOTE: Linger is not enabled for your user. On headless servers,\n"
                "  the systemd user session (and the 10-minute timer) will not survive\n"
                "  logout. To fix this, run:\n"
                f"\n    loginctl enable-linger {user}\n"
            )
    except Exception:
        pass


def enable_timer() -> None:
    r = systemctl_user("daemon-reload")
    if r.returncode != 0:
        die(f"systemctl daemon-reload failed:\n{r.stderr}")
    ok("systemctl daemon-reload")

    r = systemctl_user("enable", "--now", f"{UNIT_NAME}.timer")
    if r.returncode != 0:
        die(f"Failed to enable timer:\n{r.stderr}")
    ok(f"{UNIT_NAME}.timer enabled and started")


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap_cache(claude: str) -> None:
    info("Running initial claim to bootstrap the reset-time cache…")
    python = sys.executable
    claim_py = os.path.join(LIB_DIR, "claim.py")
    env = os.environ.copy()
    env["CLAUDE_BIN"] = claude
    result = subprocess.run([python, claim_py], env=env)
    if result.returncode == 0:
        ok("Initial claim succeeded — reset cache written")
    else:
        info("Initial claim returned non-zero (window may already be open or rate-limited). Continuing.")


def run_scheduler_once() -> None:
    info("Running scheduler once to schedule the first claim job…")
    python = sys.executable
    scheduler_py = os.path.join(LIB_DIR, "scheduler.py")
    result = subprocess.run([python, scheduler_py])
    if result.returncode == 0:
        ok("Scheduler ran — first claim job scheduled if cache was fresh")
    else:
        info("Scheduler returned non-zero. Check the log for details.")


def print_next_claim() -> None:
    if not os.path.isfile(RESET_CACHE):
        return
    try:
        ts = int(open(RESET_CACHE).read().strip())
        human = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))
        print(f"\n  Next window claim target: {human}")
    except (ValueError, OSError):
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    reinstall = is_reinstall()
    header = "claim-claude-window reinstaller" if reinstall else "claim-claude-window installer"
    print(f"\n{header}\n" + "=" * len(header))
    if reinstall:
        info("Previous installation detected — overwriting.")

    step(1, "Checking prerequisites")
    check_linux()
    claude = find_claude()
    check_claude_version(claude)
    check_claude_auth(claude)
    check_settings_conflict()

    step(2, "Installing scripts")
    install_lib_scripts(reinstall)
    install_statusline(reinstall)

    step(3, "Patching ~/.claude/settings.json")
    patch_settings(reinstall)

    step(4, "Installing systemd user units")
    install_systemd_units(reinstall)

    step(5, "Enabling systemd timer")
    check_linger()
    enable_timer()

    step(6, "Bootstrapping reset-time cache")
    bootstrap_cache(claude)

    step(7, "Scheduling first claim job")
    run_scheduler_once()

    print_next_claim()

    print(
        "\n\033[32mInstallation complete.\033[0m\n"
        "\n"
        "  The statusline hook will update your reset time automatically\n"
        "  during interactive Claude Code sessions.\n"
        "\n"
        "  The 10-minute timer checks the cache and keeps the claim job\n"
        "  scheduled even when you're not actively using Claude Code.\n"
        "\n"
        "  Log: tail -f ~/.claude/claim-claude-window.log\n"
    )


if __name__ == "__main__":
    main()
