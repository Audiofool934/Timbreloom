# Live microphone transcription

**Transcription > Live microphone** shows revisable draft text during recording and an editable saved transcript after **Stop and save**.
The shared model picker offers Whisper Turbo Q4, Nemotron 3.5 ASR 0.6B 8-bit, Moonshine Small Streaming English, and Moonshine Tiny Streaming Mandarin.
The selected model also handles uploaded files, and each saved job records its model for restart recovery.
Models are separate, verified downloads in **Models**.

## Implementation

- [Live capture](../static/live-transcription.js) manages permission, listening, stop, disconnect, and saved states.
- [AudioWorklet](../static/live-audio-worklet.js) and [resampler](../static/pcm-resampler.js) send mono 16 kHz PCM16 in 100 ms packets, maintaining continuity across capture callbacks.
- [WebSocket API](../timbreloom/live_asr_api.py) validates the local address and browser origin and accepts one live session at a time.
- [Session service](../timbreloom/live_asr.py) saves received audio incrementally and bounds pending audio to 60 seconds, decoding windows of at most 28 seconds.
- [Persistent worker](../timbreloom/live_whisper_worker.py) loads Whisper once per session and runs outside the web server process.

The Whisper decoder starts after two seconds of audio, then updates as more audio arrives.
Matching words across successive hypotheses become stable, while the latest words remain revisable.
The buffer retains two seconds of context behind committed text to avoid clipping word onsets and adjacent Mandarin syllables.
Timestamp ties are resolved using overlapping words rather than automatically discarding everything ending at the previous timestamp.
A conservative energy gate avoids decoding empty silence; this is not a neural voice-activity detector.

Nemotron and Moonshine use continuous inference in a separate pinned Python runtime, preserving the main service and Whisper dependencies.
They consume each PCM packet once and flush the remaining audio at stop.
Nemotron maps language choices to the model's native locale prompts and retains token emission times for segment timestamps.
Those timestamps are approximate recognition emission times, not forced word alignment.
Moonshine merges repeated context only across overlapping adjacent native lines, preserving repetitions at nonoverlapping times.
Moonshine is language-specific; Nemotron does not accept vocabulary hints.

The accelerator coordinator keeps this worker separate from concurrent TTS and conversion inference.
If another model is already busy, live startup reports that conflict instead of waiting with an active microphone.
Leaving the workspace stops capture and finishes received audio.
Worker failure or silence still leaves a downloadable recording.
Received audio uses an incrementally updated WAV header, so existing ASR job recovery can transcribe it after an interrupted service restarts.

## Measured behavior on this Mac

Hardware: Apple M2 Pro with 16 GiB unified memory.
Fixtures were synthesized locally with installed macOS voices, converted to 16 kHz PCM16, and delivered at their original wall-clock rate.
No cloud service or additional weights were used.

| Fixture | Audio duration | Model startup | First draft after audio starts | Finish after audio ends | Median decode time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mandarin | 16.30 s | 1.91 s | 4.41 s | 1.67 s | 1.53 s |
| Repeated English narration | 47.77 s | 2.11 s | 4.56 s | 2.31 s | 1.44 s |

The Mandarin sample preserved the spoken characters after the overlap fix, with punctuation differences from normal file transcription.
The English stream retained all four repetitions, but recognized the application name as “Timberloom”; proper names still need review or vocabulary hints.
The longer run crossed rolling-window boundaries without accumulating increasing lag.
Its largest measured audio backlog after a decode was 2.7 seconds.
These figures describe these synthetic fixtures, not a latency or accuracy guarantee for arbitrary microphones and speech.

The original short-overlap implementation dropped Mandarin syllables.
Comparison with offline Whisper identified that regression before completion; timestamp-tie tests and the repeated real-model run cover the correction.

Local measurements and per-update events are saved under `build/live-asr-20260927/mandarin-context-benchmark/` and `build/live-asr-20260927/long-english-benchmark/`.
The reusable [benchmark script](../scripts/benchmark_live_asr.py) accepts a user-supplied 16 kHz mono PCM16 WAV and requires an explicit isolated output directory.

```bash
.venv/bin/python scripts/benchmark_live_asr.py /path/to/fixture.wav \
  --language en --output /path/to/isolated-benchmark
```

## Verification and limits

Backend checks cover text arriving before stop, a short final packet, transcript editing and subtitle export, persisted job reload, disconnect, silence, worker failure, malformed input, foreign origins, concurrent sessions, and accelerator contention.
Audio checks cover 44.1, 48, and 16 kHz input, packet boundaries, and final PCM flushing.
The native WebKit harness uses a generated audio stream through the real AudioWorklet and WebSocket pipeline with synthetic recognition.
It checks permission denial, late permission cancellation, live text, stop/save, releasing tracks, and saving after workspace switching.
Native screenshots and the 390 px browser layout were inspected; the live controls did not overflow horizontally.

Physical microphone quality and the macOS system permission dialog still require a real-user check.
Thirty-minute sessions, noisy rooms, overlapping speakers, and Mandarin-English switching have not been benchmarked.
Word timings come from rolling recognition and should be reviewed for precise subtitle work.
Approximately one-second responsiveness is not demonstrated by this prototype.
See the [model comparison](live-transcription-research.md) if lower latency becomes a requirement.
