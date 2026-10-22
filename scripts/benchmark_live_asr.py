#!/usr/bin/env python3
"""Pace a 16 kHz mono PCM16 WAV through the real live worker, with isolated output."""
import argparse
import json
import sys
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from timbreloom.asr_service import ASRService
from timbreloom.live_asr import LiveASRService
from timbreloom.providers import AcceleratorCoordinator, LocalWhisperASRProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", type=Path, default=ROOT / "models/Whisper-large-v3-turbo-q4")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    provider = LocalWhisperASRProvider("mlx-community/whisper-large-v3-turbo-q4", args.model, AcceleratorCoordinator())
    service = LiveASRService(ASRService(args.output / "transcripts", provider))
    ready = threading.Event()
    events = []
    began = time.monotonic()
    def receive(event):
        events.append({**event, "wall_seconds": round(time.monotonic() - began, 3)})
        if event["type"] in {"ready", "error"}:
            ready.set()
        print(json.dumps(events[-1], ensure_ascii=False), flush=True)
    session = service.start(args.language, "", receive)
    try:
        if not ready.wait(120) or not any(event["type"] == "ready" for event in events):
            raise RuntimeError("Model startup failed")
        audio_started = time.monotonic()
        sent = 0
        with wave.open(str(args.audio)) as audio:
            assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 16000)
            while pcm := audio.readframes(1600):
                # Wait until the chunk would actually have been captured.
                sent += len(pcm) / 32000
                time.sleep(max(0, audio_started + sent - time.monotonic()))
                session.feed(pcm)
        session.stop()
        session.thread.join(timeout=125)
        assert not session.thread.is_alive(), "Worker did not exit"
        transcript = service.asr.get_transcript(session.job_id)
        partials = [event for event in events if event["type"] == "partial" and (event["text"] or event["draft"])]
        report = {"audio": str(args.audio), "language": args.language, "duration_seconds": sent,
                  "startup_seconds": round(audio_started - began, 3),
                  "first_text_seconds": round(partials[0]["wall_seconds"] - (audio_started - began), 3) if partials else None,
                  "finish_seconds_after_audio": round(time.monotonic() - audio_started - sent, 3),
                  "text": transcript["text"], "events": events}
        (args.output / "benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
