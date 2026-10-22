import threading
import wave
from contextlib import contextmanager

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from timbreloom.asr_service import ASRService
from timbreloom.live_asr import LiveASRService, LiveHypothesis, SAMPLE_RATE
from timbreloom.live_asr_api import create_router
from timbreloom.providers import AcceleratorCoordinator, ProviderDescriptor


def result(words):
    return {"language": "en", "segments": [{"words": [
        {"word": word, "start": start, "end": end} for word, start, end in words
    ]}]}


def test_agreement_revises_draft_and_deduplicates_trimmed_context():
    hypothesis = LiveHypothesis()
    hypothesis.update(result([("Hello", .1, .6), ("world", .7, 1.3)]), 0, 2)
    assert not hypothesis.words
    hypothesis.update(result([("Hello", .1, .65), ("there.", .7, 1.35)]), 0, 4)
    assert hypothesis.text(hypothesis.words) == "Hello"
    assert hypothesis.text(hypothesis.pending) == "there."
    # A new window overlaps the already committed word by 200 ms.
    hypothesis.update(result([("Hello", 0, .22), ("there.", .3, 1), ("Again.", 1.1, 1.5)]), .5, 5, final=True)
    assert hypothesis.result()["text"] == "Hello there. Again."
    assert hypothesis.result()["segments"][0]["end"] == 1.5


def test_mandarin_final_tail_and_forced_buffer_boundary():
    hypothesis = LiveHypothesis()
    hypothesis.update(result([("\u4f60\u597d", 0, 1), ("\u4e16\u754c", 1, 2), ("。", 2, 2.1)]), 0, 28, force_before=26)
    hypothesis.update(result([("\u518d\u89c1。", 0, .2)]), 28, 28.2, final=True)
    assert hypothesis.result()["text"] == "\u4f60\u597d\u4e16\u754c。\u518d\u89c1。"
    assert hypothesis.words[-1]["end"] == 28.2


def test_timestamp_ties_do_not_drop_a_new_mandarin_syllable():
    hypothesis = LiveHypothesis()
    hypothesis.update(result([("\u8f6c", 1, 2)]), 0, 3, final=True)
    hypothesis.update(result([("\u8f6c", 1.5, 2), ("\u5199", 2, 2)]), 0, 4, final=True)
    assert hypothesis.result()["text"] == "\u8f6c\u5199"


class FakeProvider:
    model_id = "test-whisper"
    opens = 0
    closes = 0
    calls = 0
    fail = False
    descriptor = ProviderDescriptor(provider_id="fake", name="Fake", provider_type="asr", local=True,
                                    capabilities=("transcription",), configured=True, ready=True)

    @contextmanager
    def live_engine(self, directory, cancel):
        self.opens += 1
        try:
            yield self
        finally:
            self.closes += 1

    def transcribe(self, audio, language, prompt):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Synthetic model failure")
        with wave.open(str(audio)) as wav:
            duration = wav.getnframes() / wav.getframerate()
        return result([("Words", 0, min(.3, duration)), ("during recording.", min(.3, duration), duration)])


@pytest.fixture
def live(tmp_path):
    provider = FakeProvider()
    asr = ASRService(tmp_path, provider)
    service = LiveASRService(asr)
    app = FastAPI()
    app.include_router(create_router(service, {"en", "zh", "auto"}))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client, service, provider
    service.close()


def connect(client):
    return client.websocket_connect("ws://127.0.0.1/api/asr/live", headers={"origin": "http://127.0.0.1"})


def start(socket):
    socket.send_json({"type": "start", "language": "en", "sample_rate": SAMPLE_RATE})
    assert socket.receive_json()["type"] == "preparing"
    ready = socket.receive_json()
    assert ready["type"] == "ready"
    return ready["job_id"]


def speech(seconds=1):
    samples = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (np.sin(2 * np.pi * 220 * samples) * 4000).astype("<i2").tobytes()


def test_live_input_emits_text_before_stop_and_saves_editable_transcript(live):
    client, service, provider = live
    with connect(client) as socket:
        job_id = start(socket)
        socket.send_bytes(speech())
        socket.send_bytes(speech())
        partial = socket.receive_json()
        assert partial["type"] == "partial" and partial["draft"] == "Words during recording."
        socket.send_bytes(speech(.25))
        socket.send_json({"type": "stop"})
        while (event := socket.receive_json())["type"] == "partial":
            pass
        assert event["type"] == "complete"
    transcript = service.asr.get_transcript(job_id)
    assert transcript["duration_seconds"] == 2.25
    assert transcript["text"] == "Words during recording."
    assert provider.opens == provider.closes == 1
    assert provider.calls == 2
    with wave.open(str(service.asr.transcript_dir(job_id) / "source.wav")) as audio:
        assert audio.getnframes() == 36000
    segment = transcript["segments"][0]
    service.asr.update_transcript(job_id, {segment["id"]: "Edited live text."})
    assert "Edited live text." in service.asr.export(job_id, "srt").read_text()
    assert ASRService(service.asr.transcript_root, provider).get_job(job_id).status == "complete"


