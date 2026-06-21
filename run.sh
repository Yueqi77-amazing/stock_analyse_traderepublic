#!/usr/bin/env bash
# One-command launcher for TR Insight (macOS / Linux).
# Installs deps if needed, then starts the dashboard.
set -e
cd "$(dirname "$0")"

python3 -m pip install --quiet --disconnected flask pytr yfinance 2>/dev/null || \
  python3 -m pip install --quiet flask pytr yfinance

echo "Starting TR Insight on http://127.0.0.1:${PORT:-8000}"
exec python3 app.py
