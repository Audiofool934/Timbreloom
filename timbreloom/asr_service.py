from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .media import prepare_asr_audio, probe_media
from .job_storage import atomic_json, file_digest, local_file
from .providers import ASRProvider, ASRRequest
from .transcripts import (
    build_transcript,
    load_transcript,
    public_transcript_summary,
    save_transcript,
    update_segment_texts,
    write_export,
)


MAX_ASR_DURATION_SECONDS = 8 * 60 * 60


@dataclass(slots=True)
class ASRJob:
    job_id: str
    transcript_dir: Path
    source_path: Path
    source_filename: str
    source_bytes: int
    requested_language: str
    initial_prompt: str
    created_at: str
    model_key: str = "whisper"
    status: str = "queued"
    phase: str = "queued"
    message: str = "Waiting to transcribe"
    progress: float = 0.0
    duration_seconds: float = 0.0
    audio_ready: bool = False
    audio_sha256: str = ""
    raw_ready: bool = False
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


class ASRService:
    def __init__(self, transcript_root: Path, provider: ASRProvider, providers: dict[str, ASRProvider] | None = None) -> None:
        self.transcript_root = transcript_root
        self.provider = provider
        self.providers = providers or {}
        self.transcript_root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, ASRJob] = {}
        self._jobs_lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self._transcript_lock = threading.Lock()

    def provider_for(self, model_key: str = "whisper") -> ASRProvider:
        if model_key == "whisper":
            return self.provider
        try:
            return self.providers[model_key]
        except (KeyError, TypeError) as exc:
            raise ValueError("Choose an available transcription model.") from exc

    def validate_model(self, model_key: str, language: str, prompt: str) -> ASRProvider:
        provider = self.provider_for(model_key)
        if hasattr(provider, "validate_request"):
            provider.validate_request(language, prompt)
        return provider

    def has_active_jobs(self) -> bool:
        with self._jobs_lock:
            return any(job.status in {"queued", "running"} for job in self._jobs.values())

    def create_job(
        self,
        *,
        job_id: str,
        transcript_dir: Path,
        source_path: Path,
        source_filename: str,
        source_bytes: int,
        requested_language: str,
        initial_prompt: str,
        model_key: str = "whisper",
    ) -> ASRJob:
        self.validate_model(model_key, requested_language, initial_prompt)
        job = ASRJob(
            job_id=job_id,
            transcript_dir=transcript_dir,
            source_path=source_path,
            source_filename=source_filename,
            source_bytes=source_bytes,
            requested_language=requested_language,
            initial_prompt=initial_prompt,
            created_at=datetime.now(timezone.utc).isoformat(),
            model_key=model_key,
        )
        with self._jobs_lock:
            self._jobs[job_id] = job
            self._persist(job)
        return job

    def launch(self, job: ASRJob) -> None:
        with self._jobs_lock:
            thread = self._threads.get(job.job_id)
            if thread and thread.is_alive():
                return
            thread = threading.Thread(
                target=self._process_job, args=(job,),
                name=f"asr-job-{job.job_id[:8]}", daemon=True,
            )
            self._threads[job.job_id] = thread
            thread.start()

    def _persist(self, job: ASRJob) -> None:
        payload = {
            item.name: getattr(job, item.name) for item in fields(job)
            if item.name not in {"transcript_dir", "source_path", "cancel_event"}
        }
        payload.update(
            schema_version=1, source_path=job.source_path.name,
            cancel_requested=job.cancel_event.is_set(),
            model=getattr(self.provider_for(job.model_key), "model_id", self.provider_for(job.model_key).descriptor.name),
        )
        atomic_json(job.transcript_dir / "job.json", payload)

    def _update(self, job: ASRJob, **changes: Any) -> None:
        with self._jobs_lock:
            for key, value in changes.items():
                setattr(job, key, value)
            self._persist(job)

    def snapshot(self, job: ASRJob) -> dict[str, Any]:
        with self._jobs_lock:
            return {
                "job_id": job.job_id,
                "status": job.status,
                "phase": job.phase,
                "message": job.message,
                "progress": round(job.progress, 4),
                "source_filename": job.source_filename,
                "duration_seconds": round(job.duration_seconds, 3),
                "audio_ready": job.audio_ready,
                "created_at": job.created_at,
                "model_key": job.model_key,
                "result": job.result,
                "error": job.error,
            }

    def get_job(self, job_id: str) -> ASRJob:
        directory = self.transcript_dir(job_id)
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is not None:
                return job
            try:
                payload = json.loads((directory / "job.json").read_text(encoding="utf-8"))
                if payload["schema_version"] != 1 or payload["job_id"] != job_id:
                    raise ValueError("Unsupported transcription job format.")
                source = local_file(directory, payload["source_path"])
                kwargs = {
                    item.name: (payload.get("model_key", "whisper") if item.name == "model_key" else payload[item.name]) for item in fields(ASRJob)
                    if item.name not in {"transcript_dir", "source_path", "cancel_event"}
                }
                job = ASRJob(**kwargs, transcript_dir=directory, source_path=source)
                provider = self.provider_for(job.model_key)
                if payload.get("model") != getattr(provider, "model_id", provider.descriptor.name):
                    job.raw_ready = False
                if payload.get("cancel_requested"):
                    job.cancel_event.set()
                self._jobs[job_id] = job
                return job
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise FileNotFoundError("Transcription job not found or its record is damaged.") from exc

    def recover(self) -> int:
        recovered = 0
        for path in self.transcript_root.glob("*/job.json"):
            try:
                job = self.get_job(path.parent.name)
            except FileNotFoundError:
                continue
            if job.status not in {"queued", "running"}:
                continue
            if job.cancel_event.is_set():
                self._update(job, status="cancelled", phase="cancelled",
                             message="Previous stop request confirmed after service restart")
                continue
            self._update(job, status="queued", phase="queued", error=None,
                         message="Resuming local transcription after service restart")
            self.launch(job)
            recovered += 1
        return recovered

    def cancel(self, job_id: str) -> ASRJob:
        job = self.get_job(job_id)
        if job.status in {"complete", "error", "cancelled"}:
            return job
        with self._jobs_lock:
            job.cancel_event.set()
            self._update(job, message="Stopping transcription")
        return job

    def _process_job(self, job: ASRJob) -> None:
        started = time.perf_counter()
        audio_path = job.transcript_dir / "audio.wav"
        raw_path = job.transcript_dir / "raw" / f"{job.model_key}.json"
        try:
            provider = self.provider_for(job.model_key)
            self._update(
                job,
                status="running",
                phase="probing",
                message="Checking media file",
                progress=0.05,
            )
            media_info = probe_media(job.source_path)
            if not media_info.has_audio:
                raise ValueError("The media file has no usable audio track.")
            if media_info.duration_seconds <= 0:
                raise ValueError("Cannot determine media duration.")
            if media_info.duration_seconds > MAX_ASR_DURATION_SECONDS:
                raise ValueError("Transcription files must be no longer than 8 hours.")
            self._update(job, duration_seconds=media_info.duration_seconds)

            if job.cancel_event.is_set():
                raise InterruptedError("Transcription canceled.")

            self._update(
                job,
                phase="preparing",
                message="Extracting and normalizing audio",
                progress=0.14,
            )
            if not (job.audio_ready and audio_path.is_file()
                    and file_digest(audio_path) == job.audio_sha256):
                self._update(job, audio_ready=False, raw_ready=False)
                prepare_asr_audio(job.source_path, audio_path)
                self._update(job, audio_ready=True, audio_sha256=file_digest(audio_path))

            if job.cancel_event.is_set():
                raise InterruptedError("Transcription canceled.")

            self._update(
                job,
                phase="transcribing",
                message=f"Transcribing with {provider.descriptor.name}. Audio stays on this Mac.",
                progress=0.24,
            )
            language = None if job.requested_language == "auto" else job.requested_language
            raw_result = None
            if job.raw_ready:
                try:
                    raw_result = json.loads(raw_path.read_text(encoding="utf-8"))
                    if not isinstance(raw_result, dict) or "segments" not in raw_result:
                        raw_result = None
                except (OSError, ValueError):
                    pass
            if raw_result is None:
                raw_result = provider.transcribe(
                    ASRRequest(
                        audio_path=audio_path,
                        language=language,
                        raw_output_path=raw_path,
                        initial_prompt=job.initial_prompt,
                    ),
                    cancel_event=job.cancel_event,
                )
                atomic_json(raw_path, raw_result)
                self._update(job, raw_ready=True)

            if job.cancel_event.is_set():
                raise InterruptedError("Transcription canceled.")

            self._update(
                job,
                phase="saving",
                message="Saving timestamps and subtitles",
                progress=0.9,
            )
            transcript = build_transcript(
                transcript_id=job.job_id,
                raw_result=raw_result,
                source_filename=job.source_filename,
                source_bytes=job.source_bytes,
                duration_seconds=media_info.duration_seconds,
                engine=provider.descriptor.provider_id,
                model=getattr(provider, "model_id", provider.descriptor.name),
                requested_language=job.requested_language,
            )
            save_transcript(job.transcript_dir, transcript)
            qa = {
                "engine": transcript["engine"],
                "model": transcript["model"],
                "source_filename": job.source_filename,
                "duration_seconds": media_info.duration_seconds,
                "segment_count": len(transcript["segments"]),
                "text_nonempty": bool(transcript["text"].strip()),
                "timestamps_preserved": True,
                "offline": True,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
            qa_path = job.transcript_dir / "qa.json"
            qa_path.write_text(
                json.dumps(qa, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            summary = public_transcript_summary(transcript)
            self._update(
                job,
                status="complete",
                phase="complete",
                message="Local transcription complete",
                progress=1.0,
                result=summary,
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
                message="Transcription did not complete",
                error=str(exc),
            )

    def transcript_dir(self, transcript_id: str) -> Path:
        if not transcript_id or not all(character in "0123456789abcdef" for character in transcript_id):
            raise FileNotFoundError("Transcript not found.")
        if len(transcript_id) != 32:
            raise FileNotFoundError("Transcript not found.")
        return self.transcript_root / transcript_id

    def source_media(self, transcript_id: str) -> Path:
        transcript_dir = self.transcript_dir(transcript_id)
        self.get_transcript(transcript_id)
        candidates = sorted(
            path
            for path in transcript_dir.glob("source.*")
            if path.is_file()
        )
        if len(candidates) != 1:
            raise FileNotFoundError("The original transcript media is missing or ambiguous.")
        return candidates[0]

    def get_transcript(self, transcript_id: str) -> dict[str, Any]:
        return load_transcript(self.transcript_dir(transcript_id))

    def list_transcripts(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for path in self.transcript_root.glob("*/transcript.json"):
            try:
                summaries.append(public_transcript_summary(load_transcript(path.parent)))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        summaries.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return summaries

    def update_transcript(
        self,
        transcript_id: str,
        updates: dict[str, str],
    ) -> dict[str, Any]:
        transcript_dir = self.transcript_dir(transcript_id)
        with self._transcript_lock:
            transcript = load_transcript(transcript_dir)
            updated = update_segment_texts(transcript, updates)
            save_transcript(transcript_dir, updated)
        return updated

    def export(self, transcript_id: str, export_format: str) -> Path:
        transcript_dir = self.transcript_dir(transcript_id)
        transcript = load_transcript(transcript_dir)
        return write_export(transcript_dir, transcript, export_format)
