#!/usr/bin/env python3
"""Build a relocatable LGPL FFmpeg toolchain for the macOS app from signed source."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "9.0.1"
SIGNING_KEY = "FCF986EA15E6E293A5644F10B4322F04D67658D8"
WORK = ROOT / "build/third-party" / f"ffmpeg-{VERSION}"


def fetch(url: str, destination: Path) -> None:
    if destination.is_file():
        return
    request = urllib.request.Request(url, headers={"User-Agent": "Timbreloom-build/1.1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        temporary = destination.with_suffix(destination.suffix + ".partial")
        with temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(destination)


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    archive = WORK / f"ffmpeg-{VERSION}.tar.xz"
    signature = WORK / f"ffmpeg-{VERSION}.tar.xz.asc"
    key = WORK / "ffmpeg-devel.asc"
    fetch(f"https://ffmpeg.org/releases/{archive.name}", archive)
    fetch(f"https://ffmpeg.org/releases/{signature.name}", signature)
    fetch("https://ffmpeg.org/ffmpeg-devel.asc", key)
    with tempfile.TemporaryDirectory(prefix="ffmpeg-signature-") as keyring:
        common = ["gpg", "--no-autostart", "--homedir", keyring, "--batch"]
        subprocess.run([*common, "--import", str(key)], check=True, capture_output=True)
        verification = subprocess.run(
            [*common, "--status-fd", "1", "--verify", str(signature), str(archive)],
            check=True, capture_output=True, text=True,
        )
        if f"[GNUPG:] VALIDSIG {SIGNING_KEY}" not in verification.stdout:
            raise RuntimeError("FFmpeg source was not signed by the pinned official release key")
    source = WORK / "source"
    if not source.is_dir():
        with tarfile.open(archive) as bundle:
            bundle.extractall(WORK, filter="data")
        (WORK / f"ffmpeg-{VERSION}").rename(source)
    prefix = WORK / "portable"
    config = [
        str(source / "configure"), "--prefix=/opt/timbreloom", "--install-name-dir=@rpath",
        "--disable-autodetect", "--disable-doc", "--disable-debug", "--disable-ffplay",
        "--disable-network", "--enable-shared", "--disable-static",
        "--enable-videotoolbox", "--enable-audiotoolbox", "--arch=arm64", "--target-os=darwin",
        "--extra-cflags=-mmacosx-version-min=14.0",
        "--extra-ldflags=-mmacosx-version-min=14.0 -Wl,-rpath,@executable_path/../lib",
    ]
    if not (prefix / "bin/ffmpeg").is_file():
        build = WORK / "objects-portable"
        build.mkdir(exist_ok=True)
        environment = {**os.environ, "MACOSX_DEPLOYMENT_TARGET": "14.0"}
        with (WORK / "build.log").open("w") as log:
            subprocess.run(config, cwd=build, env=environment, stdout=log, stderr=log, check=True)
            jobs = max(1, min(6, os.cpu_count() or 1))
            subprocess.run(["make", f"-j{jobs}"], cwd=build, env=environment, stdout=log, stderr=log, check=True)
            stage = WORK / "install-stage"
            subprocess.run(["make", f"DESTDIR={stage}", "install"], cwd=build, env=environment, stdout=log, stderr=log, check=True)
            (stage / "opt/timbreloom").rename(prefix)
    license_text = subprocess.check_output([str(prefix / "bin/ffmpeg"), "-L"], text=True, stderr=subprocess.STDOUT)
    if "GNU Lesser General Public License" not in " ".join(license_text.split()) or "--enable-gpl" in license_text:
        raise RuntimeError("The distributable build must use the LGPL configuration")
    with archive.open("rb") as handle:
        source_sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
    manifest = {
        "version": VERSION, "source_url": f"https://ffmpeg.org/releases/{archive.name}",
        "source_sha256": source_sha256,
        "verified_signing_key": SIGNING_KEY, "configuration": config[1:],
        "minimum_macos": "14.0", "license": "LGPL-2.1-or-later",
    }
    (WORK / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"FFmpeg toolchain: {prefix}", flush=True)


if __name__ == "__main__":
    main()
