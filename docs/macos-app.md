# Timbreloom for Mac

Timbreloom provides a native Apple Silicon window, sidebar, menus, file dialogs, and four voice workspaces.
The standalone app bundles Python, FFmpeg, and inference dependencies, so it does not need a source checkout or Homebrew.
Model weights are separate and download only when you choose them.
The current standalone build requires macOS 26.2 or later, based on the bundled binaries; validation has used macOS 26.6.2.
See [release validation](release-readiness.md) for signing status and tested builds.

## Everyday controls

| Action | Shortcut or behavior |
| --- | --- |
| Switch workspace | `⌘1` Voice cloning, `⌘2` Voice conversion, `⌘3` Transcription, `⌘4` Dubbing studio |
| Import a file | `⌘O` or the toolbar; Dubbing studio imports `.timbreloom` bundles |
| Start processing | `⌘Return` starts the available generation, transcription, or project-creation action |
| Save edits | `⌘S` saves the current transcript or dubbing project |
| Show or hide sidebar | `⌃⌘S` |
| Manage models | `⌘,` or **Models** in the sidebar |
| Reopen the studio | Select the Dock icon or press `⌘0` |
| Open the library | The toolbar folder button opens it in Finder |
| Export a file | Download links open the system save dialog and reveal the finished file in Finder |
| Close the window | `⌘W` keeps the app and active work running, including an active recording |
| Quit the app | `⌘Q` warns about active jobs, unsaved edits, selected files, or exports |

Script text, reference transcripts, voice names, and vocabulary hints are saved as local drafts.
Audio files are not copied into browser draft storage and may need to be selected again after quitting.
Transcript and dubbing edits still require **Save** or `⌘S`.
Each workspace remembers its scroll position and restores an available input focus.
Canceling an audio import preserves the currently selected saved voice.
Audio previews provide playback, pause, keyboard seeking, and 0.75x to 2x speed; original video uses system controls.
macOS and WebKit request microphone access when you first start recording, and you must allow it yourself.
See the [user guide](user-guide.md) for workflows and [Mac design](macos-design.md) for the visual system.

## Startup, storage, and shutdown

Copy the standalone app into Applications before opening it.
Its library lives in `~/Library/Application Support/Timbreloom/data`; replacing the app preserves that directory.
To migrate from a checkout-backed development app, quit the old app first and use the migration command below.
The migration preserves the source and refuses to overwrite an existing destination library.

The app connects only to `127.0.0.1` and verifies the backend root and library path before attaching.
Requests with an external Origin or non-local Host are rejected.
A library process lock prevents the browser service and app service from writing to the same files simultaneously.
The startup screen retains retry and log controls if the connection fails.

Runtime logs are stored in `~/Library/Logs/Timbreloom/desktop.log` and rotate after 2 MB, retaining the previous log.
`startup-latest.json` in the same directory records process entry, window display, WebKit creation, and workspace readiness separately.
Slow worker imports are recorded after 15 seconds.

Models load only when needed for inference.
The window appears before WebKit is initialized, and workspace icons are prepared at build time.
The app requests a macOS activity assertion during startup and processing to prevent App Nap and automatic sleep from interrupting work, then releases it when idle.

Closing the window leaves active work running; the Dock icon restores it.
Quitting terminates only the service and subprocesses started by the app.
A service started in Terminal remains owned by that terminal.
A process supervisor cleans up app-owned Python, FFmpeg, ASR, and conversion subprocesses if the app exits unexpectedly.
On restart, TTS, ASR, dubbing generation, and export recover according to their persisted state; interrupted voice conversions can be retried and reuse valid completed segments.

## Workspace controls

Search saved speech, conversions, transcripts, and dubbing projects by their displayed names or details.
Press Escape in a search field to clear the filter.
Search does not change or remove saved records.

In the transcript or dubbing editor, choose **Focus editor** to hide the import area and library.
Choose **Show import & library** to restore them with their settings intact.
The native Import command also restores the setup area.

Recording and live transcription show a real microphone input meter.
The bar shows RMS level in dBFS, with a separate peak indicator.
The meter warns about near-full-scale peaks and sustained silence without modifying the recorded audio.
Live transcripts follow new text until you scroll upward; **Jump to latest** resumes following.

Use the dubbing timeline's **+**, **-**, and **Fit** buttons to inspect timing.
When the timeline has keyboard focus, use + or - to zoom, 0 to fit, and arrow keys to scroll.
Option-scroll zooms around the pointer.
Zoom and scrolling preserve the playhead time and selected segments.

## Models and optional tools

Open **Models** to manage independent downloads: Qwen for cloning and dubbing; Whisper, Nemotron, and two language-specific Moonshine models for transcription; and Seed-VC with its supporting models for conversion.
Approximate sizes are 2.52 GB, 464 MB, and 1.88 GB respectively.
Downloads use fixed Hugging Face revisions and verify each file's SHA-256 before enabling the model.

The default model folder is `~/Library/Application Support/Timbreloom/models`.
Set `TIMBRELOOM_MODELS_DIR` to choose another location.
Partial files survive network failures, pauses, and app exits; choose **Resume download** or **Retry download** to continue.
Closing the model panel leaves downloads running, while quitting the app pauses them.
Existing library items remain available for viewing and editing without models.
Once downloaded, models support offline inference and are reused across app updates.

