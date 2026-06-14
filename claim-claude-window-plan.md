# claim-claude-window — Implementation Plan

Standalone public GitHub repo. One-click install. Linux-first with a clean seam for Windows contributions.

---

## What it does

Automatically claims each Claude Code 5-hour usage window by running `claude -p "hey"` 45 seconds after the window resets — whether or not the user is actively using Claude Code. Prevents users from waiting a full 5 hours when they resume work after a period of inactivity.

---

## Repository layout

```
claim-claude-window/
  install.sh                  # thin bootstrap: verify python3, curl install.py, run it
  install.py                  # full installer: wires settings.json, installs systemd timer
  uninstall.py                # removes everything install.py created
  scripts/
    scheduler.py              # payload for the 10-min systemd timer
    claim.py                  # runs `claude -p "hey"`, writes assumed next reset time
    statusline.py             # statusline hook: reads stdin JSON, writes cache, renders output
  systemd/
    claim-claude-window.timer # every 10 minutes
    claim-claude-window.service # runs scheduler.py
  windows/
    README.md                 # "contributions welcome" — Task Scheduler equivalent
  README.md
  LICENSE                     # MIT
```

---

## Components

### 1. Cache file: `~/.claude/next-reset-time`

Single line, Unix timestamp. Written by two sources:

- **statusline.py** — written with Anthropic's actual `rate_limits.five_hour.resets_at` value whenever Claude Code is used interactively and a response comes back
- **claim.py** — written with `now + 5 hours + 10 minutes` after each successful claim, as a provisional value until the statusline can correct it

The statusline value always wins when it arrives — it overwrites the provisional value on the next interactive turn.

### 2. statusline.py

Configured as Claude Code's `statusLine` command in `~/.claude/settings.json`. Fires after every assistant response in an interactive session.

**Input:** JSON blob on stdin from Claude Code  
**Reads:** `rate_limits.five_hour.resets_at`, `rate_limits.five_hour.used_percentage`  
**Writes:** `~/.claude/next-reset-time` with the actual reset timestamp  
**Outputs:** One line to stdout rendered in Claude Code's status bar, e.g.:
```
claude: 72% [███████░░░] -1h22m
```

Note: `rate_limits` is absent before the first API response in a session and absent for non-subscribers. Script must handle this gracefully (no cache write, minimal status output).

### 3. scheduler.py

Payload for the 10-minute systemd timer. Runs every 10 minutes regardless of user activity.

**Logic:**
1. Read `~/.claude/next-reset-time`
2. If file is missing or timestamp is in the past by more than 1 hour: do nothing (stale, no active window to claim)
3. If timestamp is in the future: check whether a claim job is already scheduled for that time (within a tolerance of ±5 minutes)
4. If no job scheduled (or scheduled time differs): cancel any existing claim job, schedule a new one for `reset_time + 45 seconds`
5. Log action to `~/.claude/claim-claude-window.log`

Scheduling mechanism: `systemd-run --user --on-calendar=...` for a transient one-shot unit.

### 4. claim.py

The one-shot job that fires at reset time + 45 seconds.

**Logic:**
1. Run `claude -p "hey"`
2. On success: write `now + 5 hours + 10 minutes` to `~/.claude/next-reset-time`
3. On failure: log error, write nothing (scheduler will retry on next tick if cache is still future-pointing)
4. Log outcome to `~/.claude/claim-claude-window.log`

The `now + 5 hours + 10 minutes` provisional value ensures the scheduler always has something to work from even when the statusline hasn't run. The 10-minute buffer accounts for imprecision in Anthropic's reset timing.

### 5. install.py

**Steps:**
1. Verify `python3` is available
2. Verify `claude` is on PATH (`claude --version`)
3. Verify `claude` is authenticated (run `claude -p "."` and check for non-auth-error response)
4. Copy `scripts/statusline.py` to `~/.claude/statusline.py`, make executable
5. Patch `~/.claude/settings.json`:
   - Add/replace `statusLine.command` pointing to `~/.claude/statusline.py`
   - Preserve all existing settings (read → merge → write)
6. Copy `scripts/scheduler.py` and `scripts/claim.py` to `~/.local/lib/claim-claude-window/`
7. Install systemd user units from `systemd/` to `~/.config/systemd/user/`
8. Run `systemctl --user daemon-reload`
9. Run `systemctl --user enable --now claim-claude-window.timer`
10. Run `claude -p "hey"` to bootstrap the cache (this populates `next-reset-time` for the first time via claim.py's provisional write, since statusline doesn't fire in `-p` mode)
11. Run `scheduler.py` once immediately to schedule the first claim job
12. Print confirmation with next scheduled claim time

### 6. install.sh

```bash
#!/usr/bin/env bash
set -euo pipefail
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required but not found." >&2
    exit 1
fi
TMPDIR=$(mktemp -d)
curl -fsSL https://github.com/<org>/claim-claude-window/archive/main.tar.gz | tar -xz -C "$TMPDIR" --strip-components=1
python3 "$TMPDIR/install.py"
rm -rf "$TMPDIR"
```

