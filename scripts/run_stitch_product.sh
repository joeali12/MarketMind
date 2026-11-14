#!/usr/bin/env bash
# Serve the exact Stitch UI + live upload API on one origin (publishable product face).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:${PYTHONPATH:-}"
exec .venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
