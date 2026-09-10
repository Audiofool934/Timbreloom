# Timbreloom user guide

Timbreloom has four workspaces that share a local voice library.
The Mac app provides native menus, file dialogs, keyboard shortcuts, and managed local services.
The same audio workflows are also available in the browser.
See [Mac app](macos-app.md) for installation and shortcuts.

## Save a voice

1. Open **Voice cloning** and choose a clear recording, ideally 5 to 15 seconds long.
2. Enter the exact words from the recording, including punctuation.
3. Give the voice a name and choose **Save voice**.
4. Select the saved voice for future speech or conversion jobs.

Reference recordings must be 2 to 30 seconds long and no larger than 40 MB.
You can also record directly in the workspace or save a consecutive passage from a transcript as a voice.
The transcript workflow extracts the exact selected time range and uses your current edited text as the reference transcript.

Voices are stored in `data/voices/` under the active library directory.
Deleting a voice removes its reference recording and transcript, while already generated WAV files remain.
Voices in use by an active job or a dubbing project cannot be deleted.

## Voice cloning and long-form speech

1. Choose a saved voice or upload a new reference recording with its transcript.
2. Write or paste your script and select a speech language, or use **Auto-detect**.
3. Choose **Generate speech**.
4. Listen after the first segment finishes, then download the complete WAV when ready.

Timbreloom finds sentence and paragraph boundaries and groups several sentences into each generation segment.
Long sentences can be split at commas, semicolons, colons, spaces, or safe character boundaries.
The conservative estimate is 880 audio tokens per segment, below the model's hard limit of 1,024 tokens.
Every character is checked against the original text before generation begins.
Failed segments are retried; the system does not silently skip them.
The total input limit is 200,000 characters, with practical limits set by runtime and disk space.

Completed segments become available for continuous playback immediately.
The player waits for the next segment and continues when it arrives.
Stopping pauses generation after the current model call or segment reaches a safe stopping point.

### Write for expression

The Base cloning model does not support hidden emotion tags or `instruct` commands.
Tags such as `[happy]`, `[laugh]`, and SSML `<prosody>` may be spoken aloud.
Use ordinary words and punctuation instead:

| Intent | Example |
| --- | --- |
| Hesitation | `Well… I am still thinking.` |
| Surprise | `Wait, it worked! It really worked!` |
| A question | `Oh? What did you say?` |
| A spoken reaction | `Ha, now I see.` |

Punctuation suggests phrasing but does not guarantee exact pitch, emotion, or duration.
Precise pauses and word lengths require audio editing beyond the current text controls.

## Voice conversion

1. Save the target voice in **Voice cloning**.
2. Open **Voice conversion** and import a recording or video that already contains the performance you want to preserve.
3. Choose the target voice and quality preset, then confirm permission to use both the media and the voice.
4. Choose **Convert voice** and listen as segments finish.
5. Compare the original and converted versions, then download WAV or, for video sources, MP4.

Seed-VC converts the original audio directly without transcribing and reading it again.
The presets use 4 diffusion steps for **Fast**, 8 for **Balanced**, and 12 for **High quality**.
Balanced is the default; more steps take longer and do not guarantee a better result for every recording.

Media can be up to 8 hours long and 2 GB, including TS, M2TS, and MTS files.
Audio longer than 6 minutes is split near natural pauses into segments of roughly 4 minutes, with a maximum of 6 minutes per segment.
Completed segments are saved individually and reused when a failed or interrupted job is retried.
Joining does not add extra silence.
After successful completion, rebuildable normalized audio and intermediate chunks are cleaned up to limit duplicate storage.

Records live in `data/conversions/<id>/` and contain the original media, results, logs, and job metadata.
Jobs interrupted by an app restart are marked for a safe manual retry.

## Transcription

1. Open **Transcription** and import audio or video, or record directly.
2. Select the spoken language or use **Auto-detect**.
3. Optionally provide vocabulary hints for names, terms, or project names.
4. Start transcription, then edit the timestamped segments.
5. Export TXT, SRT, or VTT, or select 2 to 30 consecutive seconds to save a voice.

Whisper runs locally and records word timestamps when available.
The prepared source audio becomes playable before recognition finishes.
Each record in `data/transcripts/<id>/` retains the source, normalized audio, original Whisper output, editable transcript, and QA summary.
Editing text preserves the existing timestamps.

