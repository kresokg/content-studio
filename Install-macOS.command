#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10+ is required. Install it from https://www.python.org/downloads/macos/ or 'brew install python' and try again."
  read -r -p "Press Enter to exit..."
  exit 1
fi

python3 "./install.py"
