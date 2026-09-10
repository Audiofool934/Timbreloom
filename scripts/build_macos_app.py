#!/usr/bin/env python3
"""Build an Apple Silicon app using Xcode and locked production dependencies."""

from __future__ import annotations

import argparse
import platform
import plistlib
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from macos_bundle import assemble, clone_file
from sign_macos_app import sign


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = "local.timbreloom.desktop"


def run(*args: str | Path) -> None:
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def replace_build(staged: Path, destination: Path) -> None:
    if destination.exists():
        with (destination / "Contents/Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        if info.get("CFBundleIdentifier") != BUNDLE_ID:
            raise RuntimeError(f"Refusing to replace a different app: {destination}")
        backup_root = ROOT / "build/previous-apps"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{datetime.now():%Y%m%d-%H%M%S-%f}-Timbreloom"
        shutil.move(str(destination), str(backup.with_suffix(".app")))
    shutil.move(str(staged), destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Also install in ~/Applications")
    parser.add_argument("--release", action="store_true", help="Embed standalone runtimes and an optional model download catalog; no weights")
    parser.add_argument("--sign-identity", default="-", help="Developer ID identity; default is local ad-hoc signing")
    parser.add_argument("--development-signing", action="store_true", help="Use a local Apple Development identity to test hardened runtime without uploading")
    parser.add_argument("--build-number", default="2")
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        parser.error("This local build requires an Apple Silicon Mac.")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="macos-", dir=build) as tmp:
        stage = Path(tmp)
        app = stage / "Timbreloom.app"
        macos = app / "Contents/MacOS"
        resources = app / "Contents/Resources"
        macos.mkdir(parents=True)
        resources.mkdir()
        sources = [ROOT / "macos" / name for name in (
            "App.swift", "Backend.swift", "Sidebar.swift", "WebWorkspace.swift", "FileDialogs.swift",
        )]
        run("xcrun", "swiftc", "-O", "-whole-module-optimization", "-swift-version", "5",
            "-target", "arm64-apple-macosx14.0", "-framework", "AppKit", "-framework", "WebKit",
            *sources, "-o", macos / "Timbreloom")
        iconset = stage / "Timbreloom.iconset"
        iconset.mkdir()
        run("xcrun", "swiftc", ROOT / "macos/Icon.swift", "-o", stage / "draw-icon")
        run(stage / "draw-icon", iconset, resources / "DesktopSymbols.json")
        run("iconutil", "-c", "icns", iconset, "-o", resources / "Timbreloom.icns")
        if args.release:
            assemble(resources)
        info = {
            "CFBundleName": "Timbreloom", "CFBundleDisplayName": "Timbreloom",
            "CFBundleIdentifier": BUNDLE_ID, "CFBundleExecutable": "Timbreloom",
            "CFBundleDevelopmentRegion": "en", "CFBundleLocalizations": ["en"],
            "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.1.0",
            "CFBundleVersion": args.build_number, "CFBundleIconFile": "Timbreloom",
            "LSMinimumSystemVersion": "14.0", "LSMultipleInstancesProhibited": True,
            "LSApplicationCategoryType": "public.app-category.music",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription": "Timbreloom uses the microphone to record voice references and media for conversion and transcription locally.",
            "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        }
        if args.release:
            info["TimbreloomEmbeddedRuntime"] = True
        else:
            info["TimbreloomProjectRoot"] = str(ROOT)
        with (app / "Contents/Info.plist").open("wb") as handle:
            plistlib.dump(info, handle)
        if args.release:
            sign(app, args.sign_identity, development=args.development_signing)
        else:
            run("codesign", "--force", "--sign", args.sign_identity, "--identifier", BUNDLE_ID, app)
            run("codesign", "--verify", "--strict", app)
        destination = build / ("release/Timbreloom.app" if args.release else "Timbreloom.app")
        destination.parent.mkdir(parents=True, exist_ok=True)
        replace_build(app, destination)
        print(f"Built: {destination}")
        if args.install:
            applications = Path.home() / "Applications"
            applications.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".timbreloom-install-", dir=applications) as install_tmp:
                installed_stage = Path(install_tmp) / "Timbreloom.app"
                shutil.copytree(destination, installed_stage, symlinks=True, copy_function=clone_file)
                replace_build(installed_stage, applications / "Timbreloom.app")
            print(f"Installed: {applications / 'Timbreloom.app'}")


if __name__ == "__main__":
    main()