Use **Save text changes** or **⌘S** in the Mac app to keep edits.
Optional Gemini actions operate on selected text after confirmation; review their results before saving.

## Dubbing studio

1. Create a timestamped transcript in **Transcription**.
2. Open **Dubbing studio**, choose the source transcript, default voice, and speech language, then create a project.
3. Use the shared waveform to position the playhead and adjust segment times.
4. Add roles, bind them to voices, and apply them to selected segments, or assign voices individually.
5. Edit dialogue and choose **Natural duration** or **Fit slot safely**.
6. Generate all segments, selected segments, or only failed segments.
7. Resolve blocking project checks, review timing warnings, and export.

Original ASR text is preserved separately from editable dialogue.
You can split a selected segment at the playhead or merge consecutive segments with the same role and voice.
Changed text or voices invalidate only affected renders; unchanged segments reuse cached audio.
Completed segments are available for playback while the rest of the project generates.

Projects live in `data/projects/<id>/` and retain their own source audio and, when applicable, original video.
Video media uses a hard link when available and otherwise a copy, so the project remains independent of its source transcript.
See [project format](project-format.md) for schemas, caching, and migration rules.

### Timing and video export

The waveform, media preview, timeline, and segment editor share one playhead.
The timeline shows original slots, generated audio duration, and overlaps with later segments.
When a browser cannot preview a source video codec, the editor falls back to source audio.

**Fit slot safely** uses FFmpeg `atempo` to preserve pitch while adjusting speed between 0.8x and 1.25x.
If a line still exceeds its slot, the full speech is retained and the export reports the overlap.
You can shorten the dialogue, regenerate it, adjust timing, or accept the overlap.

Audio projects export WAV and SRT.
Video projects also export MP4, with the original audio muted or mixed at 15%, 35%, 60%, or 100%.
The exporter first tries to copy the original video stream; incompatible codecs fall back to H.264.
Generated speech is not cut merely to match the original picture duration.
Exports run as persistent background jobs that can recover after a service restart.

### Portable projects

Download a `.timbreloom` project bundle to move a project with its referenced voices, source media, cached segments, subtitles, and existing exports.
Import assigns a new project ID and does not overwrite an existing project.
Matching voice IDs with identical content are reused; conflicting voice content stops the import.

## Recording and playback

Voice cloning can record up to 30 seconds, voice conversion up to 30 minutes, and transcription up to 8 hours.
Microphone permission is requested when you choose **Record**.
Use **Stop and use** to preview the result or continue to processing; **Cancel** preserves the previous file.
Changing workspaces cancels an active recording and releases the microphone.
Closing the Mac window keeps the app running and does not itself stop a recording.

The Mac audio player supports playback, pause, seeking with the keyboard, and speeds from 0.75x to 2x.
Original video uses system playback controls.

## Saving and recovery

TTS requests, reference audio, segmentation plans, and progress are saved in `data/jobs/<id>/`.
After a restart, completed chunks are verified by SHA-256 and generation resumes at the first missing or damaged chunk.
Changed model settings block automatic recovery to avoid mixing incompatible generations.

ASR requests and progress are saved atomically in `job.json`.
Recovery reuses verified prepared audio and complete raw recognition results when available.
Canceled transcription jobs remain canceled.
Dubbing generation and export use their own persistent job records.
Older jobs without request checkpoints cannot be reconstructed automatically.

The browser retains active job IDs across temporary service outages and reconnects automatically.
In the Mac app, script text, reference transcripts, voice names, and vocabulary hints are also kept as local drafts.
Audio files are not stored in browser drafts, and may need to be selected again after quitting.
Transcript and dubbing edits still require an explicit save.

## Optional Gemini text tools

Gemini can add punctuation, clean up text, or translate selected dialogue.
Provide `GEMINI_API_KEY` through the service environment rather than source files.
The Mac app launched from Finder usually does not inherit a terminal's environment; see the [Mac guide](macos-app.md#models-and-optional-tools).

Each cloud action asks for explicit confirmation and sends only selected text.
Audio, local paths, and unrelated segments are not included.
Batch requests are limited to 50 segments and 60,000 characters in total.
Results enter the editor without being saved automatically.

## Current scope

Timbreloom 1.1 includes local voice cloning, transcription, voice conversion, role-based dubbing, safe timeline fitting, resumable exports, and project bundles.
Automatic speaker identification, background-vocal separation, lip synchronization, and a separate emotion-reference model are outside the current feature set.
