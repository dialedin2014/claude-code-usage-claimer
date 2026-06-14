<p align="center">
  <img src="assets/claude-claimer.png" width="600" alt="Claude Code Usage Claimer">
</p>

# claim-claude-window

Automatically claims each Claude Code 5-hour usage window the moment it resets — whether or not you're actively using Claude Code.

## What it does

Claude Code (Pro/Max) enforces a 5-hour usage window. When the window resets, the new window doesn't open until you send a prompt. If you're away, you lose that time.

`claim-claude-window` fixes this by running `claude -p "hey"` 45 seconds after the window resets, opening the next window immediately without manual intervention.

## Install (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/dialedin2014/claude-code-usage-claimer/master/install.sh | bash
```

Or clone and run directly:

```bash
git clone https://github.com/dialedin2014/claude-code-usage-claimer
cd claude-code-usage-claimer
python3 install.py
```

**Requirements:** Python 3.8+, `claude` CLI on PATH, systemd user session.

## Uninstall

```bash
python3 uninstall.py
```

## How it works

```
Interactive session
  └─ assistant response received
       └─ statusline.py → writes actual reset time to ~/.claude/next-reset-time

Every 10 minutes (systemd timer)
  └─ scheduler.py → reads next-reset-time
       └─ schedules claim job at reset_time + 45s (if not already scheduled)

At reset_time + 45s (one-shot systemd unit)
  └─ claim.py → runs claude -p "hey"
       └─ writes provisional next reset (now + 5h) to cache
```

The statusline value always wins when it arrives — it overwrites the provisional value on the next interactive turn.

## Status bar

After install, your Claude Code status bar shows usage and time remaining:

```
claude: 72% [███████░░░] -1h22m
```

## Log

```bash
tail -f ~/.claude/claim-claude-window.log
```

Sample output:

```
2026-06-14 16:00:45 [scheduler] next reset: 2026-06-14 21:10:00 UTC — claim job scheduled
2026-06-14 21:10:45 [claim] running claude -p "hey"
2026-06-14 21:10:52 [claim] success — provisional next reset: 2026-06-15 02:20:52 UTC
2026-06-14 21:20:00 [scheduler] claim already scheduled for 02:20:52 — no action
```

## Configuration

Environment variables override defaults:

| Variable | Default | Purpose |
|---|---|---|
| `LEAD_SECONDS` | `45` | Seconds after reset to fire |
| `DUMMY_PROMPT` | `hey` | Prompt sent to open the window |
| `CLAUDE_BIN` | auto-detected | Path to the `claude` binary |

## Reset time accuracy

| Source | Accuracy | When available |
|---|---|---|
| `statusline.py` (Anthropic's actual value) | Exact | Any interactive session with ≥1 response |
| `claim.py` (provisional: now + 5h) | ~45s late | Always, after each claim |

The provisional value (`now + 5h`) is written immediately after each successful claim. It is always slightly late relative to Anthropic's actual reset time, because the claim fires 45 seconds *after* the window opens — so `now` at write time is already 45 seconds into the new window. The provisional next reset (`now + 5h`) is therefore ~45 seconds past the true reset. The scheduler then adds another `LEAD_SECONDS` (45s) on top, so the next claim fires ~90 seconds after the true reset rather than ~45 seconds.

**Why the drift doesn't accumulate:** each claim overwrites the provisional value from the actual claim time, so the error stays bounded at ~45 seconds per cycle rather than compounding.

**Why the provisional value exists at all:** `claude -p` (non-interactive) does not trigger the `statusLine` hook — this is a Claude Code constraint, not a bug in this tool. So when the claim fires unattended, there is no mechanism to receive Anthropic's real `resets_at` value. The provisional timestamp is the only way to keep the scheduler running across periods of inactivity when no interactive session has run.

**What would remove it:** if Claude Code ever fires the `statusLine` hook for `claude -p` calls, `claim.py` could read the actual reset time from the response and the provisional write could be dropped entirely.

## Files installed

| Path | Purpose |
|---|---|
| `~/.local/lib/claim-claude-window/scheduler.py` | 10-min timer payload |
| `~/.local/lib/claim-claude-window/claim.py` | One-shot window claimer |
| `~/.claude/statusline.py` | Status bar hook |
| `~/.config/systemd/user/claim-claude-window.timer` | 10-min recurring timer |
| `~/.config/systemd/user/claim-claude-window.service` | Timer service unit |
| `~/.claude/settings.json` | Patched with `statusLine.command` |
| `~/.claude/next-reset-time` | Reset time cache |
| `~/.claude/claim-claude-window.log` | Log |

## Notes

- **Headless servers:** If you log out and back in, the timer may not survive without `loginctl enable-linger $USER`. The installer will prompt you if this is needed.
- **Non-Pro/Max subscribers:** The `rate_limits` field is absent for free-tier users. `statusline.py` handles this gracefully (shows `claude: --`). The claim loop still runs but can only use the provisional timestamp.
- **`claude -p` and the statusline:** The statusline hook does not fire during `claude -p` (non-interactive) calls — this is by Claude Code design. That's why `claim.py` uses the provisional timestamp instead of relying on a statusline update from the claim call itself.

## v2: Auto-resume waiting sessions

When Claude Code hits the rate limit and the user selects "wait for reset", the session pauses waiting for input. v2 would automatically inject a resume message at reset time so the session continues without intervention.

**Mechanism:** Claude Code's CLI already exposes what's needed:

1. `claude agents --json` returns all background sessions with their IDs and states
2. After the claim job runs, query for any session in a waiting/needs-input state
3. For each: `claude -r "<session-id>" -p "continue"` resumes it

**User flow:**
1. User hits rate limit, selects "wait for reset"
2. User backgrounds the session with `/bg`
3. At reset time: claim fires, then waiting sessions are resumed automatically
4. User returns to find their session mid-conversation where they left off

**Changes required vs v1:** `claim.py` gains a post-claim step that queries `claude agents --json` and resumes any waiting sessions. Users would need to use `/bg` when hitting the rate limit rather than leaving an interactive session open.

**Open questions blocking v2:**
- What state value does `claude agents --json` report for a session paused at the rate-limit prompt?
- Does "wait for reset" mode survive the session being backgrounded with `/bg`?
- Does `claude -r <id> -p "continue"` work on a session managed by the background supervisor, or does it conflict?

## Windows

Python scripts are cross-platform. The Windows contribution surface (Task Scheduler wiring) is documented in [windows/README.md](windows/README.md).

## License

MIT