One-click install:
```
curl -fsSL https://raw.githubusercontent.com/<org>/claim-claude-window/main/install.sh | bash
```

---

## Data flow

```
Interactive Claude Code session
  └─ assistant response received
       └─ statusline.py fires (via statusLine hook)
            └─ writes actual resets_at → ~/.claude/next-reset-time

Every 10 minutes (systemd timer)
  └─ scheduler.py runs
       └─ reads ~/.claude/next-reset-time
            └─ schedules claim job at resets_at + 45s (if not already scheduled)

At resets_at + 45s (one-shot systemd unit)
  └─ claim.py runs
       └─ claude -p "hey"
            └─ writes now + 5h10m → ~/.claude/next-reset-time (provisional)
       └─ scheduler.py picks up provisional value on next 10-min tick
            └─ schedules next claim
```

---

## Reset time accuracy

| Source | Accuracy | When available |
|---|---|---|
| `statusline.py` (Anthropic's actual value) | Exact | Any interactive session with ≥1 response |
| `claim.py` (provisional: now + 5h10m) | ±10 min | Always, after each claim |

The provisional value ensures continuity during periods of inactivity. The 10-minute buffer means claims fire slightly late rather than before the window opens. Drift does not accumulate — each claim resets the assumption from the actual claim time.

---

## Logging

All components append to `~/.claude/claim-claude-window.log`:

```
2026-06-14 16:00:45 [scheduler] next reset: 2026-06-14 21:10:00 UTC — claim job scheduled
2026-06-14 21:10:45 [claim] running claude -p "hey"
2026-06-14 21:10:52 [claim] success — provisional next reset: 2026-06-15 02:20:52 UTC
2026-06-14 21:20:00 [scheduler] claim already scheduled for 02:20:52 — no action
```

---

## Windows (future)

All `scripts/*.py` files are cross-platform Python and require no changes. The Windows contribution surface is:

- `windows/install.ps1` — thin bootstrap equivalent to `install.sh`
- Windows branch in `install.py` — Task Scheduler XML instead of systemd units
- `windows/README.md` — documents the contribution target

---

## Open questions / known limitations

1. **systemd user session must be running** for `systemd-run --user` to work. On headless servers without a persistent user session (no `loginctl enable-linger`), the timer won't survive logout. The installer should detect this and offer to run `loginctl enable-linger $USER`.

2. **`claude` must be on PATH** when the systemd unit runs. If installed via a version manager (nvm, mise, etc.), the unit's `Environment=PATH=...` may need patching. Installer should detect and handle this.

3. **statusline fires only in interactive mode** — confirmed by test. `claude -p` does not trigger the statusline hook. This is why claim.py uses the provisional timestamp instead of relying on cache refresh from the claim invocation itself.

4. **Rate limits absent for non-Pro/Max subscribers** — the `rate_limits` field is only present for Claude.ai Pro/Max plans. The statusline script must handle its absence gracefully. The claim loop still works for these users if they manually provide a reset time, but auto-detection via statusline will not function.

---

## v2: Auto-resume waiting sessions

When Claude Code hits the rate limit and the user selects "wait for reset", the session is paused waiting for input. v2 will automatically inject a resume message at reset time so the session continues without user intervention.

### Mechanism

Claude Code's CLI provides all the tools needed — no tmux, no IPC, no terminal injection:

1. `claude agents --json` returns a JSON array of all background sessions with their IDs and states
2. At reset time, after the claim job runs `claude -p "hey"`, a resume step queries `claude agents --json` for any session in a waiting/needs-input state
3. For each waiting session: `claude -r "<session-id>" -p "continue"` injects a message and resumes it

### User flow

1. User hits rate limit, selects "wait for reset" in Claude Code
2. User backgrounds the session with `/bg` (or it was already a background session)
3. User walks away
4. At reset time: claim job fires, window is claimed, then waiting sessions are resumed automatically
5. User returns to find their session mid-conversation where they left off

### Changes required vs v1

- `claim.py` gains a post-claim step: query `claude agents --json`, resume any waiting sessions
- Documentation: instruct users to use `/bg` when hitting the rate limit (rather than leaving an interactive session open)
- Possibly: detect "waiting" state reliably from the `claude agents --json` output (state field TBD — needs testing)

### Open questions for v2

- What state value does `claude agents --json` report for a session paused at the rate limit prompt?
- Does "wait for reset" mode survive the session being backgrounded with `/bg`?
- Does `claude -r <id> -p "continue"` work on a session currently managed by the background supervisor, or does it conflict?

---

## Out of scope (v1)

- Windows support (seam provided, contributions welcome)
- Auto-resume of waiting sessions (v2)
- Multi-account / multi-profile support
- GUI or web dashboard
- Notification on successful claim (stretch: optional desktop notification)
