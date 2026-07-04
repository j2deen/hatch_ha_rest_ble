#!/usr/bin/env bash
#
# Convenience wrapper that runs the Hatch Rest BLE test tool inside the local
# virtual environment created by ./setup.sh.
#
# Usage:
#   ./test.sh                 # show help
#   ./test.sh scan
#   ./test.sh status
#   ./test.sh on
#   ./test.sh color 255 0 0
#   ./test.sh sound 5
#   ./test.sh watch
#   ./test.sh --address <addr> status
#
set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Virtual environment not found. Run ./setup.sh first." >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  exec "$VENV/bin/python" scripts/hatch_ble_test.py --help
fi

exec "$VENV/bin/python" scripts/hatch_ble_test.py "$@"
