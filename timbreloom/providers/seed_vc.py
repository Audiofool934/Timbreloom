from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from pathlib import Path
from threading import Event
from typing import Callable

from ..media import normalize_vc_audio, probe_media
from .base import ProviderDescriptor, VCProvider, VCRequest, VCResult
from .runtime import AcceleratorCoordinator


class LocalSeedVCProvider(VCProvider):
    """Run the GPL Seed-VC engine as an isolated project-local subprocess."""

    def __init__(
        self,
        *,
        runtime_python: Path,
        source_dir: Path,
        checkpoint: Path,
        config: Path,
        coordinator: AcceleratorCoordinator,
        before_load: Callable[[], None] | None = None,
        model_available: Callable[[], bool] | None = None,
    ) -> None:
        self.runtime_python = runtime_python
        self.source_dir = source_dir
        self.checkpoint = checkpoint
        self.config = config
        self.coordinator = coordinator
        self.before_load = before_load
        self.model_available = model_available
        self._status = "idle"
        self._error: str | None = None
        self._state_lock = threading.Lock()

    def _requirements(self) -> tuple[Path, ...]:
        model_root = self.checkpoint.parent.parent
        return (
            self.runtime_python,
            self.source_dir / "inference.py",
            self.checkpoint,
            self.config,
            model_root / "dependencies/bigvgan/config.json",
            model_root / "dependencies/bigvgan/bigvgan_generator.pt",
            model_root / "dependencies/whisper-small/config.json",
            model_root / "dependencies/whisper-small/model.safetensors",
            model_root / "dependencies/whisper-small/preprocessor_config.json",
            model_root / "dependencies/campplus/campplus_cn_common.bin",
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        configured = all(path.is_file() for path in self._requirements())
        if self.model_available:
            configured = configured and self.model_available()
        with self._state_lock:
            status = self._status
            error = self._error
        return ProviderDescriptor(
            provider_id="local-seed-vc",
            name="Seed-VC 1.0",
            provider_type="voice-conversion",
            local=True,
            capabilities=(
                "zero-shot-voice-conversion",
                "prosody-preservation",
                "saved-voices",
                "audio-and-video",
                "offline",
            ),
            configured=configured,
            ready=configured and status != "running",
            detail=error or (status if configured else "missing-runtime"),
        )

    @property
    def status(self) -> str:
        with self._state_lock:
            return self._status

    @property
    def error(self) -> str | None:
        with self._state_lock:
            return self._error

    def _set_status(self, status: str, error: str | None = None) -> None:
        with self._state_lock:
            self._status = status
            self._error = error

    def convert(
        self,
        request: VCRequest,
        cancel_event: Event | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> VCResult:
        if not self.descriptor.configured:
            raise RuntimeError("请先在“模型管理”中下载 Seed-VC，再开始换色。")
        if not 1 <= request.diffusion_steps <= 30:
            raise ValueError("Seed-VC 扩散步数必须在 1 到 30 之间。")
        if not 0.0 <= request.inference_cfg_rate <= 1.0:
            raise ValueError("Seed-VC CFG 必须在 0 到 1 之间。")
        if not 0.5 <= request.length_adjust <= 2.0:
            raise ValueError("Seed-VC 时长倍率必须在 0.5 到 2.0 之间。")

        request.work_dir.mkdir(parents=True, exist_ok=True)
        engine_output = request.work_dir / "engine-output"
        engine_output.mkdir(parents=True, exist_ok=True)
        log_path = request.work_dir / "seed-vc.log"
        source_info = probe_media(request.source_audio)
        started = time.perf_counter()
        expected_seconds = max(12.0, 8.0 + source_info.duration_seconds * 1.65)
        command = [
            str(self.runtime_python),
            str(Path(__file__).resolve().parents[1] / "seed_vc_worker.py"),
            "--engine-source", str(self.source_dir),
            "--models", str(self.checkpoint.parent.parent),
            "--",
            "--source",
            str(request.source_audio),
            "--target",
            str(request.reference_audio),
            "--output",
            str(engine_output),
            "--diffusion-steps",
            str(request.diffusion_steps),
            "--length-adjust",
            str(request.length_adjust),
            "--inference-cfg-rate",
            str(request.inference_cfg_rate),
            "--f0-condition",
            "false",
            "--checkpoint",
            str(self.checkpoint),
            "--config",
            str(self.config),
            "--fp16",
            "false",
        ]
        environment = os.environ.copy()
        environment.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "TOKENIZERS_PARALLELISM": "false",
                "PYTORCH_ENABLE_MPS_FALLBACK": "1",
            }
        )

        self._set_status("running")
        if progress_callback is not None:
            progress_callback(0.04, "正在释放 TTS 显存并准备 Seed-VC")
        try:
            with self.coordinator.session("voice-conversion"):
                if self.before_load is not None:
                    self.before_load()
                with log_path.open("w", encoding="utf-8") as log_file:
                    process = subprocess.Popen(
                        command,
                        cwd=str(self.source_dir),
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
                                    process.wait(timeout=5)
                                raise InterruptedError("原声换色已取消。")
                            if progress_callback is not None:
                                elapsed = time.perf_counter() - started
                                progress = min(0.92, 0.08 + (elapsed / expected_seconds) * 0.78)
                                progress_callback(progress, "Seed-VC 正在保留原表演并迁移音色")
                            time.sleep(0.35)
                    finally:
                        if process.poll() is None:
                            process.terminate()

            if process.returncode != 0:
                detail = log_path.read_text(encoding="utf-8", errors="replace")[-4_000:].strip()
                raise RuntimeError(detail or "Seed-VC 换声失败。")

            candidates = sorted(engine_output.glob("vc_*.wav"))
            if len(candidates) != 1:
                raise RuntimeError("Seed-VC 没有产生唯一的音频结果。")
            if progress_callback is not None:
                progress_callback(0.94, "正在标准化换声结果")
            normalize_vc_audio(candidates[0], request.output_path)
            output_info = probe_media(request.output_path)
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            match = re.search(r"RTF:\s*([0-9.]+)", log_text)
            elapsed = time.perf_counter() - started
            rtf = (
                float(match.group(1))
                if match is not None
                else elapsed / max(output_info.duration_seconds, 0.001)
            )
            self._set_status("idle")
            return VCResult(
                duration_seconds=output_info.duration_seconds,
                generation_seconds=elapsed,
                realtime_factor=rtf,
                sample_rate=24_000,
            )
        except InterruptedError:
            self._set_status("idle")
            raise
        except Exception as exc:
            self._set_status("error", str(exc))
            raise
