# Seed-VC integration

Timbreloom 1.1 uses Seed-VC as an isolated local subprocess for native speech-to-speech voice conversion.
The source performance supplies timing, pauses, pitch movement and emotion, while a saved Timbreloom voice supplies the target timbre.
No transcript is required and no audio leaves the Mac.

## Reproducible versions

| Component | Revision |
| --- | --- |
| Seed-VC source | `51383efd921027683c89e5348211d93ff12ac2a8` |
| Seed-VC model | `257283f9f41585055e8f858fba4fd044e5caed6e` |
| BigVGAN | `633ff708ed5b74903e86ff1298cf4a98e921c513` |
| Whisper Small | `973afd24965f72e36ca33b3055d56a652f456b4d` |
| CAMPPlus | `e4b6ede7ce16997aff4ae69fbca1f0175e2afede` |

Run `scripts/setup_seed_vc.sh` to reproduce the runtime and download the pinned files.
The setup script refuses to reuse a Seed-VC source checkout at a different commit.

## Isolation boundary

The Seed-VC project requires Python 3.10 and PyTorch, while the main Timbreloom application uses Python 3.12 and MLX.
Its source and dependencies therefore live in `runtime/seed-vc/`, which is excluded from Git.
Model weights live in `models/Seed-VC/`, which is also excluded from Git.
The main process starts the Timbreloom Seed-VC worker in a separate Python process with explicit local checkpoint and configuration paths, offline Hugging Face flags and Apple MPS fallback enabled.
The worker imports the upstream `hf_utils` helper, replaces its download function with a local-file resolver, and executes `inference.py` via `runpy`.
The pinned upstream files are unchanged on disk, but the worker adapts their runtime behavior.

`LocalSeedVCProvider` is Timbreloom-owned orchestration code.
It validates the isolated runtime, serializes accelerator use with Qwen and Whisper, supports cancellation, captures a per-job log and normalizes the result to 24 kHz mono WAV.

## License boundary

The upstream Seed-VC source repository and model card identify the project as GPL-3.0.
Timbreloom does not copy the upstream source or model weights into its Git history.
The setup script downloads the exact upstream revisions into ignored project-local directories.
Timbreloom-authored orchestration and worker code is licensed under MIT, while Seed-VC remains GPL-3.0.
This does not imply that a combined distribution is governed solely by MIT or that using a separate process automatically resolves the GPL boundary.
Anyone redistributing a bundled runtime or model must review and comply with the upstream GPL-3.0 terms and notices.
If the engine and its worker form a GPL-covered combined work, distribution must satisfy GPL for that combination and retain the MIT notices on the independently authored portions.

## Local benchmark

The integration was selected after a same-input benchmark on the current M2 Pro with 16 GB unified memory.
All 4, 8 and 12 step outputs retained the full spoken words in a Whisper comparison and stayed within 10 ms of the source duration.
The 8 step result improved target-speaker embedding similarity from 0.0383 to 0.6122 while keeping pitch-contour correlation at 0.9057.
Its measured generation time was 26.65 seconds for a 12.06 second source, with an observed maximum resident set around 2.08 GB and a peak process footprint around 5.30 GB.

These measurements are one local baseline, not a universal quality guarantee.
Content, language, recording noise and the reference voice can change both quality and runtime.