The app includes runtime dependencies, their licenses, and required corresponding source material.
Open third-party notices from the Help menu.
Data and rebuildable caches are written outside the bundle, so local workflows also work from a read-only application directory.
A development shell built without `--release` still depends on the checkout's environment, models, FFmpeg, and fixed path; rebuild it after moving the checkout.

Gemini text tools are optional and do not affect local audio features.
An app started from Finder usually does not inherit a terminal's `GEMINI_API_KEY`.
To supply it, quit the app and launch its `Contents/MacOS/Timbreloom` executable from a terminal that already has the variable exported.
The app does not read your full shell configuration, copy the key into its bundle or drafts, or send automatic cloud requests.

## Build

Install Xcode or Command Line Tools and prepare the project environment first.
From the repository root, build a development app with:

```bash
.venv/bin/python scripts/build_macos_app.py --install
open ~/Applications/Timbreloom.app
```

The output is `build/Timbreloom.app`; `--install` also copies it to `~/Applications`.
To build a standalone candidate and optionally migrate existing data and models:

```bash
.venv/bin/python scripts/build_ffmpeg.py
.venv/bin/python scripts/build_macos_app.py --release --development-signing
.venv/bin/python scripts/migrate_macos_data.py --source data
.venv/bin/python scripts/migrate_macos_models.py --source models
```

The standalone output is `build/release/Timbreloom.app`.
`--development-signing` requires an Apple Development certificate and is intended for local validation.
Omit it to produce an ad-hoc local build without Hardened Runtime validation.
Public distribution requires an appropriate Developer ID signature and Apple notarization; see [release validation](release-readiness.md).

Each release build creates temporary production environments rather than copying installed development packages.
The main service installs runtime dependencies from `uv.lock`; Seed-VC and streaming ASR use pinned versions and distribution hashes in `packaging/seed-vc-runtime.lock` and `packaging/streaming-asr-runtime.lock`.
The build leaves development environments unchanged and removes its temporary environments on completion or failure.
A first build may need to download locked dependencies.

Release pruning excludes development tools such as pytest and pip, dependency test suites, and Python development utilities.
Upstream runtime requirements remain, including setuptools for Torch and interactive or plotting components required by audio dependencies.
Licenses, necessary headers, runtime helpers, and required corresponding source are preserved.
The build verifies the production environment markers and checks Mach-O dependencies for non-system paths outside the app.
Model catalog metadata is included; weights are not copied into the app.
See [packaging](../packaging/README.md) for dependency maintenance.

Model migration verifies and copies existing weights, preserving the source and complete destination models.
Before replacing an app, the builder moves the old bundle into `build/previous-apps/` for recovery.
Personal voices, recordings, transcripts, projects, and credentials are excluded from the bundle.
Changes to Swift, Python, or static UI in a standalone app require rebuilding and signing again.

## Implementation and validation

AppKit owns the window, sidebar, menus, open dialogs, and save dialogs.
System WebKit hosts the workspace.
The bridge exposes fixed workspace, status, and command messages; web content cannot use it to read arbitrary local paths.
External navigation does not replace the workspace, and ordinary links opened by the user go to the default browser.
WebKit downloads finish in a temporary file before replacing or moving the selected destination.
The integration uses Apple's [WKDownloadDelegate](https://developer.apple.com/documentation/webkit/wkdownloaddelegate) and [WKUIDelegate](https://developer.apple.com/documentation/webkit/wkuidelegate) APIs.

```bash
TIMBRELOOM_DATA_DIR="$(mktemp -d -t timbreloom-tests)" TIMBRELOOM_PRELOAD=0 uv run pytest -q
node --test tests/test_browser_helpers.mjs
.venv/bin/python scripts/e2e_macos.py
.venv/bin/python scripts/e2e_macos.py --models
```

Python checks cover library locking, status endpoints, queued-job shutdown, deferred imports, and process-group cleanup.
WebKit checks use a separate temporary library, synthetic audio, and simulated ASR.
They cover all four workspaces at 1020, 760, and 640pt content widths, including overflow, import cancellation, recording states, transcript editing, dubbing creation, saves, SRT export and overwrite, draft recovery, navigation limits, and scrolling.
Playback checks use a real HTMLAudioElement for play, pause, seeking, and speed.
The `--models` run also checks download errors, retry, pause, resume, readiness, and narrow layouts using a synthetic download source.
Each run saves screenshots in its temporary evidence directory.
Injected file selections and synthetic microphone states do not validate OS dialog appearance or real microphone consent.

`scripts/benchmark_startup.py` measures service readiness and page delivery with a fresh service and isolated library, while checking that models were not loaded.
It does not clear system file caches or treat page delivery as native window paint.
`scripts/verify_release.py` runs real Whisper, Qwen, Seed-VC, dubbing export, project reimport, and generated-speech transcription from a chosen app bundle.
It uses an empty HOME, isolated library, offline flags, external downloaded models, and bundled FFmpeg, then checks audio validity and character error rate.
Single-machine measurements are evidence for that build, not a cross-machine performance or subjective voice-quality guarantee.
