# Provider architecture

Timbreloom separates model-specific code from product workflows through three narrow interfaces.
The interfaces live in `timbreloom/providers/base.py`.

## Interfaces

| Interface | Current implementation | Product responsibility |
| --- | --- | --- |
| `TTSProvider` | `LocalQwenTTSProvider` | Turn a reference voice and target text into one audio segment. |
| `ASRProvider` | `LocalWhisperASRProvider` | Turn normalized local audio into provider-native timestamped output. |
| `TextModelProvider` | `GeminiTextProvider` | Transform selected transcript text after explicit cloud confirmation. |

Each Provider publishes a `ProviderDescriptor` with an ID, type, locality, capabilities, configuration state and readiness state.
The public `/api/providers` and `/api/health` responses expose only this descriptor.
They do not expose credentials, environment contents or filesystem paths containing user names.

## Workflow boundaries

The TTS workflow owns reference validation, lossless text segmentation, retry policy, progress and final WAV stitching.
The ASR workflow owns media validation, FFmpeg normalization, background task state, raw output preservation, canonical transcript construction and export.
The Gemini workflow receives only the selected segment text, task and optional target language.
It never receives audio or a path to local media.

Provider output is converted into Timbreloom's canonical data at the workflow boundary.
This keeps future local or API engines from leaking their transient response shape throughout the UI.

## Apple Silicon lifecycle

`AcceleratorCoordinator` serializes local MLX workloads.
Before Whisper starts, the Qwen Provider releases its model and clears the MLX cache.
Whisper runs in a short-lived subprocess with `HF_HUB_OFFLINE=1`, writes its raw JSON atomically and exits after each job.
The next TTS request reloads Qwen on demand.

This design optimizes for predictable behavior on the current 16 GB unified-memory Mac.
It deliberately prefers a short reload delay over forcing Qwen and Whisper to remain resident at the same time.

## Adding a Provider

1. Implement the relevant interface and a truthful descriptor.
2. Keep credentials and provider-native objects inside the implementation.
3. Convert results to the existing workflow request and result types.
4. Add a real capability check rather than assuming that an import means the service is usable.
5. Add unit tests for configuration, error handling and secret-free public responses.
6. Run a same-input local benchmark before changing the default Provider.

An API Provider must also state which data leaves the machine, require an explicit product action, and fail closed when credentials are absent.
