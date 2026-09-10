"""Run actual offline model workflows from a relocated app with an isolated library."""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import os
import signal
import socket
import subprocess
import time
import math
import wave
from pathlib import Path

import httpx

from e2e_v1 import SOURCE_TEXT, _poll, run


def character_error_rate(expected: str, actual: str) -> float:
    expected = "".join(c.lower() for c in expected if c.isalnum())
    actual = "".join(c.lower() for c in actual if c.isalnum())
    previous = list(range(len(actual) + 1))
    for i, left in enumerate(expected, 1):
        current = [i]
        for j, right in enumerate(actual, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (left != right)))
        previous = current
    return round(previous[-1] / max(1, len(expected)), 4)


def audio_quality(path: Path) -> dict:
    with wave.open(str(path), "rb") as handle:
        assert handle.getsampwidth() == 2, "Release output must be interoperable PCM16 WAV"
        rate, channels = handle.getframerate(), handle.getnchannels()
        frames = handle.getnframes()
        samples = array.array("h", handle.readframes(frames))
    peak = max(abs(value) for value in samples) / 32768
    rms = math.sqrt(sum((value / 32768) ** 2 for value in samples) / len(samples))
    clipped = sum(abs(value) >= 32760 for value in samples) / len(samples)
    assert rms > .001 and clipped < .01, "Generated audio is silent or severely clipped"
    return {"seconds": frames / rate, "sample_rate": rate, "channels": channels,
            "peak": peak, "rms_dbfs": 20 * math.log10(rms), "clipped_fraction": clipped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--models-dir", type=Path, required=True, help="External, already downloaded model directory")
    parser.add_argument("--startup-timeout", type=float, default=120,
                        help="Functional test deadline, including OS trust checks; startup performance is measured separately")
    args = parser.parse_args()
    backend = args.app.resolve() / "Contents/Resources/backend"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    data = output / "isolated-library"
    home = output / "isolated-home"
    home.mkdir()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = {"HOME": str(home), "PATH": str(backend / "runtime/media/bin") + ":/usr/bin:/bin:/usr/sbin:/sbin",
        "TIMBRELOOM_MODELS_DIR": str(args.models_dir.expanduser().resolve()),
        "LANG": "en_US.UTF-8", "TIMBRELOOM_DATA_DIR": str(data), "TIMBRELOOM_PRELOAD": "0",
        "TIMBRELOOM_EMBEDDED": "1", "TIMBRELOOM_H264_ENCODER": "h264_videotoolbox",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HOME": str(home / "huggingface"), "NUMBA_CACHE_DIR": str(home / "numba"),
        "MPLCONFIGDIR": str(home / "matplotlib"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
    os.environ.update(environment)
    started = time.perf_counter()
    worker = None
    base = f"http://127.0.0.1:{port}"
    with (output / "backend.log").open("w") as log:
        process = subprocess.Popen([str(backend / ".venv/bin/python"), "-m", "timbreloom.desktop_server",
            "--port", str(port), "--parent", str(os.getpid())], cwd=backend, env=environment,
            stdout=log, stderr=log, start_new_session=True)
        try:
            with httpx.Client(base_url=base, timeout=120, trust_env=False) as client:
                deadline = time.perf_counter() + args.startup_timeout
                while time.perf_counter() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError((output / "backend.log").read_text()[-5000:])
                    try:
                        runtime = client.get("/api/runtime").json()
                        break
                    except httpx.ConnectError:
                        time.sleep(.1)
                else:
                    raise TimeoutError("The embedded service did not start")
                assert Path(runtime["project_root"]).resolve() == backend
                assert Path(runtime["data_root"]).resolve() == data
                worker = runtime["pid"]
                models = client.get("/api/models").json()
                assert Path(models["directory"]) == args.models_dir.expanduser().resolve()
                assert all(model["ready"] for model in models["models"]), "Download all models before offline workflow validation"
                assert not (backend / "models").exists(), "Release must not embed weights"
                (output / "model-store.json").write_text(json.dumps(models, ensure_ascii=False, indent=2))
                print(f"Relocated service ready: {time.perf_counter() - started:.3f}s", flush=True)
                (output / "startup.json").write_text(json.dumps({"spawn_to_service_ready_seconds": time.perf_counter() - started,
                    "scope": "Includes OS execution trust checks; this is a functional model test, not a startup performance budget."}, indent=2))
                result = run(base, output / "outputs")
                (output / "dubbing.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                transcript = client.get(f"/api/transcripts/{result['transcript_id']}")
                if transcript.status_code == 200:
                    (output / "transcript.json").write_text(json.dumps(transcript.json(), ensure_ascii=False, indent=2))
                source = next((data / "transcripts" / result["transcript_id"]).glob("source.*"))
                # Exercise a real Seed-VC subprocess after ASR and Qwen, including accelerator release.
                with source.open("rb") as media:
                    response = client.post("/api/voice-conversions", data={"voice_id": result["voice_id"],
                        "preset": "balanced", "confirm_rights": "true"}, files={"media": (source.name, media, "video/mp4")})
                response.raise_for_status()
                vc = _poll(client, f"/api/voice-conversions/{response.json()['id']}", timeout=1800)
                (output / "voice-conversion.json").write_text(json.dumps(vc, ensure_ascii=False, indent=2))
                if vc["status"] != "complete":
                    raise RuntimeError(f"Seed-VC failed: {vc.get('error')}")
                for kind in ("audio", "video"):
                    if url := vc["result"].get(f"{kind}_url"):
                        response = client.get(url)
                        response.raise_for_status()
                        (output / "outputs" / f"seed-vc.{'wav' if kind == 'audio' else 'mp4'}").write_bytes(response.content)
                fallback_source = output / "huffyuv-source.mkv"
                fallback_output = output / "outputs/native-h264-fallback.mp4"
                subprocess.run([str(backend / "runtime/media/bin/ffmpeg"), "-nostdin", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=0x161817:s=640x360:r=24", "-i", str(output / "outputs/e2e-output.wav"),
                    "-t", "2", "-c:v", "huffyuv", "-c:a", "pcm_s16le", str(fallback_source)], check=True, env=environment, timeout=30)
                # HuffYUV cannot be copied into MP4, so this must exercise native H.264 encoding.
                fallback = subprocess.check_output([str(backend / ".venv/bin/python"), "-c",
                    "import sys,json;from pathlib import Path;from timbreloom.media import mux_dubbed_video;print(json.dumps(mux_dubbed_video(*map(Path,sys.argv[1:]))))",
                    str(fallback_source), str(output / "outputs/e2e-output.wav"), str(fallback_output)],
                    cwd=backend, env=environment, text=True, timeout=60)
                (output / "native-h264-fallback.json").write_text(fallback)
                assert json.loads(fallback)["video_codec_mode"] == "h264"
                streams = json.loads(subprocess.check_output([str(backend / "runtime/media/bin/ffprobe"),
                    "-v", "error", "-show_streams", "-of", "json", str(fallback_output)], text=True, env=environment))
                assert any(stream["codec_type"] == "video" and stream["codec_name"] == "h264" for stream in streams["streams"])
                quality = {"source_asr_cer": character_error_rate(SOURCE_TEXT, transcript.json()["text"])}
                assert quality["source_asr_cer"] <= .25, "Source transcription diverged from the known text"
                for name in ("e2e-output.wav", "seed-vc.wav"):
                    path = output / "outputs" / name
                    metrics = audio_quality(path)
                    with path.open("rb") as media:
                        response = client.post("/api/asr/jobs", data={"language": "zh"},
                                               files={"media": (name, media, "audio/wav")})
                    response.raise_for_status()
                    decoded = _poll(client, f"/api/asr/jobs/{response.json()['job_id']}", timeout=1800)
                    assert decoded["status"] == "complete", decoded.get("error")
                    text = client.get(f"/api/transcripts/{decoded['result']['id']}").json()["text"]
                    metrics.update(transcribed_text=text, character_error_rate=character_error_rate(SOURCE_TEXT, text))
                    quality[name] = metrics
                (output / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n")
                assert all(value["character_error_rate"] <= .25 for value in quality.values() if isinstance(value, dict)), "Generated speech lost too much of the known text"
                receipts = []
                for path in sorted((output / "outputs").glob("*")):
                    with path.open("rb") as handle:
                        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
                    receipts.append({"file": path.name, "bytes": path.stat().st_size,
                                     "sha256": checksum})
                (output / "receipt.json").write_text(json.dumps({"passed": True, "app": str(args.app),
                    "seconds": time.perf_counter() - started, "isolated_home": True, "offline": True,
                    "system_path_only": True, "files": receipts}, indent=2) + "\n")
                print("Offline release workflows passed", flush=True)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
            if worker:
                try:
                    os.kill(worker, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise RuntimeError("The validation backend survived shutdown")


if __name__ == "__main__":
    main()
