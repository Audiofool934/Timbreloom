#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

uv sync --frozen

MODEL_DIR="$SCRIPT_DIR/models/Qwen3-TTS-12Hz-0.6B-Base-bf16"
MODEL_FILE="$MODEL_DIR/model.safetensors"
if [[ ! -f "$MODEL_FILE" ]]; then
  mkdir -p "$MODEL_DIR"
  uv run hf download \
    mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16 \
    --local-dir "$MODEL_DIR"
fi

uv run python scripts/preload_model.py
