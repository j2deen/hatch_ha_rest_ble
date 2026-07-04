#!/usr/bin/env bash
#
# One-time setup for the Hatch Rest BLE test tool.
# Creates a local Python virtual environment (.venv) and installs Bleak into it,
# so you can run ./test.sh without touching your system Python.
#
# Usage:
#   ./setup.sh
#
set -euo pipefail

# Always work from the directory this script lives in.
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
VENV=".venv"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: '$PYTHON' not found. Install Python 3, or set PYTHON=/path/to/python3." >&2
  exit 1
fi

echo "==> Creating virtual environment in ./$VENV"
"$PYTHON" -m venv "$VENV"

echo "==> Upgrading pip"
"$VENV/bin/pip" install --quiet --upgrade pip

echo "==> Installing test dependencies (bleak)"
"$VENV/bin/pip" install --quiet -r requirements-test.txt

echo
echo "Setup complete. Try:"
echo "  ./test.sh scan      # find your Hatch Rest"
echo "  ./test.sh status    # show its current state"
echo "  ./test.sh on        # power it on"
echo
echo "On macOS, the first run will ask permission to use Bluetooth — approve it"
echo "(System Settings -> Privacy & Security -> Bluetooth) or scanning finds nothing."
