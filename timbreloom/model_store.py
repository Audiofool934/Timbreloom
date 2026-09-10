"""Explicit, resumable downloads into a model store outside the signed application."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import quote

import httpx


ACTIVE_STATES = {"downloading", "verifying", "installing"}


@lru_cache(maxsize=1)
def model_catalog() -> dict[str, dict]:
    document = json.loads(Path(__file__).with_name("model_catalog.json").read_text())
    result = {}
    for model in document["models"]:
        if not re.fullmatch(r"[a-z0-9-]+", model["id"]):
            raise ValueError("Invalid model identifier")
        for name in [model["directory"], *(file["path"] for file in model["files"])]:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("Invalid catalog path")
        for file in model["files"]:
            if not re.fullmatch(r"[a-f0-9]{64}", file["sha256"]) or file["size"] < 1:
                raise ValueError("Invalid model digest or size")
            if not re.fullmatch(r"[a-f0-9]{40}", file["revision"]):
                raise ValueError("Model revisions must be immutable commits")
        result[model["id"]] = model
    return result


def default_model_root(app_root: Path, data_root: Path) -> Path:
    default = data_root.parent / "models" if os.getenv("TIMBRELOOM_EMBEDDED") == "1" else app_root / "models"
    return Path(os.getenv("TIMBRELOOM_MODELS_DIR", str(default))).expanduser().resolve()


def model_present(directory: Path, files: list[dict]) -> bool:
    """Cheap readiness after installation-time hash verification, with no model imports."""
    try:
        return all((directory / file["path"]).is_file()
                   and (directory / file["path"]).stat().st_size == file["size"] for file in files)
    except OSError:
        return False


def _digest(path: Path, cancelled: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError()
            digest.update(block)
    return digest.hexdigest()


class ModelStore:
    def __init__(self, root: Path, *, catalog: dict[str, dict] | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.root = root
        self.catalog = model_catalog() if catalog is None else catalog
        self.transport = transport
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._closed = False
        # Construction and status reads never create directories or contact the network.

    def ready(self, model_id: str) -> bool:
        model = self.catalog[model_id]
        return model_present(self.root / model["directory"], model["files"])

    def has_active_jobs(self) -> bool:
        with self._lock:
            return any(thread.is_alive() for thread in self._threads.values())

    def _work(self, model_id: str) -> Path:
        return self.root / ".downloads" / model_id

    def _load_status(self, model_id: str) -> dict:
        try:
            state = json.loads((self._work(model_id) / "status.json").read_text())
            if state.get("state") in ACTIVE_STATES:
                state.update(state="paused", message="Download paused. Select Resume to continue.")
            return state
        except (OSError, ValueError):
            return {}

    def _update(self, model_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs[model_id]
            job.update(changes)
            destination = self._work(model_id) / "status.json"
            temporary = destination.with_suffix(".tmp")
            try:
                temporary.write_text(json.dumps(job, ensure_ascii=False) + "\n")
                os.replace(temporary, destination)
            except OSError:
                # A full disk must still leave an actionable error in the live UI.
                # On restart, transfer state is paused and partial bytes remain resumable.
                pass

    def snapshot(self) -> dict:
        models = []
        with self._lock:
            for model_id, model in self.catalog.items():
                installed = self.ready(model_id)
                job = dict(self._jobs.get(model_id) or self._load_status(model_id))
                state = "ready" if installed else job.get("state", "missing")
                received = model["bytes"] if installed else min(job.get("downloaded_bytes", 0), model["bytes"])
                models.append({key: model[key] for key in ("id", "name", "purpose", "description", "bytes", "sources")} | {
                    "state": state, "ready": installed, "downloaded_bytes": received,
                    "progress": received / model["bytes"],
                    "message": "Downloaded and ready for offline use" if installed else job.get("message", "Download when needed, then use offline"),
                })
        return {"directory": str(self.root), "models": models, "network_policy": "user-initiated-downloads-only"}

    def start(self, model_id: str) -> dict:
        if model_id not in self.catalog:
            raise KeyError(model_id)
        with self._lock:
            if self._closed:
                raise RuntimeError("The app is closing. Reopen it to continue downloading.")
            if self.ready(model_id) or (self._threads.get(model_id) and self._threads[model_id].is_alive()):
                return self.snapshot()
            work = self._work(model_id)
            work.mkdir(parents=True, exist_ok=True)
            lease = (work / "transfer.lock").open("a+b")
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                lease.close()
                raise RuntimeError("Another Timbreloom window is downloading this model.") from exc
            cancel = threading.Event()
            self._cancel[model_id] = cancel
            self._jobs[model_id] = self._load_status(model_id)
            self._update(model_id, state="downloading", message="Connecting to download server…")
            thread = threading.Thread(target=self._run, args=(model_id, cancel, lease), daemon=True,
                                      name=f"model-download-{model_id}")
            self._threads[model_id] = thread
            thread.start()
            return self.snapshot()

    def pause(self, model_id: str) -> dict:
        if model_id not in self.catalog:
            raise KeyError(model_id)
        with self._lock:
            if event := self._cancel.get(model_id):
                event.set()
                if self._threads[model_id].is_alive():
                    self._update(model_id, message="Pausing. Downloaded data will be kept…")
            return self.snapshot()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for event in self._cancel.values():
                event.set()
            threads = list(self._threads.values())
        deadline = time.monotonic() + 3
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))

    def _progress(self, model_id: str, completed: int, received: int, name: str) -> None:
        self._update(model_id, state="downloading", downloaded_bytes=completed + received,
                     message=f"Downloading {name}")

    def _download_file(self, client: httpx.Client, model_id: str, file: dict, stage: Path,
                       completed: int, cancel: threading.Event) -> None:
        final = stage / file["path"]
        final.parent.mkdir(parents=True, exist_ok=True)
        partial = final.with_name(final.name + ".partial")
        if final.is_file():
            if final.stat().st_size == file["size"] and _digest(final, cancel) == file["sha256"]:
                return
            final.unlink()  # Only this transfer's own staging files can be replaced.
        offset = partial.stat().st_size if partial.exists() else 0
        if offset >= file["size"]:
            if offset == file["size"] and _digest(partial, cancel) == file["sha256"]:
                os.replace(partial, final)
                return
            partial.unlink()
            offset = 0
        if cancel.is_set():
            raise InterruptedError()
        url = f"https://huggingface.co/{file['repository']}/resolve/{file['revision']}/{quote(file['filename'], safe='/')}"
        headers = {"Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        with client.stream("GET", url, headers=headers) as response:
            response.raise_for_status()
            if response.status_code == 206:
                if not re.fullmatch(rf"bytes {offset}-\d+/{file['size']}", response.headers.get("content-range", "")):
                    raise ValueError("The server returned invalid resume data. Try again.")
            elif response.status_code == 200:
                offset = 0  # A server may ignore Range; never append a full response to a partial file.
            else:
                raise ValueError("The download server is unavailable. Try again later.")
            received = offset
            last_update = 0.0
            with partial.open("ab" if offset else "wb") as handle:
                for chunk in response.iter_bytes(256 * 1024):
                    if cancel.is_set():
                        raise InterruptedError()
                    if received + len(chunk) > file["size"]:
                        raise ValueError("The file size does not match the pinned version. Try again.")
                    handle.write(chunk)
                    received += len(chunk)
                    now = time.monotonic()
                    if now - last_update > .25:
                        self._progress(model_id, completed, received, Path(file["path"]).name)
                        last_update = now
            self._progress(model_id, completed, received, Path(file["path"]).name)
        if received != file["size"]:
            raise ValueError("The connection ended early. Downloaded data is saved; resume to continue.")
        self._update(model_id, state="verifying", message="Verifying downloaded files…")
        if _digest(partial, cancel) != file["sha256"]:
            partial.unlink()
            raise ValueError("File verification failed. Download again.")
        os.replace(partial, final)

    def _publish(self, model: dict, stage: Path) -> None:
        final = self.root / model["directory"]
        previous = None
        if final.exists():
            previous = self._work(model["id"]) / f"previous-{uuid.uuid4().hex}"
            os.replace(final, previous)
        try:
            os.replace(stage, final)
        except BaseException:
            if previous is not None:
                os.replace(previous, final)
            raise

    def _run(self, model_id: str, cancel: threading.Event, lease) -> None:
        model = self.catalog[model_id]
        stage = self._work(model_id) / "files"
        try:
            stage.mkdir(exist_ok=True)
            completed = 0
            on_disk = sum(min(file["size"], sum(path.stat().st_size for path in
                (stage / file["path"], stage / (file["path"] + ".partial")) if path.is_file())) for file in model["files"])
            if shutil.disk_usage(self.root).free < model["bytes"] - on_disk + 64 * 1024 * 1024:
                raise ValueError("Not enough disk space. Free up space and resume the download.")
            with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(20, connect=15), transport=self.transport) as client:
                for file in model["files"]:
                    if cancel.is_set():
                        raise InterruptedError()
                    self._download_file(client, model_id, file, stage, completed, cancel)
                    completed += file["size"]
                    self._update(model_id, downloaded_bytes=completed)
            if cancel.is_set():
                raise InterruptedError()
            self._update(model_id, state="installing", message="Finishing installation…")
            self._publish(model, stage)
            self._update(model_id, state="ready", downloaded_bytes=model["bytes"], message="Downloaded and ready for offline use")
        except InterruptedError:
            self._update(model_id, state="paused", message="Download paused. Downloaded data is saved.")
        except httpx.HTTPStatusError as exc:
            self._update(model_id, state="error", message=f"Download server returned {exc.response.status_code}. Try again later.")
        except httpx.HTTPError:
            self._update(model_id, state="error", message="Connection lost. Check your network and resume the download.")
        except OSError:
            self._update(model_id, state="error", message="Cannot write to the models folder. Check disk space and permissions.")
        except Exception as exc:
            self._update(model_id, state="error", message=str(exc) if isinstance(exc, ValueError) else "Model download failed. Try again.")
        finally:
            lease.close()

    def import_existing(self, source: Path, copy_file: Callable = shutil.copy2) -> list[str]:
        """Migrate explicitly selected local weights, preserving source and complete targets."""
        imported = []
        for model_id, model in self.catalog.items():
            if self.ready(model_id):
                continue
            origin = source / model["directory"]
            if not model_present(origin, model["files"]):
                continue
            work = self._work(model_id)
            work.mkdir(parents=True, exist_ok=True)
            with (work / "transfer.lock").open("a+b") as lease:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                stage = work / "files"
                stage.mkdir(exist_ok=True)
                for file in model["files"]:
                    original = origin / file["path"]
                    if _digest(original) != file["sha256"]:
                        raise ValueError(f"Local model checksum mismatch: {original.name}")
                    destination = stage / file["path"]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    copy_file(original, destination)
                self._publish(model, stage)
                imported.append(model_id)
        return imported
