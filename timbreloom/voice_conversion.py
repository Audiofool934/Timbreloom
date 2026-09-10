from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .audio import stitch_wav_files
from .media import (
    detect_silence_midpoints,
    extract_vc_chunk,
    mux_dubbed_video,
    prepare_vc_audio,
    probe_media,
)
from .providers import VCProvider, VCRequest, VCResult


MAX_VC_DURATION_SECONDS = 8 * 60 * 60
VC_CHUNK_TARGET_SECONDS = 4 * 60
VC_CHUNK_MIN_SECONDS = 90
VC_CHUNK_MAX_SECONDS = 6 * 60
VC_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "label": "Fast",
        "diffusion_steps": 4,
        "inference_cfg_rate": 0.7,
        "description": "Faster previews with slightly lower voice similarity.",
    },
    "balanced": {
        "label": "Balanced",
        "diffusion_steps": 8,
        "inference_cfg_rate": 0.7,
        "description": "Recommended balance of voice similarity, rhythm, and speed.",
    },
    "quality": {
        "label": "High quality",
        "diffusion_steps": 12,
        "inference_cfg_rate": 0.7,
        "description": "Slower processing for final exports.",
    },
}


def plan_vc_chunks(
    duration_seconds: float,
    silence_midpoints: list[float],
) -> list[tuple[float, float]]:
    """Plan bounded, contiguous chunks and prefer cuts inside nearby pauses."""
    if duration_seconds <= 0:
        raise ValueError("Voice conversion audio duration must be greater than 0.")
    if duration_seconds <= VC_CHUNK_MAX_SECONDS:
        return [(0.0, duration_seconds)]

    safe_silences = sorted(
        point for point in silence_midpoints if 0.0 < point < duration_seconds
    )
    chunks: list[tuple[float, float]] = []
    start = 0.0
    while duration_seconds - start > VC_CHUNK_MAX_SECONDS:
        earliest = start + VC_CHUNK_MIN_SECONDS
        latest = min(
            start + VC_CHUNK_MAX_SECONDS,
            duration_seconds - VC_CHUNK_MIN_SECONDS,
        )
        ideal = min(start + VC_CHUNK_TARGET_SECONDS, latest)
        candidates = [point for point in safe_silences if earliest <= point <= latest]
        cut = min(candidates, key=lambda point: abs(point - ideal)) if candidates else latest
        if cut <= start:
            raise ValueError("Cannot create safe voice conversion audio segments.")
        chunks.append((round(start, 3), round(cut, 3)))
        start = cut
    chunks.append((round(start, 3), round(duration_seconds, 3)))
    return chunks


@dataclass(slots=True)
class VoiceConversionJob:
    job_id: str
    job_dir: Path
    source_path: Path
    source_filename: str
    source_bytes: int
    voice_id: str
    voice_name: str
    preset: str
    created_at: str
    status: str = "queued"
    phase: str = "queued"
    message: str = "Waiting for voice conversion"
    progress: float = 0.0
    duration_seconds: float = 0.0
    source_has_video: bool = False
    chunk_total: int = 0
    chunks_completed: int = 0
    current_chunk: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    updated_at: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event)


