from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .media import prepare_asr_audio, probe_media
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
    status: str = "queued"
    phase: str = "queued"
    message: str = "等待转录"
    progress: float = 0.0
    duration_seconds: float = 0.0
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


class ASRService:
    def __init__(self, transcript_root: Path, provider: ASRProvider) -> None:
        self.transcript_root = transcript_root
        self.provider = provider
        self.transcript_root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, ASRJob] = {}
        self._jobs_lock = threading.Lock()
        self._transcript_lock = threading.Lock()

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
    ) -> ASRJob:
        job = ASRJob(
            job_id=job_id,
            transcript_dir=transcript_dir,
            source_path=source_path,
            source_filename=source_filename,
            source_bytes=source_bytes,
            requested_language=requested_language,
            initial_prompt=initial_prompt,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._jobs_lock:
            self._jobs[job_id] = job
        return job

    def launch(self, job: ASRJob) -> None:
        threading.Thread(
            target=self._process_job,
            args=(job,),
            name=f"asr-job-{job.job_id[:8]}",
            daemon=True,
        ).start()

    def _update(self, job: ASRJob, **changes: Any) -> None:
        with self._jobs_lock:
            for key, value in changes.items():
                setattr(job, key, value)

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
                "created_at": job.created_at,
                "result": job.result,
                "error": job.error,
            }

    def get_job(self, job_id: str) -> ASRJob:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise FileNotFoundError("转录任务不存在。")
        return job

    def cancel(self, job_id: str) -> ASRJob:
        job = self.get_job(job_id)
        if job.status in {"complete", "error", "cancelled"}:
            return job
        job.cancel_event.set()
        self._update(job, message="正在停止转录")
        return job

    def _process_job(self, job: ASRJob) -> None:
        started = time.perf_counter()
        audio_path = job.transcript_dir / "audio.wav"
        raw_path = job.transcript_dir / "raw" / "whisper.json"
        try:
            self._update(
                job,
                status="running",
                phase="probing",
                message="正在检查媒体文件",
                progress=0.05,
            )
            media_info = probe_media(job.source_path)
            if not media_info.has_audio:
                raise ValueError("媒体文件中没有可用音轨。")
            if media_info.duration_seconds <= 0:
                raise ValueError("无法确定媒体时长。")
            if media_info.duration_seconds > MAX_ASR_DURATION_SECONDS:
                raise ValueError("单个转录文件最长支持 8 小时。")
            self._update(job, duration_seconds=media_info.duration_seconds)

            if job.cancel_event.is_set():
                raise InterruptedError("转录已取消。")

            self._update(
                job,
                phase="preparing",
                message="正在提取并标准化音频",
                progress=0.14,
            )
            prepare_asr_audio(job.source_path, audio_path)

            if job.cancel_event.is_set():
                raise InterruptedError("转录已取消。")

            self._update(
                job,
                phase="transcribing",
                message="正在使用本地 Whisper 转录，音频不会上传",
                progress=0.24,
            )
            language = None if job.requested_language == "auto" else job.requested_language
            raw_result = self.provider.transcribe(
                ASRRequest(
                    audio_path=audio_path,
                    language=language,
                    raw_output_path=raw_path,
                    initial_prompt=job.initial_prompt,
                ),
                cancel_event=job.cancel_event,
            )

            if job.cancel_event.is_set():
                raise InterruptedError("转录已取消。")

            self._update(
                job,
                phase="saving",
                message="正在保存时间戳和字幕数据",
                progress=0.9,
            )
            transcript = build_transcript(
                transcript_id=job.job_id,
                raw_result=raw_result,
                source_filename=job.source_filename,
                source_bytes=job.source_bytes,
                duration_seconds=media_info.duration_seconds,
                engine=self.provider.descriptor.provider_id,
                model=getattr(self.provider, "model_id", self.provider.descriptor.name),
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
                message="本地转录完成",
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
                message="转录没有完成",
                error=str(exc),
            )

    def transcript_dir(self, transcript_id: str) -> Path:
        if not transcript_id or not all(character in "0123456789abcdef" for character in transcript_id):
            raise FileNotFoundError("转录不存在。")
        if len(transcript_id) != 32:
            raise FileNotFoundError("转录不存在。")
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
            raise FileNotFoundError("转录的原始媒体不存在或不唯一。")
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
