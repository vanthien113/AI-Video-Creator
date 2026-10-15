#!/usr/bin/env bash
# Khởi động AI Video Creator rồi mở giao diện trong trình duyệt.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="$(grep -A1 '^server:' "$ROOT/config.yaml" | grep -o 'port: *[0-9]*' | grep -o '[0-9]*' || echo 8765)"
[ -d "$ROOT/frontend/dist" ] || (cd "$ROOT/frontend" && npm run build)
(sleep 2 && open "http://127.0.0.1:${PORT}") &
cd "$ROOT/backend" && exec ../.venv/bin/python -m app
