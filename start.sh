#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

export TIMBRELOOM_PRELOAD="${TIMBRELOOM_PRELOAD:-1}"
export TIMBRELOOM_PORT="${TIMBRELOOM_PORT:-7865}"

exec uv run uvicorn app:app --host 127.0.0.1 --port "$TIMBRELOOM_PORT"
