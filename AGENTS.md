# Timbreloom project instructions

Read [README.md](README.md) and the relevant project documentation before making changes.

## App updates

Follow [the app update workflow](docs/update-workflow.md) whenever preparing or installing an update.
Every delivered update must increase the visible package version and the internal build number.
Keep package metadata, API version, native bundle metadata, and the About panel consistent.
Replace the existing installed app, preserve the user's library and models, and keep recovery copies as verified archives.
Remove obsolete app copies and unregister or exclude spare builds from app search so only the intended installed app appears.
Verify the installed app's version, rendered interface, relevant functionality, and app-search result before declaring the update complete.
Do not manually edit generated lockfiles or historical release records to make versions appear consistent.