class VoiceConversionService:
    def __init__(
        self,
        conversion_root: Path,
        provider: VCProvider,
        load_voice: Callable[[str], dict[str, Any]],
    ) -> None:
        self.conversion_root = conversion_root
        self.provider = provider
        self.load_voice = load_voice
        self.conversion_root.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, VoiceConversionJob] = {}
        self._lock = threading.Lock()

    def has_active_jobs(self) -> bool:
        with self._lock:
            return any(job.status in {"queued", "running"} for job in self._jobs.values())

    @staticmethod
    def _valid_id(value: str) -> bool:
        return len(value) == 32 and all(character in "0123456789abcdef" for character in value)

    def _metadata_path(self, job: VoiceConversionJob) -> Path:
        return job.job_dir / "conversion.json"

    def _serialize_unlocked(self, job: VoiceConversionJob) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "id": job.job_id,
            "status": job.status,
            "phase": job.phase,
            "message": job.message,
            "progress": round(job.progress, 4),
            "source_filename": job.source_filename,
            "source_storage_filename": job.source_path.name,
            "source_bytes": job.source_bytes,
            "source_has_video": job.source_has_video,
            "duration_seconds": round(job.duration_seconds, 3),
            "voice_id": job.voice_id,
            "voice_name": job.voice_name,
            "preset": job.preset,
            "chunk_total": job.chunk_total,
            "chunks_completed": job.chunks_completed,
            "current_chunk": job.current_chunk,
            "stream_chunks": self._available_stream_chunks_unlocked(job),
            "created_at": job.created_at,
            "updated_at": job.updated_at or job.created_at,
            "result": dict(job.result) if job.result is not None else None,
            "error": job.error,
        }

    def _persist_unlocked(self, job: VoiceConversionJob) -> None:
        job.updated_at = datetime.now(timezone.utc).isoformat()
        temporary = self._metadata_path(job).with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self._serialize_unlocked(job), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._metadata_path(job))

    def _update(self, job: VoiceConversionJob, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)
            self._persist_unlocked(job)

    def create_job(
        self,
        *,
        job_id: str,
        source_path: Path,
        source_filename: str,
        source_bytes: int,
        voice_id: str,
        voice_name: str,
        preset: str,
    ) -> VoiceConversionJob:
        if preset not in VC_PRESETS:
            raise ValueError("Invalid voice conversion quality preset.")
        job = VoiceConversionJob(
            job_id=job_id,
            job_dir=source_path.parent,
            source_path=source_path,
            source_filename=source_filename,
            source_bytes=source_bytes,
            voice_id=voice_id,
            voice_name=voice_name,
            preset=preset,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._jobs[job_id] = job
            self._persist_unlocked(job)
        return job

    def launch(self, job: VoiceConversionJob) -> None:
        threading.Thread(
            target=self._process_job,
            args=(job,),
            name=f"vc-job-{job.job_id[:8]}",
            daemon=True,
        ).start()

    def _progress(self, job: VoiceConversionJob, progress: float, message: str) -> None:
        overall = 0.18 + min(1.0, max(0.0, progress)) * 0.72
        self._update(
            job,
            phase="converting",
            progress=min(0.9, overall),
            message=message,
        )

    @staticmethod
    def _chunk_manifest_path(job: VoiceConversionJob) -> Path:
        return job.job_dir / "vc-chunks.json"

    def _available_stream_chunks_unlocked(
        self,
        job: VoiceConversionJob,
    ) -> list[dict[str, Any]]:
        path = self._chunk_manifest_path(job)
        if not path.is_file():
            return []
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            entries = manifest.get("chunks", [])
            if not isinstance(entries, list):
                return []
            available = []
            total = len(entries)
            for entry in entries:
                index = int(entry["index"])
                if entry.get("status") != "complete":
                    break
                audio_path = (
                    job.job_dir / "converted.wav"
                    if total == 1
                    else job.job_dir / "chunks" / f"converted-{index:05d}.wav"
                )
                if not audio_path.is_file():
                    break
                available.append(
                    {
                        "index": index,
                        "duration_seconds": round(
                            float(entry["end"]) - float(entry["start"]), 3
                        ),
                        "label": f"Segment {index}",
                    }
                )
            return available
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return []

    def _write_chunk_manifest(
        self,
        job: VoiceConversionJob,
        manifest: dict[str, Any],
    ) -> None:
        path = self._chunk_manifest_path(job)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)

    def _load_chunk_manifest(
        self,
        job: VoiceConversionJob,
        duration_seconds: float,
    ) -> dict[str, Any] | None:
        path = self._chunk_manifest_path(job)
        if not path.is_file():
            return None
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            chunks = manifest["chunks"]
            if manifest.get("schema_version") != 1 or not isinstance(chunks, list):
                return None
            if abs(float(manifest["source_duration_seconds"]) - duration_seconds) > 0.1:
                return None
            previous_end = 0.0
            for index, chunk in enumerate(chunks, start=1):
                start = float(chunk["start"])
                end = float(chunk["end"])
                if int(chunk["index"]) != index or abs(start - previous_end) > 0.01:
                    return None
                if end <= start or end - start > VC_CHUNK_MAX_SECONDS + 0.1:
                    return None
                previous_end = end
            if not chunks or abs(previous_end - duration_seconds) > 0.1:
                return None
            return manifest
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def _new_chunk_manifest(
        self,
        job: VoiceConversionJob,
        duration_seconds: float,
        chunks: list[tuple[float, float]],
    ) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "source_duration_seconds": round(duration_seconds, 3),
            "chunks": [
                {
                    "index": index,
                    "start": start,
                    "end": end,
                    "status": "pending",
                    "generation_seconds": 0.0,
                }
                for index, (start, end) in enumerate(chunks, start=1)
            ],
        }
        self._write_chunk_manifest(job, manifest)
        return manifest

    def _process_job(self, job: VoiceConversionJob) -> None:
        prepared_path = job.job_dir / "source-audio.wav"
        output_path = job.job_dir / "converted.wav"
        try:
            self._update(
                job,
                status="running",
                phase="probing",
                message="Checking source media",
                progress=0.04,
                result=None,
                error=None,
            )
            media_info = probe_media(job.source_path)
            if not media_info.has_audio:
                raise ValueError("The media file has no usable audio track.")
            if media_info.duration_seconds <= 0:
                raise ValueError("Cannot determine media duration.")
            if media_info.duration_seconds > MAX_VC_DURATION_SECONDS:
                raise ValueError("Voice conversion supports up to 8 hours per job.")
            self._update(
                job,
                source_has_video=media_info.has_video,
            )
            if job.cancel_event.is_set():
                raise InterruptedError("Voice conversion canceled.")

            voice = self.load_voice(job.voice_id)
            reference_path = Path(voice["audio_path"])
            self._update(
                job,
                phase="preparing",
                message="Extracting and normalizing source audio",
                progress=0.1,
            )
            prepare_vc_audio(job.source_path, prepared_path)
            prepared_info = probe_media(prepared_path)
            source_duration = prepared_info.duration_seconds
            if not prepared_info.has_audio or source_duration <= 0:
                raise ValueError("Cannot determine the extracted audio duration.")
            if source_duration > MAX_VC_DURATION_SECONDS:
                raise ValueError("Voice conversion supports up to 8 hours per job.")
            self._update(job, duration_seconds=source_duration)
            if job.cancel_event.is_set():
                raise InterruptedError("Voice conversion canceled.")

            preset = VC_PRESETS[job.preset]
            manifest = self._load_chunk_manifest(job, source_duration)
            if manifest is None:
                self._update(
                    job,
                    phase="chunking",
                    message="Finding natural pauses and planning long audio segments",
                    progress=0.13,
                )
                silence_midpoints = (
                    detect_silence_midpoints(prepared_path)
                    if source_duration > VC_CHUNK_MAX_SECONDS
                    else []
                )
                chunk_ranges = plan_vc_chunks(
                    source_duration,
                    silence_midpoints,
                )
                manifest = self._new_chunk_manifest(
                    job,
                    source_duration,
                    chunk_ranges,
                )

            chunk_entries = manifest["chunks"]
            chunk_total = len(chunk_entries)
            self._update(
                job,
                chunk_total=chunk_total,
                chunks_completed=0,
                current_chunk=1,
            )
            generation_seconds = 0.0
            sample_rate = 24_000

            if chunk_total == 1:
                result = self.provider.convert(
                    VCRequest(
                        source_audio=prepared_path,
                        reference_audio=reference_path,
                        output_path=output_path,
                        work_dir=job.job_dir / "runtime",
                        diffusion_steps=int(preset["diffusion_steps"]),
                        inference_cfg_rate=float(preset["inference_cfg_rate"]),
                    ),
                    cancel_event=job.cancel_event,
                    progress_callback=lambda progress, message: self._progress(
                        job, progress, message
                    ),
                )
                generation_seconds = result.generation_seconds
                sample_rate = result.sample_rate
                chunk_entries[0]["status"] = "complete"
                chunk_entries[0]["generation_seconds"] = round(
                    result.generation_seconds, 3
                )
                chunk_entries[0]["sample_rate"] = result.sample_rate
                self._write_chunk_manifest(job, manifest)
                self._update(job, chunks_completed=1, current_chunk=1)
            else:
                chunk_dir = job.job_dir / "chunks"
                chunk_dir.mkdir(parents=True, exist_ok=True)
                converted_paths: list[Path] = []
                completed = 0
                for entry in chunk_entries:
                    index = int(entry["index"])
                    source_chunk = chunk_dir / f"source-{index:05d}.wav"
                    converted_chunk = chunk_dir / f"converted-{index:05d}.wav"
                    converted_paths.append(converted_chunk)
                    cached = False
                    if entry.get("status") == "complete" and converted_chunk.is_file():
                        cached_info = probe_media(converted_chunk)
                        cached = cached_info.has_audio and cached_info.duration_seconds > 0
                    if cached:
                        completed += 1
                        generation_seconds += float(entry.get("generation_seconds", 0.0))
                        sample_rate = int(entry.get("sample_rate", sample_rate))
                        self._update(
                            job,
                            chunks_completed=completed,
                            current_chunk=min(index + 1, chunk_total),
                            message=f"Reused segment {index}/{chunk_total}",
                        )
                        continue

                    if job.cancel_event.is_set():
                        raise InterruptedError("Voice conversion canceled.")
                    self._update(
                        job,
                        phase="converting",
                        current_chunk=index,
                        chunks_completed=completed,
                        message=f"Processing segment {index}/{chunk_total}",
                    )
                    extract_vc_chunk(
                        prepared_path,
                        source_chunk,
                        float(entry["start"]),
                        float(entry["end"]),
                    )
                    converted_chunk.unlink(missing_ok=True)
                    work_dir = job.job_dir / "runtime" / f"chunk-{index:05d}"
                    shutil.rmtree(work_dir, ignore_errors=True)
                    chunk_result = self.provider.convert(
                        VCRequest(
                            source_audio=source_chunk,
                            reference_audio=reference_path,
                            output_path=converted_chunk,
                            work_dir=work_dir,
                            diffusion_steps=int(preset["diffusion_steps"]),
                            inference_cfg_rate=float(preset["inference_cfg_rate"]),
                        ),
                        cancel_event=job.cancel_event,
                        progress_callback=lambda progress, message, index=index: self._progress(
                            job,
                            ((index - 1) + progress) / chunk_total,
                            f"Segment {index}/{chunk_total} · {message}",
                        ),
                    )
                    entry["status"] = "complete"
                    entry["generation_seconds"] = round(
                        chunk_result.generation_seconds, 3
                    )
                    entry["sample_rate"] = chunk_result.sample_rate
                    self._write_chunk_manifest(job, manifest)
                    generation_seconds += chunk_result.generation_seconds
                    sample_rate = chunk_result.sample_rate
                    completed += 1
                    source_chunk.unlink(missing_ok=True)
                    shutil.rmtree(work_dir, ignore_errors=True)
                    self._update(
                        job,
                        chunks_completed=completed,
                        current_chunk=index,
                        message=f"Completed segment {index}/{chunk_total}",
                    )

                if job.cancel_event.is_set():
                    raise InterruptedError("Voice conversion canceled.")
                self._update(
                    job,
                    phase="stitching",
                    message=f"Joining {chunk_total} audio segments without extra pauses",
                    progress=0.91,
                )
                stitched_duration = stitch_wav_files(
                    converted_paths,
                    output_path,
                    gap_seconds=0.0,
                )
                result = VCResult(
                    duration_seconds=stitched_duration,
                    generation_seconds=generation_seconds,
                    realtime_factor=generation_seconds / max(stitched_duration, 0.001),
                    sample_rate=sample_rate,
                )
            if job.cancel_event.is_set():
                raise InterruptedError("Voice conversion canceled.")

            result_payload: dict[str, Any] = {
                "audio_filename": output_path.name,
                "duration_seconds": round(result.duration_seconds, 3),
                "generation_seconds": round(result.generation_seconds, 3),
                "realtime_factor": round(result.realtime_factor, 4),
                "sample_rate": result.sample_rate,
                "chunk_count": chunk_total,
                "diffusion_steps": int(preset["diffusion_steps"]),
                "inference_cfg_rate": float(preset["inference_cfg_rate"]),
            }
            if media_info.has_video:
                self._update(
                    job,
                    phase="muxing",
                    message="Adding the converted voice to the video",
                    progress=0.93,
                )
                video_path = job.job_dir / "converted.mp4"
                video_result = mux_dubbed_video(
                    job.source_path,
                    output_path,
                    video_path,
                    original_audio_gain=0.0,
                )
                result_payload["video_filename"] = video_path.name
                result_payload["video_size_bytes"] = video_result["size_bytes"]

            if chunk_total > 1:
                for source_chunk in (job.job_dir / "chunks").glob("source-*.wav"):
                    source_chunk.unlink(missing_ok=True)
                shutil.rmtree(job.job_dir / "runtime", ignore_errors=True)
                prepared_path.unlink(missing_ok=True)

            self._update(
                job,
                status="complete",
                phase="complete",
                message="Voice conversion complete",
                progress=1.0,
                result=result_payload,
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
                message="Voice conversion did not complete",
                error=str(exc),
            )

    def snapshot(self, job: VoiceConversionJob) -> dict[str, Any]:
        with self._lock:
            return dict(self._serialize_unlocked(job))

    def _load_from_disk(self, job_id: str) -> VoiceConversionJob:
        if not self._valid_id(job_id):
            raise FileNotFoundError("Voice conversion job not found.")
        job_dir = self.conversion_root / job_id
        metadata_path = job_dir / "conversion.json"
        if not metadata_path.is_file():
            raise FileNotFoundError("Voice conversion job not found.")
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        storage_filename = str(data["source_storage_filename"])
        if Path(storage_filename).name != storage_filename:
            raise ValueError("Invalid source file record for this voice conversion job.")
        source_path = job_dir / storage_filename
        return VoiceConversionJob(
            job_id=job_id,
            job_dir=job_dir,
            source_path=source_path,
            source_filename=str(data["source_filename"]),
            source_bytes=int(data.get("source_bytes", 0)),
            voice_id=str(data["voice_id"]),
            voice_name=str(data.get("voice_name", "Saved voice")),
            preset=str(data.get("preset", "balanced")),
            created_at=str(data["created_at"]),
            status=str(data.get("status", "error")),
            phase=str(data.get("phase", "error")),
            message=str(data.get("message", "")),
            progress=float(data.get("progress", 0.0)),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            source_has_video=bool(data.get("source_has_video", False)),
            chunk_total=int(data.get("chunk_total", 0)),
            chunks_completed=int(data.get("chunks_completed", 0)),
            current_chunk=int(data.get("current_chunk", 0)),
            result=data.get("result"),
            error=data.get("error"),
            updated_at=str(data.get("updated_at", data["created_at"])),
        )

    def get_job(self, job_id: str) -> VoiceConversionJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        job = self._load_from_disk(job_id)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for metadata_path in self.conversion_root.glob("*/conversion.json"):
            try:
                job = self.get_job(metadata_path.parent.name)
                items.append(self.snapshot(job))
            except (OSError, ValueError, KeyError, json.JSONDecodeError, FileNotFoundError):
                continue
        items.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return items

    def cancel(self, job_id: str) -> VoiceConversionJob:
        job = self.get_job(job_id)
        if job.status in {"complete", "error", "cancelled"}:
            return job
        job.cancel_event.set()
        self._update(job, message="Stopping voice conversion")
        return job

    def retry(self, job_id: str) -> VoiceConversionJob:
        job = self.get_job(job_id)
        if job.status not in {"error", "cancelled"}:
            raise ValueError("Only failed or canceled jobs can be retried.")
        job.cancel_event = threading.Event()
        self._update(
            job,
            status="queued",
            phase="queued",
            message="Waiting for voice conversion",
            progress=0.0,
            error=None,
            result=None,
            chunks_completed=0,
            current_chunk=0,
        )
        self.launch(job)
        return job

    def recover(self) -> int:
        recovered = 0
        for metadata_path in self.conversion_root.glob("*/conversion.json"):
            try:
                job = self.get_job(metadata_path.parent.name)
            except (OSError, ValueError, KeyError, json.JSONDecodeError, FileNotFoundError):
                continue
            if job.status in {"queued", "running"}:
                self._update(
                    job,
                    status="error",
                    phase="error",
                    message="Voice conversion was interrupted by an app restart. It is safe to retry.",
                    error="The job was interrupted by an app restart.",
                )
                recovered += 1
        return recovered

    def source_media(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        if not job.source_path.is_file():
            raise FileNotFoundError("Source media not found.")
        return job.source_path

    def result_audio(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        path = job.job_dir / "converted.wav"
        if job.status != "complete" or not path.is_file():
            raise FileNotFoundError("Converted audio has not been generated yet.")
        return path

    def stream_chunk(self, job_id: str, chunk_index: int) -> Path:
        job = self.get_job(job_id)
        available = {
            int(chunk["index"])
            for chunk in self._available_stream_chunks_unlocked(job)
        }
        if chunk_index not in available:
            raise FileNotFoundError("This voice conversion segment is not ready yet.")
        if job.chunk_total == 1:
            path = job.job_dir / "converted.wav"
        else:
            path = job.job_dir / "chunks" / f"converted-{chunk_index:05d}.wav"
        if not path.is_file():
            raise FileNotFoundError("Voice conversion segment not found.")
        return path

    def result_video(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        path = job.job_dir / "converted.mp4"
        if job.status != "complete" or not path.is_file():
            raise FileNotFoundError("Converted video has not been generated yet.")
        return path

    def voice_in_use(self, voice_id: str) -> bool:
        return any(
            item.get("voice_id") == voice_id
            and item.get("status") in {"queued", "running"}
            for item in self.list()
        )
