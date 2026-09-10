import io
import os
import wave
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ["TIMBRELOOM_PRELOAD"] = "0"

from fastapi.testclient import TestClient

import app
from timbreloom.dub_projects import DubProjectStore, DubRenderService
from timbreloom.dubbing_api import _public_dub_job
from timbreloom.providers import TTSResult
from timbreloom.segmentation import SEGMENT_ESTIMATED_TOKEN_LIMIT, segment_text


client = TestClient(app.app, base_url="http://127.0.0.1")


def test_local_api_rejects_other_websites_and_rebound_hostnames() -> None:
    assert client.get("/api/voices", headers={"Host": "attacker.example"}).status_code == 403
    assert client.post("/api/voices", headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.get("/api/voices", headers={"Origin": "null"}).status_code == 403
    assert client.get("/api/voices", headers={"Origin": "http://127.0.0.1:9999"}).status_code == 403
    response = client.get("/api/runtime", headers={"Origin": "http://127.0.0.1"})
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"


def test_home_renders_local_privacy_copy() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "参考录音仅在这台 Mac 上处理" in response.text
    assert "TEMPERATURE 1.0" in response.text
    assert "当前 Base 克隆模型没有隐藏的情绪标签" in response.text
    assert response.text.count('class="recorder-panel"') == 3
    assert response.text.count("开始录音") == 3
    assert response.text.count('<section id="cloneStreamCard"') == 1
    assert response.text.count('class="stream-card"') == 3
    assert response.text.count('class="stream-card compact-stream-card"') == 1
    assert "边生成边听" in response.text


def test_transport_stream_media_suffixes_are_supported() -> None:
    assert app._validate_asr_suffix("audiobook.ts") == ".ts"
    assert app._validate_asr_suffix("chapter.m2ts") == ".m2ts"
    assert app._validate_asr_suffix("recording.MTS") == ".mts"


def test_health_does_not_load_model() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["privacy"] == "localhost-only"
    assert payload["version"] == "1.1.0"
    assert payload["model"] == app.MODEL_ID
    assert payload["sampling_temperature"] == 1.0
    provider_ids = {provider["id"] for provider in payload["providers"]}
    assert provider_ids == {
        "local-qwen-tts",
        "local-seed-vc",
        "local-whisper-asr",
        "gemini-text",
    }


def test_voice_conversion_requires_rights_confirmation() -> None:
    response = client.post(
        "/api/voice-conversions",
        data={"voice_id": "a" * 32, "preset": "balanced", "confirm_rights": "false"},
        files={"media": ("source.wav", _wav_bytes(), "audio/wav")},
    )
    assert response.status_code == 400
    assert "有权使用" in response.json()["detail"]


def test_voice_conversion_presets_expose_balanced_default() -> None:
    response = client.get("/api/voice-conversions/presets")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default"] == "balanced"
    assert {preset["id"] for preset in payload["presets"]} == {
        "fast",
        "balanced",
        "quality",
    }


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

    service = app.TTSService(
        job_dir.parent, output_dir, generate_segment=app._generate_segment,
        normalize_audio=app._normalize_audio, model_id=app.MODEL_ID,
        settings={"temperature": 1.0}, max_attempts=app.MAX_GENERATION_ATTEMPTS,
    )
    service.add(job)
    service.process(job)

    assert job.status == "complete"
    assert job.segments_completed == len(segments)
    assert job.result is not None
    assert job.result["segment_count"] == len(segments)
    assert (output_dir / job.result["filename"]).is_file()
    assert job_dir.is_dir()
    assert len(list(job_dir.glob("segment-*.wav"))) == len(segments)
    stream = service.snapshot(job)["stream"]
    assert stream["available"] == len(segments)
    assert stream["complete"] is True
    assert stream["chunks"][0]["audio_url"].endswith("/segments/1/audio")
    monkeypatch.setattr(app, "_tts_jobs", service)
    response = client.get(f"/api/jobs/{job.job_id}/segments/1/audio")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"


def test_asr_job_exposes_prepared_audio_while_transcribing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    transcript_dir = tmp_path / "transcript"
    transcript_dir.mkdir()
    _write_wav(transcript_dir / "audio.wav", 7.0)
    job = SimpleNamespace(
        job_id="f" * 32,
        transcript_dir=transcript_dir,
        audio_ready=True,
    )

    class FakeASRService:
        @staticmethod
        def snapshot(current_job) -> dict:
            return {
                "job_id": job.job_id,
                "status": "running",
                "duration_seconds": 7.0,
                "audio_ready": current_job.audio_ready,
            }

        @staticmethod
        def get_job(job_id: str):
            if job_id != job.job_id:
                raise FileNotFoundError
            return job

    monkeypatch.setattr(app, "_asr_service", FakeASRService())

    payload = app._public_asr_job(job)
    assert payload["stream"]["kind"] == "source"
    assert payload["stream"]["available"] == 1
    assert payload["stream"]["chunks"][0]["audio_url"].endswith("/audio")
    assert client.get(f"/api/asr/jobs/{job.job_id}/audio").status_code == 200
    job.audio_ready = False
    assert app._public_asr_job(job)["stream"]["available"] == 0
    assert client.get(f"/api/asr/jobs/{job.job_id}/audio").status_code == 404


def test_dub_job_stream_contains_only_processed_ready_segments(
    monkeypatch,
    tmp_path: Path,
) -> None:
    project_id = "d" * 32
    ready_path = tmp_path / "ready.wav"
    _write_wav(ready_path, 1.0)
    project = {
        "id": project_id,
        "segments": [
            {
                "id": "seg-1",
                "active_text": "第一段已经完成。",
                "render": {
                    "status": "ready",
                    "filename": ready_path.name,
                    "duration_seconds": 1.0,
                },
            },
            {
                "id": "seg-2",
                "active_text": "第二段还在生成。",
                "render": {"status": "rendering", "filename": ""},
            },
        ],
    }

    class FakeStore:
        @staticmethod
        def load(_project_id: str) -> dict:
            return project

        @staticmethod
        def render_path(_project_id: str, filename: str) -> Path:
            return tmp_path / filename

    monkeypatch.setattr(app, "_dub_store", FakeStore())
    payload = _public_dub_job(
        app._dubbing_context(),
        project_id,
        {
            "kind": "render",
            "job_id": "e" * 32,
            "project_id": project_id,
            "segment_ids": ["seg-1", "seg-2"],
            "processed": 1,
            "total": 2,
            "status": "running",
        },
    )

    assert payload["stream"]["available"] == 1
    assert payload["stream"]["total"] == 2
    assert payload["stream"]["chunks"][0]["label"] == "第一段已经完成。"


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

    service = app.TTSService(
        job_dir.parent, output_dir, generate_segment=app._generate_segment,
        normalize_audio=app._normalize_audio, model_id=app.MODEL_ID,
        settings={"temperature": 1.0}, max_attempts=app.MAX_GENERATION_ATTEMPTS,
    )
    service.add(job)
    service.process(job)

    assert attempts == app.MAX_GENERATION_ATTEMPTS
    assert job.status == "error"
    assert job.segments_completed == 0
    assert "漏读" in (job.error or "")
    assert not list(output_dir.glob("*.wav"))


def test_dub_project_api_creates_and_updates_persistent_project(
    monkeypatch,
    tmp_path: Path,
) -> None:
    transcript_root = tmp_path / "transcripts"
    transcript_dir = transcript_root / ("a" * 32)
    transcript_dir.mkdir(parents=True)
    _write_wav(transcript_dir / "audio.wav", 3.0)
    _write_wav(transcript_dir / "source.wav", 3.0)
    transcript = {
        "id": "a" * 32,
        "title": "API 配音测试",
        "source_filename": "source.wav",
        "duration_seconds": 3.0,
        "language": "zh",
        "segments": [
            {"id": "seg-00001", "start": 0.0, "end": 1.2, "text": "原始第一句。"},
            {"id": "seg-00002", "start": 1.4, "end": 2.7, "text": "原始第二句。"},
        ],
    }

    class FakeASRService:
        def get_transcript(self, transcript_id: str) -> dict:
            if transcript_id != transcript["id"]:
                raise FileNotFoundError("转录不存在。")
            return transcript

        def transcript_dir(self, transcript_id: str) -> Path:
            if transcript_id != transcript["id"]:
                raise FileNotFoundError("转录不存在。")
            return transcript_dir

        def source_media(self, transcript_id: str) -> Path:
            if transcript_id != transcript["id"]:
                raise FileNotFoundError("转录不存在。")
            return transcript_dir / "source.wav"

    reference = tmp_path / "reference.wav"
    _write_wav(reference, 3.0)
    voice_id = "b" * 32

    def fake_voice(requested_voice_id: str) -> dict:
        if requested_voice_id != voice_id:
            raise FileNotFoundError("音色不存在。")
        return {
            "id": voice_id,
            "created_at": "voice-created",
            "reference_text": "准确参考文字。",
            "audio_path": reference,
        }

    store = DubProjectStore(tmp_path / "projects")
    render_service = DubRenderService(
        store,
        load_voice=fake_voice,
        generate_segment=lambda *_args: {},
        model_id="test-model",
        settings={"temperature": 1.0},
    )
    monkeypatch.setattr(app, "_asr_service", FakeASRService())
    monkeypatch.setattr(app, "_load_voice_profile", fake_voice)
    monkeypatch.setattr(app, "_dub_store", store)
    monkeypatch.setattr(app, "_dub_render_service", render_service)

    created_response = client.post(
        "/api/dub/projects",
        json={
            "transcript_id": transcript["id"],
            "title": "我的配音项目",
            "target_language": "chinese",
            "default_voice_id": voice_id,
        },
    )
    assert created_response.status_code == 201
    project = created_response.json()["project"]
    project_id = project["id"]
    assert project["segments"][0]["source_text"] == "原始第一句。"
    assert project["source_audio_url"].endswith("/audio")

    updated_response = client.patch(
        f"/api/dub/projects/{project_id}",
        json={
            "segments": [
                {"id": "seg-00001", "active_text": "用于配音的新文字。"}
            ]
        },
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()["project"]
    assert updated["segments"][0]["source_text"] == "原始第一句。"
    assert updated["segments"][0]["active_text"] == "用于配音的新文字。"
    assert client.get(f"/api/dub/projects/{project_id}/audio").status_code == 200

    gemini_response = client.post(
        f"/api/dub/projects/{project_id}/gemini",
        json={
            "segment_id": "seg-00001",
            "task": "translate",
            "target_language": "English",
            "confirm_cloud": False,
        },
    )
    assert gemini_response.status_code == 400
    assert "明确确认" in gemini_response.json()["detail"]

    class FakeGeminiProvider:
        configured = True

        def transform(self, text: str, task: str, target_language: str = "") -> dict:
            assert task == "translate"
            assert target_language == "English"
            return {"text": f"translated:{text}"}

    monkeypatch.setattr(app, "_gemini_provider", FakeGeminiProvider())
    batch_response = client.post(
        f"/api/dub/projects/{project_id}/gemini-batch",
        json={
            "segment_ids": ["seg-00001", "seg-00002"],
            "task": "translate",
            "target_language": "English",
            "confirm_cloud": True,
        },
    )
    assert batch_response.status_code == 200
    batch = batch_response.json()
    assert [item["segment_id"] for item in batch["results"]] == ["seg-00001", "seg-00002"]
    assert all(item["text"].startswith("translated:") for item in batch["results"])

    waveform_response = client.get(f"/api/dub/projects/{project_id}/waveform?points=240")
    assert waveform_response.status_code == 200
    assert waveform_response.json()["peaks"]

    bundle_response = client.get(f"/api/dub/projects/{project_id}/bundle")
    assert bundle_response.status_code == 200
    imported_response = client.post(
        "/api/dub/projects/import",
        files={
            "bundle": (
                "project.timbreloom",
                bundle_response.content,
                "application/zip",
            )
        },
    )
    assert imported_response.status_code == 201
    assert imported_response.json()["project"]["id"] != project_id
