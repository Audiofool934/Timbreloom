# Live microphone transcription: feasibility and implementation plan

Researched on 2026-09-27 against the current Timbreloom checkout and primary upstream sources.
Status: the first Whisper prototype is now implemented in the source checkout.
See [implementation and validation](live-transcription.md) for measured results and remaining limits.
The baseline analysis and candidate comparison below document the initial research before that implementation.
Target machine verified locally: Apple M2 Pro, 16 GiB unified memory.
Working assumption: Mandarin and English both matter; a delay of a few seconds is acceptable for an initial prototype.
The initial research made no model downloads or dependency upgrades.
Subsequent prototype validation uses the existing weights and synthetic speech fixtures.

## Decision

Timbreloom can support text appearing while the microphone is recording without necessarily replacing its current Whisper model.
The missing feature is a continuous capture and transcription pipeline.
Whisper can repeatedly decode an overlapping, bounded audio buffer and revise the newest words while committing stable text.
This is an established approach, including an MLX implementation in [WhisperStreaming](https://github.com/ufal/whisper_streaming).
It is an appropriate baseline if a few seconds of delay is acceptable, but its latency on this Mac remains unmeasured.

For approximately one-second responsiveness, benchmark a dedicated streaming model before choosing the production engine.
Voxtral Realtime and Nemotron ASR now have actual continuous-input session implementations in upstream MLX Audio.
Neither is established as the winner for this machine or the user's speech.
Keep Whisper available for file transcription and optional final refinement regardless of the live engine selected.

## Baseline before the live prototype

| Component | Verified behavior | Consequence |
| --- | --- | --- |
| [Model configuration](../app.py) | Uses `mlx-community/whisper-large-v3-turbo-q4`, revision `660c343bbf4e52ac257f0b7d952e5388e6f93bef`. | Existing local weights can serve the baseline. |
| [Microphone recorder](../static/audio-recorder.js) | Collects `MediaRecorder` chunks every 250 ms, then assembles a file when recording stops. | Capturing chunks does not currently trigger recognition. |
| [ASR service](../timbreloom/asr_service.py) | Normalizes a completed file and invokes the provider. | The existing job is a file-processing workflow. |
| [Whisper provider](../timbreloom/providers/local_whisper.py) | Starts a new worker subprocess per request and reads its final JSON after exit. | Sending each small microphone chunk through this route would repeatedly load the model. |
| [Whisper worker](../timbreloom/whisper_worker.py) | Calls `mlx_whisper.transcribe` once, with word timestamps. | There is no incremental text event channel. |
| [Accelerator coordinator](../timbreloom/providers/runtime.py) | Serializes local heavy-model work. | Live recognition must participate in model ownership and release it reliably. |

The installed `mlx_whisper` accepts waveform arrays and caches a loaded model within its process.
A persistent worker can therefore reuse weights across rolling-buffer calls.
Its transcription function still returns after processing the supplied buffer; it does not become a native streaming decoder through a UI flag.
The standard Whisper implementation uses sliding 30-second windows, and short input does not guarantee proportionally cheap inference in the installed MLX implementation. [Whisper documentation](https://github.com/openai/whisper), [MLX transcription source](https://github.com/ml-explore/mlx-examples/blob/main/whisper/mlx_whisper/transcribe.py).

## Candidate comparison

These are capability findings, not comparable performance measurements.
Model look-ahead, time until the first draft word, and time until stable text are different measurements.

| Candidate | Live-input evidence | Mandarin and English | Assessment for Timbreloom |
| --- | --- | --- | --- |
| Current Whisper Turbo Q4 | Rolling-buffer decoding with a stability policy; WhisperStreaming includes an MLX backend. | Multilingual recognition; mixed-language behavior needs evaluation. | First baseline, reuses installed weights and the existing ASR stack. |
| Voxtral Mini 4B Realtime | Native causal architecture; MLX exposes `create_streaming_session`, `feed`, `step`, and finalization. | Both are in the model's 13-language coverage. | Strong candidate for lower latency; larger model, so measure memory and sustained speed on 16 GiB. |
| Nemotron 3.5 ASR streaming 0.6B | Cache-aware streaming architecture; MLX implements independent live-input sessions. | Both supported, but NVIDIA places Mandarin in its broad-coverage tier. | Smaller candidate worth comparing; Mandarin quality is a selection gate. |
| Apple SpeechAnalyzer / SpeechTranscriber | Native asynchronous audio input and provisional/final results, processed on device. | Query supported and installed locales on the actual Mac; mixed-language behavior remains unverified. | Attractive native-app option, requiring a Swift bridge and OS-managed model assets. |
| Qwen3-ASR 0.6B / 1.7B | Official streaming path uses vLLM; inspected MLX method streams text from supplied audio. | 30 languages and 22 Chinese dialects in official coverage. | Useful accuracy candidate, but not yet a verified turnkey continuous-microphone path for this project's Mac runtime. |

### Evidence and qualifications

**Whisper:** WhisperStreaming uses local agreement across successive hypotheses to decide which text is stable.
Its authors report 3.3-second latency in their evaluation, which is not a measurement of Timbreloom or this Mac.
The repository now directs new development toward SimulStreaming, so use it as evidence and an algorithm reference rather than adopting the entire older stack automatically. [Author repository](https://github.com/ufal/whisper_streaming).

**Voxtral:** Mistral publishes a configurable delay/accuracy tradeoff and recommends a 480 ms setting.
That parameter is not end-to-end microphone-to-screen latency.
The weights use Apache-2.0, and the official card lists Chinese and English evaluation results. [Official model card](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602).
The inspected MLX implementation queues raw PCM in `feed()` and advances recognition through `step()`; this is stronger evidence of live input than a `generate("audio.wav", stream=True)` example. [Model implementation](https://github.com/Blaizzy/mlx-audio/blob/4ab7e6f7dedd69a136cfaa318c5dc8aed5119446/mlx_audio/stt/models/voxtral_realtime/voxtral_realtime.py), [session implementation](https://github.com/Blaizzy/mlx-audio/blob/4ab7e6f7dedd69a136cfaa318c5dc8aed5119446/mlx_audio/stt/models/voxtral_realtime/streaming.py).

**Nemotron:** NVIDIA documents 600M parameters, several streaming chunk sizes, and language-dependent accuracy tiers.
Its model card identifies the license as OpenMDW-1.1; record the actual redistribution terms before packaging weights. [Official model card](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b).
MLX documents approximately 1.2 GB BF16 and 720 MB 8-bit variants; these are model sizes, not peak process memory. [Port documentation](https://github.com/Blaizzy/mlx-audio/blob/4ab7e6f7dedd69a136cfaa318c5dc8aed5119446/mlx_audio/stt/models/nemotron_asr/README.md).
Its `feed()` accepts mono PCM and `step()` produces text deltas. [Session source](https://github.com/Blaizzy/mlx-audio/blob/4ab7e6f7dedd69a136cfaa318c5dc8aed5119446/mlx_audio/stt/models/nemotron_asr/session.py).

**Apple:** The native Speech APIs support live provisional results, final results, audio timing attributes, and explicit stream finalization.
Assets are managed by the OS and may need a first-use download.
Availability and locale support must be checked on device.
This route also changes model version control and browser-mode support, so it should be a deliberate product decision. [Apple's implementation walkthrough](https://developer.apple.com/videos/play/wwdc2025/277/).

**Qwen:** Qwen3-ASR is separate from the Qwen3-TTS model already used for cloning.
The official Python package currently documents streaming only with vLLM and says that mode does not return timestamps. [Official repository](https://github.com/QwenLM/Qwen3-ASR/#streaming-inference).
At the inspected MLX revision, `stream_transcribe` accepts a path or an existing waveform and yields decoded text; no equivalent `create_streaming_session` method was found in this model.
It could still be wrapped around rolling buffers, but that requires its own latency and stability evaluation. [MLX source](https://github.com/Blaizzy/mlx-audio/blob/4ab7e6f7dedd69a136cfaa318c5dc8aed5119446/mlx_audio/stt/models/qwen3_asr/qwen3_asr.py).

Upstream MLX Audio was inspected at `4ab7e6f7dedd69a136cfaa318c5dc8aed5119446`.
Timbreloom pins `feb57c82ecd90bbb516f39d3cf0a33c77bf5ec4a` in [pyproject.toml](../pyproject.toml), so upstream capabilities must not be described as already installed.
Evaluate a newer runtime in isolation before changing the shared TTS environment.
Upstream also documents a PCM WebSocket endpoint with partial and final transcription events, which can inform the integration without adopting another full application server. [MLX server documentation](https://github.com/Blaizzy/mlx-audio/blob/main/docs/guides/web-ui-api-server.md#real-time-websocket-transcription).

## Proposed user experience

Add a **Live microphone** mode beside file transcription.
Starting it checks model readiness, obtains microphone permission, and displays a clear listening state.
Text appears during speech; the newest draft remains visually distinct until stable.
Stopping releases the microphone immediately, drains pending audio, finalizes the text, and saves the recording and transcript to the existing library.
The saved transcript remains editable and exportable through the current workflow.
An optional refinement pass can improve the final transcript, but must preserve user edits and show when it is still processing.

## Implementation sequence

1. **Build the smallest real-time evaluation harness.**
   Feed recorded fixtures at their original wall-clock rate into one persistent Whisper worker, with a bounded overlapping buffer and draft/final events.
   Measure cold startup separately from steady-state decoding.
   Test Mandarin, English, and switching languages before committing to latency targets.
2. **Compare one dedicated streaming engine if needed.**
   Start with quantized Voxtral for a multilingual comparison, or Nemotron if memory and throughput are the first constraints.
   Use identical paced audio and reporting metrics.
   Select based on this machine's results, not vendor throughput or advertised look-ahead.
3. **Connect capture to the selected engine.**
   Use continuous PCM from an AudioWorklet for the browser workflow, or AVAudioEngine for a native-only implementation.
   Preserve sample-rate continuity and sequence numbers through resampling and transport.
   Do not assume individual compressed `MediaRecorder` blobs are independent decodable files.
4. **Add session persistence and resource ownership.**
   Save incoming audio incrementally, bound queued inference work, and retain committed transcript segments.
   Define start, append, partial, final, stop, error, and disconnect behavior.
   Coordinate with TTS/VC so a live session neither competes for uncontrolled memory nor silently waits behind a long job.
5. **Integrate and verify the product flow.**
   Add partial-text rendering, stop/finalize, transcript history, editing, export, and recovery.
   Keep inference off the HTTP event loop and close the worker when its session ends.

## Acceptance measurements

| Measure | What to record |
| --- | --- |
| Responsiveness | Time from spoken content to first visible draft and to stable text, including median and p95. |
| Sustained speed | Queue delay during uninterrupted speech, rather than only total file-processing speed. |
| Accuracy | Mandarin character error rate, English word error rate, names/numbers, punctuation, and language switching. |
| Stability | Repeated or dropped words across buffer boundaries, silence hallucinations, and revision frequency. |
| Long sessions | A 30-minute paced fixture, peak unified-memory pressure, and whether lag grows with duration. |
| Completion | Final syllables survive immediate stop; permission denial, device loss, window closure, and cancellation release resources. |
| Product behavior | Real microphone flow in native WebKit, readable partial/final text, saved history, editing, and TXT/SRT/VTT export. |

Proposed initial target: useful drafts within a few seconds without increasing backlog.
If approximately one-second drafts are required, treat that as a separate acceptance target for the dedicated streaming comparison.
The prototype subsequently demonstrated first drafts within a few seconds on short synthetic fixtures; approximately one-second drafts and long-session targets remain unverified.
Precise final subtitles may need a post-recording alignment or transcription pass even when live captions are already useful.

Refresh this assessment when latency requirements become explicit, target hardware changes, the pinned MLX runtime changes, or a candidate's live-input support changes.
