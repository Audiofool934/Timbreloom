# Local data

This directory contains private runtime data and generated artifacts.

- `voices/` stores normalized reference recordings and their exact transcripts.
- `outputs/` stores generated WAV files.
- `transcripts/` stores imported media, normalized ASR audio, editable transcripts, raw provider output, and QA summaries.
- `projects/` stores persistent dubbing projects, project-owned source video links or copies, segment renders, resumable jobs, and timeline exports.
- `conversions/` stores speech-to-speech source media, normalized audio, converted WAV or MP4 results, progress state, and local engine logs.
- `uploads/` stores temporary TTS uploads while a request is running.
- `jobs/` stores durable TTS requests, owned reference recordings, verified completed chunks and result metadata.
- `smoke/` stores local smoke-test fixtures.

Each transcript record uses `transcripts/<id>/` and contains `transcript.json` as the editable canonical record.
Provider-native results remain under `raw/` so later editor changes never overwrite the original ASR evidence.
`qa.json` records source coverage, timestamp bounds, segment count, and warnings.
New TTS and ASR tasks use an atomically written `job.json` to preserve requests, progress and cancellation across restarts.
TTS resumes from its verified completed prefix; ASR reuses prepared audio and completed raw recognition results when available.
Completed and failed TTS jobs retain their completed chunks for playback.

Voice recordings, transcripts, job state, source media, conversion results, and generated audio are excluded from Git.
