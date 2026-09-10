"""Copy an existing local library into Application Support without changing the source."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path

from macos_bundle import copy_tree


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def migrate(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if destination.exists():
        return {"migrated": False, "reason": "The destination already exists; no files were overwritten."}
    if not source.is_dir() or destination.is_relative_to(source):
        raise ValueError("Use an existing source and a separate destination")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (source / ".service.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Quit Timbreloom before copying its library") from None
        with tempfile.TemporaryDirectory(prefix=".migration-", dir=destination.parent) as temporary:
            staged = Path(temporary) / "data"
            copy_tree(source, staged)
            count, total = 0, 0
            for path in source.rglob("*"):
                if not path.is_file() or path.name in {".DS_Store", ".service.lock"} or ".cache" in path.parts or "__pycache__" in path.parts:
                    continue
                target = staged / path.relative_to(source)
                if not target.is_file() or digest(path) != digest(target):
                    raise RuntimeError(f"Migration verification failed for {path.relative_to(source)}")
                count += 1
                total += path.stat().st_size
            # Persisted media paths are relative. Refuse legacy absolute paths rather than rewriting user text.
            for path in staged.rglob("*.json"):
                if str(source) in path.read_text():
                    raise RuntimeError(f"A legacy absolute data path needs migration: {path.relative_to(staged)}")
            if destination.exists():
                raise RuntimeError("The destination appeared during migration; refusing to overwrite it")
            staged.rename(destination)
    return {"migrated": True, "files": count, "bytes": total, "all_sha256_matched": True,
            "source_unchanged": True, "destination": str(destination)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path.home() / "Library/Application Support/Timbreloom/data")
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.destination), ensure_ascii=False, indent=2))
