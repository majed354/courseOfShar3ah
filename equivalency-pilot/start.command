#!/bin/zsh
set -e
PILOT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PILOT_ROOT"
exec "$PILOT_ROOT/.venv-equivalency/bin/python" -m scripts.equivalency serve --port 8798
