#!/bin/zsh
set -euo pipefail

STREAMING_ROOT="${0:A:h:h}"
cd "$STREAMING_ROOT"
uv venv --python "$STREAMING_ROOT/.venv/bin/python" "$STREAMING_ROOT/runtime/streaming-asr/.venv"
uv pip sync --python "$STREAMING_ROOT/runtime/streaming-asr/.venv/bin/python" \
  --require-hashes --strict "$STREAMING_ROOT/packaging/streaming-asr-runtime.lock"
uv pip check --python "$STREAMING_ROOT/runtime/streaming-asr/.venv/bin/python"
