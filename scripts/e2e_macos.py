#!/usr/bin/env python3
"""Exercise the desktop WebKit integration with synthetic ASR, without model inference."""

import argparse
import array
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def seed_history(app):
    """Seed completed history with synthetic audio, without loading either model."""
    import shutil
    from datetime import datetime, timezone
    from timbreloom.tts_service import GenerationJob

    reference = app.DATA_DIR / "reference.wav"
    directory = app.JOB_DIR / ("a" * 32)
    directory.mkdir()
    job = GenerationJob(
        job_id=directory.name, voice_id=None, voice_name="Sample narration",
        reference_source=reference, reference_is_normalized=True,
        reference_text="A test reference voice.", reference_duration_seconds=3,
        language="english", segments=app.segment_text("History narration.\n\nA second paragraph."),
        job_dir=directory, created_at=datetime.now(timezone.utc).isoformat(),
    )
    def generate(_reference, _ref_text, _text, _language, output):
        shutil.copyfile(reference, output)
        return {"duration_seconds": 3, "generation_seconds": .1, "peak_memory_gb": 0}
    app._tts_jobs.generate_segment = generate
    app._tts_jobs.add(job)
    app._tts_jobs.process(job)
    directory = app.CONVERSION_DIR / ("c" * 32)
    directory.mkdir()
    for name in ("source.wav", "converted.wav"):
        shutil.copyfile(reference, directory / name)
    job = app._vc_service.create_job(
        job_id=directory.name, source_path=directory / "source.wav", source_filename="History performance.wav",
        source_bytes=reference.stat().st_size, voice_id="b" * 32, voice_name="Sample narration", preset="balanced",
    )
    app._vc_service._update(job, status="complete", phase="complete", progress=1, duration_seconds=3,
                           result={"audio_filename": "converted.wav", "duration_seconds": 3,
                                   "generation_seconds": .1, "diffusion_steps": 8, "chunk_count": 1})


def serve(port):
    sys.path.insert(0, str(ROOT))
    import app
    import uvicorn

    def transcribe(request, cancel_event=None):
        time.sleep(1)
        if request.initial_prompt == "UI_TEST_FAILURE":
            raise RuntimeError("Synthetic transcription failure. Import the media again and retry.")
        return {"language": "en", "text": "Wind moves through the trees. We walk slowly, listening to falling leaves.", "segments": [
            {"id": 0, "start": 0.0, "end": 1.0, "text": "Wind moves through the trees.", "words": []},
            {"id": 1, "start": 1.0, "end": 2.0, "text": "We walk slowly,", "words": []},
            {"id": 2, "start": 2.0, "end": 3.0, "text": "listening to falling leaves.", "words": []},
        ]}

    app._asr_provider.transcribe = transcribe
    from contextlib import contextmanager
    @contextmanager
    def live_engine(directory, cancel_event):
        class Engine:
            def transcribe(self, audio, language, prompt):
                return {"language": "en", "segments": [{"start": 0, "end": 1.5,
                        "text": "Live words appear while recording.", "words": [
                            {"word": "Live words appear while recording.", "start": 0, "end": 1.5}]}]}
        yield Engine()
    app._asr_provider.live_engine = live_engine
    @contextmanager
    def native_live_engine(directory, cancel_event, language, prompt):
        class Engine:
            def push(self, pcm, *, final=False):
                text = "Live words appear while recording."
                return {"language": language, "text": text, "stable_text": text if final else "",
                        "draft": "" if final else text, "segments": [{"start": 0, "end": 1.5, "text": text}]}
        yield Engine()
    for provider in app._streaming_asr_providers.values():
        provider.transcribe = transcribe
        provider.live_engine = native_live_engine
    if os.getenv("TIMBRELOOM_TEST_MODEL_DOWNLOADS") != "1":
        seed_history(app)
    if os.getenv("TIMBRELOOM_TEST_MODEL_DOWNLOADS") == "1":
        import copy
        import hashlib
        import httpx
        from timbreloom.model_store import ModelStore, model_catalog
        content = b"synthetic model!" * (1024 * 1024)
        catalog = copy.deepcopy(model_catalog())
        for model in catalog.values():
            model["bytes"] = len(content)
            model["files"] = [{"path": "synthetic.bin", "filename": "synthetic.bin", "repository": f"test/{model['id']}",
                               "revision": "a" * 40, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}]
        requests = []
        class SlowModel(httpx.SyncByteStream):
            def __init__(self, offset):
                self.offset = offset
            def __iter__(self):
                for offset in range(self.offset, len(content), 256 * 1024):
                    time.sleep(.12)
                    yield content[offset:offset + 256 * 1024]
        def respond(request):
            requests.append({"url": str(request.url), "range": request.headers.get("Range")})
            (app.DATA_DIR / "model-requests.json").write_text(json.dumps(requests, indent=2))
            if len(requests) == 1:
                raise httpx.ConnectError("Synthetic offline download", request=request)
            offset = int(request.headers.get("Range", "bytes=0-").split("=")[1].split("-")[0])
            return httpx.Response(206 if offset else 200, stream=SlowModel(offset),
                                  headers={"Content-Range": f"bytes {offset}-{len(content)-1}/{len(content)}"} if offset else {})
        app._model_store = ModelStore(app.DATA_DIR / "downloaded-models", catalog=catalog,
                                      transport=httpx.MockTransport(respond))
    uvicorn.run(app.app, host="127.0.0.1", port=port, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", type=int)
    parser.add_argument("--models", action="store_true", help="Exercise optional model downloads with an isolated synthetic source")
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
        return
    directory = Path(tempfile.mkdtemp(prefix="timbreloom-macos-e2e-"))
    with wave.open(str(directory / "reference.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        # Audible, bounded synthetic input also makes waveform rendering testable.
        samples = array.array("h", (int(4000 * math.sin(2 * math.pi * 220 * i / 24000)
                                      * math.sin(math.pi * (i % 12000) / 12000) ** 2)
                                   for i in range(24000 * 3)))
        if sys.byteorder != "little":
            samples.byteswap()
        audio.writeframes(samples.tobytes())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "TIMBRELOOM_DATA_DIR": str(directory), "TIMBRELOOM_PROJECT_ROOT": str(ROOT),
           "TIMBRELOOM_PORT": str(port), "TIMBRELOOM_PRELOAD": "0", "TIMBRELOOM_STARTUP_TRACE": str(directory / "startup.json")}
    env.pop("GEMINI_API_KEY", None)
    if args.models:
        env["TIMBRELOOM_TEST_MODEL_DOWNLOADS"] = "1"
    binary = directory / "WebKitSmoke"
    sources = [ROOT / "macos" / name for name in ["SmokeTests.swift", "Backend.swift", "WebWorkspace.swift", "FileDialogs.swift"]]
    subprocess.run(["xcrun", "swiftc", "-O", "-swift-version", "5", "-target", "arm64-apple-macosx14.0",
                    "-framework", "AppKit", "-framework", "WebKit", *map(str, sources), "-o", str(binary)], check=True)
    with (directory / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, str(Path(__file__)), "--serve", str(port)],
                                  env=env, cwd=ROOT, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/runtime", timeout=.3) as response:
                        assert json.load(response)["data_root"] == str(directory.resolve())
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("Test server did not start")
            subprocess.run([str(binary)], env=env, cwd=ROOT, timeout=105, check=True)
        finally:
            server.terminate()
            server.wait(timeout=8)
    print(f"Synthetic evidence: {directory}")


if __name__ == "__main__":
    main()