def test_disconnect_saves_short_final_audio_and_closes_engine(live):
    client, service, provider = live
    with connect(client) as socket:
        job_id = start(socket)
        socket.send_bytes(speech(.3))
    service.session.thread.join(timeout=3)
    assert not service.session.thread.is_alive()
    assert service.asr.get_transcript(job_id)["duration_seconds"] == .3
    assert provider.closes == 1


@pytest.mark.parametrize("failure", [False, True])
def test_silence_or_model_failure_keeps_recording(live, failure):
    client, service, provider = live
    provider.fail = failure
    with connect(client) as socket:
        job_id = start(socket)
        socket.send_bytes(speech(.25) if failure else b"\0\0" * 4000)
        socket.send_json({"type": "stop"})
        while (event := socket.receive_json())["type"] == "partial":
            pass
        assert event["type"] == "error"
        assert event["audio_url"].endswith(f"{job_id}/audio")
    assert service.asr.get_job(job_id).audio_ready
    assert provider.closes == 1


def test_rejects_foreign_origin_and_malformed_input(live):
    from starlette.websockets import WebSocketDisconnect
    client, service, _ = live
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("ws://127.0.0.1/api/asr/live", headers={"origin": "https://example.org"}):
            pass
    with connect(client) as socket:
        socket.send_json({"type": "start", "sample_rate": 48000})
        assert socket.receive_json()["type"] == "error"
    assert service.session is None


def test_overlapping_sessions_and_invalid_pcm_are_rejected(live):
    client, service, _ = live
    with connect(client) as socket:
        start(socket)
        with connect(client) as other:
            other.send_json({"type": "start", "sample_rate": SAMPLE_RATE})
            assert "already running" in other.receive_json()["message"]
        socket.send_bytes(b"odd")
        assert socket.receive_json()["type"] == "stopping"
        assert socket.receive_json()["type"] == "cancelled"


def test_live_accelerator_acquisition_does_not_wait_behind_another_model():
    coordinator = AcceleratorCoordinator()
    entered = threading.Event()
    release = threading.Event()
    def hold():
        with coordinator.session("tts"):
            entered.set()
            release.wait(3)
    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert entered.wait(1)
        with pytest.raises(RuntimeError, match="busy"):
            with coordinator.session("asr", wait=False):
                pass
    finally:
        release.set()
        thread.join()
    assert coordinator.active is None


@pytest.mark.parametrize("ending", ["finish", "disconnect", "cancel", "silence", "failure"])
def test_native_stream_selection_flushes_and_releases_engine(tmp_path, ending):
    class Native(FakeProvider):
        native_streaming = True
        model_id = "test-native"
        final = False
        @contextmanager
        def live_engine(self, directory, cancel, language, prompt):
            self.opens += 1
            try:
                yield self
            finally:
                self.closes += 1
        def push(self, pcm, *, final=False):
            self.calls += 1
            self.final = final
            if ending == "failure":
                raise RuntimeError("Synthetic model failure")
            text = "Native stream words." if ending not in {"cancel", "silence"} else ""
            return {"language": "en", "text": text, "stable_text": text if final else "", "draft": "" if final else text,
                    "segments": [{"start": 0, "end": .3, "text": text}] if text else []}
    baseline, native = FakeProvider(), Native()
    service = LiveASRService(ASRService(tmp_path, baseline, {"nemotron": native}))
    events = []
    try:
        session = service.start("en", "", events.append, model_key="nemotron")
        if ending != "cancel":
            session.feed(speech(.3) if ending != "silence" else b"\0\0" * 4800)
        session.stop()  # The websocket disconnect path uses the same finalization.
        session.thread.join(3)
        assert not session.thread.is_alive()
        assert native.opens == native.closes == 1 and baseline.opens == 0
        assert service.asr.get_job(session.job_id).model_key == "nemotron"
        if ending in {"finish", "disconnect"}:
            assert native.final and events[-1]["type"] == "complete"
            transcript = service.asr.get_transcript(session.job_id)
            assert transcript["model"] == "test-native" and transcript["engine"] == "local-nemotron-live"
            assert "Native stream words." in service.asr.export(session.job_id, "vtt").read_text()
        else:
            assert events[-1]["type"] == ("cancelled" if ending == "cancel" else "error")
            assert (session.job.transcript_dir / "audio.wav").is_file()
    finally:
        service.close()
