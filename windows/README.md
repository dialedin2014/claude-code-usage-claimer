# Windows Support — Contributions Welcome

The Python scripts (`scripts/statusline.py`, `scripts/claim.py`, `scripts/scheduler.py`) are cross-platform and require no changes on Windows.

The Linux installer uses **systemd** for the 10-minute recurring timer and for scheduling the one-shot claim job. The Windows equivalent is **Task Scheduler**.

## What needs to be built

### `windows/install.ps1`

A PowerShell bootstrap equivalent to `install.sh`:

```powershell
# Thin bootstrap — verify python3, download repo, run install.py
if (-not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    Write-Error "python3 is required but not found."
    exit 1
}
# ... download and extract archive, then:
python3 install.py
```

### Windows branch in `install.py`

`install.py` currently exits early on non-Linux. Add a Windows branch that:

1. Skips the systemd steps
2. Creates a Task Scheduler XML task that runs `scheduler.py` every 10 minutes:

```python
import subprocess, textwrap

xml = textwrap.dedent(f"""
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <TimeTrigger>
      <Repetition><Interval>PT10M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>2000-01-01T00:00:00</StartBoundary>
    </TimeTrigger>
  </Triggers>
  <Actions>
    <Exec>
      <Command>python3</Command>
      <Arguments>{scheduler_py}</Arguments>
    </Exec>
  </Actions>
</Task>
""")
# Write xml to a temp file and import:
# schtasks /Create /XML <tmpfile> /TN "claim-claude-window"
```

3. `scheduler.py` on Windows needs to replace `systemd-run --user --on-calendar=...` with a one-shot scheduled task:

```python
# Windows equivalent of systemd-run --on-calendar
subprocess.run([
    "schtasks", "/Create", "/F",
    "/TN", f"claim-claude-window-{fire_ts}",
    "/TR", f"python3 {claim_py}",
    "/SC", "ONCE",
    "/ST", time.strftime("%H:%M", time.localtime(fire_ts)),
    "/SD", time.strftime("%m/%d/%Y", time.localtime(fire_ts)),
], check=True)
```

### `windows/uninstall.ps1`

Removes the Task Scheduler tasks and installed files.

## Testing notes

- The Python scripts use only stdlib — no pip dependencies.
- `statusline.py` reads from stdin; the JSON format is the same on all platforms.
- `claim.py` uses `subprocess` to call `claude` — works on Windows if `claude` is on PATH.
- `scheduler.py` needs the `schtasks` branch for both the recurring check and the one-shot fire.

## Pull requests

PRs are welcome. Please:
- Keep the Python scripts cross-platform (no Linux-only stdlib calls in the shared scripts)
- Add a `windows/` test script that exercises the scheduler without actually firing
- Update the top-level `README.md` with Windows install instructions
