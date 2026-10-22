"""Verify every selectable ASR engine through a bundled API with an isolated library."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import socket
import subprocess
import time
import wave
from pathlib import Path

import httpx
from websockets.asyncio.client import connect


def check_transcript(client, job, key):
    assert job["status"] == "complete", job
    response = client.get(f"/api/transcripts/{job['job_id']}")
    response.raise_for_status()
    transcript = response.json()
    assert transcript["text"].strip() and transcript["segments"], transcript
    assert key in transcript["engine"], transcript
    assert all(0 <= segment["start"] <= segment["end"] <= transcript["duration_seconds"] + .01
               for segment in transcript["segments"]), transcript
    for format in ("txt", "srt", "vtt"):
        response = client.get(f"/api/transcripts/{job['job_id']}/export/{format}")
        response.raise_for_status()
        assert response.content
    return transcript


def file_case(client, fixture, key, language, *, expect_speech=True):
    began = time.monotonic()
    with fixture.open("rb") as audio:
        response = client.post("/api/asr/jobs", data={"model": key, "language": language, "initial_prompt": "Timbreloom" if key == "moonshine-en" else ""},
                               files={"media": (fixture.name, audio, "audio/wav")})
    response.raise_for_status()
    job = response.json()
    deadline = time.monotonic() + 180
    while job["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(.1)
        job = client.get(f"/api/asr/jobs/{job['job_id']}").json()
    assert job["model_key"] == key
    if expect_speech:
        transcript = check_transcript(client, job, key)
    else:
        assert job["status"] in {"complete", "error"}, job
        if job["status"] == "complete":
            transcript = client.get(f"/api/transcripts/{job['job_id']}").json()
            assert not transcript["text"].strip(), transcript
        else:
            assert job["error"] == "The transcript is empty." and job["audio_ready"], job
            transcript = {"text": ""}
    return {"mode": "file", "model": key, "fixture": fixture.name, "language": language,
            "elapsed_seconds": round(time.monotonic() - began, 3), "job": job, "transcript": transcript}


async def live_case(base, client, fixture, key, language):
    with wave.open(str(fixture)) as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (16000, 1, 2)
        pcm = audio.readframes(audio.getnframes())
    events = []
    async with connect(base.replace("http", "ws") + "/api/asr/live", origin=base) as stream:
        await stream.send(json.dumps({"type": "start", "model": key, "language": language, "prompt": "Timbreloom" if key == "moonshine-en" else "", "sample_rate": 16000}))
        async with asyncio.timeout(180):
            while True:
                event = json.loads(await stream.recv())
                events.append(event)
                assert event["type"] not in {"error", "cancelled"}, event
                if event["type"] == "ready":
                    break
        began = time.monotonic()
        first = None
        async def receive():
            nonlocal first
            async for message in stream:
                event = json.loads(message)
                event["elapsed_seconds"] = round(time.monotonic() - began, 3)
                events.append(event)
                if first is None and event["type"] == "partial" and (event.get("text") or event.get("draft")):
                    first = event["elapsed_seconds"]
                if event["type"] in {"complete", "error", "cancelled"}:
                    return event
        receiver = asyncio.create_task(receive())
        try:
            for offset in range(0, len(pcm), 3200):
                await asyncio.sleep(max(0, began + min(offset + 3200, len(pcm)) / 32000 - time.monotonic()))
                await stream.send(pcm[offset:offset + 3200])
            await asyncio.sleep(max(0, began + len(pcm) / 32000 - time.monotonic()))
            stopped = time.monotonic()
            await stream.send(json.dumps({"type": "stop"}))
            terminal = await asyncio.wait_for(receiver, 180)
            tail = time.monotonic() - stopped
        finally:
            if not receiver.done():
                receiver.cancel()
                await asyncio.gather(receiver, return_exceptions=True)
    assert terminal["type"] == "complete" and first is not None and first < len(pcm) / 32000, terminal
    job = client.get(f"/api/asr/jobs/{terminal['job_id']}").json()
    assert job["model_key"] == key and abs(job["duration_seconds"] - len(pcm) / 32000) < .001
    transcript = check_transcript(client, job, key)
    return {"mode": "live", "model": key, "fixture": fixture.name, "language": language,
            "first_text_seconds": first, "finish_seconds": round(tail, 3), "job": job,
            "transcript": transcript, "events": events}


async def cancel_case(base, key):
    events = []
    async with connect(base.replace("http", "ws") + "/api/asr/live", origin=base) as stream:
        await stream.send(json.dumps({"type": "start", "model": key, "language": "auto", "sample_rate": 16000}))
        assert json.loads(await stream.recv())["type"] == "preparing"
        await stream.send(json.dumps({"type": "stop"}))
        async with asyncio.timeout(180):
            async for message in stream:
                event = json.loads(message)
                events.append(event)
                if event["type"] in {"complete", "cancelled", "error"}:
                    assert event["type"] == "cancelled", event
                    return {"mode": "cancel-start", "model": key, "events": events}
    raise AssertionError("The cancelled session did not finish")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--models-dir", required=True, type=Path)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    backend = args.app.resolve() / "Contents/Resources/backend"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    environment = {**os.environ, "TIMBRELOOM_DATA_DIR": str(output / "library"),
        "TIMBRELOOM_MODELS_DIR": str(args.models_dir.resolve()), "TIMBRELOOM_PRELOAD": "0", "TIMBRELOOM_EMBEDDED": "1",
        "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": str(backend / "runtime/media/bin") + ":/usr/bin:/bin:/usr/sbin:/sbin"}
    results = []
    report = {"app": str(args.app.resolve()), "cases": results, "fixtures": {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in args.fixtures.glob("*.wav")}}
    with (output / "backend.log").open("w") as log:
        process = subprocess.Popen([str(backend / ".venv/bin/python"), "-m", "timbreloom.desktop_server",
                                    "--port", str(port), "--parent", str(os.getpid())], cwd=backend, env=environment,
                                   stdout=log, stderr=log, start_new_session=True)
        report["server_pid"] = process.pid
        try:
            with httpx.Client(base_url=base, timeout=180, trust_env=False) as client:
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError((output / "backend.log").read_text())
                    try:
                        response = client.get("/api/runtime")
                        response.raise_for_status()
                        report["runtime"] = response.json()
                        break
                    except httpx.ConnectError:
                        time.sleep(.1)
                else:
                    raise TimeoutError("The bundled service did not start")
                choices = client.get("/api/asr/models").json()["models"]
                assert len(choices) == 4 and all(model["ready"] for model in choices), choices
                for key, name, language in [("whisper", "english", "en"), ("nemotron", "english", "en"),
                                            ("moonshine-en", "english", "en"), ("moonshine-zh", "mandarin", "zh")]:
                    fixture = args.fixtures / f"{name}.wav"
                    results.append(file_case(client, fixture, key, language))
                    print(f"PASS file: {key}", flush=True)
                    results.append(asyncio.run(live_case(base, client, fixture, key, language)))
                    print(f"PASS live: {key}", flush=True)
                for key, name, language, speech in [("nemotron", "mixed", "auto", True),
                                                    ("moonshine-en", "long_english", "en", True),
                                                    ("nemotron", "silence", "auto", False),
                                                    ("moonshine-en", "silence", "en", False),
                                                    ("moonshine-zh", "silence", "zh", False)]:
                    results.append(file_case(client, args.fixtures / f"{name}.wav", key, language, expect_speech=speech))
                    print(f"PASS file: {key} / {name}", flush=True)
                for key in ("nemotron", "moonshine-en", "moonshine-zh"):
                    results.append(asyncio.run(cancel_case(base, key)))
                    print(f"PASS cancel start: {key}", flush=True)
                report["passed"] = True
        finally:
            process.terminate()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            try:
                os.killpg(process.pid, 0)
                raise RuntimeError("A verification worker is still running")
            except ProcessLookupError:
                report["process_group_exited"] = True
            (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"Evidence: {output / 'report.json'}")


if __name__ == "__main__":
    main()
