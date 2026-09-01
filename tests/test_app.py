import io
import os
import wave
from datetime import datetime, timezone
from pathlib import Path

os.environ["TIMBRELOOM_PRELOAD"] = "0"

from fastapi.testclient import TestClient

import app
from timbreloom.providers import TTSResult
from timbreloom.segmentation import SEGMENT_ESTIMATED_TOKEN_LIMIT, segment_text


client = TestClient(app.app)


def test_home_renders_local_privacy_copy() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "参考录音仅在这台 Mac 上处理" in response.text
    assert "TEMPERATURE 1.0" in response.text
    assert "当前 Base 克隆模型没有隐藏的情绪标签" in response.text


def test_health_does_not_load_model() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["privacy"] == "localhost-only"
    assert payload["model"] == app.MODEL_ID
    assert payload["sampling_temperature"] == 1.0
    provider_ids = {provider["id"] for provider in payload["providers"]}
    assert provider_ids == {"local-qwen-tts", "local-whisper-asr", "gemini-text"}


def test_provider_response_never_exposes_gemini_key(monkeypatch) -> None:
    secret = "gemini-test-secret-that-must-not-leak"
    monkeypatch.setenv("GEMINI_API_KEY", secret)

    response = client.get("/api/providers")

    assert response.status_code == 200
    assert secret not in response.text
    assert "GEMINI_API_KEY" not in response.text


def test_gemini_requires_explicit_cloud_confirmation() -> None:
    response = client.post(
        f"/api/transcripts/{'a' * 32}/gemini",
        json={
            "segment_id": "seg-00001",
            "task": "punctuation",
            "confirm_cloud": False,
        },
    )
    assert response.status_code == 400
    assert "明确确认" in response.json()["detail"]


