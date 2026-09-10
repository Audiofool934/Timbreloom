from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    provider_id: str
    name: str
    provider_type: str
    local: bool
    capabilities: tuple[str, ...]
    configured: bool
    ready: bool
    detail: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "name": self.name,
            "type": self.provider_type,
            "local": self.local,
            "capabilities": list(self.capabilities),
            "configured": self.configured,
            "ready": self.ready,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class TTSRequest:
    reference_audio: Path
    reference_text: str
    text: str
    language: str
    output_path: Path
    temperature: float
    max_tokens: int
    max_audio_seconds: float


@dataclass(frozen=True, slots=True)
class TTSResult:
    duration_seconds: float
    generation_seconds: float
    peak_memory_gb: float
    sample_rate: int


@dataclass(frozen=True, slots=True)
class ASRRequest:
    audio_path: Path
    language: str | None
    raw_output_path: Path
    initial_prompt: str = ""


@dataclass(frozen=True, slots=True)
class VCRequest:
    source_audio: Path
    reference_audio: Path
    output_path: Path
    work_dir: Path
    diffusion_steps: int
    inference_cfg_rate: float
    length_adjust: float = 1.0


@dataclass(frozen=True, slots=True)
class VCResult:
    duration_seconds: float
    generation_seconds: float
    realtime_factor: float
    sample_rate: int


class TTSProvider(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> ProviderDescriptor:
        raise NotImplementedError

    @abstractmethod
    def preload(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def unload(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def synthesize(self, request: TTSRequest) -> TTSResult:
        raise NotImplementedError


class ASRProvider(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> ProviderDescriptor:
        raise NotImplementedError

    @abstractmethod
    def transcribe(
        self,
        request: ASRRequest,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class VCProvider(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> ProviderDescriptor:
        raise NotImplementedError

    @abstractmethod
    def convert(
        self,
        request: VCRequest,
        cancel_event: Event | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> VCResult:
        raise NotImplementedError

class TextModelProvider(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> ProviderDescriptor:
        raise NotImplementedError

    @abstractmethod
    def check_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def transform(
        self,
        text: str,
        task: str,
        target_language: str = "",
    ) -> dict[str, Any]:
        raise NotImplementedError
