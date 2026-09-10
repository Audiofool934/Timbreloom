from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event
from typing import Any, Callable

from .base import ASRProvider, ASRRequest, ProviderDescriptor
from .runtime import AcceleratorCoordinator


class LocalWhisperASRProvider(ASRProvider):
    def __init__(
        self,
        model_id: str,
        model_source: Path,
        coordinator: AcceleratorCoordinator,
        before_load: Callable[[], None] | None = None,
        model_available: Callable[[], bool] | None = None,
    ) -> None:
        self.model_id = model_id
        self.model_source = model_source
        self.coordinator = coordinator
        self.before_load = before_load
        self.model_available = model_available

    @property
    def descriptor(self) -> ProviderDescriptor:
        model_ready = (
            (self.model_source / "config.json").is_file()
            and (self.model_source / "weights.npz").is_file()
        )
        if self.model_available:
            model_ready = self.model_available()
        return ProviderDescriptor(
            provider_id="local-whisper-asr",
            name="Whisper Large v3 Turbo Q4",
            provider_type="asr",
            local=True,
            capabilities=(
                "transcription",
                "language-detection",
                "segment-timestamps",
                "word-timestamps",
                "offline",
            ),
            configured=model_ready,
            ready=model_ready,
            detail="project-local" if model_ready else "missing-model",
        )

    def transcribe(
        self,
        request: ASRRequest,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        descriptor = self.descriptor
        if not descriptor.ready:
            raise RuntimeError("请先在“模型管理”中下载 Whisper，再开始转录。")

        request.raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path = request.raw_output_path.with_suffix(".log")
        command = [
            sys.executable,
            "-m",
            "timbreloom.whisper_worker",
            "--audio",
            str(request.audio_path),
            "--model",
            str(self.model_source),
            "--output",
            str(request.raw_output_path),
        ]
        if request.language:
            command.extend(["--language", request.language])
        if request.initial_prompt:
            command.extend(["--initial-prompt", request.initial_prompt])

        environment = os.environ.copy()
        environment["HF_HUB_OFFLINE"] = "1"
        environment["TOKENIZERS_PARALLELISM"] = "false"

        with self.coordinator.session("asr"):
            if self.before_load is not None:
                self.before_load()
            with log_path.open("w", encoding="utf-8") as log_file:
                process = subprocess.Popen(
                    command,
                    cwd=str(Path(__file__).resolve().parents[2]),
                    env=environment,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                try:
                    while process.poll() is None:
                        if cancel_event is not None and cancel_event.is_set():
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                            raise InterruptedError("转录已取消。")
                        time.sleep(0.2)
                finally:
                    if process.poll() is None:
                        process.terminate()

        if process.returncode != 0:
            detail = log_path.read_text(encoding="utf-8", errors="replace")[-4_000:].strip()
            raise RuntimeError(detail or "本地 Whisper 转录失败。")
        if not request.raw_output_path.is_file():
            raise RuntimeError("本地 Whisper 没有产生转录结果。")
        return json.loads(request.raw_output_path.read_text(encoding="utf-8"))
