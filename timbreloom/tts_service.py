from __future__ import annotations

import json
import re
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable

from .audio import stitch_wav_files, wav_duration
from .job_storage import atomic_json, file_digest, local_file
from .segmentation import AUDIO_TOKENS_PER_SECOND, GENERATION_TOKEN_LIMIT, TextSegment


@dataclass(slots=True)
class GenerationJob:
    job_id: str
    voice_id: str | None
    voice_name: str
    reference_source: Path
    reference_is_normalized: bool
    reference_text: str
    reference_duration_seconds: float | None
    language: str
    segments: list[TextSegment]
    job_dir: Path
    created_at: str
    title: str = ""
    status: str = "queued"
    phase: str = "queued"
    message: str = "Waiting to generate"
    progress: float = 0.0
    segments_completed: int = 0
    current_segment: int = 0
    current_text: str = ""
    stream_chunks: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


class TTSService:
    """Own durable cloning jobs and resume their verified completed prefix."""

    def __init__(
        self,
        root: Path,
        output_root: Path,
        *,
        generate_segment: Callable,
        normalize_audio: Callable,
        model_id: str,
        settings: dict[str, Any],
        max_attempts: int = 2,
    ) -> None:
        self.root = root
        self.output_root = output_root
        self.generate_segment = generate_segment
        self.normalize_audio = normalize_audio
        self.model_id = model_id
        self.settings = settings
        self.max_attempts = max_attempts
        self._lock = threading.RLock()
        self._jobs: dict[str, GenerationJob] = {}
        self._threads: dict[str, threading.Thread] = {}
        root.mkdir(parents=True, exist_ok=True)
        output_root.mkdir(parents=True, exist_ok=True)

    def has_active_jobs(self) -> bool:
        with self._lock:
            return any(job.status in {"queued", "running"} for job in self._jobs.values())

    def add(self, job: GenerationJob) -> None:
        # A job owns its reference so a restart never depends on a temporary upload.
        if job.reference_source.parent != job.job_dir:
            destination = job.job_dir / f"source{job.reference_source.suffix}"
            shutil.copyfile(job.reference_source, destination)
            job.reference_source = destination
        with self._lock:
            self._jobs[job.job_id] = job
            self._persist(job)

    def _persist(self, job: GenerationJob) -> None:
        payload = {
            item.name: getattr(job, item.name)
            for item in fields(job)
            if item.name
            not in {"job_dir", "reference_source", "cancel_event", "segments"}
        }
        payload.update(
            schema_version=1,
            reference_source=job.reference_source.name,
            segments=[asdict(segment) for segment in job.segments],
            cancel_requested=job.cancel_event.is_set(),
            model_id=self.model_id,
            settings=self.settings,
        )
        atomic_json(job.job_dir / "job.json", payload)

    def _update(self, job: GenerationJob, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)
            self._persist(job)

    def get_job(self, job_id: str) -> GenerationJob:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise FileNotFoundError("Generation job not found.")
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]
            directory = self.root / job_id
            try:
                payload = json.loads(
                    (directory / "job.json").read_text(encoding="utf-8")
                )
                if payload["schema_version"] != 1 or payload["job_id"] != job_id:
                    raise ValueError("Unsupported generation job format.")
                reference = local_file(directory, payload["reference_source"])
                segments = [TextSegment(**segment) for segment in payload["segments"]]
                kwargs = {
                    item.name: payload[item.name]
                    for item in fields(GenerationJob)
                    if item.name
                    not in {"job_dir", "reference_source", "cancel_event", "segments"}
                    and item.name in payload
                }
                job = GenerationJob(
                    **kwargs,
                    job_dir=directory,
                    reference_source=reference,
                    segments=segments,
                )
                if payload.get("cancel_requested"):
                    job.cancel_event.set()
                if job.status in {"queued", "running"} and (
                    payload.get("model_id") != self.model_id
                    or payload.get("settings") != self.settings
                ):
                    job.status = job.phase = "error"
                    job.error = job.message = (
                        "Generation settings have changed. Create a new job to avoid mixing segments from different settings."
                    )
                self._jobs[job_id] = job
                return job
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise FileNotFoundError("Generation job not found or its record is damaged.") from exc

    def _validate_chunks(self, job: GenerationJob) -> None:
        valid = []
        for index, chunk in enumerate(job.stream_chunks, start=1):
            path = job.job_dir / f"segment-{index:05d}.wav"
            if (
                index > len(job.segments)
                or chunk["index"] != index
                or not path.is_file()
                or file_digest(path) != chunk.get("sha256")
            ):
                break
            valid.append(chunk)
        self._update(job, stream_chunks=valid, segments_completed=len(valid))

    def launch(self, job: GenerationJob) -> None:
        with self._lock:
            thread = self._threads.get(job.job_id)
            if thread and thread.is_alive():
                return
            thread = threading.Thread(
                target=self.process,
                args=(job,),
                name=f"voice-job-{job.job_id[:8]}",
                daemon=True,
            )
            self._threads[job.job_id] = thread
            thread.start()

    def recover(self) -> int:
        recovered = 0
        for path in self.root.glob("*/job.json"):
            try:
                job = self.get_job(path.parent.name)
            except FileNotFoundError:
                continue
            if job.status not in {"queued", "running"}:
                continue
            if job.cancel_event.is_set():
                self._update(
                    job,
                    status="cancelled",
                    phase="cancelled",
                    message="Previous stop request confirmed after service restart",
                )
                continue
            self._update(
                job,
                status="queued",
                phase="queued",
                error=None,
                message="Resuming generation after service restart, reusing completed segments",
            )
            self.launch(job)
            recovered += 1
        return recovered

    def cancel(self, job_id: str) -> GenerationJob:
        job = self.get_job(job_id)
        with self._lock:
            if job.status in {"queued", "running"}:
                job.cancel_event.set()
                self._update(job, message="Canceling after the current segment")
        return job

    def voice_in_use(self, voice_id: str) -> bool:
        with self._lock:
            return any(
                job.voice_id == voice_id and job.status in {"queued", "running"}
                for job in self._jobs.values()
            )

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            items = []
            for path in self.root.glob("*/job.json"):
                try:
                    items.append(self.snapshot(self.get_job(path.parent.name), include_input=False))
                except FileNotFoundError:
                    continue
            return sorted(items, key=lambda item: item["created_at"], reverse=True)

    def rename(self, job_id: str, title: str) -> GenerationJob:
        with self._lock:
            job = self.get_job(job_id)
            self._update(job, title=title)
            return job

    def delete(self, job_id: str) -> None:
        with self._lock:
            job = self.get_job(job_id)
            thread = self._threads.get(job_id)
            if job.status in {"queued", "running"} or (thread and thread.is_alive()):
                raise ValueError("Stop this generation and wait for it to finish before deleting it.")
            # Derive owned exports from the ID, never from a filename in metadata.
            for name in (f"timbreloom-long-{job_id}.wav", f"timbreloom-long-{job_id}.tmp.wav"):
                (self.output_root / name).unlink(missing_ok=True)
            shutil.rmtree(job.job_dir)
            self._jobs.pop(job_id, None)
            self._threads.pop(job_id, None)

    def snapshot(self, job: GenerationJob, *, include_input: bool = True) -> dict[str, Any]:
        with self._lock:
            stream_chunks = [
                {
                    **chunk,
                    "audio_url": (
                        f"/api/jobs/{job.job_id}/segments/{chunk['index']}/audio"
                    ),
                }
                for chunk in job.stream_chunks
            ]
            snapshot = {
                "job_id": job.job_id,
                "title": job.title or " ".join("".join(segment.text for segment in job.segments).split())[:80] or "Untitled speech",
                "status": job.status,
                "phase": job.phase,
                "message": job.message,
                "progress": round(job.progress, 4),
                "segment_total": len(job.segments),
                "segments_completed": job.segments_completed,
                "current_segment": job.current_segment,
                "current_text": job.current_text,
                "voice_name": job.voice_name,
                "created_at": job.created_at,
                "error": job.error,
                "result": job.result,
                "stream": {
                    "kind": "generated",
                    "available": len(stream_chunks),
                    "total": len(job.segments),
                    "complete": job.status == "complete",
                    "chunks": stream_chunks,
                },
            }
            if include_input:
                snapshot.update(
                    target_text="".join(segment.text for segment in job.segments),
                    voice_id=job.voice_id,
                    language=job.language,
                    reference_text=job.reference_text,
                    reference_url=f"/api/jobs/{job.job_id}/reference",
                    reference_filename=job.reference_source.name,
                )
        return snapshot

    def process(self, job: GenerationJob) -> None:
        started = time.perf_counter()
        segment_paths: list[Path] = []
        peak_memory = 0.0
        reference_path = job.reference_source

        try:
            self._validate_chunks(job)
            self._update(
                job,
                status="running",
                phase="preparing",
                message="Preparing the reference voice",
                progress=0.02,
            )

            if not job.reference_is_normalized:
                reference_path = job.job_dir / "reference.wav"
                duration = self.normalize_audio(job.reference_source, reference_path)
                self._update(job, reference_duration_seconds=duration)

            if job.cancel_event.is_set():
                raise InterruptedError("Generation canceled.")

            total = len(job.segments)
            for index, segment in enumerate(job.segments, start=1):
                if job.cancel_event.is_set():
                    raise InterruptedError("Generation canceled.")

                preview = " ".join(segment.text.split())
                preview_text = preview if len(preview) <= 180 else f"{preview[:177]}..."
                self._update(
                    job,
                    phase="generating",
                    message=f"Generating segment {index} of {total}",
                    current_segment=index,
                    current_text=preview_text,
                    progress=0.04 + 0.88 * ((index - 1) / total),
                )

                segment_path = job.job_dir / f"segment-{index:05d}.wav"
                if index <= len(job.stream_chunks):
                    segment_paths.append(segment_path)
                    continue
                last_error: Exception | None = None
                metrics: dict[str, float] | None = None
                for attempt in range(1, self.max_attempts + 1):
                    try:
                        metrics = self.generate_segment(
                            reference_path,
                            job.reference_text,
                            segment.text,
                            job.language,
                            segment_path,
                        )
                        expected_duration = (
                            segment.estimated_audio_tokens / AUDIO_TOKENS_PER_SECOND
                        )
                        if (
                            segment.estimated_audio_tokens >= 240
                            and metrics["duration_seconds"] < expected_duration * 0.35
                        ):
                            segment_path.unlink(missing_ok=True)
                            raise RuntimeError(
                                "The generated audio is too short for this text and may contain skipped words."
                            )
                        break
                    except Exception as exc:
                        last_error = exc
                        metrics = None
                        if attempt < self.max_attempts:
                            self._update(job, message=f"Retrying segment {index}")
                            time.sleep(0.25)

                if metrics is None:
                    raise RuntimeError(f"Segment {index} failed: {last_error}")

                segment_paths.append(segment_path)
                peak_memory = max(peak_memory, metrics["peak_memory_gb"])
                duration = wav_duration(segment_path)
                stream_chunks = [
                    *job.stream_chunks,
                    {
                        "index": index,
                        "duration_seconds": round(duration, 3),
                        "label": preview_text,
                        "sha256": file_digest(segment_path),
                    },
                ]
                self._update(
                    job,
                    segments_completed=index,
                    progress=0.04 + 0.88 * (index / total),
                    stream_chunks=stream_chunks,
                )

            if job.cancel_event.is_set():
                raise InterruptedError("Generation canceled.")

            self._update(
                job,
                phase="assembling",
                message="Joining all segments without re-encoding",
                progress=0.95,
                current_text="",
            )
            filename = f"timbreloom-long-{job.job_id}.wav"
            output_path = self.output_root / filename
            temporary_output = output_path.with_suffix(".tmp.wav")
            generated_duration = stitch_wav_files(segment_paths, temporary_output)
            temporary_output.replace(output_path)
            elapsed = time.perf_counter() - started
            result = {
                "ok": True,
                "audio_url": f"/outputs/{filename}",
                "filename": filename,
                "model": self.model_id,
                "voice_name": job.voice_name,
                "reference_duration_seconds": round(
                    job.reference_duration_seconds or 0.0, 2
                ),
                "audio_duration_seconds": round(generated_duration, 2),
                "generation_seconds": round(elapsed, 2),
                "peak_memory_gb": round(peak_memory, 2),
                "segment_count": len(job.segments),
                "text_characters": sum(len(segment.text) for segment in job.segments),
                "generation_token_limit_per_segment": GENERATION_TOKEN_LIMIT,
            }
            self._update(
                job,
                status="complete",
                phase="complete",
                message="All segments generated and joined",
                progress=1.0,
                current_segment=len(job.segments),
                result=result,
            )
        except InterruptedError as exc:
            self._update(
                job,
                status="cancelled",
                phase="cancelled",
                message=str(exc),
                error=str(exc),
            )
        except Exception as exc:
            self._update(
                job,
                status="error",
                phase="error",
                message="Generation stopped. Failed segments were not skipped.",
                error=str(exc),
            )
