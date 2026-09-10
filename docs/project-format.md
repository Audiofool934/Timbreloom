# Timbreloom project format

Each dubbing project lives in `data/projects/<project-id>/` under the active library directory.
This directory is the authoritative working copy; the browser and Mac workspaces edit the same local data.

## Directory structure

```text
<project-id>/
├── project.json
├── source.wav
├── source-media.<ext>       Optional original video
├── waveform-<points>.json   Rebuildable waveform cache
├── renders/                 Segment WAV files named by content fingerprint
├── jobs/                    Generation and export job snapshots
├── exports/                 WAV, SRT, and optional MP4
└── bundles/                 Recently generated .timbreloom bundles
```

`project.json` currently uses schema version 4.
Older schema 1, 2, and 3 projects migrate forward in place when read, preserving source media, segment text, cached audio, and exports.

## Segment invariants

Each segment stores read-only `source_text` and editable `active_text`.
Split and merge operations update `source_segment_ids` to preserve links to the original ASR segments.
Segments are ordered by `order` and nondecreasing `start`; `end` cannot precede `start`.

A render fingerprint includes dialogue, effective voice, target language, model ID, and generation settings.
Changing timestamps, gain, or duration fit does not regenerate speech because those fields affect the final timeline only.
Text or voice changes mark only the affected renders as stale.

## Roles and voices

Roles belong to a project and include a name, display color, and optional voice ID.
Segments store both `role_id` and the resolved `voice_id`, so export does not need to infer a voice at runtime.
Changing a role's voice invalidates only the segments assigned to that role.

## Safe duration fitting

With `fit_mode: natural`, generated speech starts at the original segment position and plays at its natural duration.
With `fit_mode: slot`, export adjusts playback speed while preserving pitch to approach the available slot length.
Speed is limited to 0.8x through 1.25x, and content beyond that range is never cut.

## Project bundles

A `.timbreloom` file is a ZIP container using bundle version 2.
It contains a versioned `manifest.json`, `project.json`, referenced voices, source media, renders, and existing exports.
Identical voice profiles with matching IDs are reused during import; conflicting content with the same ID fails the entire import instead of overwriting a local voice.
Job snapshots, waveform caches, and nested bundles are excluded because they are not prerequisites for the migrated project.
The importer rejects absolute paths, parent-directory traversal, excessive entries, and extracted data beyond its safety limits.
Import always assigns a new project ID and resets unfinished job references, preserving existing local projects.
