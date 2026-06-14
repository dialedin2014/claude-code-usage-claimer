#!/usr/bin/env bash
# install.sh — thin bootstrap for claim-claude-window
#
# One-liner install:
#   curl -fsSL https://raw.githubusercontent.com/dialedin2014/claude-code-usage-claimer/master/install.sh | bash
set -euo pipefail

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 is required but not found." >&2
    exit 1
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Downloading claim-claude-window..."
curl -fsSL https://github.com/dialedin2014/claude-code-usage-claimer/archive/master.tar.gz \
    | tar -xz -C "$TMPDIR" --strip-components=1

python3 "$TMPDIR/install.py"
