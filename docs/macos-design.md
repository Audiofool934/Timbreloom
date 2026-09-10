# Mac interface design

Timbreloom uses paper white, dark ink, and soft green to support focused audio work.
The English interface preserves the existing visual identity, with concise labels and responsive controls.

## Visual system

| Element | Specification |
| --- | --- |
| Workspace background | `#f4f5f1` |
| Main panel | `#fffefa` |
| Primary and secondary text | `#20251f` and `#6b7267` |
| Selection and focus | `#eef5de` and `#6e854a` |
| Typography | macOS system font; 13pt body, 15pt script, 28pt page title |
| Controls | 40pt inputs and primary actions; 32pt secondary buttons |
| Corners | 16pt workspace shells, 12pt panels, 8pt inputs, 7pt secondary buttons |
| Window spacing | 12pt outer inset and space between the two top-aligned workspace shells |
| Icons | Apple SF Symbols in the native shell and workspace |
| Motion | 120ms state transitions; respect reduced motion and increased contrast |

## Components and behavior

| Component | Design and interaction |
| --- | --- |
| Sidebar | Workspace titles, purpose, and shortcuts with distinct selected, hover, and focus states |
| Toolbar and menus | Current workspace, context-sensitive import action, and selected menu markers |
| Startup | Deferred model loading, connection explanation, retry, and log access |
| Import dialogs | Separate allowed types and descriptions for references, media, and project bundles |
| Drop area | Empty, dragging, selected-file, and keyboard-focus states; long filenames can wrap |
| Recording | Permission request, timer, stop, cancel, and permission-error feedback |
| Saved voice | Reference details remain intact when an import is canceled |
| Script | Readable text, a separate character count, and punctuation guidance |
| Quality and language | Consistent selectors, radio presets, and visible focus |
| Library | Compact records, selection and hover states, and actionable empty states |
| Progress | Task title, current detail, progress, and cancel; completed conversion hides duplicate progress |
| Audio preview | Play, pause, seek, speed, loading errors, and retry; video uses system controls |
| Metrics | Conversion time divided by displayed audio duration, avoiding stale historical ratio fields |
| Transcript editor | Timestamp seeking, selection, text edits, save, subtitles, and optional text tools |
| Dubbing editor | Original text and dialogue, roles, voices, timeline, timing inputs, generation, and export state |
| Pending renders | Neutral preparation states; actual generation failures retain error feedback |
| Sticky toolbar | Horizontal controls that wrap at narrow widths; segment scrolling reserves toolbar space |
| Errors and drafts | Dismissible errors and draft-save status |
| Workspace switching | Independent scroll positions and restorable input focus |

## Verification

The WebKit harness checks all four workspaces at 1020, 760, and 640pt content widths, including populated transcript and dubbing editors.
It detects visible horizontal overflow and verifies saved-voice preservation after canceled imports, temporary file-input cleanup, native import types, scroll restoration, project-creation shortcuts, subtitle content, and overwrite exports.
Real HTMLAudioElement checks cover playback, pause, seeking, and speed.

The harness uses simulated ASR and synthetic microphone states in an isolated library.
It does not request real microphone permission or measure model quality.
Full AppKit layout, system dialogs, and the installed app are inspected separately.

```bash
.venv/bin/python scripts/e2e_macos.py
.venv/bin/python scripts/e2e_macos.py --models
```

Each run saves current screenshots in its temporary evidence directory.
Public screenshots under `docs/assets/` use a separate demonstration library.
