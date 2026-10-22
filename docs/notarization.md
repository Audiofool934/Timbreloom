# Notarization credentials

The Mac mini uses the Keychain profile `mac-mini-notary` for all products in developer team `DAK5S3455A`.
`scripts/notarize_macos_release.py` uses an explicit `--keychain-profile` first, then `APPLE_NOTARY_PROFILE`, then `mac-mini-notary`.
The profile contains the Apple ID, team, and app-specific password; the repository contains only its name.

Check the stored credentials without uploading an artifact:

```sh
xcrun notarytool history --keychain-profile "${APPLE_NOTARY_PROFILE:-mac-mini-notary}"
```

After building and reviewing a Developer ID-signed app and its matching DMG, run the local prerequisites check:

```sh
python scripts/notarize_macos_release.py --app /path/to/Timbreloom.app --dmg /path/to/Timbreloom.dmg
```

The command uploads only when `--submit` is explicitly added.
An explicit `--keychain-profile` can select another machine's credential profile.
Credential validation does not establish that a release artifact has been notarized.
Keep the release checks in [release readiness](release-readiness.md), including stapling and Gatekeeper verification.
