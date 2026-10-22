# Updating the installed Mac app

Use this workflow for every delivered Timbreloom update.
The update is complete only when the installed app has a higher visible version, opens with the new interface, preserves the user's work, and appears once in app search.
Changing only the internal build number is insufficient.

## 1. Inspect the current installation

Locate the installed app and read `CFBundleShortVersionString` and `CFBundleVersion` from its `Contents/Info.plist`.
The current installation location is `~/Applications/Timbreloom.app`; verify it instead of creating another copy in `/Applications`.
Check the running process path and `/api/runtime` to identify the backend, library, and any active work.
Account for existing checkout changes before building.
Record the original library and model inventory so preservation can be verified after installation.

## 2. Increase and synchronize versions

Choose a visible version greater than the installed version, using a patch increment for fixes and a minor increment for new compatible features.
Choose an internal build number greater than the installed build number.
Read both values from the current installation each time; do not reuse a historical command's numbers or the builder's default build number.

The current implementation repeats its version in several places.
Keep these values consistent before building:

| Location | Required update |
| --- | --- |
| `pyproject.toml` | `[project].version`, the release's package version |
| `uv.lock` | Regenerate the project's metadata with uv; never edit the generated lockfile manually |
| `app.py` | FastAPI version, also reported by the health and runtime APIs |
| `scripts/build_macos_app.py` | `CFBundleShortVersionString` |
| `macos/App.swift` | The About panel's application version |
| `tests/test_app.py` | The expected health version |

For example, `uv version --bump patch --no-sync` updates the project version and lock metadata without syncing the developer environment.
Use the appropriate increment or an explicit version when the source and installed versions differ.
Review the lockfile diff to ensure a version change did not introduce unrelated dependency upgrades.
Update current package artifact names and delivery notes to match the new version.
Leave historical release records, dependency versions, and automatically generated changelogs alone.

## 3. Build and validate a standalone candidate

Use `scripts/build_macos_app.py --release` with the existing signing setup and an explicit `--build-number`.
Build and validate the candidate before replacing the installed app.
Preserve standalone packaging when updating a standalone installation; the checkout-backed development shell is a different delivery mode.
Confirm the candidate's bundle metadata, source manifest, signature, and bundled API all report or contain the intended release.
Run checks appropriate to the change and exercise the changed behavior using the bundled runtime with isolated test data.
Do not create test history in the user's library.
Follow [the Mac build guide](macos-app.md#build) for runtime preparation and signing.

## 4. Replace the existing app safely

Quit the installed app gracefully before replacing its bundle and wait for its owned backend to exit.
Preserve unsaved work and avoid interrupting active recordings, jobs, or exports.
Use the existing `replace_build` helper in `scripts/build_macos_app.py` to preserve the old app as a ZIP archive and validate the archive before removing the old bundle.
Stage and verify the new signed bundle before installing it at the same application path.
Do not rename the old version to another visible `.app` or leave version-suffixed app copies in Applications.
Keep voices, history, transcripts, projects, and models in their existing Application Support directories.
Do not rerun migration over an existing library or reset browser drafts during an update.

## 5. Remove duplicate launchable copies

The builder currently leaves a second app in `build/release/Timbreloom.app`, including when `--install` is used.
Installation alone therefore does not finish cleanup.
After verifying the installed copy, unregister the spare build's original path with the system `lsregister -u` command and move any build that must be retained into a hidden `.noindex` directory, such as `build/release/.build-copy.noindex/`.
Archive superseded retained builds before replacing them, using verified ZIP backups rather than accumulating more `.app` copies.
Register the canonical installed path with `lsregister -f`.
If an old build or disk image was mounted for this update, eject that task-owned volume as well.
Scope cleanup to verified Timbreloom copies from this workflow; do not reset the entire Launch Services database or delete unrelated applications.

Check the actual app-search index:

```bash
mdfind 'kMDItemContentType == "com.apple.application-bundle" && (kMDItemFSName == "Timbreloom.app" || kMDItemCFBundleIdentifier == "local.timbreloom.desktop")'
```

The result must contain only the intended installed app.
Verify the launcher interface when accessible, refreshing its search panel if it still displays cached results.

## 6. Verify the delivered update

Open the installed app from its canonical path and confirm `/api/runtime` points to that bundle and the original library.
Confirm that the About panel, `CFBundleShortVersionString`, and API agree on the new package version, and that `CFBundleVersion` contains the new internal build number.
Inspect the actual rendered interface and exercise the changed feature; successful source tests or a health response alone do not establish delivery.
If WebKit still displays the old interface, quit the app and move only its HTTP `NetworkCache` into the update's backup directory before reopening.
Preserve `WebsiteData`, LocalStorage, drafts, microphone permissions, and library data.
Recheck the original library and model inventory, the single app-search entry, and any task-owned processes.
Stop temporary test servers and inference workers, leaving only the user-facing app running when it has been opened for the user.
Save a local update receipt with the old and new versions and build numbers, installed path, archive paths, relocated build paths, and verification results.
Report the installed visible version and any material testing limitation in the delivery message.
