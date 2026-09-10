from __future__ import annotations

import gc
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .base import ProviderDescriptor, TTSProvider, TTSRequest, TTSResult
from .runtime import AcceleratorCoordinator


class LocalQwenTTSProvider(TTSProvider):
    def __init__(
        self,
        model_id: str,
        model_source: str,
        coordinator: AcceleratorCoordinator,
        model_available: Callable[[], bool] | None = None,
    ) -> None:
        self.model_id = model_id
        self.model_source = model_source
        self.coordinator = coordinator
        self.model_available = model_available
        self._model: Any | None = None
        self._status = "idle"
        self._error: str | None = None
        self._model_lock = threading.Lock()

    @property
    def descriptor(self) -> ProviderDescriptor:
        model_path = Path(self.model_source)
        configured = self.model_available() if self.model_available else (model_path.is_dir() if model_path.is_absolute() else True)
        detail = self._error or self._status
        return ProviderDescriptor(
            provider_id="local-qwen-tts",
            name="Qwen3-TTS 0.6B Base",
            provider_type="tts",
            local=True,
            capabilities=("voice-clone", "long-form", "saved-voices"),
            configured=configured,
            ready=self._status == "ready",
            detail=detail,
        )

    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def get_model(self) -> Any:
        if not self.descriptor.configured:
            raise RuntimeError("Download Qwen3-TTS from Models before generating speech.")
        if self._model is not None:
            return self._model

        with self._model_lock:
            if self._model is not None:
                return self._model
            self._status = "loading"
            self._error = None
            try:
                from mlx_audio.tts.utils import load_model

                self._model = load_model(self.model_source)
                self._status = "ready"
                return self._model
            except Exception as exc:
                self._status = "error"
                self._error = str(exc)
                raise

    def preload(self) -> None:
        with self.coordinator.session("tts-preload"):
            self.get_model()

    def unload(self) -> None:
        with self._model_lock:
            if self._model is None and "mlx.core" not in sys.modules:
                return
            import mlx.core as mx

            self._model = None
            if self._status != "error":
                self._status = "idle"
            gc.collect()
            mx.clear_cache()

    def synthesize(self, request: TTSRequest) -> TTSResult:
        if not self.descriptor.configured:
            raise RuntimeError("Download Qwen3-TTS from Models before generating speech.")
        import mlx.core as mx
        from mlx_audio.audio_io import write as audio_write

        started = time.perf_counter()
        with self.coordinator.session("tts"):
            model = self.get_model()
            results = list(
                model.generate(
                    text=request.text.strip(),
                    ref_audio=str(request.reference_audio),
                    ref_text=request.reference_text,
                    lang_code=request.language,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    verbose=False,
                    stream=False,
                )
            )

            if not results:
                raise RuntimeError("The model did not return audio.")
            audio_parts = [result.audio for result in results if result.audio.size > 0]
            if not audio_parts:
                raise RuntimeError("The model returned empty audio.")

            audio = audio_parts[0] if len(audio_parts) == 1 else mx.concatenate(audio_parts)
            mx.eval(audio)
            sample_rate = int(results[0].sample_rate)
            generated_duration = int(audio.shape[0]) / sample_rate
            if generated_duration >= request.max_audio_seconds - 1.0:
                raise RuntimeError(
                    f"Segment audio is near the {request.max_tokens:,} token limit. Stopped to prevent truncation."
                )
            peak_memory = max(float(result.peak_memory_usage) for result in results)
            audio_write(request.output_path, audio, sample_rate, format="wav")

        return TTSResult(
            duration_seconds=generated_duration,
            generation_seconds=time.perf_counter() - started,
            peak_memory_gb=peak_memory,
            sample_rate=sample_rate,
        )