def test_generate_rejects_unsupported_file_before_model_load() -> None:
    response = client.post(
        "/api/generate",
        data={
            "reference_text": "hello",
            "target_text": "new words",
            "language": "english",
        },
        files={"reference_audio": ("voice.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 400
    assert "不支持该文件格式" in response.json()["detail"]


def test_text_validation_collapses_whitespace() -> None:
    assert app._normalize_text("  one   two  ", "text", 20) == "one two"


def test_segment_generation_uses_temperature_one(monkeypatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    class FakeProvider:
        def synthesize(self, request):
            received["request"] = request
            return TTSResult(
                duration_seconds=0.1,
                generation_seconds=0.01,
                peak_memory_gb=0.1,
                sample_rate=24_000,
            )

    monkeypatch.setattr(app, "_tts_provider", FakeProvider())

    app._generate_segment(
        reference_path=tmp_path / "reference.wav",
        reference_text="准确的参考文字。",
        target_text="测试新的表现力设置。",
        language="chinese",
        output_path=tmp_path / "output.wav",
    )

    request = received["request"]
    assert request.temperature == 1.0
    assert request.max_tokens == app.GENERATION_TOKEN_LIMIT


def test_long_text_segmentation_is_lossless_and_groups_sentences() -> None:
    sentences = [
        f"这是第{index}句话，用来确认分段不会漏字，而且不会把每句话单独生成。"
        for index in range(1, 31)
    ]
    source = "".join(sentences)
    segments = segment_text(source)

    assert "".join(segment.text for segment in segments) == source
    assert 1 < len(segments) < len(sentences)
    assert all(
        segment.estimated_audio_tokens <= SEGMENT_ESTIMATED_TOKEN_LIMIT
        for segment in segments
    )
    assert all(sentence in "".join(segment.text for segment in segments) for sentence in sentences)


def test_unpunctuated_text_is_split_without_losing_characters() -> None:
    source = "连续长文本" * 400
    segments = segment_text(source)
    assert len(segments) > 1
    assert "".join(segment.text for segment in segments) == source


def _wav_bytes(duration_seconds: float = 3.0, sample_rate: int = 24_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(sample_rate)
        audio_file.writeframes(b"\x01\x00" * round(duration_seconds * sample_rate))
    return buffer.getvalue()


def _write_wav(path: Path, duration_seconds: float = 0.25) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(24_000)
        audio_file.writeframes(b"\x01\x00" * round(duration_seconds * 24_000))


def test_voice_profile_is_saved_and_listed(monkeypatch, tmp_path: Path) -> None:
    voice_dir = tmp_path / "voices"
    voice_dir.mkdir()
    monkeypatch.setattr(app, "VOICE_DIR", voice_dir)

    response = client.post(
        "/api/voices",
        data={"name": "测试音色", "reference_text": "这是一段准确的参考文字。"},
        files={"reference_audio": ("voice.wav", _wav_bytes(), "audio/wav")},
    )

    assert response.status_code == 201
    voice = response.json()["voice"]
    assert voice["name"] == "测试音色"
    assert (voice_dir / voice["id"] / "reference.wav").is_file()
    listed = client.get("/api/voices").json()["voices"]
    assert [item["id"] for item in listed] == [voice["id"]]


def test_background_job_generates_every_segment_and_stitches(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "outputs"
    job_dir = tmp_path / "job"
    output_dir.mkdir()
    job_dir.mkdir()
    reference_path = tmp_path / "reference.wav"
    _write_wav(reference_path, 3.0)

    source = "".join(
        f"这是第{index}句话，用来测试后台生成会按顺序处理全部分段。"
        for index in range(1, 31)
    )
    segments = segment_text(source)

    def fake_generate_segment(
        reference_path: Path,
        reference_text: str,
        target_text: str,
        language: str,
        output_path: Path,
    ) -> dict[str, float]:
        assert reference_path.is_file()
        assert reference_text
        assert target_text
        assert language == "chinese"
        _write_wav(output_path)
        return {
            "duration_seconds": 30.0,
            "generation_seconds": 0.01,
            "peak_memory_gb": 1.0,
        }

    monkeypatch.setattr(app, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(app, "_generate_segment", fake_generate_segment)
    job = app.GenerationJob(
        job_id="a" * 32,
        voice_id=None,
        voice_name="测试音色",
        reference_source=reference_path,
        reference_is_normalized=True,
        reference_text="准确参考文字",
        reference_duration_seconds=3.0,
        language="chinese",
        segments=segments,
        job_dir=job_dir,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    app._process_job(job)

    assert job.status == "complete"
    assert job.segments_completed == len(segments)
    assert job.result is not None
    assert job.result["segment_count"] == len(segments)
    assert (output_dir / job.result["filename"]).is_file()
    assert not job_dir.exists()


def test_background_job_stops_instead_of_skipping_suspicious_audio(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "outputs"
    job_dir = tmp_path / "job"
    output_dir.mkdir()
    job_dir.mkdir()
    reference_path = tmp_path / "reference.wav"
    _write_wav(reference_path, 3.0)
    segments = segment_text("这段内容需要足够长来触发漏读防护。" * 30)
    attempts = 0

    def suspicious_generate(
        reference_path: Path,
        reference_text: str,
        target_text: str,
        language: str,
        output_path: Path,
    ) -> dict[str, float]:
        nonlocal attempts
        attempts += 1
        _write_wav(output_path, 0.1)
        return {
            "duration_seconds": 0.1,
            "generation_seconds": 0.01,
            "peak_memory_gb": 1.0,
        }

    monkeypatch.setattr(app, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(app, "_generate_segment", suspicious_generate)
    job = app.GenerationJob(
        job_id="b" * 32,
        voice_id=None,
        voice_name="测试音色",
        reference_source=reference_path,
        reference_is_normalized=True,
        reference_text="准确参考文字",
        reference_duration_seconds=3.0,
        language="chinese",
        segments=segments,
        job_dir=job_dir,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    app._process_job(job)

    assert attempts == app.MAX_GENERATION_ATTEMPTS
    assert job.status == "error"
    assert job.segments_completed == 0
    assert "漏读" in (job.error or "")
    assert not list(output_dir.glob("*.wav"))
