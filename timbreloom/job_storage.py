"""Small filesystem primitives shared by durable model jobs."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def local_file(directory: Path, name: str) -> Path:
    if not name or Path(name).name != name:
        raise ValueError("Job files must be inside the jobs folder.")
    path = directory / name
    if path.resolve().parent != directory.resolve():
        raise ValueError("Job files cannot point to another folder.")
    return path


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
