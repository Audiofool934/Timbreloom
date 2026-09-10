# Mac release validation

The source repository is public under MIT for Timbreloom-authored code.
Standalone binaries remain local development candidates: Developer ID distribution signing and Apple notarization are not complete.
Validation uses Apple Silicon on macOS 26.6.2, with a minimum standalone system version of macOS 26.2.
Model weights are stored separately and downloaded by user choice.

## RC7: English interface and documentation

The September 10, 2026 validation covered version 1.1.0 RC7, internal build 9.
All maintained application copy, native menus, accessibility labels, errors, examples, and documentation are now English.
Multilingual speech and text input remain supported.
The README includes direct screenshots from the signed Mac app using an isolated English demonstration library.

The local disk image is `build/release/Timbreloom-1.1.0-rc7-arm64.dmg`, with a neighboring `.sha256` file.
It is 1,060,028,293 bytes and has SHA-256 `c7e156a6245b2747ab561002e00640925f047deced0b35b21567860b3b3d5262`.
RC7 uses fresh production dependency environments, contains no model weights, and remains Apple Development-signed.

| Check | Result | Local evidence |
| --- | --- | --- |
| Application regressions | 87 Python tests and five browser helper tests passed, including English copy and multilingual text behavior | `build/english-rollout/pytest-final.log` and `browser-helpers-final.log` |
| Native WebKit workspaces | All four English workspaces passed; model controls passed offline, retry, pause, resume, and narrow-window checks | `build/english-rollout/webkit-final.log` and the model-manager WebKit run |
| Bundle and image | Application source hashes match; strict signatures and DMG verification passed | `build/english-rollout/final-app-source.json`, `dmg-reverify.log`, and `verify-rc7-final.log` |
| Fresh startup without models | The service started from the read-only image with an empty HOME; processing required a model download and created no model directory | `build/release-validation/fresh-rc7-final/receipt.json` |
| Real offline workflows | Whisper, Qwen, Seed-VC, WAV/SRT/MP4 exports, bundle reimport, and native H.264 fallback passed in 100.31 seconds | `build/release-validation/real-models-rc7-final-readonly/receipt.json` |
| English speech check | Generated speech had transcription character error rates of 0.00% for Qwen and 1.41% for Seed-VC; loudness and severe-clipping checks passed | `build/release-validation/real-models-rc7-final-readonly/quality.json` |

The functional model run used synthetic English narration and external downloaded models in a separate test library.
Those short checks establish workflow operation and basic intelligibility, not subjective voice quality or accuracy across languages and speakers.
The image retained its signature after inference and was detached when validation finished.
The installed copy passed native English-interface and model-manager checks, with all 57 existing library files unchanged by content hash.
Installation retained the previous app for recovery.
The packager initially left its disk image attached; detaching it allowed image verification to complete successfully.

## RC6: isolated production runtimes

The September 8, 2026 validation covered version 1.1.0 RC6, internal build 8.
RC6 rebuilt the app from fresh production dependency environments and removed development tools, dependency test suites, and duplicate metadata.
It did not upgrade the retained dependency versions.

The local disk image is `build/release/Timbreloom-1.1.0-rc6-arm64.dmg`, with a neighboring `.sha256` file.
Its summary receipt is `build/release-validation/release-receipt-rc6.json`.
The SHA-256 is `e9d7c8c93b41ec81013d979be0d5450fd45734683eda300d17ce18fea47c2d0d`.

| Size | RC5 | RC6 | Reduction |
| --- | ---: | ---: | ---: |
| DMG | 1,197,930,044 bytes | 1,052,827,613 bytes | 145,102,431 bytes, about 12.1% |
| App regular-file logical size | 2,718,255,443 bytes | 2,489,549,594 bytes | 228,705,849 bytes, about 8.4% |

Logical size excludes symbolic links and does not represent additional APFS clone disk usage.
The app is Apple Development-signed with Hardened Runtime, without a Developer ID signature or notarization ticket.
Python 3.12, the Seed-VC Python 3.10 runtime, inference libraries, FFmpeg 9.0.1, and necessary corresponding source remain bundled.
These runtime components account for most of the package size.

### Production dependency isolation

`scripts/release_runtime.py` creates fresh temporary environments for every release build.
The main service uses `uv sync --locked --no-default-groups --no-editable` with `uv.lock`.
Seed-VC installs pinned versions and verifies distribution hashes from `packaging/seed-vc-runtime.lock`.
The build uses existing interpreters but does not copy installed development packages or change the development environments.

