# Local streaming ASR comparison for Timbreloom

Measured on 2026-10-03 using this Mac's Apple M2 Pro and 16 GiB of unified memory.
This compares the current Whisper microphone pipeline with three downloaded configurations: Moonshine Small Streaming English, Moonshine Tiny Streaming Mandarin, and Nemotron 3.5 ASR Streaming 0.6B in MLX 8-bit format.
Twenty main runs cover six synthetic fixtures, with one additional Moonshine run to inspect final transcript assembly.
These are integration smoke tests, not a representative speech recognition benchmark.

**Nemotron is the best next candidate for a live-engine integration.**
It produced first text at about one second on the main English, Mandarin, and mixed-language samples, retained all three language sections in the mixed sample, and finalized quickly.
Whisper remains a useful reference and file-transcription engine.
Moonshine's 32 MB Mandarin model is a promising smaller option, but its overlapping transcript lines and language-switching behavior need integration work.
The experiments use an isolated runtime and output directory; they do not constitute an installed-app update or a new engine selector in the UI.

## Measured results

First text is the first nonempty hypothesis after audio starts, including 300 ms of leading silence.
Model preparation is measured separately.
English word error rate and Mandarin character error rate ignore punctuation, case, and whitespace differences.
Counts include errors in the application name, repeated text, insertions, and missing words.
The fixtures contain only 52 English words and 77 Mandarin characters, so a single error changes the percentage substantially.

| Engine and fixture | First text | Finish after audio ends | Final text errors |
| --- | ---: | ---: | ---: |
| Whisper Turbo Q4, English | 4.32 s | 1.44 s | 1 / 52 words, 1.9% |
| Moonshine Small English, English | 1.33 s | 0.19 s | 3 / 52 words, 5.8% |
| Nemotron 8-bit, English | 1.05 s | 0.09 s | 1 / 52 words, 1.9% |
| Whisper Turbo Q4, Mandarin | 4.57 s | 2.22 s | 2 / 77 characters, 2.6% |
| Moonshine Tiny Mandarin, Mandarin | 1.13 s | 0.06 s | 4 / 77 characters, 5.2% |
| Nemotron 8-bit, Mandarin | 1.04 s | 0.07 s | 3 / 77 characters, 3.9% |

The Moonshine rows score concatenated SDK lines without overlap removal.
They therefore measure this direct integration, including transcript assembly behavior, rather than isolating the recognition model's accuracy.
An additional English run confirmed that the native final transcript itself contains two lines overlapping by 480 ms, with “I stop” present in both.
The repeated phrase accounts for two of that sample's three word errors.
A production Moonshine adapter needs a tested policy for merging overlapping lines; the benchmark retains the native output so that limitation stays visible.

## Language switching and longer speech

The mixed fixture lasts 12.52 seconds and consists of an English sentence, a Mandarin sentence, and another English sentence, synthesized with two macOS voices.
It tests a language transition with a speaker change, not one bilingual human speaker.
Whisper and Nemotron receive an automatic-language prompt; each Moonshine run uses its fixed language model.

| Engine | Mixed-language result | First text | Finish after audio ends |
| --- | --- | ---: | ---: |
| Whisper | Damaged the opening English phrase into mixed Chinese and English; retained the Mandarin and final English sections. | 6.16 s | 4.79 s |
| Moonshine English | Retained the English sections but lost most of the Mandarin section. | 1.24 s | 0.15 s |
| Moonshine Mandarin | Retained the Mandarin section, damaged part of the opening English, and omitted the final English section. | 1.15 s | 0.06 s |
| Nemotron | Retained all three sections with the expected words and Chinese characters after normalization. | 1.04 s | 0.05 s |

For example, the mixed reference begins “Please open the transcription workspace and start recording.”
Whisper replaced the opening English words with unintended Chinese before “workspace and start recording.”
Nemotron retained the expected opening and continued through the Mandarin and final English speech.
Full references and outputs are retained in the [measurement data](benchmarks/asr-2026-10-03.json).
No aggregate error rate is assigned to the mixed fixture because English words and Mandarin characters require different tokenization.

The longer English fixture lasts 45.12 seconds and crosses Whisper's 28-second rolling window.

