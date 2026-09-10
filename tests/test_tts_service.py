import wave
from datetime import datetime, timezone
from pathlib import Path

import pytest

from timbreloom.segmentation import TextSegment
from timbreloom.tts_service import GenerationJob, TTSService


def write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\0\0" * 4000)


def make_service(root: Path, generate) -> TTSService:
    return TTSService(
        root / "jobs",
        root / "outputs",
        generate_segment=generate,
        normalize_audio=lambda *_: pytest.fail("Owned normalized reference was lost"),
        model_id="test-model",
        settings={"temperature": 1.0},
        max_attempts=1,
    )


def make_job(root: Path, service: TTSService) -> GenerationJob:
    directory = service.root / ("a" * 32)
    directory.mkdir()
    reference = root / "reference.wav"
    write_wav(reference)
    job = GenerationJob(
        job_id=directory.name,
        voice_id="b" * 32,
        voice_name="Test voice",
        reference_source=reference,
        reference_is_normalized=True,
        reference_text="Reference words",
        reference_duration_seconds=0.5,
        language="english",
        segments=[
            TextSegment(1, 0, 6, "First.", 12),
            TextSegment(2, 6, 13, "Second.", 12),
        ],
        job_dir=directory,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    service.add(job)
    reference.unlink()
    return job


def generator(calls, *, crash=False):
    def generate(reference, _reference_text, text, _language, output):
        assert reference.is_file()
        calls.append(text)
        if crash and text == "Second.":
            output.write_bytes(b"interrupted WAV")
            raise SystemExit("simulated process termination")
        write_wav(output)
        return {
            "duration_seconds": 0.5,
            "peak_memory_gb": 0.0,
            "generation_seconds": 0.0,
        }

    return generate


@pytest.mark.parametrize("damage_chunk", [False, True])
def test_restart_reuses_only_verified_chunks_and_keeps_downloads(
    tmp_path, monkeypatch, damage_chunk
):
    first_calls = []
    first = make_service(tmp_path, generator(first_calls, crash=True))
    job = make_job(tmp_path, first)
    with pytest.raises(SystemExit):
        first.process(job)
    assert first.snapshot(job)["stream"]["available"] == 1
    if damage_chunk:
        (job.job_dir / "segment-00001.wav").write_bytes(b"damaged after checkpoint")

    resumed_calls = []
    restarted = make_service(tmp_path, generator(resumed_calls))
    monkeypatch.setattr(restarted, "launch", restarted.process)
    assert restarted.recover() == 1
    restored = restarted.get_job(job.job_id)
    assert restored.status == "complete"
    assert resumed_calls == (["First.", "Second."] if damage_chunk else ["Second."])
    assert (restarted.output_root / restored.result["filename"]).is_file()
    assert restarted.snapshot(restored)["stream"]["available"] == 2

    third = make_service(
        tmp_path, lambda *_: pytest.fail("A completed job was regenerated")
    )
    assert third.recover() == 0
    assert third.snapshot(third.get_job(job.job_id)) == restarted.snapshot(restored)


def test_cancel_requested_before_restart_is_not_resumed(tmp_path, monkeypatch):
    first = make_service(tmp_path, generator([]))
    job = make_job(tmp_path, first)
    first.cancel(job.job_id)
    restarted = make_service(tmp_path, generator([]))
    monkeypatch.setattr(
        restarted, "launch", lambda _: pytest.fail("Cancelled job resumed")
    )
    assert restarted.recover() == 0
    assert restarted.get_job(job.job_id).status == "cancelled"


def test_changed_model_settings_do_not_mix_cached_segments(tmp_path, monkeypatch):
    first = make_service(tmp_path, generator([], crash=True))
    job = make_job(tmp_path, first)
    with pytest.raises(SystemExit):
        first.process(job)
    restarted = make_service(tmp_path, generator([]))
    restarted.settings = {"temperature": 0.5}
    monkeypatch.setattr(
        restarted, "launch", lambda _: pytest.fail("Changed recipe resumed")
    )
    assert restarted.recover() == 0
    assert restarted.get_job(job.job_id).status == "error"


def test_failed_job_retains_playable_completed_prefix(tmp_path):
    calls = []

    def fail_second(*args):
        if args[2] == "Second.":
            raise RuntimeError("Model failed")
        return generator(calls)(*args)

    service = make_service(tmp_path, fail_second)
    job = make_job(tmp_path, service)
    service.process(job)
    restarted = make_service(tmp_path, fail_second)
    restored = restarted.get_job(job.job_id)
    assert restored.status == "error"
    assert restarted.snapshot(restored)["stream"]["available"] == 1
    assert (job.job_dir / "segment-00001.wav").is_file()
