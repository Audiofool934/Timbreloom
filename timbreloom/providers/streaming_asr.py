from __future__ import annotations

import base64
import json
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from threading import Event

from .base import ASRProvider, ASRRequest, ProviderDescriptor
from .live_whisper import LiveWhisperProcess
from ..asr_streams import NEMOTRON_LANGUAGES


class StreamingASRProcess(LiveWhisperProcess):
    def push(self, pcm: bytes, *, final: bool = False) -> dict:
        self.process.stdin.write(json.dumps({"pcm": base64.b64encode(pcm).decode("ascii"), "final": final}) + "\n")
        self.process.stdin.flush()
        return self.read()


class LocalStreamingASRProvider(ASRProvider):
    native_streaming = True

    def __init__(self, model_key, model_source, runtime_python, coordinator, *,
                 model_available, before_load=None):
        self.model_key = model_key
        self.model_source = Path(model_source)
        self.runtime_python = Path(runtime_python)
        self.coordinator = coordinator
        self.model_available = model_available
        self.before_load = before_load
        self.model_id = {"nemotron": "mlx-community/nemotron-3.5-asr-streaming-0.6b-8bit",
                         "moonshine-en": "moonshine/small-streaming-en/quantized_26_08_21",
                         "moonshine-zh": "moonshine/tiny-streaming-zh/quantized_26_08_24"}[model_key]
        self.name = {"nemotron": "Nemotron 3.5 ASR", "moonshine-en": "Moonshine English",
                     "moonshine-zh": "Moonshine Mandarin"}[model_key]

    @property
    def descriptor(self):
        weights = self.model_available()
        runtime = self.runtime_python.is_file()
        capabilities = ["transcription", "live-transcription", "segment-timestamps", "offline"]
        if self.model_key == "nemotron":
            capabilities.append("language-detection")
        else:
            capabilities.append("vocabulary-hints")
        return ProviderDescriptor(
            provider_id=f"local-{self.model_key}-asr", name=self.name, provider_type="asr", local=True,
            capabilities=tuple(capabilities), configured=weights and runtime, ready=weights and runtime,
            detail="missing-runtime" if not runtime else "missing-model" if not weights else "local",
        )

    def validate_request(self, language: str, prompt: str) -> str:
        if self.model_key.startswith("moonshine-"):
            supported = self.model_key.rsplit("-", 1)[1]
            if language not in {"auto", supported}:
                label = "English" if supported == "en" else "Mandarin"
                raise ValueError(f"{self.name} supports {label}. Choose another model for this language.")
            return supported
        if language not in NEMOTRON_LANGUAGES:
            raise ValueError("Nemotron does not support the selected language.")
        if prompt.strip():
            raise ValueError("Vocabulary hints are available with Whisper and Moonshine. Clear hints to use Nemotron.")
        return language

    def _command(self, language, prompt):
        language = self.validate_request(language or "auto", prompt)
        if not self.runtime_python.is_file():
            raise RuntimeError("The streaming transcription runtime is missing. Run scripts/setup_streaming_asr.sh or reinstall Timbreloom.")
        if not self.model_available():
            raise RuntimeError(f"Download {self.name} from Models before starting transcription.")
        return [str(self.runtime_python), "-u", "-m", "timbreloom.streaming_asr_worker",
                "--engine", self.model_key, "--model", str(self.model_source),
                "--language", language, "--prompt", prompt]

    @contextmanager
    def live_engine(self, directory: Path, cancel_event: Event, language="auto", prompt=""):
        command = self._command(language, prompt)
        with self.coordinator.session("asr", wait=False):
            if self.before_load:
                self.before_load()
            engine = StreamingASRProcess(self.model_source, directory, cancel_event, command=command, name=self.name)
            try:
                yield engine
            finally:
                engine.close()

    def transcribe(self, request: ASRRequest, cancel_event: Event | None = None) -> dict:
        command = self._command(request.language, request.initial_prompt)
        command += ["--audio", str(request.audio_path), "--output", str(request.raw_output_path)]
        request.raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path = request.raw_output_path.with_suffix(".log")
        with self.coordinator.session("asr"):
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Transcription canceled.")
            if self.before_load:
                self.before_load()
            with log_path.open("w") as log:
                process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[2], stdout=log, stderr=log,
                                           env={**os.environ, "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"})
                try:
                    while process.poll() is None:
                        if cancel_event and cancel_event.wait(.1):
                            raise InterruptedError("Transcription canceled.")
                        if cancel_event is None:
                            time.sleep(.1)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                if process.returncode:
                    raise RuntimeError(f"{self.name} could not transcribe this audio. Try another model or restart the app.")
        return json.loads(request.raw_output_path.read_text())
