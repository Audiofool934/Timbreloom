"""Bounded microphone sessions using the existing local Whisper weights."""
from __future__ import annotations

import re
import shutil
import threading
import time
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable

from .asr_service import ASRService, MAX_ASR_DURATION_SECONDS
from .job_storage import atomic_json, file_digest
from .transcripts import build_transcript, join_segment_texts, public_transcript_summary, save_transcript


SAMPLE_RATE = 16000
WINDOW_SECONDS = 28
UPDATE_SECONDS = 2
MAX_BUFFER_SECONDS = 60


class LiveHypothesis:
    """Commit a matching prefix from two decodes; keep the newest words revisable."""

    def __init__(self) -> None:
        self.words: list[dict] = []
        self.pending: list[dict] = []
        self.language = "auto"

    @property
    def committed_end(self) -> float:
        return self.words[-1]["end"] if self.words else 0.0

    @staticmethod
    def key(word: dict) -> str:
        return re.sub(r"\s+", "", word["word"]).casefold()

    def update(self, raw: dict, start: float, end: float, *, final: bool = False, force_before: float = 0) -> None:
        self.language = raw.get("language") or self.language
        candidates = []
        for segment in raw.get("segments", []):
            if segment.get("no_speech_prob", 0) > .6 and segment.get("avg_logprob", 0) < -1:
                continue
            words = segment.get("words") or [{"word": segment.get("text", ""),
                                              "start": segment.get("start", 0), "end": segment.get("end", end - start)}]
            for word in words:
                left = max(start, min(end, start + float(word["start"])))
                right = max(left, min(end, start + float(word["end"])))
                if not word["word"].strip() or (self.words and right < self.committed_end - .1):
                    continue
                candidates.append({"word": word["word"], "start": left, "end": right})
        # Whisper can give adjacent syllables the same timestamp. Resolve overlap
        # by matching words before clamping times, rather than dropping that tail.
        if self.words and candidates and candidates[0]["start"] < self.committed_end + .1:
            for size in range(min(8, len(self.words), len(candidates)), 0, -1):
                if [self.key(w) for w in self.words[-size:]] == [self.key(w) for w in candidates[:size]]:
                    candidates = candidates[size:]
                    break
        for word in candidates:
            word["start"] = max(word["start"], self.committed_end)
            word["end"] = max(word["end"], word["start"])
        count = 0
        for old, new in zip(self.pending, candidates):
            if self.key(old) != self.key(new) or abs(old["start"] - new["start"]) > 1.0 or new["end"] > end - .8:
                break
            count += 1
        if final:
            count = len(candidates)
        elif force_before:
            count = max(count, next((i for i, word in enumerate(candidates) if word["end"] > force_before), len(candidates)))
        self.words.extend(candidates[:count])
        self.pending = candidates[count:]

    @staticmethod
    def text(words: list[dict]) -> str:
        return join_segment_texts({"text": word["word"]} for word in words)

    def result(self, *, include_pending: bool = False) -> dict:
        words = self.words + (self.pending if include_pending else [])
        segments: list[dict] = []
        group: list[dict] = []
        for word in words:
            group.append(word)
            if word["end"] - group[0]["start"] >= 6 or word["word"].rstrip().endswith((".", "?", "!", "。", "？", "！")):
                segments.append({"start": group[0]["start"], "end": word["end"], "text": self.text(group), "words": group})
                group = []
        if group:
            segments.append({"start": group[0]["start"], "end": group[-1]["end"], "text": self.text(group), "words": group})
        return {"language": self.language, "text": self.text(words), "segments": segments}