| Engine | First text | Finish after audio ends | Final text errors |
| --- | ---: | ---: | ---: |
| Whisper | 4.97 s | 3.79 s | 3 / 133 words, 2.3% |
| Moonshine English | 1.19 s | 0.24 s | 11 / 133 words, 8.3% |
| Nemotron | 0.74 s | 0.17 s | 4 / 133 words, 3.0% |

Moonshine's longer output includes repeated words at line boundaries, which the direct adapter leaves intact.
Whisper repeated “transcript” once near a boundary.
These results establish behavior over 45 seconds, not sustained performance over a long meeting.

All four configurations produced no text during five seconds of pure silence.
Whisper returned the application's expected no-speech outcome and retained the recording.
The older Whisper benchmark helper then attempted to load a nonexistent transcript; the comparison harness recognizes only that specific expected case, records its exit code, and preserves the original log.
An initial unsuccessful helper run is kept under the local artifacts as well.

The 4.14-second stop-tail sample ends 20 ms after the last sample above the amplitude threshold of 100 PCM16 units, without the additional silence used in the other speech fixtures.
Whisper returned all 11 reference words correctly.
Nemotron preserved the final words but rendered the opening “Keep” as “Keek.”
Moonshine English changed the final “garden” to “Buzz.”
The latter is a substitution, not evidence that all final audio was discarded.

## Runtime and resource observations

| Configuration | Local model artifact size | Runtime | Observed preparation time | Peak sampled process RSS across main runs |
| --- | ---: | --- | ---: | ---: |
| Whisper Turbo Q4 | 463.7 MB | Existing `mlx-whisper 0.4.3`, MLX `0.32.2` | 1.90-4.28 s | 808 MiB |
| Moonshine Small English | 142.3 MB | `moonshine-voice 0.1.5` | 0.13-1.36 s | 862 MiB |
| Moonshine Tiny Mandarin | 32.3 MB | `moonshine-voice 0.1.5` | 0.09-0.26 s | 190 MiB |
| Nemotron 8-bit | 756.2 MB | `mlx-audio 0.5.7`, MLX `0.32.3` | 1.46-5.76 s | 835 MiB |

Sizes are decimal MB for the selected local artifact directories, excluding download metadata and shared runtime dependencies.
The English Moonshine download also fetched an optional shared spelling model that was not loaded during these tests.
The retained experiment, including its isolated environment, downloads, and audio, occupies about 1.4 GiB on disk.
RSS was sampled every 50 ms across each worker's process tree; it is not a measurement of total unified GPU memory and should not decide the memory budget by itself.
The extra Moonshine English audit run reached 956 MiB RSS, above its main-run peak, illustrating run-to-run variation.

Each case starts a fresh process without an explicit inference warmup, but operating-system file and Metal caches are shared across runs.
The first Nemotron stop-tail run needed 5.76 seconds to prepare and 2.04 seconds to show text after audio began; the later main language samples were faster.
Do not interpret a 1.04-second first-text result as time from pressing Record on a fully cold application.
Timing also excludes browser capture, WebSocket transport, and rendering.

## Test protocol

The [comparison harness](../scripts/benchmark_asr_candidates.py) generates explicit reference fixtures with the installed Samantha and Tingting macOS voices, converts them to mono 16 kHz PCM16, and saves audio hashes in a manifest.
Speech uses a requested synthesis rate of 165 words per minute.
English is 18.30 seconds, Mandarin 19.55 seconds, mixed language 12.52 seconds, longer English 45.12 seconds, stop-tail 4.14 seconds, and silence 5 seconds.
No vocabulary hints or spelling bias were enabled.

Audio arrives as 100 ms packets at its original wall-clock rate.
The new candidate workers use a separate capture thread and a bounded queue so inference cannot silently slow the simulated microphone.
The largest measured capture scheduling delay across the main candidate runs was 55 ms.
Whisper uses its existing asynchronous worker and two-second update policy through [the original benchmark](../scripts/benchmark_live_asr.py).
Moonshine uses a 0.5-second update floor; Mandarin uses `max_tokens_per_second=13`.
Nemotron uses `att_context_size=[56,3]` and its continuous-input `feed`, `step`, and `close` session interface, with four joint evaluations per decoder step.
Monolingual Whisper cases receive an explicit language; mixed and silence cases use `auto`.
The benchmark passes short `en` and `zh` codes to Nemotron, but this pinned upstream wrapper expects `en-US` and `zh-CN` and falls back to `auto` for those short codes.
The recorded Nemotron measurements therefore use automatic language prompting; the production adapter maps the selected language to the native locale codes.

