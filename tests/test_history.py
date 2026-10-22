import json
import shutil
import threading
import wave
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app
from timbreloom.segmentation import segment_text
from timbreloom.tts_service import GenerationJob, TTSService
from timbreloom.voice_conversion import VoiceConversionService


@pytest.fixture
def history(tmp_path, monkeypatch):
    reference = tmp_path / "saved-voice.wav"
    with wave.open(str(reference), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\0\0" * 48000)

    def generate(_reference, _ref_text, _text, _language, output):
        shutil.copyfile(reference, output)
        return {"duration_seconds": 2, "peak_memory_gb": 0, "generation_seconds": .1}

    def normalize(source, output):
        shutil.copyfile(source, output)
        return 2

    tts = TTSService(tmp_path / "jobs", tmp_path / "outputs", generate_segment=generate,
                     normalize_audio=normalize, model_id="test", settings={})
    directory = tts.root / ("a" * 32)
    directory.mkdir()
    text = "First paragraph.\n\nSecond paragraph, with spaces."
    clone = GenerationJob(job_id=directory.name, voice_id="b" * 32, voice_name="Saved voice",
                          reference_source=reference, reference_is_normalized=True,
                          reference_text="Reference words", reference_duration_seconds=2,
                          language="english", segments=segment_text(text), job_dir=directory,
                          created_at=datetime.now(timezone.utc).isoformat())
    tts.add(clone)
    tts.process(clone)
    vc = VoiceConversionService(tmp_path / "conversions", None, lambda _: {"audio_path": reference})
    directory = vc.conversion_root / ("c" * 32)
    directory.mkdir()
    shutil.copyfile(reference, directory / "source.wav")
    shutil.copyfile(reference, directory / "converted.wav")
    conversion = vc.create_job(job_id=directory.name, source_path=directory / "source.wav",
                               source_filename="Original.wav", source_bytes=reference.stat().st_size,
                               voice_id="b" * 32, voice_name="Saved voice", preset="balanced")
    vc._update(conversion, status="complete", phase="complete")
    monkeypatch.setattr(app, "_tts_jobs", tts)
    monkeypatch.setattr(app, "_vc_service", vc)
    monkeypatch.setattr(app, "JOB_DIR", tts.root)
    return TestClient(app.app, base_url="http://127.0.0.1"), tts, clone, vc, conversion, reference


def test_clone_history_restores_exact_script_and_owned_reference(history):
    client, service, job, _, _, reference = history
    original = "".join(segment.text for segment in job.segments)
    reference.unlink()  # The job remains usable when its saved voice disappears.
    listing = client.get("/api/jobs").json()["jobs"]
    assert [item["job_id"] for item in listing] == [job.job_id]
    assert "target_text" not in listing[0]
    saved = client.get(f"/api/jobs/{job.job_id}").json()
    assert saved["target_text"] == original
    assert saved["language"] == "english"
    assert saved["reference_text"] == "Reference words"
    response = client.get(saved["reference_url"])
    assert response.status_code == 200
    assert response.content == job.reference_source.read_bytes()


@pytest.mark.parametrize("kind", ["clone", "conversion"])
def test_rename_survives_restart_and_accepts_legacy_history(history, kind):
    client, tts, clone, vc, conversion, _ = history
    service, job, endpoint, metadata = (
        (tts, clone, "/api/jobs", "job.json") if kind == "clone" else
        (vc, conversion, "/api/voice-conversions", "conversion.json")
    )
    path = job.job_dir / metadata
    payload = json.loads(path.read_text())
    payload.pop("title", None)
    path.write_text(json.dumps(payload))
    service._jobs.clear()
    assert client.get(endpoint).status_code == 200
    url = f"{endpoint}/{job.job_id}"
    assert client.patch(url, json={"title": "  Revised narration  "}).status_code == 200
    service._jobs.clear()
    assert client.get(url).json()["title"] == "Revised narration"
    for bad_title in ["", "   ", "a" * 161]:
        assert client.patch(url, json={"title": bad_title}).status_code == 422
    assert client.get(url).json()["title"] == "Revised narration"


@pytest.mark.parametrize("kind", ["clone", "conversion"])
def test_delete_removes_only_finished_job_and_owned_outputs(history, kind):
    client, tts, clone, vc, conversion, reference = history
    service, job, endpoint = (tts, clone, "/api/jobs") if kind == "clone" else (vc, conversion, "/api/voice-conversions")
    unrelated = tts.output_root / "another-recording.wav"
    unrelated.write_bytes(b"keep")
    if kind == "clone":
        # Deletion must not trust a filename that points at a different recording.
        job.result["filename"] = unrelated.name
    url = f"{endpoint}/{job.job_id}"
    job.status = "running"
    assert client.delete(url).status_code == 409
    assert job.job_dir.is_dir()
    job.status = "cancelled"
    assert client.delete(url).status_code == 200
    assert not job.job_dir.exists()
    assert client.get(url).status_code == 404
    assert client.delete(url).status_code == 404
    assert service.list() == []
    assert reference.is_file()
    assert unrelated.read_bytes() == b"keep"
    if kind == "clone":
        assert not (tts.output_root / f"timbreloom-long-{job.job_id}.wav").exists()


def test_regenerating_edited_history_creates_new_job_without_changing_original(history, monkeypatch):
    client, tts, original, _, _, _ = history
    monkeypatch.setattr(app._tts_provider, "model_available", lambda: True)
    monkeypatch.setattr(tts, "launch", tts.process)
    original_record = (original.job_dir / "job.json").read_bytes()
    original_audio = (tts.output_root / original.result["filename"]).read_bytes()
    saved = client.get(f"/api/jobs/{original.job_id}").json()
    response = client.post("/api/jobs", data={
        "target_text": "Revised paragraph.", "language": saved["language"], "reference_text": saved["reference_text"],
    }, files={"reference_audio": (saved["reference_filename"], client.get(saved["reference_url"]).content, "audio/wav")})
    assert response.status_code == 202
    assert response.json()["status"] == "complete"
    assert response.json()["job_id"] != original.job_id
    assert response.json()["target_text"] == "Revised paragraph."
    assert len(tts.list()) == 2
    assert (original.job_dir / "job.json").read_bytes() == original_record
    assert (tts.output_root / original.result["filename"]).read_bytes() == original_audio


@pytest.mark.parametrize("endpoint", ["/api/jobs", "/api/voice-conversions"])
def test_history_mutations_reject_unknown_ids(history, endpoint):
    client, *_ = history
    for job_id in ["not-a-job", "d" * 32]:
        assert client.delete(f"{endpoint}/{job_id}").status_code == 404
        assert client.patch(f"{endpoint}/{job_id}", json={"title": "Changed"}).status_code == 404


@pytest.mark.parametrize("kind", ["clone", "conversion"])
def test_delete_waits_for_worker_to_exit(history, kind):
    client, tts, clone, vc, conversion, _ = history
    service, job, endpoint = (tts, clone, "/api/jobs") if kind == "clone" else (vc, conversion, "/api/voice-conversions")
    finished = threading.Event()
    worker = threading.Thread(target=lambda: finished.wait(timeout=5))
    service._threads[job.job_id] = worker
    worker.start()
    try:
        assert client.delete(f"{endpoint}/{job.job_id}").status_code == 409
        assert job.job_dir.is_dir()
    finally:
        finished.set()
        worker.join(timeout=2)
    assert client.delete(f"{endpoint}/{job.job_id}").status_code == 200