class LiveASRSession:
    def __init__(self, service: ASRService, language: str, prompt: str, emit: Callable[[dict], None], model_key="whisper") -> None:
        self.service = service
        self.provider = service.provider_for(model_key)
        self.native_result = None
        self.emit = emit
        self.condition = threading.Condition()
        self.buffer = bytearray()
        self.offset = 0
        self.total = 0
        self.stopped = False
        self.hypothesis = LiveHypothesis()
        self.job_id = uuid.uuid4().hex
        directory = service.transcript_root / self.job_id
        directory.mkdir()
        self.audio = wave.open(str(directory / "source.wav"), "wb")
        self.audio.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        self.audio.writeframes(b"")
        self.job = service.create_job(
            job_id=self.job_id, transcript_dir=directory, source_path=directory / "source.wav",
            source_filename=f"Live recording {datetime.now():%Y-%m-%d %H-%M-%S}.wav",
            source_bytes=0, requested_language=language, initial_prompt=prompt,
            model_key=model_key,
        )
        self.thread = threading.Thread(target=self.run, name=f"live-asr-{self.job_id[:8]}", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def feed(self, pcm: bytes) -> None:
        if not pcm or len(pcm) % 2 or len(pcm) > SAMPLE_RATE * 2:
            raise ValueError("Send mono 16 kHz PCM16 in chunks of at most one second.")
        with self.condition:
            if self.stopped:
                return
            if self.total + len(pcm) // 2 > MAX_ASR_DURATION_SECONDS * SAMPLE_RATE:
                raise ValueError("The eight-hour recording limit was reached. Saving your transcript.")
            if len(self.buffer) + len(pcm) > MAX_BUFFER_SECONDS * SAMPLE_RATE * 2:
                raise ValueError("Whisper is falling behind. Stopping to save your recording and transcript.")
            # writeframes updates the WAV header, keeping received audio recoverable.
            self.audio.writeframes(pcm)
            self.buffer.extend(pcm)
            self.total += len(pcm) // 2
            self.condition.notify_all()

    def stop(self) -> None:
        with self.condition:
            self.stopped = True
            self.condition.notify_all()

    def abort(self) -> None:
        self.job.cancel_event.set()
        self.stop()

    def run(self) -> None:
        service, job = self.service, self.job
        last_end = 0
        checkpoint_at = 0.0
        started = time.monotonic()
        error = None
        try:
            import numpy as np

            service._update(job, status="running", phase="live", message=f"Preparing {self.provider.descriptor.name} for live transcription")
            self.emit({"type": "preparing", "job_id": self.job_id})
            if getattr(self.provider, "native_streaming", False):
                self.run_native()
                return
            with self.provider.live_engine(job.transcript_dir, job.cancel_event) as engine:
                self.emit({"type": "ready", "job_id": self.job_id, "sample_rate": SAMPLE_RATE})
                while True:
                    with self.condition:
                        self.condition.wait_for(lambda: self.stopped or self.total - last_end >= UPDATE_SECONDS * SAMPLE_RATE, timeout=.5)
                        if job.cancel_event.is_set():
                            raise InterruptedError("Live transcription stopped. Received audio was kept.")
                        if self.stopped and last_end >= self.total:
                            break
                        if not self.stopped and self.total - last_end < UPDATE_SECONDS * SAMPLE_RATE:
                            continue
                        end = min(self.total, self.offset + WINDOW_SECONDS * SAMPLE_RATE)
                        pcm = bytes(self.buffer[:(end - self.offset) * 2])
                        offset = self.offset
                        final = self.stopped and end == self.total
                    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
                    silence = not len(samples) or float(np.sqrt(np.mean(samples * samples))) < .001
                    quiet_tail = len(samples) >= SAMPLE_RATE and float(np.sqrt(np.mean(samples[-11200:] ** 2))) < .001
                    decode_started = time.monotonic()
                    if silence:
                        raw = {"segments": []}
                    else:
                        window = job.transcript_dir / "live-window.wav"
                        with wave.open(str(window), "wb") as audio:
                            audio.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                            audio.writeframes(pcm)
                        raw = engine.transcribe(window, None if job.requested_language == "auto" else job.requested_language, job.initial_prompt)
                    force_before = end / SAMPLE_RATE - 2 if end - offset >= WINDOW_SECONDS * SAMPLE_RATE else 0
                    self.hypothesis.update(raw, offset / SAMPLE_RATE, end / SAMPLE_RATE,
                                           final=final or quiet_tail, force_before=force_before)
                    # Keep context across updates, but never re-decode an ever-growing recording.
                    trim = int(max(0, self.hypothesis.committed_end - 2, force_before) * SAMPLE_RATE)
                    if silence or quiet_tail:
                        trim = end - 3200
                    with self.condition:
                        trim = max(self.offset, min(end, trim))
                        del self.buffer[:(trim - self.offset) * 2]
                        self.offset = trim
                        total = self.total
                    last_end = end
                    if time.monotonic() - checkpoint_at >= 15 or final:
                        atomic_json(job.transcript_dir / "raw" / "live.json", self.hypothesis.result(include_pending=True))
                        checkpoint_at = time.monotonic()
                    self.emit({"type": "partial", "job_id": self.job_id,
                               "text": self.hypothesis.text(self.hypothesis.words),
                               "draft": self.hypothesis.text(self.hypothesis.pending),
                               "duration_seconds": total / SAMPLE_RATE,
                               "processed_seconds": end / SAMPLE_RATE,
                               "decode_seconds": round(time.monotonic() - decode_started, 3)})
        except Exception as exc:
            error = str(exc)
        finally:
            self.stop()
            with self.condition:
                self.audio.close()
            try:
                self.save(error, time.monotonic() - started)
            except Exception as exc:
                service._update(job, status="error", phase="error", error=str(exc), message="Could not save the live transcript")
                self.emit({"type": "error", "message": str(exc), "job_id": self.job_id})
            (job.transcript_dir / "live-window.wav").unlink(missing_ok=True)

    def run_native(self) -> None:
        job = self.job
        checkpoint_at = 0.0
        with self.provider.live_engine(job.transcript_dir, job.cancel_event, job.requested_language, job.initial_prompt) as engine:
            self.emit({"type": "ready", "job_id": self.job_id, "sample_rate": SAMPLE_RATE})
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.stopped or bool(self.buffer), timeout=.5)
                    if job.cancel_event.is_set():
                        raise InterruptedError("Live transcription stopped. Received audio was kept.")
                    if not self.buffer and not self.stopped:
                        continue
                    count = min(len(self.buffer), 2 * SAMPLE_RATE)
                    pcm = bytes(self.buffer[:count])
                    del self.buffer[:count]
                    self.offset += count // 2
                    final = self.stopped and not self.buffer
                    total = self.total
                began = time.monotonic()
                self.native_result = engine.push(pcm, final=final)
                if final or time.monotonic() - checkpoint_at >= 15:
                    atomic_json(job.transcript_dir / "raw" / "live.json", self.native_result)
                    checkpoint_at = time.monotonic()
                self.emit({"type": "partial", "job_id": self.job_id,
                           "text": self.native_result.get("stable_text", ""),
                           "draft": self.native_result.get("draft", ""),
                           "duration_seconds": total / SAMPLE_RATE,
                           "processed_seconds": self.offset / SAMPLE_RATE,
                           "decode_seconds": round(time.monotonic() - began, 3)})
                if final:
                    break

    def save(self, error: str | None, elapsed: float) -> None:
        service, job = self.service, self.job
        duration = self.total / SAMPLE_RATE
        audio_path = job.transcript_dir / "audio.wav"
        shutil.copyfile(job.source_path, audio_path)
        raw = self.native_result or self.hypothesis.result(include_pending=True)
        atomic_json(job.transcript_dir / "raw" / "live.json", raw)
        changes = dict(source_bytes=job.source_path.stat().st_size, duration_seconds=duration,
                       audio_ready=True, audio_sha256=file_digest(audio_path))
        if not self.total and not error:
            service._update(job, **changes, status="cancelled", phase="cancelled", message="Live transcription start cancelled")
            self.emit({"type": "cancelled", "job_id": self.job_id})
        elif raw["text"]:
            transcript = build_transcript(
                transcript_id=self.job_id, raw_result=raw, source_filename=job.source_filename,
                source_bytes=changes["source_bytes"], duration_seconds=duration,
                engine="local-whisper-live" if job.model_key == "whisper" else f"local-{job.model_key}-live",
                model=getattr(self.provider, "model_id", self.provider.descriptor.name),
                requested_language=job.requested_language,
            )
            transcript["live"] = {"interrupted": bool(error), "elapsed_seconds": round(elapsed, 3)}
            save_transcript(job.transcript_dir, transcript)
            service._update(job, **changes, status="complete", phase="complete", progress=1,
                            result=public_transcript_summary(transcript), message="Live transcript saved", error=error)
            self.emit({"type": "complete", "job_id": self.job_id, "transcript_id": self.job_id, "warning": error})
        else:
            message = error or "No speech was recognized. Your recording is available below."
            service._update(job, **changes, status="error", phase="error", message=message, error=message)
            self.emit({"type": "error", "job_id": self.job_id, "message": message,
                       "audio_url": f"/api/asr/jobs/{self.job_id}/audio"})


class LiveASRService:
    def __init__(self, asr: ASRService) -> None:
        self.asr = asr
        self.lock = threading.Lock()
        self.session: LiveASRSession | None = None

    def start(self, language: str, prompt: str, emit: Callable[[dict], None], model_key="whisper") -> LiveASRSession:
        with self.lock:
            if self.session and self.session.thread.is_alive():
                raise ValueError("A live transcription is already running. Stop it before starting another.")
            provider = self.asr.validate_model(model_key, language, prompt)
            if not provider.descriptor.ready:
                raise ValueError(f"Download {provider.descriptor.name} from Models before starting live transcription.")
            self.session = LiveASRSession(self.asr, language, prompt, emit, model_key)
            self.session.start()
            return self.session

    def close(self) -> None:
        with self.lock:
            session = self.session
        if session and session.thread.is_alive():
            session.abort()
            session.thread.join(timeout=8)
