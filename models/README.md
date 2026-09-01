# Local models

Timbreloom keeps all runtime model weights inside this directory.
The model directories are intentionally excluded from Git.

## TTS

- Hugging Face repository: `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16`.
- Local directory: `Qwen3-TTS-12Hz-0.6B-Base-bf16/`.
- Fixed revision: `1eccf1cb2519b5a4e8a95b5f0544f3303568164f`.
- Approximate weight size: 2.4 GB.

## ASR

- Hugging Face repository: `mlx-community/whisper-large-v3-turbo-q4`.
- Local directory: `Whisper-large-v3-turbo-q4/`.
- Fixed revision: `660c343bbf4e52ac257f0b7d952e5388e6f93bef`.
- Approximate weight size: 442 MB.

Run `./setup.sh` to restore either model when its local weight file is missing.
Runtime inference uses the local directories directly and can run ASR with `HF_HUB_OFFLINE=1`.
