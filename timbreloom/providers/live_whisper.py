from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from threading import Event


class LiveWhisperProcess:
    """Own a single persistent MLX process for one microphone session."""

    def __init__(self, model: Path, directory: Path, cancel: Event, *, command=None, name="Whisper") -> None:
        self.cancel = cancel
        self.name = name
        self.log = (directory / ("live-asr.log" if command else "live-whisper.log")).open("w")
        self.selector = selectors.DefaultSelector()
        try:
            self.process = subprocess.Popen(
                command or [sys.executable, "-u", "-m", "timbreloom.live_whisper_worker", "--model", str(model)],
                cwd=Path(__file__).resolve().parents[2],
                env={**os.environ, "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"},
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True,
            )
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            if not self.read().get("ready"):
                raise RuntimeError(f"{self.name} did not finish loading.")
        except BaseException:
            self.close()
            raise

    def read(self) -> dict:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self.cancel.is_set():
                raise InterruptedError("Live transcription stopped.")
            if self.selector.select(timeout=0.1):
                line = self.process.stdout.readline()
                if not line:
                    raise RuntimeError(f"The live {self.name} worker exited. Your recording was kept.")
                result = json.loads(line)
                if result.get("error"):
                    raise RuntimeError(result["error"])
                return result
        raise TimeoutError(f"{self.name} took too long to respond. Your recording was kept.")

    def transcribe(self, audio: Path, language: str | None, prompt: str) -> dict:
        self.process.stdin.write(json.dumps({"audio": str(audio), "language": language, "prompt": prompt}) + "\n")
        self.process.stdin.flush()
        return self.read()

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout):
                if pipe:
                    pipe.close()
        self.selector.close()
        self.log.close()
