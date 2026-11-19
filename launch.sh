#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8765
URL="http://127.0.0.1:${PORT}/"
LOG_FILE="${APP_DIR}/studio.log"

is_running() {
  /usr/bin/python3 -c "import socket; s=socket.create_connection(('127.0.0.1', ${PORT}), 0.3); s.close()" >/dev/null 2>&1
}

if ! is_running; then
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-system-running >/dev/null 2>&1; then
    systemctl --user start linkedin-content-studio.service || true
  fi
  if ! is_running; then
    cd "$APP_DIR"
    /usr/bin/setsid -f /usr/bin/python3 "$APP_DIR/studio.py" --host 127.0.0.1 --port "$PORT" </dev/null >>"$LOG_FILE" 2>&1
  fi
  for _ in $(seq 1 50); do
    if is_running; then
      break
    fi
    sleep 0.1
  done
fi

/usr/bin/xdg-open "$URL" >/dev/null 2>&1 &
