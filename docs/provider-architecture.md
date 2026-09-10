# Provider architecture

Timbreloom separates model-specific code from product workflows through four narrow interfaces.
The interfaces live in `timbreloom/providers/base.py`.

## Interfaces

| Interface | Current implementation | Product responsibility |
| --- | --- | --- |
| `TTSProvider` | `LocalQwenTTSProvider` | Turn a reference voice and target text into one audio segment. |
| `ASRProvider` | `LocalWhisperASRProvider` | Turn normalized local audio into provider-native timestamped output. |
| `VCProvider` | `LocalSeedVCProvider` | Transfer a source performance into a saved target timbre. |
| `TextModelProvider` | `GeminiTextProvider` | Transform selected transcript text after explicit cloud confirmation. |

Each Provider publishes a `ProviderDescriptor` with an ID, type, locality, capabilities, configuration state and readiness state.
The public `/api/providers` and `/api/health` responses expose only this descriptor.
They do not expose credentials, environment contents or filesystem paths containing user names.

## Workflow boundaries

The TTS workflow owns reference validation, lossless text segmentation, retry policy, progress and final WAV stitching.
The ASR workflow owns media validation, FFmpeg normalization, background task state, raw output preservation, canonical transcript construction and export.
The VC workflow owns source-media validation, target-voice lookup, quality presets, persistent progress, cancellation, audio normalization and optional video remuxing.
The Gemini workflow receives only the selected segment text, task and optional target language.
It never receives audio or a path to local media.

Provider output is converted into Timbreloom's canonical data at the workflow boundary.
This keeps future local or API engines from leaking their transient response shape throughout the UI.

## Progressive playback

Long-running audio workflows expose the same `stream` object in task snapshots.
It contains ordered immutable WAV chunks, the available and total counts, completion state and local audio URLs.
The browser plays the finished prefix as a queue and waits for the next chunk without interrupting the model task.
TTS chunks live with the active generation task, VC chunks live with the persistent conversion, and dubbing chunks reuse persistent segment renders.
ASR uses the same shape with `kind: source` after FFmpeg has safely closed the standardized source WAV.
Providers remain unaware of browser playback because chunk publication belongs to the workflow boundary.

## Durable jobs and application modules

`TTSService` owns cloning requests, reference copies, progress checkpoints and completed chunks.
It atomically records each completed chunk with its SHA-256 digest before exposing it for playback.
On restart, it resumes the verified contiguous prefix and regenerates the first invalid chunk and everything after it.
A changed generation configuration blocks automatic recovery so cached audio from different settings is not combined.
Completed and failed jobs retain their metadata and completed chunks.

`ASRService` persists the original request, cancellation state, audio readiness and raw-result readiness.
It reuses a verified prepared audio file and a completed raw result after a restart, or reruns recognition when only preparation finished.
Cancellation survives restart in both services.
Browser polling retains the active job ID during connection failures and server errors, and reconnects automatically.
Missing-job responses remain terminal errors.
Historical jobs without request checkpoints cannot be reconstructed automatically.

`app.py` composes providers and services.
`api_models.py` owns the request schemas, while `dubbing_api.py` registers dubbing routes through an explicit typed service context.
The frontend uses native JavaScript modules for dubbing, recording, progressive playback and job requests, without a bundler or framework dependency.

## Apple Silicon lifecycle

`AcceleratorCoordinator` serializes all local accelerator workloads.
Before Whisper starts, the Qwen Provider releases its model and clears the MLX cache.
Whisper runs in a short-lived subprocess with `HF_HUB_OFFLINE=1`, writes its raw JSON atomically and exits after each job.
Before Seed-VC starts, Qwen is also released.
Seed-VC runs in an isolated Python 3.10 and PyTorch subprocess with pinned project-local dependencies and offline model paths.
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
