import json
import shutil
import subprocess
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from timbreloom.dub_projects import (
    DubProjectStore,
    DubRenderService,
    content_fingerprint,
    mix_timeline_wav,
    render_project_srt,
)
from timbreloom.media import mux_dubbed_video, probe_media


VOICE_ID = "b" * 32


def _write_wav(
    path: Path,
    *,
    duration: float = 0.2,
    value: int = 1_000,
    sample_rate: int = 24_000,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.full(round(duration * sample_rate), value, dtype="<i2")
    with wave.open(str(path), "wb") as audio_file:
        audio_file.setnchannels(1)
        audio_file.setsampwidth(2)
        audio_file.setframerate(sample_rate)
        audio_file.writeframes(samples.tobytes())


def _transcript() -> dict:
    return {
        "id": "a" * 32,
        "title": "访谈测试",
        "source_filename": "source.wav",
        "duration_seconds": 3.0,
        "language": "zh",
        "segments": [
            {"id": "seg-00001", "start": 0.25, "end": 1.0, "text": "第一句。"},
            {"id": "seg-00002", "start": 1.4, "end": 2.3, "text": "第二句。"},
        ],
    }


def _project(store: DubProjectStore, tmp_path: Path) -> dict:
    source = tmp_path / "transcript-audio.wav"
    _write_wav(source, duration=3.0)
    return store.create(
        transcript=_transcript(),
        source_audio=source,
        target_language="chinese",
        default_voice_id=VOICE_ID,
    )


def _wait_for_job(service: DubRenderService, project_id: str, job_id: str) -> dict:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        job = service.get_job(project_id, job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError("配音测试任务没有按时结束。")


def test_project_preserves_source_text_and_only_invalidates_edited_segment(
    tmp_path: Path,
) -> None:
    store = DubProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    original = project["segments"][1]["source_text"]
    project["segments"][0]["render"].update(
        {"status": "ready", "filename": "seg-1.wav", "fingerprint": "one"}
    )
    project["segments"][1]["render"].update(
        {"status": "ready", "filename": "seg-2.wav", "fingerprint": "two"}
    )
    store.save(project)

    updated = store.update(
        project["id"],
        segment_updates=[{"id": "seg-00002", "active_text": "第二句，改过。"}],
    )

    assert updated["segments"][1]["source_text"] == original
    assert updated["segments"][1]["active_text"] == "第二句，改过。"
    assert updated["segments"][0]["render"]["status"] == "ready"
    assert updated["segments"][1]["render"]["status"] == "stale"
    assert store.source_audio(project["id"]).is_file()


def test_video_source_is_project_owned_and_schema_one_is_upgraded(tmp_path: Path) -> None:
    store = DubProjectStore(tmp_path / "projects")
    source_audio = tmp_path / "transcript-audio.wav"
    source_video = tmp_path / "source.mov"
    _write_wav(source_audio, duration=3.0)
    source_video.write_bytes(b"synthetic-video-container")
    project = store.create(
        transcript=_transcript(),
        source_audio=source_audio,
        source_media=source_video,
        default_voice_id=VOICE_ID,
    )

    assert project["source_has_video"] is True
    assert store.source_media(project["id"]).read_bytes() == source_video.read_bytes()

    project_path = store.project_dir(project["id"]) / "project.json"
    legacy = json.loads(project_path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 1
    legacy.pop("source_media_filename")
    legacy.pop("source_has_video")
    project_path.write_text(json.dumps(legacy), encoding="utf-8")

    upgraded = store.load(project["id"])
    assert upgraded["schema_version"] == 2
    assert upgraded["source_has_video"] is False


def test_fingerprint_changes_for_text_voice_language_and_model(tmp_path: Path) -> None:
    store = DubProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    segment = project["segments"][0]
    voice = {"created_at": "now", "reference_text": "参考文字"}
    settings = {"temperature": 1.0, "max_tokens": 1024}
    baseline = content_fingerprint(segment, project, voice, "model-a", settings)

    changed_text = dict(segment, active_text="另一句话。")
    changed_language = dict(project, target_language="english")

    assert content_fingerprint(changed_text, project, voice, "model-a", settings) != baseline
    assert content_fingerprint(segment, changed_language, voice, "model-a", settings) != baseline
    assert content_fingerprint(segment, project, voice, "model-b", settings) != baseline


def test_render_job_uses_cache_and_rerenders_only_changed_segment(tmp_path: Path) -> None:
    store = DubProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    reference = tmp_path / "reference.wav"
    _write_wav(reference, duration=3.0)
    calls: list[str] = []

    def load_voice(voice_id: str) -> dict:
        assert voice_id == VOICE_ID
        return {
            "id": voice_id,
            "created_at": "voice-created",
            "reference_text": "准确参考文字。",
            "audio_path": reference,
        }

    def generate(
        reference_path: Path,
        reference_text: str,
        target_text: str,
        language: str,
        output_path: Path,
    ) -> dict[str, float]:
        calls.append(target_text)
        assert reference_path == reference
        assert reference_text == "准确参考文字。"
        assert language == "chinese"
        _write_wav(output_path, duration=0.25)
        return {
            "duration_seconds": 0.25,
            "generation_seconds": 0.01,
            "peak_memory_gb": 0.1,
        }

    service = DubRenderService(
        store,
        load_voice=load_voice,
        generate_segment=generate,
        model_id="test-model",
        settings={"temperature": 1.0, "max_tokens": 1024},
    )

    first = service.create_job(project["id"], mode="all")
    first_done = _wait_for_job(service, project["id"], first["job_id"])
    assert first_done["status"] == "complete"
    assert first_done["generated"] == 2
    assert first_done["cached"] == 0

    store.update(
        project["id"],
        segment_updates=[{"id": "seg-00002", "active_text": "第二句已经修改。"}],
    )
    second = service.create_job(project["id"], mode="all")
    second_done = _wait_for_job(service, project["id"], second["job_id"])

    assert second_done["status"] == "complete"
    assert second_done["generated"] == 1
    assert second_done["cached"] == 1
    assert calls == ["第一句。", "第二句。", "第二句已经修改。"]


def test_failed_segment_can_be_retried_independently(tmp_path: Path) -> None:
    store = DubProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    reference = tmp_path / "reference.wav"
    _write_wav(reference, duration=3.0)
    should_fail = {"value": True}

    def load_voice(_: str) -> dict:
        return {
            "created_at": "voice-created",
            "reference_text": "参考文字。",
            "audio_path": reference,
        }

    def generate(
        _reference_path: Path,
        _reference_text: str,
        target_text: str,
        _language: str,
        output_path: Path,
    ) -> dict[str, float]:
        if target_text == "第二句。" and should_fail["value"]:
            raise RuntimeError("synthetic failure")
        _write_wav(output_path)
        return {
            "duration_seconds": 0.2,
            "generation_seconds": 0.01,
            "peak_memory_gb": 0.1,
        }

    service = DubRenderService(
        store,
        load_voice=load_voice,
        generate_segment=generate,
        model_id="test-model",
        settings={"temperature": 1.0},
    )
    first = service.create_job(project["id"], mode="all")
    first_done = _wait_for_job(service, project["id"], first["job_id"])
    assert first_done["status"] == "partial"
    assert first_done["failed"] == 1

    should_fail["value"] = False
    retry = service.create_job(project["id"], mode="failed")
    retry_done = _wait_for_job(service, project["id"], retry["job_id"])
    assert retry_done["status"] == "complete"
    assert retry_done["total"] == 1
    assert retry_done["generated"] == 1


def test_queued_job_recovers_after_service_restart(tmp_path: Path) -> None:
    store = DubProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    reference = tmp_path / "reference.wav"
    _write_wav(reference, duration=3.0)

    def load_voice(_: str) -> dict:
        return {
            "created_at": "voice-created",
            "reference_text": "参考文字。",
            "audio_path": reference,
        }

    def generate(
        _reference_path: Path,
        _reference_text: str,
        _target_text: str,
        _language: str,
        output_path: Path,
    ) -> dict[str, float]:
        _write_wav(output_path)
        return {
            "duration_seconds": 0.2,
            "generation_seconds": 0.01,
            "peak_memory_gb": 0.1,
        }

    stopped_service = DubRenderService(
        store,
        load_voice=load_voice,
        generate_segment=generate,
        model_id="test-model",
        settings={"temperature": 1.0},
    )
    stopped_service.launch = lambda _project_id, _job_id: None
    queued = stopped_service.create_job(project["id"], mode="all")
    assert store.load_job(project["id"], queued["job_id"])["status"] == "queued"

    restarted_service = DubRenderService(
        store,
        load_voice=load_voice,
        generate_segment=generate,
        model_id="test-model",
        settings={"temperature": 1.0},
    )
    assert restarted_service.recover() == 1
    recovered = _wait_for_job(
        restarted_service,
        project["id"],
        queued["job_id"],
    )
    assert recovered["status"] == "complete"
    assert recovered["processed"] == 2
    assert recovered["generated"] == 2


def test_timeline_export_uses_original_onsets_and_active_text(tmp_path: Path) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    output = tmp_path / "timeline.wav"
    _write_wav(first, duration=0.2, value=1_000)
    _write_wav(second, duration=0.2, value=2_000)

    duration = mix_timeline_wav(
        [
            {"path": first, "start": 0.25, "gain": 1.0},
            {"path": second, "start": 0.75, "gain": 0.5},
        ],
        output,
        project_duration_seconds=1.2,
    )
    with wave.open(str(output), "rb") as audio_file:
        samples = np.frombuffer(audio_file.readframes(audio_file.getnframes()), dtype="<i2")

    assert duration == 1.2
    assert samples[round(0.1 * 24_000)] == 0
    assert samples[round(0.3 * 24_000)] == 1_000
    assert samples[round(0.8 * 24_000)] == 1_000

    project = {
        "segments": [
            {"start": 0.25, "end": 0.5, "active_text": "修改后的第一句。"},
            {"start": 0.75, "end": 1.0, "active_text": "第二句。"},
        ]
    }
    srt = render_project_srt(project)
    assert "00:00:00,250 --> 00:00:00,500" in srt
    assert "修改后的第一句。" in srt


def test_video_project_export_creates_mp4_record(tmp_path: Path) -> None:
    store = DubProjectStore(tmp_path / "projects")
    source_audio = tmp_path / "transcript-audio.wav"
    source_video = tmp_path / "source.mp4"
    reference = tmp_path / "reference.wav"
    _write_wav(source_audio, duration=3.0)
    _write_wav(reference, duration=3.0)
    source_video.write_bytes(b"synthetic-video-container")
    project = store.create(
        transcript=_transcript(),
        source_audio=source_audio,
        source_media=source_video,
        target_language="chinese",
        default_voice_id=VOICE_ID,
    )

    def load_voice(_: str) -> dict:
        return {
            "id": VOICE_ID,
            "created_at": "voice-created",
            "reference_text": "参考文字。",
            "audio_path": reference,
        }

    def generate(
        _reference_path: Path,
        _reference_text: str,
        _target_text: str,
        _language: str,
        output_path: Path,
    ) -> dict[str, float]:
        _write_wav(output_path, duration=0.3)
        return {
            "duration_seconds": 0.3,
            "generation_seconds": 0.01,
            "peak_memory_gb": 0.1,
        }

    def fake_mux(
        input_video: Path,
        dubbed_audio: Path,
        destination: Path,
        *,
        original_audio_gain: float,
    ) -> dict[str, object]:
        assert input_video.read_bytes() == source_video.read_bytes()
        assert dubbed_audio.is_file()
        assert original_audio_gain == 0.35
        destination.write_bytes(b"muxed-mp4")
        return {"video_codec_mode": "copy", "size_bytes": destination.stat().st_size}

    service = DubRenderService(
        store,
        load_voice=load_voice,
        generate_segment=generate,
        model_id="test-model",
        settings={"temperature": 1.0},
        mux_video=fake_mux,
    )
    job = service.create_job(project["id"], mode="all")
    assert _wait_for_job(service, project["id"], job["job_id"])["status"] == "complete"

    exported = service.export(project["id"], original_audio_gain=0.35)

    assert exported["mp4_filename"].endswith(".mp4")
    assert exported["original_audio_gain"] == 0.35
    assert exported["video_codec_mode"] == "copy"
    assert (store.project_dir(project["id"]) / "exports" / exported["mp4_filename"]).is_file()


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="FFmpeg is required for video export",
)
def test_real_video_mux_preserves_video_and_audio_tracks(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    dubbed = tmp_path / "dubbed.wav"
    output = tmp_path / "dubbed.mp4"
    _write_wav(dubbed, duration=1.2, value=2_000)
    subprocess.run(
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:r=24:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
        timeout=30,
    )

    metrics = mux_dubbed_video(
        source,
        dubbed,
        output,
        original_audio_gain=0.15,
    )
    info = probe_media(output)

    assert info.has_video is True
    assert info.has_audio is True
    assert info.duration_seconds >= 1.15
    assert metrics["original_audio_gain"] == 0.15
    assert metrics["video_codec_mode"] in {"copy", "h264"}
