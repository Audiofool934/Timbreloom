"""Create and verify a local DMG; notarization is a separate explicit command."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from macos_bundle import clone_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app, output = args.app.resolve(), args.output.resolve()
    if output.exists():
        parser.error("The output already exists; choose a new artifact name")
    with (app / "Contents/Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    manifest = json.loads((app / "Contents/Resources/ReleaseManifest.json").read_text())
    if manifest.get("models_embedded") is not False or (app / "Contents/Resources/backend/models").exists():
        parser.error("Release apps must contain the runtime and download catalog only; model weights stay separate")
    if not all(manifest["runtimes"][name].get("production_only") for name in ("main", "seed-vc", "streaming-asr")):
        parser.error("Release apps must be assembled from locked production-only environments")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dmg-stage-", dir=output.parent) as temporary:
        stage = Path(temporary)
        shutil.copytree(app, stage / "Timbreloom.app", symlinks=True, copy_function=clone_file)
        (stage / "Applications").symlink_to("/Applications")
        (stage / "Installation.txt").write_text(
            f"Timbreloom {info['CFBundleShortVersionString']}\n\n"
            f"Requires Apple Silicon and macOS {info['LSMinimumSystemVersion']} or later.\n"
            "Drag Timbreloom into Applications, then open it from there.\n"
            "The local runtime is included. Python and Homebrew are not required.\n"
            "Models are stored separately. Choose which to download in Models; nothing downloads automatically.\n"
            "Models are saved in ~/Library/Application Support/Timbreloom/models and can be used offline after download.\n"
            "Voices, transcripts, and projects are saved in ~/Library/Application Support/Timbreloom/data.\n"
            "Replacing the app does not delete your library.\n")
        subprocess.run(["hdiutil", "create", "-format", "ULFO", "-nospotlight",
            "-volname", "Timbreloom", "-srcfolder", str(stage), str(output)], check=True)
    subprocess.run(["hdiutil", "verify", str(output)], check=True)
    with output.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    output.with_suffix(".sha256").write_text(f"{checksum}  {output.name}\n")
    print(json.dumps({"artifact": str(output), "bytes": output.stat().st_size, "sha256": checksum}, indent=2))


if __name__ == "__main__":
    main()
