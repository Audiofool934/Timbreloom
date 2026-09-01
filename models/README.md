# Local models

Timbreloom keeps its runtime model weights inside this directory.

The active model is `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16`.
Its local directory is `Qwen3-TTS-12Hz-0.6B-Base-bf16/`.
The copied Hugging Face snapshot is `1eccf1cb2519b5a4e8a95b5f0544f3303568164f`.

Model weights are intentionally excluded from Git because they occupy about 2.4 GB.
Run `./setup.sh` to restore the local model directory when it is missing.
