"""Assemble and inspect a relocatable, offline Apple Silicon runtime."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from release_runtime import (
    assert_production_packages, distributions, lock_provenance,
    production_environments, prune_runtime,
)

ROOT = Path(__file__).resolve().parents[1]
_clone = ctypes.CDLL(None, use_errno=True).clonefile
_clone.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int)
MACHO_MAGIC = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf"}


def clone_file(source, destination):
    """APFS copy-on-write, with a portable fallback and no external symlinks."""
    source, destination = Path(source), Path(destination)
    if destination.exists():
        destination.unlink()
    if _clone(os.fsencode(source), os.fsencode(destination), 0) != 0:
        shutil.copy2(source, destination)
    return str(destination)


def copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, symlinks=True, dirs_exist_ok=True, copy_function=clone_file,
                    ignore=shutil.ignore_patterns("__pycache__", ".DS_Store", ".cache", "*.pyc", "_virtualenv.*"))


def python_runtime(venv: Path, destination: Path) -> dict:
    details = json.loads(subprocess.check_output([str(venv / "bin/python"), "-c",
        "import json,sys;print(json.dumps({'base':sys.base_prefix,'version':f'{sys.version_info.major}.{sys.version_info.minor}','full_version':sys.version}))"], text=True))
    # The interpreter's own site-packages can contain bootstrap pip/setuptools.
    # Only the resolver-created production environment supplies installed packages.
    shutil.copytree(Path(details["base"]), destination, symlinks=True, copy_function=clone_file,
                    ignore=shutil.ignore_patterns("site-packages", "__pycache__", ".DS_Store", "*.pyc"))
    copy_tree(venv / f"lib/python{details['version']}/site-packages",
              destination / f"lib/python{details['version']}/site-packages")
    for path in (destination / "bin").iterdir():
        if path.name not in {"python", "python3", f"python{details['version']}"}:
            path.unlink()
    # uv rewrites this install ID to the development interpreter's absolute prefix.
    library = destination / f"lib/libpython{details['version']}.dylib"
    subprocess.run(["install_name_tool", "-id", f"@rpath/{library.name}", str(library)], check=True)
    # Console entrypoints from venv/bin have absolute interpreter paths. The app uses -m.
    for path in destination.rglob("direct_url.json"):
        path.unlink()  # Local build checkout URLs are not runtime metadata.
    pruning = prune_runtime(destination, details["version"])
    packages = distributions(destination / "bin/python")
    assert_production_packages(packages)
    return {"python": details["full_version"], "packages": packages, "production_only": True, "pruning": pruning}


def fetch(url: str, path: Path) -> bytes:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read()
        path.write_bytes(payload)
    return path.read_bytes()


def model_manifest(notices: Path) -> list[dict]:
    """Bundle download metadata and attribution only; weights never enter the app."""
    models = json.loads((ROOT / "timbreloom/model_catalog.json").read_text())["models"]
    cache = ROOT / "build/release-metadata"
    for model in models:
        for source in model["sources"]:
            if source.get("notice_url"):
                name = f"{model['id']}-LICENSE.txt"
                payload = fetch(source["notice_url"], cache / name)
                if hashlib.sha256(payload).hexdigest() != source["notice_sha256"]:
                    raise RuntimeError(f"Model license differs from its pinned source: {model['id']}")
                target = notices / "models" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                continue
            repository, revision = source["repository"], source["revision"]
            key = repository.replace("/", "--")
            metadata = json.loads(fetch(f"https://huggingface.co/api/models/{repository}/revision/{revision}?blobs=true",
                                        cache / f"{key}-{revision}.json"))
            for info in metadata["siblings"]:
                name = info["rfilename"]
                if not (Path(name).name.upper().startswith(("LICENSE", "NOTICE")) or name == "README.md"):
                    continue
                if info.get("size", 0) > 2_000_000:
                    continue
                payload = fetch(f"https://huggingface.co/{repository}/resolve/{revision}/{name}", cache / key / revision / name)
                target = notices / "models" / key / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
    return models


def macho_files(root: Path) -> list[Path]:
    result = []
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as handle:
                if handle.read(4) in MACHO_MAGIC:
                    result.append(path)
    return result


def audit(app: Path) -> dict:
    binaries = macho_files(app)
    failures = []
    for path in app.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(app.resolve()):
            failures.append(f"External symlink: {path.relative_to(app)}")
    rows = []
    # One invocation reduces tool startup cost across the Python wheels.
    ids = subprocess.check_output(["otool", "-D", *map(str, binaries)], text=True)
    install_ids = {}
    current = ""
    for line in ids.splitlines():
        if line.endswith(":"):
            current = line.split(" (architecture", 1)[0].rstrip(":")
        elif line.strip():
            install_ids[current] = line.strip()
    output = subprocess.check_output(["otool", "-L", *map(str, binaries)], text=True)
    current = ""
    for line in output.splitlines():
        if line.endswith(":"):
            current = line.split(" (architecture", 1)[0].rstrip(":")
        elif line.startswith("\t"):
            library = line.strip().split(" (", 1)[0]
            if library == install_ids.get(current):
                continue  # LC_ID_DYLIB names the binary itself; it is not a runtime dependency.
            if library.startswith("/") and not library.startswith(("/usr/lib/", "/System/Library/")):
                failures.append(f"External dylib: {library}")
    for path in binaries:
        rows.append(str(path.relative_to(app)))
    if failures:
        raise RuntimeError("\n".join(sorted(set(failures))))
    commands = subprocess.check_output(["otool", "-arch", "arm64", "-l", *map(str, binaries)], text=True)
    versions = re.findall(r"\bminos (\d+\.\d+(?:\.\d+)?)", commands)
    minimum = max(["14.0", *versions], key=lambda value: tuple(map(int, value.split("."))))
    return {"mach_o_count": len(binaries), "external_dependencies": [], "binaries": rows,
            "minimum_macos": minimum}


def assemble(resources: Path) -> dict:
    backend = resources / "backend"
    backend.mkdir()
    notices = resources / "ThirdPartyNotices"
    notices.mkdir()
    for name in ("app.py",):
        clone_file(ROOT / name, backend / name)
    for name in ("timbreloom", "static"):
        copy_tree(ROOT / name, backend / name)
    (backend / "docs").mkdir()
    clone_file(ROOT / "docs/macos-app.md", backend / "docs/macos-app.md")
    print("Preparing locked production-only Python runtimes", flush=True)
    with production_environments() as environments:
        main_runtime = python_runtime(environments["main"], backend / ".venv")
        seed_runtime = python_runtime(environments["seed-vc"], backend / "runtime/seed-vc/.venv")
        streaming_runtime = python_runtime(environments["streaming-asr"], backend / "runtime/streaming-asr/.venv")
    source = ROOT / "runtime/seed-vc/source"
    source_revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if source_revision != "51383efd921027683c89e5348211d93ff12ac2a8" or subprocess.check_output(["git", "-C", str(source), "diff", "HEAD"], text=True):
        raise RuntimeError("Seed-VC source must match the pinned, unmodified revision")
    for filename in subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"]).decode().split("\0"):
        if filename:
            target = backend / "runtime/seed-vc/source" / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            clone_file(source / filename, target)
    media = ROOT / "build/third-party/ffmpeg-9.0.1/portable"
    copy_tree(media, backend / "runtime/media")
    # Include the exact signed FFmpeg source and reproducible build recipe.
    ffmpeg_sources = notices / "FFmpeg"
    ffmpeg_sources.mkdir()
    for source in (ROOT / "scripts/build_ffmpeg.py", *sorted(media.parent.glob("ffmpeg-9.0.1.tar.xz*")),
                   media.parent / "ffmpeg-devel.asc", media.parent / "manifest.json"):
        if not source.is_file():
            raise RuntimeError(f"Missing FFmpeg provenance: {source.name}")
        clone_file(source, ffmpeg_sources / source.name)
    print("Including optional model download catalog, without weights", flush=True)
    models = model_manifest(notices)
    if (backend / "models").exists():
        raise RuntimeError("Model weights must remain outside the application bundle")
    # SoundFile wheels dynamically load LGPL libsndfile. Ship each exact upstream source version.
    sndfile = []
    for version in ("1.2.0", "1.2.2"):
        url = f"https://github.com/libsndfile/libsndfile/releases/download/{version}/libsndfile-{version}.tar.xz"
        payload = fetch(url, ROOT / "build/release-metadata" / f"libsndfile-{version}.tar.xz")
        target = notices / "libsndfile" / f"libsndfile-{version}.tar.xz"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        sndfile.append({"version": version, "source_url": url, "sha256": hashlib.sha256(payload).hexdigest()})
    for root, label in ((backend / ".venv", "python-main"), (backend / "runtime/seed-vc/.venv", "python-seed-vc"),
                        (backend / "runtime/streaming-asr/.venv", "python-streaming-asr")):
        for path in root.rglob("*"):
            if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "AUTHORS")):
                target = notices / label / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                clone_file(path, target)
    (notices / "README.txt").write_text(
        "Timbreloom includes third-party runtimes and an optional model download catalog.\n"
        "The adjacent license texts and ReleaseManifest.json identify their versions and sources.\n"
        "Seed-VC is GPL-3.0; its complete pinned engine source is in backend/runtime/seed-vc/source.\n"
        "FFmpeg is built as shared LGPL-2.1-or-later libraries without GPL or nonfree components.\n"
        "Its exact source, upstream signature, signing key and build recipe are in FFmpeg/.\n"
        "FFmpeg can be replaced with a compatible build in backend/runtime/media.\n")
    manifest = {"format": 2, "architecture": "arm64", "models_embedded": False,
                "model_download_policy": "user-initiated",
                "runtime_locks": lock_provenance(),
                "runtimes": {"main": main_runtime, "seed-vc": seed_runtime, "streaming-asr": streaming_runtime},
                "seed_vc_source": {"url": "https://github.com/Plachtaa/seed-vc", "revision": source_revision},
                "models": models, "ffmpeg": json.loads((media.parent / "manifest.json").read_text()),
                "libsndfile_sources": sndfile}
    # Precompile with relative embedded filenames, so first launch does not write into a signed app.
    for runtime, target in ((backend / ".venv", backend / ".venv"),
                            (backend / "runtime/seed-vc/.venv", backend / "runtime/seed-vc"),
                            (backend / "runtime/streaming-asr/.venv", backend / "runtime/streaming-asr"),
                            (backend / ".venv", backend / "timbreloom"),
                            (backend / ".venv", backend / "app.py")):
        subprocess.run([str(runtime / "bin/python"), "-m", "compileall", "-q", "-s", str(backend), "-p", "timbreloom", str(target)], check=True)
    (resources / "ReleaseManifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    application_sources = [ROOT / "app.py", ROOT / "timbreloom/model_catalog.json",
                           *sorted(path for path in (ROOT / "macos").glob("*.swift") if not path.name.endswith("Tests.swift")),
                           *sorted((ROOT / "timbreloom").rglob("*.py")), *sorted((ROOT / "static").glob("*"))]
    application = []
    for path in application_sources:
        if path.is_file():
            with path.open("rb") as handle:
                checksum = hashlib.file_digest(handle, "sha256").hexdigest()
            application.append({"path": path.relative_to(ROOT).as_posix(), "sha256": checksum})
    (resources / "ApplicationManifest.json").write_text(json.dumps(application, indent=2) + "\n")
    return manifest
