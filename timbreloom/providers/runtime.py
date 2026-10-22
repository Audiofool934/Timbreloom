from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


class AcceleratorCoordinator:
    """Serialize MLX workloads so large local models do not contend for memory."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._active: str | None = None

    @contextmanager
    def session(self, workload: str, *, wait: bool = True) -> Iterator[None]:
        if not self._lock.acquire(blocking=wait):
            raise RuntimeError("Another local model is busy. Finish that job before starting live transcription.")
        try:
            with self._state_lock:
                self._active = workload
            try:
                yield
            finally:
                with self._state_lock:
                    self._active = None
        finally:
            self._lock.release()

    @property
    def active(self) -> str | None:
        with self._state_lock:
            return self._active
