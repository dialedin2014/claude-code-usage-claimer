# claim-claude-window

Automatically claims each Claude Code 5-hour usage window the moment it resets — whether or not you're actively using Claude Code.

## What it does

Claude Code (Pro/Max) enforces a 5-hour usage window. When the window resets, the new window doesn't open until you send a prompt. If you're away, you lose that time.

`claim-claude-window` fixes this by running `claude -p "hey"` 45 seconds after the window resets, opening the next window immediately without manual intervention.

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
       └─ writes provisional next reset (now + 5h10m) to cache
```

The statusline value always wins when it arrives — it overwrites the provisional value on the next interactive turn.

## Install (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/dialedin2014/claude-code-usage-claimer/main/install.sh | bash
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
| `claim.py` (provisional: now + 5h10m) | ±10 min | Always, after each claim |

The provisional value ensures continuity during inactivity. Drift does not accumulate — each claim resets from the actual claim time.

## Files installed

| Path | Purpose |
|---|---|
| `~/.local/lib/claim-claude-window/scheduler.py` | 10-min timer payload |
| `~/.local/lib/claim-claude-window/claim.py` | One-shot window claimer |
| `~/.claude/statusline.py` | Status bar hook |
| `~/.config/systemd/user/claim-claude-window.timer` | 10-min recurring timer |
| `~/.config/systemd/user/claim-claude-window.service` | Timer service unit |
| `~/.claude/settings.json` | Patched with `statusLine.command` |
| `~/.claude/next-reset-time` | Reset time cache (not removed on uninstall) |
| `~/.claude/claim-claude-window.log` | Log (not removed on uninstall) |

## Notes

- **Headless servers:** If you log out and back in, the timer may not survive without `loginctl enable-linger $USER`. The installer will prompt you if this is needed.
- **Non-Pro/Max subscribers:** The `rate_limits` field is absent for free-tier users. `statusline.py` handles this gracefully (shows `claude: --`). The claim loop still runs but can only use the provisional timestamp.
- **`claude -p` and the statusline:** The statusline hook does not fire during `claude -p` (non-interactive) calls — this is by Claude Code design. That's why `claim.py` uses the provisional timestamp instead of relying on a statusline update from the claim call itself.

## Windows

Python scripts are cross-platform. The Windows contribution surface (Task Scheduler wiring) is documented in [windows/README.md](windows/README.md).

## License

MIT