These are candidate integration measurements with different runtimes and streaming policies, not an experiment that varies only model weights.
There is one main run per applicable engine and fixture, with no statistical confidence interval.
Real microphone audio, accents, room noise, overlapping speakers, one-speaker code switching, thirty-minute sessions, and word-level or stable-text latency remain untested.

## Reproduce and inspect

The retained local experiment is `build/asr-comparison-20261003/`.
It contains the isolated Python environment, downloaded models, fixture WAVs and references, complete dependency freezes, model file hashes, source snapshots, event streams, worker logs, and a CSV summary.
The portable [JSON results](benchmarks/asr-2026-10-03.json) include exact references, hypotheses, measurements, versions, and model hashes.
The command refuses to reuse an output directory, preserving earlier runs.

```bash
build/asr-comparison-20261003/venv/bin/python scripts/benchmark_asr_candidates.py run \
  --engine nemotron \
  --model build/asr-comparison-20261003/models/nemotron-3.5-8bit \
  --manifest build/asr-comparison-20261003/fixtures/manifest.json \
  --case mixed --output build/asr-comparison-20261003/repeat-nemotron-mixed
```

The other engine names are `whisper`, `moonshine-en`, and `moonshine-zh`.
Use the matching model directory recorded in the local `model-manifest.json`.
Whisper defaults to `.venv/bin/python`; `--whisper-python` can select another compatible baseline environment.
Nemotron accepts `--right-context 0`, `3`, `6`, or `13` for separate latency and accuracy experiments; the reported results all use `3`.
To generate fresh fixtures, use `fixtures --output <new-directory>` with the comparison Python interpreter.

For a clean setup, create an isolated Python 3.12 environment and install `moonshine-voice==0.1.5`, `mlx-audio[stt]==0.5.7`, and `psutil==7.2.2`.
The full resolved package lists are saved in `runtime-freeze.txt` and `whisper-runtime-freeze.txt` inside the local experiment directory.
Nemotron's conversion is pinned to revision `7279359e4481b5e9e185a318bd618e429c6d86cd` of `mlx-community/nemotron-3.5-asr-streaming-0.6b-8bit`.
Moonshine uses the official `small-streaming-en/quantized_26_08_21` and `tiny-streaming-zh/quantized_26_08_24` artifacts; every downloaded model file is hashed in the measurement data.

## Product integration implications

Use a streaming provider interface that exposes audio input, revisable text, final text, cancellation, errors, and model release independently of the UI.
Prototype Nemotron behind that interface first, while retaining the Whisper path for comparison and file processing.
Make Moonshine an additional small-model experiment after resolving overlapping lines; the Mandarin model is especially compact.
Keep mixed-language behavior explicit when presenting language-specific engines.
Before choosing a default, repeat the same comparison on consented real recordings and a sustained session, then exercise microphone permissions, stop/save, switching workspaces, and resource release in the actual app.

Upstream Moonshine currently states that all streaming STT models, including the tested Mandarin model, use MIT; the legacy non-streaming non-English models are the exceptions.
The installed downloader still prints a generic non-English community-license warning, so its message does not match that current streaming-model license statement. [Moonshine license](https://github.com/moonshine-ai/moonshine/blob/main/LICENSE).
NVIDIA's current original model card lists OpenMDW-1.1, while the pinned MLX conversion still labels the NVIDIA Open Model License.
That metadata discrepancy is recorded here and should be resolved before redistributing the conversion in a product. [NVIDIA model card](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b), [pinned MLX conversion](https://huggingface.co/mlx-community/nemotron-3.5-asr-streaming-0.6b-8bit/tree/7279359e4481b5e9e185a318bd618e429c6d86cd).
