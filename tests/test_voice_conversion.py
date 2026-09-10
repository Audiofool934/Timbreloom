import json
import shutil
import time
import wave
from pathlib import Path

import timbreloom.voice_conversion as voice_conversion
from timbreloom.media import MediaInfo
from timbreloom.providers import (
    AcceleratorCoordinator,
    LocalSeedVCProvider,
    ProviderDescriptor,
    VCResult,
)
from timbreloom.voice_conversion import VoiceConversionService, plan_vc_chunks


class FakeVCProvider:
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id="fake-vc",
            name="Fake VC",
            provider_type="voice-conversion",
            local=True,
            capabilities=("offline",),
            configured=True,
            ready=True,
        )

    def convert(self, request, cancel_event=None, progress_callback=None) -> VCResult:
        if progress_callback:
            progress_callback(0.5, "正在测试换声")
        shutil.copyfile(request.source_audio, request.output_path)
        return VCResult(
            duration_seconds=2.0,
            generation_seconds=0.2,
            realtime_factor=0.1,
            sample_rate=24_000,
        )


def _write_wav(path: Path, duration_seconds: float, sample_rate: int = 24_000) -> None:
    with wave.open(str(path), "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(sample_rate)
        audio_file.writeframes(b"\x00\x00" * round(duration_seconds * sample_rate))


def _wait_for_terminal(service: VoiceConversionService, job_id: str) -> str:
    deadline = time.monotonic() + 3
    while service.get_job(job_id).status in {"queued", "running"}:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    return service.get_job(job_id).status


def test_chunk_plan_prefers_natural_pauses_and_covers_every_second() -> None:
    chunks = plan_vc_chunks(1_000.0, [235.0, 490.0, 745.0])

    assert chunks == [
        (0.0, 235.0),
        (235.0, 490.0),
        (490.0, 745.0),
        (745.0, 1_000.0),
    ]
    assert all(left[1] == right[0] for left, right in zip(chunks, chunks[1:]))


def test_long_conversion_reuses_completed_chunks_after_retry(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(voice_conversion, "VC_CHUNK_TARGET_SECONDS", 2.0)
    monkeypatch.setattr(voice_conversion, "VC_CHUNK_MIN_SECONDS", 1.0)
    monkeypatch.setattr(voice_conversion, "VC_CHUNK_MAX_SECONDS", 3.0)

    def probe(path: Path) -> MediaInfo:
        with wave.open(str(path), "rb") as audio_file:
            duration = audio_file.getnframes() / audio_file.getframerate()
        return MediaInfo(duration, True, False, "wav")

    def extract(
        _source: Path,
        destination: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> None:
        _write_wav(destination, end_seconds - start_seconds)

    class FlakyVCProvider(FakeVCProvider):
        def __init__(self) -> None:
            self.calls = 0

        def convert(self, request, cancel_event=None, progress_callback=None) -> VCResult:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("planned chunk failure")
            shutil.copyfile(request.source_audio, request.output_path)
            duration = probe(request.output_path).duration_seconds
            return VCResult(duration, 0.2, 0.1, 24_000)

    monkeypatch.setattr(voice_conversion, "probe_media", probe)
    monkeypatch.setattr(
        voice_conversion,
        "prepare_vc_audio",
        lambda source, destination: shutil.copyfile(source, destination),
    )
    monkeypatch.setattr(voice_conversion, "detect_silence_midpoints", lambda _: [2.0])
    monkeypatch.setattr(voice_conversion, "extract_vc_chunk", extract)

    reference = tmp_path / "reference.wav"
    _write_wav(reference, 2.0)
    root = tmp_path / "conversions"
    job_dir = root / ("e" * 32)
    job_dir.mkdir(parents=True)
    source = job_dir / "source.wav"
    _write_wav(source, 5.0)
    provider = FlakyVCProvider()
    service = VoiceConversionService(
        root,
        provider,
        load_voice=lambda _: {"audio_path": reference},
    )
    job = service.create_job(
        job_id="e" * 32,
        source_path=source,
        source_filename="audiobook.ts",
        source_bytes=source.stat().st_size,
        voice_id="f" * 32,
        voice_name="有声书音色",
        preset="balanced",
    )

    service.launch(job)
    assert _wait_for_terminal(service, job.job_id) == "error"
    manifest = json.loads((job_dir / "vc-chunks.json").read_text(encoding="utf-8"))
    assert [item["status"] for item in manifest["chunks"]] == ["complete", "pending"]

    service.retry(job.job_id)
    assert _wait_for_terminal(service, job.job_id) == "complete"
    snapshot = service.snapshot(job)
    assert provider.calls == 3
    assert snapshot["chunks_completed"] == 2
    assert snapshot["result"]["chunk_count"] == 2
    assert snapshot["result"]["duration_seconds"] == 5.0
    assert [item["index"] for item in snapshot["stream_chunks"]] == [1, 2]
    assert service.stream_chunk(job.job_id, 1).is_file()
    assert len(list((job_dir / "chunks").glob("converted-*.wav"))) == 2
    assert not list((job_dir / "chunks").glob("source-*.wav"))

def test_seed_vc_provider_reports_missing_runtime(tmp_path: Path) -> None:
    provider = LocalSeedVCProvider(
        runtime_python=tmp_path / "runtime/.venv/bin/python",
        source_dir=tmp_path / "runtime/source",
        checkpoint=tmp_path / "models/v1/model.pth",
        config=tmp_path / "models/v1/config.yml",
        coordinator=AcceleratorCoordinator(),
    )

    descriptor = provider.descriptor

    assert descriptor.configured is False
    assert descriptor.ready is False
    assert descriptor.detail == "missing-runtime"

def test_conversion_job_is_persistent_and_completes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        voice_conversion,
        "probe_media",
        lambda path: MediaInfo(
            1.7 if path.name == "source.wav" else 2.0,
            True,
            False,
            "wav",
        ),
    )
    monkeypatch.setattr(
        voice_conversion,
        "prepare_vc_audio",
        lambda source, destination: shutil.copyfile(source, destination),
    )
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference")
    root = tmp_path / "conversions"
    service = VoiceConversionService(
        root,
        FakeVCProvider(),
        load_voice=lambda _: {"audio_path": reference},
    )
    job_dir = root / ("a" * 32)
    job_dir.mkdir(parents=True)
    source = job_dir / "source.wav"
    source.write_bytes(b"source")
    job = service.create_job(
        job_id="a" * 32,
        source_path=source,
        source_filename="source.wav",
        source_bytes=source.stat().st_size,
        voice_id="b" * 32,
        voice_name="测试音色",
        preset="balanced",
    )
    service.launch(job)

    deadline = time.monotonic() + 3
    while service.get_job(job.job_id).status in {"queued", "running"}:
        assert time.monotonic() < deadline
        time.sleep(0.02)

    snapshot = service.snapshot(service.get_job(job.job_id))
    assert snapshot["status"] == "complete"
    assert snapshot["duration_seconds"] == 2.0
    assert snapshot["result"]["diffusion_steps"] == 8
    assert service.result_audio(job.job_id).read_bytes() == b"source"
    assert (job_dir / "conversion.json").is_file()
    manifest = json.loads((job_dir / "vc-chunks.json").read_text(encoding="utf-8"))
    assert manifest["chunks"][0]["status"] == "complete"
    assert service.list()[0]["voice_name"] == "测试音色"


def test_recovery_marks_interrupted_jobs_retryable(tmp_path: Path) -> None:
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference")
    root = tmp_path / "conversions"
    service = VoiceConversionService(
        root,
        FakeVCProvider(),
        load_voice=lambda _: {"audio_path": reference},
    )
    job_dir = root / ("c" * 32)
    job_dir.mkdir(parents=True)
    source = job_dir / "source.wav"
    source.write_bytes(b"source")
    job = service.create_job(
        job_id="c" * 32,
        source_path=source,
        source_filename="source.wav",
        source_bytes=source.stat().st_size,
        voice_id="d" * 32,
        voice_name="测试音色",
        preset="fast",
    )
    service._update(job, status="running", phase="converting")

    restarted = VoiceConversionService(
        root,
        FakeVCProvider(),
        load_voice=lambda _: {"audio_path": reference},
    )
    assert restarted.recover() == 1
    recovered = restarted.get_job(job.job_id)
    assert recovered.status == "error"
    assert "可安全重试" in recovered.message
