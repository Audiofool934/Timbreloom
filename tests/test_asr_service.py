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