The portable interpreter's base site-packages are excluded, avoiding duplicate pip and setuptools metadata.
`ReleaseManifest.json` records lock-file hashes, installed dependencies, pruned paths, and removed byte counts.
The packager rejects bundles without a production-environment marker.
The main environment decreased from 90 distribution entries to 83; Seed-VC decreased from 103 metadata entries to 99.

Pruning removes dependency directories named `test` or `tests`, pip and pytest, Python installation bootstrap tools, development interfaces, and interpreter build headers.
Runtime helpers such as `numpy.testing`, `unittest`, package headers, and declared upstream dependencies remain.
This includes setuptools for Torch and interactive or plotting components required by audio dependencies.
Third-party notices and required corresponding source are preserved.

### Direct RC6 checks

| Check | Result | Local evidence |
| --- | --- | --- |
| Runtime pruning constraints | Passed two tests for development-package and duplicate-metadata rejection, while preserving runtime helpers, headers, data, and licenses | `build/release-validation/runtime-clean/unit-final.log` |
| Dependency consistency | Both environments passed `uv pip check`; main-service and actual Seed-VC inference imports passed | `build/release-validation/runtime-clean/preflight-report.json` and import logs |
| Dependency versions | No changes among retained packages | `build/release-validation/runtime-clean/dependency-diff.json` |
| Final bundle contents | Two production environments, no model weights or test suites, matching application source hashes | `build/release-validation/rc6-bundle-check.json` |
| Image and signatures | DMG verification and strict signatures passed before packaging, after read-only inference, and on the installed copy | `build/release-validation/package-rc6.log`, `verify-rc6.log`, and the summary receipt |
| Fresh startup without models | Read-only app launched with an empty HOME and isolated library; no model directory was created and processing required a download | `build/release-validation/fresh-rc6/receipt.json` |
| Real offline workflows | Whisper, Qwen, Seed-VC, WAV/SRT/MP4, bundle reimport, and native H.264 fallback passed in 217.10 seconds | `build/release-validation/real-models-rc6-readonly/receipt.json` |
| Installed app | Home screen and three ready models inspected; external model storage confirmed | `build/release-validation/native-rc6.json` |
| Existing library | Content hashes were unchanged after installation | `build/release-validation/native-rc6.json` |
| Cleanup | Validation services exited, the disk image detached, and temporary runtime and installation staging directories were removed | `build/release-validation/verify-rc6.log` and the summary receipt |

The first no-model execution took 91.03 seconds to reach service readiness, including system checks before program entry.
A subsequent isolated functional run reached service readiness in 0.391 seconds; this is not a first-install startup promise.
In that run, generated-speech transcription had a character error rate of 10.71% for Qwen and 25% for Seed-VC, with Seed-VC exactly at the existing threshold.
Both outputs passed loudness and severe-clipping checks, which do not establish subjective voice quality.
The real workflows used external downloaded models and a separate test library.

### Earlier model-download evidence

RC6 changed runtime packaging, so it did not repeat the complete network download or every WebKit regression.
RC5 evidence covered 79 Python checks, five playback and recording checks, a real Whisper download with interruption recovery, WebKit download controls, and all four workspaces.
Those historical records remain in `build/release-validation/release-readiness-rc5.md` and `release-receipt-rc5.json`.
They are distinct from the direct RC6 checks above.

## Validation limits

Developer ID signing, notarization, and Gatekeeper first-launch testing on another Mac remain incomplete.
Real microphone consent and recording have not been validated; synthetic recording tests do not grant or replace that permission.
A September 10 native preview with a new, non-existent custom `TIMBRELOOM_DATA_DIR` reported a path-check failure despite a healthy service.
Creating that directory before launch worked; this existing behavior was recorded separately from the English update, and default first-install behavior was not established by that check.
Subjective listening, speaker diversity, and long-audio quality need separate evaluation.
Local evidence paths are generated validation artifacts and are not committed to the source repository.

## Build and reproduce

```bash
.venv/bin/python scripts/build_macos_app.py --release --development-signing --build-number 9
.venv/bin/python scripts/package_macos_release.py --app build/release/Timbreloom.app --output build/release/Timbreloom-1.1.0-rc7-arm64.dmg
.venv/bin/python scripts/verify_release.py --app build/release/Timbreloom.app --models-dir "$HOME/Library/Application Support/Timbreloom/models" --output build/release-validation/new-offline-run
```

Real model validation requires all three model groups already present in the external model directory and a new output directory.
See [packaging](../packaging/README.md) for dependency maintenance and [Mac app](macos-app.md) for build variants.
Previous app bundles and disk images are retained for recovery.
The installed app owns its local service and stops that service when quit with `⌘Q`.
