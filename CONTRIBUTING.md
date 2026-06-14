# Contributing

Thanks for your interest. A few notes before you open a PR.

## What's welcome

- **Windows support** — the biggest gap. See [windows/README.md](windows/README.md) for the exact contribution surface (`windows/install.ps1`, Windows branch in `install.py`, `schtasks`-based scheduling in `scheduler.py`).
- **Bug fixes** — especially around systemd timing, PATH detection, or authentication edge cases.
- **v2: auto-resume waiting sessions** — see the v2 section in [README.md](README.md). The open questions there need answers before code can be written; if you've tested `claude agents --json` behavior at the rate-limit boundary, that data is valuable.

## What's out of scope (for now)

- Multi-account / multi-profile support
- GUI or web dashboard
- Notification on successful claim
- Changes that add pip dependencies — the scripts must stay stdlib-only

## Running the tests

```bash
python3 -m unittest discover -s tests -v
```

No dependencies beyond Python 3.8+ stdlib. All 41 tests should pass before you open a PR.

## Code style

- Python only in `scripts/` — no shell logic beyond what's already in `install.sh`
- No pip dependencies
- Keep `scripts/*.py` cross-platform (no Linux-only stdlib calls in the shared scripts)
- Default to no comments; only add one when the why is non-obvious

## Opening a PR

- Include a test for any new logic in `scripts/`
- If you're adding Windows support, include a test script that exercises the scheduler without actually firing a claim
- Update the relevant section of `README.md`
