from pathlib import Path

from timbreloom.asr_service import ASRService
from timbreloom.media import MediaInfo
from timbreloom.providers import ProviderDescriptor


class FakeASRProvider:
    model_id = "fake-whisper"

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id="fake-asr",
            name="Fake ASR",
            provider_type="asr",
            local=True,
            capabilities=("transcription", "segment-timestamps"),
            configured=True,
            ready=True,
        )

    def transcribe(self, request, cancel_event=None):
        request.raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        request.raw_output_path.write_text("{}", encoding="utf-8")
        return {
            "text": "这是本地转录。",
            "language": "zh",
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "text": "这是本地转录。",
                    "words": [],
                }
            ],
        }


def test_asr_service_preserves_raw_and_canonical_results(
    monkeypatch,
    tmp_path: Path,
) -> None:
    transcript_root = tmp_path / "transcripts"
    transcript_dir = transcript_root / ("b" * 32)
    transcript_dir.mkdir(parents=True)
    source_path = transcript_dir / "source.wav"
    source_path.write_bytes(b"media")

    monkeypatch.setattr(
        "timbreloom.asr_service.probe_media",
        lambda _: MediaInfo(3.0, True, False, "wav"),
    )
    monkeypatch.setattr(
        "timbreloom.asr_service.prepare_asr_audio",
        lambda _source, destination: destination.write_bytes(b"wav"),
    )

    service = ASRService(transcript_root, FakeASRProvider())
    job = service.create_job(
        job_id="b" * 32,
        transcript_dir=transcript_dir,
        source_path=source_path,
        source_filename="source.wav",
        source_bytes=5,
        requested_language="auto",
        initial_prompt="",
    )
    service._process_job(job)

    assert job.status == "complete"
    assert (transcript_dir / "raw" / "whisper.json").is_file()
    transcript = service.get_transcript(job.job_id)
    assert transcript["segments"][0]["start"] == 0.0
    assert transcript["segments"][0]["end"] == 3.0
    assert transcript["text"] == "这是本地转录。"
    assert (transcript_dir / "qa.json").is_file()

    restarted = ASRService(transcript_root, FakeASRProvider())
    restored = restarted.get_job(job.job_id)
    assert restarted.snapshot(restored) == service.snapshot(job)


def test_interrupted_asr_reuses_audio_and_resumes_after_restart(tmp_path, monkeypatch):
    import pytest
    preparations = []
    monkeypatch.setattr("timbreloom.asr_service.probe_media", lambda _: MediaInfo(3.0, True, False, "wav"))
    def prepare(_source, destination):
        preparations.append(destination)
        destination.write_bytes(b"prepared audio")
    monkeypatch.setattr("timbreloom.asr_service.prepare_asr_audio", prepare)

    class InterruptedProvider(FakeASRProvider):
        def transcribe(self, request, cancel_event=None):
            raise SystemExit("simulated process termination")

    root = tmp_path / "transcripts"
    directory = root / ("c" * 32)
    directory.mkdir(parents=True)
    source = directory / "source.wav"
    source.write_bytes(b"source")
    first = ASRService(root, InterruptedProvider())
    job = first.create_job(job_id=directory.name, transcript_dir=directory,
                           source_path=source, source_filename="source.wav", source_bytes=6,
                           requested_language="auto", initial_prompt="")
    with pytest.raises(SystemExit):
        first._process_job(job)
    restarted = ASRService(root, FakeASRProvider())
    monkeypatch.setattr(restarted, "launch", restarted._process_job)
    assert restarted.recover() == 1
    assert len(preparations) == 1
    restored = restarted.get_job(job.job_id)
    assert restored.status == "complete"
    assert restarted.get_transcript(job.job_id)["text"] == "这是本地转录。"
    assert restarted.recover() == 0


def test_asr_restart_during_save_reuses_raw_result(tmp_path, monkeypatch):
    import pytest
    import timbreloom.asr_service as module
    root = tmp_path / "transcripts"
    directory = root / ("d" * 32)
    directory.mkdir(parents=True)
    source = directory / "source.wav"
    source.write_bytes(b"source")
    monkeypatch.setattr(module, "probe_media", lambda _: MediaInfo(3.0, True, False, "wav"))
    monkeypatch.setattr(module, "prepare_asr_audio", lambda _, dest: dest.write_bytes(b"audio"))
    original_save = module.save_transcript
    def interrupted_save(*_):
        raise SystemExit("interrupted after transcription")
    monkeypatch.setattr(module, "save_transcript", interrupted_save)
    first = ASRService(root, FakeASRProvider())
    job = first.create_job(job_id=directory.name, transcript_dir=directory, source_path=source,
                           source_filename="source.wav", source_bytes=6,
                           requested_language="auto", initial_prompt="")
    with pytest.raises(SystemExit):
        first._process_job(job)
    monkeypatch.setattr(module, "save_transcript", original_save)
    provider = FakeASRProvider()
    monkeypatch.setattr(provider, "transcribe", lambda *_args, **_kwargs: pytest.fail("Repeated recognition"))
    restarted = ASRService(root, provider)
    monkeypatch.setattr(restarted, "launch", restarted._process_job)
    assert restarted.recover() == 1
    assert restarted.get_job(job.job_id).status == "complete"


def test_asr_restart_respects_persisted_cancel(tmp_path, monkeypatch):
    import pytest
    root = tmp_path / "transcripts"
    directory = root / ("e" * 32)
    directory.mkdir(parents=True)
    source = directory / "source.wav"
    source.write_bytes(b"source")
    first = ASRService(root, FakeASRProvider())
    job = first.create_job(job_id=directory.name, transcript_dir=directory, source_path=source,
                           source_filename="source.wav", source_bytes=6,
                           requested_language="auto", initial_prompt="")
    first.cancel(job.job_id)
    restarted = ASRService(root, FakeASRProvider())
    monkeypatch.setattr(restarted, "launch", lambda _: pytest.fail("Cancelled ASR resumed"))
    assert restarted.recover() == 0
    assert restarted.get_job(job.job_id).status == "cancelled"
