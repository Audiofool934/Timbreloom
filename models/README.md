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

## Voice conversion

- Hugging Face repository: `Plachta/Seed-VC` with project-local BigVGAN, Whisper Small, and CAMPPlus dependencies.
- Local directory: `Seed-VC/`.
- Fixed Seed-VC model revision: `257283f9f41585055e8f858fba4fd044e5caed6e`.
- The isolated source and Python 3.10 runtime live under `runtime/seed-vc/` and do not enter Git.
- Run `scripts/setup_seed_vc.sh` to reproduce this runtime without changing the main MLX environment.

Run `./setup.sh` to restore the complete local model set when a required file is missing.
Runtime inference uses the local directories directly and runs ASR and voice conversion with offline model flags.
