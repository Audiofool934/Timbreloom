# VoiceStudio dubbing workflow study

This note records the parts of VoiceStudio that are useful for Timbreloom's future dubbing workspace.
It is based on VoiceStudio commit [`497d57ee62c84b226c2941fd345922f70d61bec4`](https://github.com/debpalash/VoiceStudio/tree/497d57ee62c84b226c2941fd345922f70d61bec4), inspected on 2026-09-02.
No VoiceStudio source code was copied into Timbreloom.

## License boundary

VoiceStudio is licensed under [AGPL-3.0-only](https://github.com/debpalash/VoiceStudio/blob/497d57ee62c84b226c2941fd345922f70d61bec4/LICENSE) and also offers a separate commercial license.
Its bundled OmniVoice model retains a separate Apache-2.0 upstream license.
Timbreloom can study product concepts, independently implement general workflow patterns and use separately licensed upstream models.
Copying AGPL implementation code into a differently licensed or closed-source Timbreloom distribution would create obligations that need an explicit licensing decision.
This note is an engineering boundary, not legal advice.

## What is worth learning

VoiceStudio treats dubbing as a persistent project rather than one long generation request.
The visible pipeline is upload or ingest, media preparation, transcription, editing, translation, generation, quality review and export.
Its frontend state distinguishes stable content from transient execution state, as shown in [`dubSlice.ts`](https://github.com/debpalash/VoiceStudio/blob/497d57ee62c84b226c2941fd345922f70d61bec4/frontend/src/store/dubSlice.ts).

The segment table is the center of the workspace.
Each row exposes time range, speaker, editable target text, original text, language, voice, gain, preview, fit status and row actions.
The implementation is visible in [`DubSegmentRow.jsx`](https://github.com/debpalash/VoiceStudio/blob/497d57ee62c84b226c2941fd345922f70d61bec4/frontend/src/components/DubSegmentRow.jsx) and [`DubSegmentTable.jsx`](https://github.com/debpalash/VoiceStudio/blob/497d57ee62c84b226c2941fd345922f70d61bec4/frontend/src/components/DubSegmentTable.jsx).

The waveform and table share one playhead and selected segment.
Time edits, drag and resize operations commit back to the same segment record.
This behavior is implemented around [`WaveformTimeline.jsx`](https://github.com/debpalash/VoiceStudio/blob/497d57ee62c84b226c2941fd345922f70d61bec4/frontend/src/components/WaveformTimeline.jsx).

Original text is preserved when a translation becomes the active text.
Generated segment hashes and per-language tracks make incremental regeneration possible without rebuilding the entire project.
The backend synchronization path is visible in [`dub_generate.py`](https://github.com/debpalash/VoiceStudio/blob/497d57ee62c84b226c2941fd345922f70d61bec4/backend/api/routers/dub_generate.py).

VoiceStudio also separates translation engines and states whether they are local, optional or credentialed.
Its current translation matrix is documented in [translation-engines.md](https://github.com/debpalash/VoiceStudio/blob/497d57ee62c84b226c2941fd345922f70d61bec4/docs/dubbing/translation-engines.md).

## Patterns Timbreloom should adopt

| Pattern | Reason |
| --- | --- |
| Persistent project record | A long edit session must survive refreshes and model restarts. |
| Stable segment IDs | Text, voice, timing and cached audio need a durable join key. |
| Original and active text fields | Translation and cleanup must not destroy ASR evidence. |
| Per-segment generation status | Failed lines can be retried without regenerating completed lines. |
| Content fingerprint cache | Only changed text, voice or synthesis settings should invalidate audio. |
| Shared table and timeline selection | Editing, seeking and previewing should refer to one authoritative segment. |
| Explicit local or cloud badges | Users should know when audio or text can leave the machine. |
| Export as a separate stage | Rendering subtitles, stems and final media should not mutate editable project state. |

## Proposed Timbreloom data model

The first dubbing data model should remain smaller than VoiceStudio's current implementation.

```text
DubProject
  id
  title
  source_asset_id
  source_language
  target_language
  status
  created_at
  updated_at

MediaAsset
  id
  project_id
  original_filename
  media_type
  duration_seconds
  local_path
  normalized_audio_path

DubSegment
  id
  project_id
  order
  start_seconds
  end_seconds
  source_text
  active_text
  speaker_id
  voice_id
  gain
  revision

SegmentRender
  id
  segment_id
  provider_id
  content_fingerprint
  status
  audio_path
  duration_seconds
  error

ExportJob
  id
  project_id
  format
  status
  output_path
  error
```

`source_text` is immutable ASR evidence unless the user explicitly replaces the source transcript.
`active_text` is the editable or translated line used for TTS.
`revision` increases whenever timing, text, speaker or voice changes.
`content_fingerprint` includes the active text, voice identity, Provider, Provider version and generation settings.

## Recommended implementation order

1. Add a persistent `DubProject` with one local media asset and imported Timbreloom transcript.
2. Build a table editor with stable segment IDs, source text, active text, time range and voice assignment.
3. Add per-segment preview and cached regeneration using the existing Qwen Provider.
4. Add a lightweight waveform with table synchronization and safe time edits.
5. Add optional translation through the existing text Provider boundary.
6. Add subtitle and mixed-audio export before attempting video rendering.
7. Add speaker diarization, background separation, timing fit and multi-language tracks only after the single-speaker workflow is stable.

The current local ASR page already establishes the first reusable pieces: stable timestamped segments, editable text, exports, voice creation and explicit Provider locality.
