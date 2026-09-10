#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
RUNTIME_DIR="$PROJECT_DIR/runtime/seed-vc"
SOURCE_DIR="$RUNTIME_DIR/source"
RUNTIME_PYTHON="$RUNTIME_DIR/.venv/bin/python"
HF_BIN="$PROJECT_DIR/.venv/bin/hf"
MODEL_DIR="$PROJECT_DIR/models/Seed-VC"

SEED_SOURCE_COMMIT="51383efd921027683c89e5348211d93ff12ac2a8"
SEED_MODEL_REVISION="257283f9f41585055e8f858fba4fd044e5caed6e"
BIGVGAN_REVISION="633ff708ed5b74903e86ff1298cf4a98e921c513"
WHISPER_REVISION="973afd24965f72e36ca33b3055d56a652f456b4d"
CAMPPLUS_REVISION="e4b6ede7ce16997aff4ae69fbca1f0175e2afede"

mkdir -p "$RUNTIME_DIR" "$MODEL_DIR"

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/Plachtaa/seed-vc.git "$SOURCE_DIR"
  git -C "$SOURCE_DIR" checkout --detach "$SEED_SOURCE_COMMIT"
else
  CURRENT_COMMIT="$(git -C "$SOURCE_DIR" rev-parse HEAD)"
  if [[ "$CURRENT_COMMIT" != "$SEED_SOURCE_COMMIT" ]]; then
    print -u2 "Seed-VC source is at $CURRENT_COMMIT, expected $SEED_SOURCE_COMMIT."
    print -u2 "Move the existing runtime/seed-vc/source aside, then run this script again."
    exit 1
  fi
fi

if [[ ! -x "$RUNTIME_PYTHON" ]]; then
  uv venv --python 3.10 "$RUNTIME_DIR/.venv"
fi
uv pip install --python "$RUNTIME_PYTHON" -r "$PROJECT_DIR/scripts/seed-vc-requirements.txt"

SEED_LOCAL="$MODEL_DIR/v1-offline"
BIGVGAN_LOCAL="$MODEL_DIR/dependencies/bigvgan"
WHISPER_LOCAL="$MODEL_DIR/dependencies/whisper-small"
CAMPPLUS_LOCAL="$MODEL_DIR/dependencies/campplus"
mkdir -p "$SEED_LOCAL" "$BIGVGAN_LOCAL" "$WHISPER_LOCAL" "$CAMPPLUS_LOCAL"

"$HF_BIN" download Plachta/Seed-VC \
  DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth \
  config_dit_mel_seed_uvit_whisper_small_wavenet.yml \
  --revision "$SEED_MODEL_REVISION" \
  --local-dir "$SEED_LOCAL"
"$HF_BIN" download nvidia/bigvgan_v2_22khz_80band_256x \
  config.json bigvgan_generator.pt \
  --revision "$BIGVGAN_REVISION" \
  --local-dir "$BIGVGAN_LOCAL"
"$HF_BIN" download openai/whisper-small \
  config.json model.safetensors preprocessor_config.json \
  --revision "$WHISPER_REVISION" \
  --local-dir "$WHISPER_LOCAL"
"$HF_BIN" download funasr/campplus campplus_cn_common.bin \
  --revision "$CAMPPLUS_REVISION" \
  --local-dir "$CAMPPLUS_LOCAL"

CAMPPLUS_CACHE="$SOURCE_DIR/checkpoints"
"$RUNTIME_PYTHON" - "$CAMPPLUS_CACHE" "$CAMPPLUS_REVISION" <<'PY'
import sys
from pathlib import Path
from huggingface_hub import hf_hub_download

cache_dir = Path(sys.argv[1])
revision = sys.argv[2]
hf_hub_download(
    repo_id="funasr/campplus",
    filename="campplus_cn_common.bin",
    revision=revision,
    cache_dir=cache_dir,
)
reference = cache_dir / "models--funasr--campplus" / "refs" / "main"
reference.parent.mkdir(parents=True, exist_ok=True)
reference.write_text(revision, encoding="utf-8")
PY

ORIGINAL_CONFIG="$SEED_LOCAL/config_dit_mel_seed_uvit_whisper_small_wavenet.yml"
LOCAL_CONFIG="$SEED_LOCAL/config-timbreloom-mac.yml"
"$RUNTIME_PYTHON" - "$ORIGINAL_CONFIG" "$LOCAL_CONFIG" "$WHISPER_LOCAL" "$BIGVGAN_LOCAL" <<'PY'
import sys
from pathlib import Path

source, destination, whisper_path, bigvgan_path = map(Path, sys.argv[1:])
text = source.read_text(encoding="utf-8")
text = text.replace('name: "openai/whisper-small"', f'name: "{whisper_path}"')
text = text.replace(
    'name: "nvidia/bigvgan_v2_22khz_80band_256x"',
    f'name: "{bigvgan_path}"',
)
destination.write_text(text, encoding="utf-8")
PY

print "Seed-VC runtime and pinned model dependencies are ready."
