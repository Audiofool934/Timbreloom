#!/usr/bin/env python3
"""Isolated, paced ASR comparison. Does not modify Timbreloom's installed runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import unicodedata
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATE = 16000
PACKET = 1600


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path)) as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, RATE):
            raise ValueError("Expected mono 16 kHz PCM16 WAV")
        return audio.readframes(audio.getnframes())


def make_fixtures(output: Path) -> None:
    """Create explicit reference text and repeatable, synthetic smoke fixtures."""
    import numpy as np

    output.mkdir(parents=True, exist_ok=False)
    english = (
        "Today we are testing live transcription in Timbreloom. "
        "The microphone sends small pieces of audio while the words appear on screen. "
        "Please preserve the final sentence when I stop recording. "
        "A useful voice tool should respond quickly, handle pauses, and let me correct "
        "a name without losing the rest of the transcript."
    )
    chinese = (
        "\u4eca\u5929\u6211\u4eec\u6d4b\u8bd5\u5b9e\u65f6\u8bed\u97f3\u8f6c\u5199。\u8bf4\u8bdd\u7684\u65f6\u5019，\u6587\u5b57\u5e94\u8be5\u6301\u7eed\u51fa\u73b0\u5728\u5c4f\u5e55\u4e0a。"
        "\u8bf7\u4fdd\u7559\u505c\u987f\u524d\u540e\u7684\u5185\u5bb9，\u4e5f\u4e0d\u8981\u4e22\u6389\u5f55\u97f3\u7ed3\u675f\u65f6\u7684\u6700\u540e\u4e00\u53e5。"
        "\u6211\u4eec\u5e0c\u671b\u8fd9\u4e2a\u5de5\u5177\u53cd\u5e94\u5feb，\u4e2d\u6587\u51c6\u786e，\u800c\u4e14\u80fd\u591f\u968f\u65f6\u4fee\u6539。"
    )
    definitions = [
        ("english", "en", [("Samantha", english)]),
        ("mandarin", "zh", [("Tingting", chinese)]),
        ("mixed", "auto", [
            ("Samantha", "Please open the transcription workspace and start recording."),
            ("Tingting", "\u73b0\u5728\u5207\u6362\u5230\u4e2d\u6587，\u4fdd\u7559\u539f\u6765\u7684\u610f\u601d，\u4e0d\u8981\u81ea\u52a8\u7ffb\u8bd1。"),
            ("Samantha", "Then save the final transcript and keep the original audio."),
        ]),
        ("long_english", "en", [("Samantha", " ".join([
            "This is the first part of a longer recording. " + english,
            "We are now starting the second part. " + english,
            "This is the final part. Please keep every word until the recording ends.",
        ]))]),
        ("stop_tail", "en", [("Samantha", "Keep the last words when I stop recording: silver mountain garden.")]),
        ("silence", "auto", []),
    ]
    fixtures = []
    for name, language, parts in definitions:
        chunks = [np.zeros(int(0.3 * RATE), dtype="<i2")]
        for index, (voice, text) in enumerate(parts):
            source = output / f"{name}-{index}.aiff"
            converted = output / f"{name}-{index}.wav"
            subprocess.run(["say", "-v", voice, "-r", "165", "-o", str(source), text], check=True)
            subprocess.run([
                "ffmpeg", "-v", "error", "-i", str(source), "-ar", str(RATE),
                "-ac", "1", "-c:a", "pcm_s16le", str(converted),
            ], check=True)
            samples = np.frombuffer(read_pcm(converted), dtype="<i2")
            active = np.flatnonzero(np.abs(samples.astype(np.int32)) > 100)
            if not active.size:
                raise ValueError(f"Speech synthesis produced silence: {name}")
            # Retain 20 ms after the last sample above the amplitude threshold.
            samples = samples[:min(len(samples), int(active[-1]) + 321)]
            chunks.append(samples)
            if index + 1 < len(parts):
                chunks.append(np.zeros(int(0.25 * RATE), dtype="<i2"))
        if not parts:
            chunks = [np.zeros(5 * RATE, dtype="<i2")]
        elif name != "stop_tail":
            chunks.append(np.zeros(int(0.2 * RATE), dtype="<i2"))
        pcm = np.concatenate(chunks).astype("<i2").tobytes()
        path = output / f"{name}.wav"
        with wave.open(str(path), "wb") as audio:
            audio.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
            audio.writeframes(pcm)
        fixtures.append({
            "id": name, "language": language, "audio": path.name,
            "reference": " ".join(text for _, text in parts),
            "voices": [voice for voice, _ in parts], "rate_wpm": 165,
            "duration_seconds": len(pcm) / (2 * RATE), "sha256": digest(path),
            "synthetic": True, "leading_silence_seconds": 0.3 if parts else 5.0,
        })
    save_json(output / "manifest.json", {"fixtures": fixtures})
    print(json.dumps(fixtures, ensure_ascii=False, indent=2))


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def accuracy(reference: str, hypothesis: str, language: str) -> dict:
    def normalized(text: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFKC", text).casefold()
                       if c.isalnum() or c.isspace())

    if not reference.strip():
        return {"metric": "silence", "passed": not hypothesis.strip()}
    if language not in {"en", "zh"}:
        return {"metric": "qualitative_mixed_language", "error_rate": None}
    tokenize = str.split if language == "en" else lambda s: list(re.sub(r"\s", "", s))
    expected = tokenize(normalized(reference))
    observed = tokenize(normalized(hypothesis))
    errors = edit_distance(expected, observed)
    return {"metric": "WER" if language == "en" else "CER", "errors": errors,
            "reference_units": len(expected), "error_rate": errors / len(expected)}


def whisper_silence_report(log: str, duration: float) -> dict | None:
    """The legacy helper expects a saved transcript, even for valid no-speech results."""
    if "FileNotFoundError: Transcript not found." not in log:
        return None
    events = []
    for line in log.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and "type" in event:
            events.append(event)
    errors = [event for event in events if event["type"] == "error"]
    ready = next((event for event in events if event["type"] == "ready"), None)
    if (not ready or len(errors) != 1
            or errors[0].get("message") != "No speech was recognized. Your recording is available below."
            or any(event.get("text") or event.get("draft") for event in events)):
        return None
    return {
        "duration_seconds": duration, "startup_seconds": ready["wall_seconds"],
        "first_text_seconds": None,
        "finish_seconds_after_audio": errors[0]["wall_seconds"] - ready["wall_seconds"] - duration,
        "text": "", "events": events, "terminal_status": "no_speech",
        "timing_source": "ready event approximation for silence only",
        "baseline_helper_exit_code": 1,
        "baseline_helper_limitation": "Expected no-speech result has no saved transcript; legacy helper tries to read one.",
    }


class Events:
    def __init__(self) -> None:
        self.started = 0.0
        self.events: list[dict] = []
        self.text = ""

    def emit(self, text: str, **metadata) -> None:
        if text == self.text:
            return
        self.text = text
        self.events.append({"audio_wall_seconds": round(time.monotonic() - self.started, 4),
                            "text": text, **metadata})


def candidate_worker(args) -> None:
    """Inference consumes a queue; the simulated microphone keeps its own clock."""
    import numpy as np

    pcm = read_pcm(args.audio)
    duration = len(pcm) / (2 * RATE)
    events = Events()
    engine_errors = []
    loading = time.monotonic()
    if args.engine.startswith("moonshine"):
        from moonshine_voice import ModelArch, Transcriber

        arch = ModelArch.SMALL_STREAMING if args.engine == "moonshine-en" else ModelArch.TINY_STREAMING
        options = {"max_tokens_per_second": 13} if args.engine == "moonshine-zh" else {}
        transcriber = Transcriber(args.model, arch, update_interval=0.5, options=options)
        stream = transcriber.create_stream(update_interval=0.5)
        lines = {}

        def on_event(event):
            if hasattr(event, "error"):
                # The library catches listener exceptions, so preserve errors
                # for the decoder loop to raise outside the callback.
                engine_errors.append(event.error)
                return
            line = getattr(event, "line", None)
            if line is not None:
                lines[line.line_id] = line
                events.emit(" ".join(item.text for item in sorted(lines.values(), key=lambda item: item.start_time)),
                            event=type(event).__name__, line_complete=line.is_complete)

        stream.add_listener(on_event)
        stream.start()
    else:
        from mlx_audio.stt.utils import load_model

        model = load_model(str(args.model))
        # Four 80 ms encoder frames per chunk, including the current frame.
        model.default_att_context_size = [56, args.right_context]
        stream = model.create_streaming_session(language=args.language)

    startup = time.monotonic() - loading
    packets: queue.Queue = queue.Queue(maxsize=600)
    cancel = threading.Event()
    producer_errors = []
    max_capture_lateness = 0.0
    max_consume_lag = 0.0
    events.started = time.monotonic()

    def capture():
        nonlocal max_capture_lateness
        try:
            for position in range(0, len(pcm), 2 * PACKET):
                chunk = pcm[position:position + 2 * PACKET]
                end = (position + len(chunk)) / (2 * RATE)
                if cancel.wait(max(0, events.started + end - time.monotonic())):
                    return
                max_capture_lateness = max(max_capture_lateness, time.monotonic() - events.started - end)
                packets.put_nowait((end, chunk))
            packets.put_nowait(None)
        except BaseException as error:
            producer_errors.append(error)
            cancel.set()

    producer = threading.Thread(target=capture, name="asr-fixture-capture")
    producer.start()
    input_done = False
    try:
        while True:
            if engine_errors:
                raise RuntimeError("Moonshine emitted an error") from engine_errors[0]
            if producer_errors:
                raise RuntimeError("Audio producer failed") from producer_errors[0]
            if args.engine.startswith("moonshine"):
                item = packets.get(timeout=max(10, duration + 10))
                if item is None:
                    transcript = stream.stop()
                    if engine_errors:
                        raise RuntimeError("Moonshine failed to finalize") from engine_errors[0]
                    if transcript is None:
                        raise RuntimeError("Moonshine did not return a final transcript")
                    for line in transcript.lines:
                        lines[line.line_id] = line
                    events.emit(" ".join(item.text for item in sorted(lines.values(), key=lambda item: item.start_time)),
                                event="final")
                    break
                end, chunk = item
                stream.add_audio((np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768).tolist(), RATE)
                max_consume_lag = max(max_consume_lag, time.monotonic() - events.started - end)
            else:
                if not input_done:
                    try:
                        item = packets.get_nowait()
                    except queue.Empty:
                        item = "waiting"
                    if item is None:
                        stream.close()
                        input_done = True
                    elif item != "waiting":
                        end, chunk = item
                        stream.feed(np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768)
                        max_consume_lag = max(max_consume_lag, time.monotonic() - events.started - end)
                deltas = stream.step(max_decode_tokens=4)
                if deltas:
                    events.emit(events.text + "".join(deltas), event="delta")
                if stream.done:
                    break
                if not deltas:
                    time.sleep(0.001)
        finished = time.monotonic() - events.started
        first_text = next((event["audio_wall_seconds"] for event in events.events if event["text"].strip()), None)
        report = {
            "duration_seconds": duration, "startup_seconds": startup,
            "first_text_seconds": first_text, "finish_seconds_after_audio": finished - duration,
            "text": events.text, "events": events.events,
            "max_capture_lateness_seconds": max_capture_lateness,
            "max_packet_consume_lag_seconds": max_consume_lag,
            "settings": {"packet_ms": 100, "moonshine_update_floor_seconds": 0.5,
                         "moonshine_options": options} if args.engine.startswith("moonshine") else
                        {"packet_ms": 100, "att_context_size": [56, args.right_context], "max_decode_tokens": 4},
        }
        if args.engine.startswith("moonshine"):
            report["native_final_lines"] = [
                {"line_id": line.line_id, "start_time": line.start_time,
                 "duration": line.duration, "text": line.text, "is_complete": line.is_complete}
                for line in transcript.lines
            ]
        save_json(args.output / "benchmark.json", report)
    finally:
        cancel.set()
        producer.join(timeout=5)
        if args.engine.startswith("moonshine"):
            stream.close()
            transcriber.close()
        elif not stream.done:
            stream.cancel()


def run(args) -> None:
    """Own one worker process group, collect a bounded report, and always reap it."""
    import os
    import psutil

    args.output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads(args.manifest.read_text())
    fixture = next(item for item in manifest["fixtures"] if item["id"] == args.case)
    args.audio = (args.manifest.parent / fixture["audio"]).resolve()
    if digest(args.audio) != fixture["sha256"]:
        raise ValueError("Fixture hash differs from its reference manifest")
    args.language = args.language or fixture["language"]
    if args.engine == "whisper":
        command = [str(args.whisper_python), str(ROOT / "scripts/benchmark_live_asr.py"), str(args.audio),
                   "--language", args.language, "--model", str(args.model), "--output", str(args.output)]
    else:
        command = [sys.executable, str(Path(__file__).resolve()), "worker", "--engine", args.engine,
                   "--audio", str(args.audio), "--language", args.language, "--model", str(args.model),
                   "--output", str(args.output), "--right-context", str(args.right_context)]
    peak_rss = 0
    process = None
    report = None
    try:
        with (args.output / "worker.log").open("w") as log:
            process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True,
                                       env={**os.environ, "HF_HUB_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false"})
            save_json(args.output / "process.json", {"pid": process.pid, "command": command})
            monitored = psutil.Process(process.pid)
            deadline = time.monotonic() + fixture["duration_seconds"] + 150
            while process.poll() is None:
                rss = 0
                try:
                    family = [monitored, *monitored.children(recursive=True)]
                except psutil.NoSuchProcess:
                    family = []
                for child in family:
                    try:
                        rss += child.memory_info().rss
                    except psutil.NoSuchProcess:
                        pass
                peak_rss = max(peak_rss, rss)
                if time.monotonic() >= deadline:
                    raise TimeoutError("ASR worker exceeded audio duration plus 150 seconds")
                time.sleep(0.05)
            if process.returncode:
                if args.engine == "whisper" and not fixture["reference"].strip() and process.returncode == 1:
                    report = whisper_silence_report((args.output / "worker.log").read_text(), fixture["duration_seconds"])
                if report is None:
                    raise RuntimeError(f"ASR worker exited {process.returncode}; see {args.output / 'worker.log'}")
        if report is None:
            report = json.loads((args.output / "benchmark.json").read_text())
        report.update({"engine": args.engine, "case": args.case, "language": args.language,
                       "model": str(args.model.resolve()), "audio_sha256": fixture["sha256"],
                       "reference": fixture["reference"], "synthetic": fixture.get("synthetic", False),
                       "peak_process_tree_rss_mib": peak_rss / (1024 * 1024),
                       "accuracy": accuracy(fixture["reference"], report["text"], fixture["language"])})
        save_json(args.output / "benchmark.json", report)
        print(json.dumps({key: value for key, value in report.items() if key != "events"}, ensure_ascii=False), flush=True)
    finally:
        if process is not None:
            # This process group was created exclusively for this benchmark.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    fixtures = modes.add_parser("fixtures")
    fixtures.add_argument("--output", type=Path, required=True)
    for name in ("run", "worker"):
        command = modes.add_parser(name)
        command.add_argument("--engine", choices=["whisper", "moonshine-en", "moonshine-zh", "nemotron"], required=True)
        command.add_argument("--model", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--language")
        command.add_argument("--right-context", type=int, choices=[0, 3, 6, 13], default=3)
        if name == "run":
            command.add_argument("--manifest", type=Path, required=True)
            command.add_argument("--case", required=True)
            command.add_argument("--whisper-python", type=Path, default=ROOT / ".venv/bin/python")
        else:
            command.add_argument("--audio", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "fixtures":
        make_fixtures(args.output)
    elif args.mode == "run":
        run(args)
    else:
        candidate_worker(args)


if __name__ == "__main__":
    main()
