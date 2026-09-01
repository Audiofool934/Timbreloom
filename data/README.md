# Local data

This directory contains private runtime data and generated artifacts.

- `voices/` stores normalized reference recordings and their exact transcripts.
- `outputs/` stores generated WAV files.
- `uploads/` stores temporary uploads while a request is running.
- `jobs/` stores resumable generation state.
- `smoke/` stores local smoke-test fixtures.

Voice recordings, transcripts, job state, and generated audio are excluded from Git.
