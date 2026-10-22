import json
from pathlib import Path
from threading import Event

import pytest

from timbreloom.asr_service import ASRService
from timbreloom.asr_streams import NEMOTRON_LANGUAGES, merge_moonshine_lines, snapshot
from timbreloom.media import MediaInfo
from timbreloom.providers import AcceleratorCoordinator, ProviderDescriptor
from timbreloom.providers.streaming_asr import LocalStreamingASRProvider


@pytest.mark.parametrize("old,new,expected", [
    ("Words when I stop.", "I stop recording.", "Words when I stop recording."),
    ("\u4eca\u5929\u6211\u4eec\u8ba8\u8bba\u8bed\u97f3", "\u8bed\u97f3\u6a21\u578b。", "\u4eca\u5929\u6211\u4eec\u8ba8\u8bba\u8bed\u97f3\u6a21\u578b。"),
    ("I stop.", "I stop recording.", "I stop recording."),
])
def test_moonshine_overlapping_context_prefers_newer_line(old, new, expected):
    lines = [{"start": 0, "end": 3, "text": old}, {"start": 2.5, "end": 5, "text": new}]
    merged = merge_moonshine_lines(lines)
    assert snapshot(merged, "en", final=True)["text"] == expected
    assert all(a["end"] <= b["start"] for a, b in zip(merged, merged[1:]))
    assert lines[0]["text"] == old


def test_moonshine_keeps_deliberate_repetition_without_time_overlap():
    lines = [{"start": 0, "end": 1, "text": "Go again."}, {"start": 1, "end": 2, "text": "Go again."}]
    assert snapshot(merge_moonshine_lines(lines), "en", final=True)["text"] == "Go again. Go again."


@pytest.mark.parametrize("key,language,normalized", [("moonshine-en", "auto", "en"), ("moonshine-zh", "zh", "zh"), ("nemotron", "zh", "zh")])
def test_streaming_provider_language_and_hint_contract(key, language, normalized, tmp_path):
    provider = LocalStreamingASRProvider(key, tmp_path, Path(__file__), AcceleratorCoordinator(), model_available=lambda: True)
    assert provider.validate_request(language, "") == normalized
    assert provider.descriptor.ready
    if key == "nemotron":
        assert NEMOTRON_LANGUAGES[language] == "zh-CN"
        with pytest.raises(ValueError, match="Vocabulary hints"):
            provider.validate_request(language, "Names")
    else:
        with pytest.raises(ValueError, match="supports"):
            provider.validate_request("ja", "")


def test_file_jobs_pin_selected_provider_and_recover_without_changing_default(tmp_path, monkeypatch):
    class Provider:
        def __init__(self, name):
            self.model_id = name
            self.calls = 0
            self.descriptor = ProviderDescriptor(name, name, "asr", True, ("transcription",), True, True)
        def transcribe(self, request, cancel_event=None):
            self.calls += 1
            return {"language": "en", "text": self.model_id, "segments": [{"start": 0, "end": 1, "text": self.model_id}]}
    baseline, selected = Provider("baseline"), Provider("selected")
    monkeypatch.setattr("timbreloom.asr_service.probe_media", lambda _: MediaInfo(1, True, False, "wav"))
    monkeypatch.setattr("timbreloom.asr_service.prepare_asr_audio", lambda _, path: path.write_bytes(b"audio"))
    service = ASRService(tmp_path, baseline, {"nemotron": selected})
    directory = tmp_path / ("a" * 32)
    directory.mkdir()
    source = directory / "source.wav"
    source.write_bytes(b"source")
    service.create_job(job_id=directory.name, transcript_dir=directory, source_path=source,
                       source_filename=source.name, source_bytes=6, requested_language="en", initial_prompt="", model_key="nemotron")
    restarted = ASRService(tmp_path, baseline, {"nemotron": selected})
    job = restarted.get_job(directory.name)
    restarted._process_job(job)
    assert job.status == "complete" and job.model_key == "nemotron"
    assert selected.calls == 1 and baseline.calls == 0
    assert restarted.provider_for() is baseline
    assert (directory / "raw/nemotron.json").is_file()
    assert restarted.get_transcript(job.job_id)["model"] == "selected"
    assert json.loads((directory / "job.json").read_text())["model_key"] == "nemotron"
    with pytest.raises(ValueError, match="available"):
        service.validate_model("unknown", "auto", "")


@pytest.mark.parametrize("model,language,prompt", [("unknown", "auto", ""), ("moonshine-en", "zh", ""), ("moonshine-zh", "en", ""), ("nemotron", "en", "names")])
def test_api_rejects_incompatible_selection_before_inference(model, language, prompt):
    import app
    from fastapi.testclient import TestClient
    client = TestClient(app.app, base_url="http://127.0.0.1")
    response = client.post("/api/asr/jobs", data={"model": model, "language": language, "initial_prompt": prompt},
                           files={"media": ("test.wav", b"unused", "audio/wav")})
    assert response.status_code == 400


def test_model_choices_report_capabilities_and_missing_downloads(tmp_path, monkeypatch):
    import app
    from fastapi.testclient import TestClient
    from timbreloom.model_store import ModelStore
    monkeypatch.setattr(app, "_model_store", ModelStore(tmp_path / "missing"))
    client = TestClient(app.app, base_url="http://127.0.0.1")
    choices = {model["id"]: model for model in client.get("/api/asr/models").json()["models"]}
    assert set(choices) == {"whisper", "nemotron", "moonshine-en", "moonshine-zh"}
    assert not any(model["ready"] for model in choices.values())
    assert choices["moonshine-en"]["languages"] == ["en"]
    assert not choices["nemotron"]["supports_hints"]
    for model in choices:
        response = client.post("/api/asr/jobs", data={"model": model}, files={"media": ("test.wav", b"unused", "audio/wav")})
        assert response.status_code == 409
    assert not (tmp_path / "missing").exists()
