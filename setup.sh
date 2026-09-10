#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

uv sync --frozen

TTS_MODEL_ID="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
TTS_MODEL_REVISION="1eccf1cb2519b5a4e8a95b5f0544f3303568164f"
TTS_MODEL_DIR="$SCRIPT_DIR/models/Qwen3-TTS-12Hz-0.6B-Base-bf16"
TTS_MODEL_FILE="$TTS_MODEL_DIR/model.safetensors"
if [[ ! -f "$TTS_MODEL_FILE" ]]; then
  mkdir -p "$TTS_MODEL_DIR"
  uv run hf download \
    "$TTS_MODEL_ID" \
    --revision "$TTS_MODEL_REVISION" \
    --local-dir "$TTS_MODEL_DIR"
fi

ASR_MODEL_ID="mlx-community/whisper-large-v3-turbo-q4"
ASR_MODEL_REVISION="660c343bbf4e52ac257f0b7d952e5388e6f93bef"
ASR_MODEL_DIR="$SCRIPT_DIR/models/Whisper-large-v3-turbo-q4"
ASR_MODEL_FILE="$ASR_MODEL_DIR/weights.npz"
if [[ ! -f "$ASR_MODEL_FILE" ]]; then
  mkdir -p "$ASR_MODEL_DIR"
  uv run hf download \
    "$ASR_MODEL_ID" \
    --revision "$ASR_MODEL_REVISION" \
    --local-dir "$ASR_MODEL_DIR"
fi

uv run python scripts/preload_model.py
"$SCRIPT_DIR/scripts/setup_seed_vc.sh"
