#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10+ is required. Install python3 via your package manager and try again." >&2
  exit 1
fi

python3 "./install.py"
