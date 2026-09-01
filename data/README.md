# Local data

This directory contains private runtime data and generated artifacts.

- `voices/` stores normalized reference recordings and their exact transcripts.
- `outputs/` stores generated WAV files.
- `transcripts/` stores imported media, normalized ASR audio, editable transcripts, raw provider output, and QA summaries.
- `uploads/` stores temporary TTS uploads while a request is running.
- `jobs/` stores resumable TTS generation state.
- `smoke/` stores local smoke-test fixtures.

Each transcript record uses `transcripts/<id>/` and contains `transcript.json` as the editable canonical record.
Provider-native results remain under `raw/` so later editor changes never overwrite the original ASR evidence.
`qa.json` records source coverage, timestamp bounds, segment count, and warnings.

Voice recordings, transcripts, job state, source media, and generated audio are excluded from Git.
