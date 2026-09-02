from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

from .audio import stitch_wav_files, wav_duration
from .segmentation import AUDIO_TOKENS_PER_SECOND, segment_text


DUB_PROJECT_SCHEMA_VERSION = 1
DUB_JOB_SCHEMA_VERSION = 1
PROJECT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
RENDER_STATUSES = {"missing", "stale", "rendering", "ready", "error"}
JOB_STATUSES = {"queued", "running", "complete", "partial", "cancelled", "error"}
ACTIVE_JOB_STATUSES = {"queued", "running"}
MAX_SEGMENT_TEXT_CHARS = 200_000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_title(value: str, fallback: str) -> str:
    title = " ".join(str(value).strip().split()) or fallback
    if len(title) > 160:
        raise ValueError("配音项目名称不能超过 160 个字符。")
    return title


def _clean_text(value: str) -> str:
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("配音文字不能为空。")
    if len(text) > MAX_SEGMENT_TEXT_CHARS:
        raise ValueError(f"单个配音片段不能超过 {MAX_SEGMENT_TEXT_CHARS:,} 个字符。")
    return text


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _safe_filename(value: str) -> str:
    if not value or Path(value).name != value:
        raise ValueError("项目文件名无效。")
    return value


def _blank_render() -> dict[str, Any]:
    return {
        "status": "missing",
        "fingerprint": "",
        "filename": "",
        "duration_seconds": 0.0,
        "generation_seconds": 0.0,
        "peak_memory_gb": 0.0,
        "error": None,
        "updated_at": "",
    }


def validate_project(project: dict[str, Any]) -> None:
    if project.get("schema_version") != DUB_PROJECT_SCHEMA_VERSION:
        raise ValueError("不支持该配音项目数据版本。")
    project_id = str(project.get("id", ""))
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ValueError("配音项目 ID 无效。")
    _safe_filename(str(project.get("source_audio_filename", "")))
    segments = project.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("配音项目没有有效片段。")

    seen_ids: set[str] = set()
    previous_start = -1.0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError("配音片段格式无效。")
        segment_id = str(segment.get("id", ""))
        if not segment_id or segment_id in seen_ids:
            raise ValueError("配音片段 ID 无效或重复。")
        seen_ids.add(segment_id)
        if int(segment.get("order", -1)) != index:
            raise ValueError("配音片段顺序无效。")
        start = _number(segment.get("start"), -1.0)
        end = _number(segment.get("end"), -1.0)
        if start < 0 or end < start or start < previous_start:
            raise ValueError("配音片段时间戳无效。")
        previous_start = start
        if not str(segment.get("source_text", "")).strip():
            raise ValueError("原始 ASR 文字不能为空。")
        _clean_text(str(segment.get("active_text", "")))
        voice_id = segment.get("voice_id")
        if voice_id is not None and not PROJECT_ID_PATTERN.fullmatch(str(voice_id)):
            raise ValueError("配音片段的音色 ID 无效。")
        gain = _number(segment.get("gain"), 1.0)
        if not 0.0 <= gain <= 2.0:
            raise ValueError("片段音量必须在 0 到 2 之间。")
        render = segment.get("render")
        if not isinstance(render, dict) or render.get("status") not in RENDER_STATUSES:
            raise ValueError("片段渲染状态无效。")
        filename = str(render.get("filename", ""))
        if filename:
            _safe_filename(filename)


def project_summary(project: dict[str, Any]) -> dict[str, Any]:
    segments = project["segments"]
    statuses = [segment["render"]["status"] for segment in segments]
    return {
        "id": project["id"],
        "title": project["title"],
        "source_filename": project.get("source_filename", ""),
        "source_transcript_id": project.get("source_transcript_id", ""),
        "duration_seconds": project.get("duration_seconds", 0.0),
        "source_language": project.get("source_language", "unknown"),
        "target_language": project.get("target_language", "auto"),
        "segment_count": len(segments),
        "ready_count": statuses.count("ready"),
        "failed_count": statuses.count("error"),
        "stale_count": statuses.count("stale"),
        "status": project.get("status", "draft"),
        "last_job_id": project.get("last_job_id"),
        "created_at": project.get("created_at", ""),
        "updated_at": project.get("updated_at", ""),
    }


def content_fingerprint(
    segment: dict[str, Any],
    project: dict[str, Any],
    voice_profile: dict[str, Any],
    model_id: str,
    settings: dict[str, Any],
) -> str:
    payload = {
        "active_text": segment["active_text"],
        "voice_id": segment["voice_id"],
        "voice_created_at": voice_profile.get("created_at", ""),
        "voice_reference_text": voice_profile.get("reference_text", ""),
        "target_language": project.get("target_language", "auto"),
        "model_id": model_id,
        "settings": settings,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DubProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def project_dir(self, project_id: str) -> Path:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise FileNotFoundError("配音项目不存在。")
        return self.root / project_id

    def _project_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"

    def create(
        self,
        *,
        transcript: dict[str, Any],
        source_audio: Path,
        title: str = "",
        target_language: str = "auto",
        default_voice_id: str | None = None,
    ) -> dict[str, Any]:
        if not source_audio.is_file():
            raise FileNotFoundError("转录源音频不存在。")
        transcript_segments = transcript.get("segments")
        if not isinstance(transcript_segments, list) or not transcript_segments:
            raise ValueError("转录没有可用片段。")
        if default_voice_id is not None and not PROJECT_ID_PATTERN.fullmatch(default_voice_id):
            raise ValueError("默认音色 ID 无效。")

        project_id = uuid.uuid4().hex
        created_at = _utc_now()
        fallback_title = str(transcript.get("title", "")).strip() or "未命名配音项目"
        project = {
            "schema_version": DUB_PROJECT_SCHEMA_VERSION,
            "id": project_id,
            "title": _clean_title(title, fallback_title),
            "source_transcript_id": str(transcript.get("id", "")),
            "source_filename": str(transcript.get("source_filename", "")),
            "source_audio_filename": "source.wav",
            "duration_seconds": round(max(0.0, _number(transcript.get("duration_seconds"))), 3),
            "source_language": str(transcript.get("language", "unknown")),
            "target_language": target_language,
            "status": "draft",
            "created_at": created_at,
            "updated_at": created_at,
            "last_job_id": None,
            "segments": [],
            "exports": [],
        }
        for index, source in enumerate(transcript_segments):
            source_text = str(source.get("text", "")).strip()
            start = round(max(0.0, _number(source.get("start"))), 3)
            end = round(max(start, _number(source.get("end"), start)), 3)
            project["segments"].append(
                {
                    "id": str(source.get("id", f"seg-{index + 1:05d}")),
                    "order": index,
                    "start": start,
                    "end": end,
                    "source_text": source_text,
                    "active_text": source_text,
                    "voice_id": default_voice_id,
                    "gain": 1.0,
                    "revision": 1,
                    "render": _blank_render(),
                }
            )
        validate_project(project)

        project_dir = self.project_dir(project_id)
        with self._lock:
            project_dir.mkdir(parents=True, exist_ok=False)
            try:
                (project_dir / "renders").mkdir()
                (project_dir / "jobs").mkdir()
                (project_dir / "exports").mkdir()
                shutil.copyfile(source_audio, project_dir / "source.wav")
                _atomic_json(project_dir / "project.json", project)
            except Exception:
                shutil.rmtree(project_dir, ignore_errors=True)
                raise
        return project

    def load(self, project_id: str) -> dict[str, Any]:
        path = self._project_path(project_id)
        with self._lock:
            if not path.is_file():
                raise FileNotFoundError("配音项目不存在。")
            project = json.loads(path.read_text(encoding="utf-8"))
        validate_project(project)
        return project

    def save(self, project: dict[str, Any]) -> dict[str, Any]:
        project["updated_at"] = _utc_now()
        validate_project(project)
        with self._lock:
            _atomic_json(self._project_path(project["id"]), project)
        return project

    def list(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for project_path in self.root.glob("*/project.json"):
            try:
                project = json.loads(project_path.read_text(encoding="utf-8"))
                validate_project(project)
                projects.append(project_summary(project))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        projects.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return projects

    def update(
        self,
        project_id: str,
        *,
        title: str | None = None,
        target_language: str | None = None,
        segment_updates: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        with self._lock:
            project = self.load(project_id)
            invalidate_all = False
            if title is not None:
                project["title"] = _clean_title(title, project["title"])
            if target_language is not None and target_language != project["target_language"]:
                project["target_language"] = target_language
                invalidate_all = True

            by_id = {segment["id"]: segment for segment in project["segments"]}
            for update in segment_updates:
                segment_id = str(update.get("id", ""))
                if segment_id not in by_id:
                    raise ValueError("修改中包含不存在的配音片段。")
                segment = by_id[segment_id]
                invalidated = False
                if "active_text" in update:
                    active_text = _clean_text(str(update["active_text"]))
                    if active_text != segment["active_text"]:
                        segment["active_text"] = active_text
                        invalidated = True
                if "voice_id" in update:
                    voice_id = update["voice_id"] or None
                    if voice_id is not None and not PROJECT_ID_PATTERN.fullmatch(str(voice_id)):
                        raise ValueError("音色 ID 无效。")
                    if voice_id != segment["voice_id"]:
                        segment["voice_id"] = voice_id
                        invalidated = True
                if "gain" in update:
                    gain = _number(update["gain"], -1.0)
                    if not 0.0 <= gain <= 2.0:
                        raise ValueError("片段音量必须在 0 到 2 之间。")
                    segment["gain"] = round(gain, 3)
                if invalidated:
                    segment["revision"] = int(segment.get("revision", 0)) + 1
                    self._mark_stale(segment)

            if invalidate_all:
                for segment in project["segments"]:
                    self._mark_stale(segment)
            if invalidate_all or any(
                segment["render"]["status"] != "ready"
                for segment in project["segments"]
            ):
                project["status"] = "draft"
            return self.save(project)

    @staticmethod
    def _mark_stale(segment: dict[str, Any]) -> None:
        render = segment["render"]
        render["status"] = "stale" if render.get("filename") else "missing"
        render["error"] = None
        render["updated_at"] = _utc_now()

    def source_audio(self, project_id: str) -> Path:
        project = self.load(project_id)
        path = self.project_dir(project_id) / project["source_audio_filename"]
        if not path.is_file():
            raise FileNotFoundError("配音项目源音频不存在。")
        return path

    def render_path(self, project_id: str, filename: str) -> Path:
        _safe_filename(filename)
        return self.project_dir(project_id) / "renders" / filename

    def job_path(self, project_id: str, job_id: str) -> Path:
        if not PROJECT_ID_PATTERN.fullmatch(job_id):
            raise FileNotFoundError("配音任务不存在。")
        return self.project_dir(project_id) / "jobs" / f"{job_id}.json"

    def save_job(self, job: dict[str, Any]) -> dict[str, Any]:
        if job.get("schema_version") != DUB_JOB_SCHEMA_VERSION:
            raise ValueError("配音任务版本无效。")
        if job.get("status") not in JOB_STATUSES:
            raise ValueError("配音任务状态无效。")
        job["updated_at"] = _utc_now()
        with self._lock:
            _atomic_json(self.job_path(job["project_id"], job["job_id"]), job)
        return job

    def load_job(self, project_id: str, job_id: str) -> dict[str, Any]:
        path = self.job_path(project_id, job_id)
        with self._lock:
            if not path.is_file():
                raise FileNotFoundError("配音任务不存在。")
            job = json.loads(path.read_text(encoding="utf-8"))
        if job.get("schema_version") != DUB_JOB_SCHEMA_VERSION:
            raise ValueError("不支持该配音任务版本。")
        return job

    def list_jobs(self, project_id: str) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        job_dir = self.project_dir(project_id) / "jobs"
        if not job_dir.is_dir():
            return jobs
        for path in job_dir.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job.get("schema_version") == DUB_JOB_SCHEMA_VERSION:
                    jobs.append(job)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return jobs


def _subtitle_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1_000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1_000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def render_project_srt(project: dict[str, Any]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(project["segments"], start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_subtitle_timestamp(segment['start'])} --> {_subtitle_timestamp(segment['end'])}",
                    segment["active_text"].strip(),
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def mix_timeline_wav(
    segments: list[dict[str, Any]],
    destination: Path,
    *,
    project_duration_seconds: float,
    sample_rate: int = 24_000,
    block_seconds: float = 10.0,
) -> float:
    if not segments:
        raise ValueError("没有可导出的配音片段。")

    sources: list[dict[str, Any]] = []
    total_frames = round(max(0.0, project_duration_seconds) * sample_rate)
    for segment in segments:
        path = Path(segment["path"])
        with wave.open(str(path), "rb") as audio_file:
            if audio_file.getsampwidth() != 2:
                raise ValueError("配音片段必须是 16-bit PCM WAV。")
            if audio_file.getframerate() != sample_rate:
                raise ValueError("配音片段采样率不一致。")
            frames = audio_file.getnframes()
            channels = audio_file.getnchannels()
            if channels not in {1, 2}:
                raise ValueError("配音片段必须是单声道或双声道 WAV。")
        start_frame = round(max(0.0, _number(segment.get("start"))) * sample_rate)
        total_frames = max(total_frames, start_frame + frames)
        sources.append(
            {
                "path": path,
                "start_frame": start_frame,
                "frames": frames,
                "channels": channels,
                "gain": min(2.0, max(0.0, _number(segment.get("gain"), 1.0))),
            }
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    block_frames = max(1, round(block_seconds * sample_rate))
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for block_start in range(0, total_frames, block_frames):
            frame_count = min(block_frames, total_frames - block_start)
            mixed = np.zeros(frame_count, dtype=np.float64)
            block_end = block_start + frame_count
            for source in sources:
                source_start = source["start_frame"]
                source_end = source_start + source["frames"]
                overlap_start = max(block_start, source_start)
                overlap_end = min(block_end, source_end)
                if overlap_start >= overlap_end:
                    continue
                source_offset = overlap_start - source_start
                read_count = overlap_end - overlap_start
                with wave.open(str(source["path"]), "rb") as audio_file:
                    audio_file.setpos(source_offset)
                    raw = audio_file.readframes(read_count)
                samples = np.frombuffer(raw, dtype="<i2")
                if source["channels"] == 2:
                    samples = samples.reshape(-1, 2).mean(axis=1)
                destination_start = overlap_start - block_start
                destination_end = destination_start + samples.shape[0]
                mixed[destination_start:destination_end] += samples.astype(np.float64) * source["gain"]
            output.writeframesraw(np.clip(np.rint(mixed), -32_768, 32_767).astype("<i2").tobytes())
        output.writeframes(b"")
    return total_frames / sample_rate


class DubRenderService:
    def __init__(
        self,
        store: DubProjectStore,
        *,
        load_voice: Callable[[str], dict[str, Any]],
        generate_segment: Callable[[Path, str, str, str, Path], dict[str, float]],
        model_id: str,
        settings: dict[str, Any],
        max_attempts: int = 2,
    ) -> None:
        self.store = store
        self.load_voice = load_voice
        self.generate_segment = generate_segment
        self.model_id = model_id
        self.settings = settings
        self.max_attempts = max_attempts
        self._lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._running_jobs: set[str] = set()

    def _fingerprint(self, segment: dict[str, Any], project: dict[str, Any], voice: dict[str, Any]) -> str:
        return content_fingerprint(segment, project, voice, self.model_id, self.settings)

    def create_job(
        self,
        project_id: str,
        *,
        mode: str,
        segment_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        project = self.store.load(project_id)
        if mode not in {"all", "selected", "failed"}:
            raise ValueError("不支持该配音任务模式。")
        with self._lock:
            if any(job.get("status") in ACTIVE_JOB_STATUSES for job in self.store.list_jobs(project_id)):
                raise RuntimeError("该项目已有正在执行的配音任务。")
            known_ids = {segment["id"] for segment in project["segments"]}
            if mode == "all":
                selected_ids = [segment["id"] for segment in project["segments"]]
            elif mode == "failed":
                selected_ids = [segment["id"] for segment in project["segments"] if segment["render"]["status"] == "error"]
            else:
                selected_ids = list(dict.fromkeys(segment_ids or []))
                if not selected_ids:
                    raise ValueError("请选择至少一个需要生成的片段。")
                if not set(selected_ids).issubset(known_ids):
                    raise ValueError("选择中包含不存在的配音片段。")
                order = {segment["id"]: segment["order"] for segment in project["segments"]}
                selected_ids.sort(key=order.__getitem__)
            if not selected_ids:
                raise ValueError("当前没有符合条件的配音片段。")

            job_id = uuid.uuid4().hex
            created_at = _utc_now()
            job = {
                "schema_version": DUB_JOB_SCHEMA_VERSION,
                "job_id": job_id,
                "project_id": project_id,
                "mode": mode,
                "segment_ids": selected_ids,
                "status": "queued",
                "phase": "queued",
                "progress": 0.0,
                "current_segment_id": "",
                "current_text": "",
                "total": len(selected_ids),
                "processed": 0,
                "generated": 0,
                "cached": 0,
                "failed": 0,
                "message": "等待生成",
                "error": None,
                "cancel_requested": False,
                "created_at": created_at,
                "updated_at": created_at,
            }
            self.store.save_job(job)
            project["last_job_id"] = job_id
            project["status"] = "rendering"
            self.store.save(project)
            self.launch(project_id, job_id)
            return job

    def launch(self, project_id: str, job_id: str) -> None:
        with self._lock:
            if job_id in self._running_jobs:
                return
            self._running_jobs.add(job_id)
            cancel_event = threading.Event()
            self._cancel_events[job_id] = cancel_event
        threading.Thread(
            target=self._process,
            args=(project_id, job_id, cancel_event),
            name=f"dub-job-{job_id[:8]}",
            daemon=True,
        ).start()

    def recover(self) -> int:
        recovered = 0
        for project in self.store.list():
            for job in self.store.list_jobs(project["id"]):
                if job.get("status") not in ACTIVE_JOB_STATUSES:
                    continue
                if job.get("cancel_requested"):
                    job["status"] = "cancelled"
                    job["phase"] = "cancelled"
                    job["message"] = "服务重启时确认了此前的停止请求"
                    job["error"] = job["message"]
                    self.store.save_job(job)
                    cancelled_project = self.store.load(project["id"])
                    cancelled_project["status"] = "draft"
                    self.store.save(cancelled_project)
                    continue
                render_dir = self.store.project_dir(project["id"]) / "renders"
                for work_dir in render_dir.glob(".*"):
                    if work_dir.is_dir():
                        shutil.rmtree(work_dir, ignore_errors=True)
                job["status"] = "queued"
                job["phase"] = "queued"
                job["message"] = "服务重启后继续生成"
                job["progress"] = 0.0
                job["processed"] = 0
                job["generated"] = 0
                job["cached"] = 0
                job["failed"] = 0
                job["cancel_requested"] = False
                self.store.save_job(job)
                self.launch(project["id"], job["job_id"])
                recovered += 1
        return recovered

    def get_job(self, project_id: str, job_id: str) -> dict[str, Any]:
        return self.store.load_job(project_id, job_id)

    def cancel(self, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.load_job(project_id, job_id)
        if job["status"] in ACTIVE_JOB_STATUSES:
            job["cancel_requested"] = True
            job["message"] = "正在完成当前模型调用后停止"
            self.store.save_job(job)
            with self._lock:
                event = self._cancel_events.get(job_id)
            if event is not None:
                event.set()
        return job

    def _update_job(self, project_id: str, job_id: str, **changes: Any) -> dict[str, Any]:
        job = self.store.load_job(project_id, job_id)
        job.update(changes)
        return self.store.save_job(job)

    def _render_one(
        self,
        project: dict[str, Any],
        segment: dict[str, Any],
        voice: dict[str, Any],
        fingerprint: str,
    ) -> dict[str, float | str]:
        project_dir = self.store.project_dir(project["id"])
        work_dir = project_dir / "renders" / f".{segment['id']}-{uuid.uuid4().hex}"
        work_dir.mkdir(parents=True, exist_ok=False)
        generated_paths: list[Path] = []
        total_generation = 0.0
        peak_memory = 0.0
        try:
            chunks = segment_text(segment["active_text"])
            for chunk_index, chunk in enumerate(chunks, start=1):
                chunk_path = work_dir / f"chunk-{chunk_index:05d}.wav"
                metrics: dict[str, float] | None = None
                last_error: Exception | None = None
                for attempt in range(1, self.max_attempts + 1):
                    try:
                        metrics = self.generate_segment(
                            Path(voice["audio_path"]),
                            str(voice["reference_text"]),
                            chunk.text,
                            str(project.get("target_language", "auto")),
                            chunk_path,
                        )
                        expected_duration = chunk.estimated_audio_tokens / AUDIO_TOKENS_PER_SECOND
                        if chunk.estimated_audio_tokens >= 240 and metrics["duration_seconds"] < expected_duration * 0.35:
                            chunk_path.unlink(missing_ok=True)
                            raise RuntimeError("生成音频明显短于本段文字，可能存在漏读。")
                        break
                    except Exception as exc:
                        last_error = exc
                        metrics = None
                        if attempt < self.max_attempts:
                            time.sleep(0.25)
                if metrics is None:
                    raise RuntimeError(str(last_error or "模型没有返回音频。"))
                generated_paths.append(chunk_path)
                total_generation += metrics["generation_seconds"]
                peak_memory = max(peak_memory, metrics["peak_memory_gb"])

            assembled_path = work_dir / "segment.wav"
            if len(generated_paths) == 1:
                shutil.copyfile(generated_paths[0], assembled_path)
                duration = wav_duration(assembled_path)
            else:
                duration = stitch_wav_files(generated_paths, assembled_path, gap_seconds=0.08)
            filename = f"{segment['id']}-{fingerprint[:12]}.wav"
            final_path = self.store.render_path(project["id"], filename)
            assembled_path.replace(final_path)
            return {
                "filename": filename,
                "duration_seconds": duration,
                "generation_seconds": total_generation,
                "peak_memory_gb": peak_memory,
            }
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _process(self, project_id: str, job_id: str, cancel_event: threading.Event) -> None:
        try:
            job = self._update_job(
                project_id,
                job_id,
                status="running",
                phase="rendering",
                message="正在逐段生成配音",
                error=None,
            )
            segment_ids = list(job["segment_ids"])
            total = len(segment_ids)
            generated = int(job.get("generated", 0))
            cached = int(job.get("cached", 0))
            failed = int(job.get("failed", 0))

            for index, segment_id in enumerate(segment_ids, start=1):
                current_job = self.store.load_job(project_id, job_id)
                if cancel_event.is_set() or current_job.get("cancel_requested"):
                    raise InterruptedError("配音任务已停止。")
                project = self.store.load(project_id)
                segment = next(item for item in project["segments"] if item["id"] == segment_id)
                preview = " ".join(segment["active_text"].split())
                self._update_job(
                    project_id,
                    job_id,
                    current_segment_id=segment_id,
                    current_text=preview[:180],
                    processed=index - 1,
                    progress=(index - 1) / total,
                    message=f"正在处理第 {index} / {total} 段",
                )

                try:
                    if not segment.get("voice_id"):
                        raise ValueError("该片段还没有分配音色。")
                    voice = self.load_voice(segment["voice_id"])
                    fingerprint = self._fingerprint(segment, project, voice)
                    render = segment["render"]
                    cached_path = self.store.render_path(project_id, render["filename"]) if render.get("filename") else None
                    if (
                        render.get("status") == "ready"
                        and render.get("fingerprint") == fingerprint
                        and cached_path is not None
                        and cached_path.is_file()
                    ):
                        cached += 1
                    else:
                        render["status"] = "rendering"
                        render["error"] = None
                        render["updated_at"] = _utc_now()
                        self.store.save(project)
                        metrics = self._render_one(project, segment, voice, fingerprint)
                        fresh_project = self.store.load(project_id)
                        fresh_segment = next(item for item in fresh_project["segments"] if item["id"] == segment_id)
                        fresh_voice = self.load_voice(fresh_segment["voice_id"])
                        fresh_fingerprint = self._fingerprint(fresh_segment, fresh_project, fresh_voice)
                        fresh_render = fresh_segment["render"]
                        if fresh_fingerprint != fingerprint:
                            self.store.render_path(project_id, str(metrics["filename"])).unlink(missing_ok=True)
                            fresh_render["status"] = "stale"
                            fresh_render["error"] = "生成期间文字或音色发生变化，请重新生成此片段。"
                        else:
                            previous_filename = fresh_render.get("filename", "")
                            fresh_render.update(
                                {
                                    "status": "ready",
                                    "fingerprint": fingerprint,
                                    "filename": metrics["filename"],
                                    "duration_seconds": round(float(metrics["duration_seconds"]), 3),
                                    "generation_seconds": round(float(metrics["generation_seconds"]), 3),
                                    "peak_memory_gb": round(float(metrics["peak_memory_gb"]), 3),
                                    "error": None,
                                    "updated_at": _utc_now(),
                                }
                            )
                            if previous_filename and previous_filename != metrics["filename"]:
                                self.store.render_path(project_id, previous_filename).unlink(missing_ok=True)
                            generated += 1
                        self.store.save(fresh_project)
                except Exception as exc:
                    failed += 1
                    failed_project = self.store.load(project_id)
                    failed_segment = next(item for item in failed_project["segments"] if item["id"] == segment_id)
                    failed_segment["render"]["status"] = "error"
                    failed_segment["render"]["error"] = str(exc)
                    failed_segment["render"]["updated_at"] = _utc_now()
                    self.store.save(failed_project)

                self._update_job(
                    project_id,
                    job_id,
                    processed=index,
                    generated=generated,
                    cached=cached,
                    failed=failed,
                    progress=index / total,
                )

            final_status = "partial" if failed else "complete"
            final_project = self.store.load(project_id)
            final_project["status"] = "ready" if all(segment["render"]["status"] == "ready" for segment in final_project["segments"]) else "draft"
            self.store.save(final_project)
            self._update_job(
                project_id,
                job_id,
                status=final_status,
                phase=final_status,
                progress=1.0,
                current_segment_id="",
                current_text="",
                message="所选片段已经生成" if not failed else f"已完成，{failed} 个片段需要单独重试",
            )
        except InterruptedError as exc:
            project = self.store.load(project_id)
            project["status"] = "draft"
            self.store.save(project)
            self._update_job(
                project_id,
                job_id,
                status="cancelled",
                phase="cancelled",
                message=str(exc),
                error=str(exc),
            )
        except Exception as exc:
            try:
                project = self.store.load(project_id)
                project["status"] = "draft"
                self.store.save(project)
                self._update_job(
                    project_id,
                    job_id,
                    status="error",
                    phase="error",
                    message="配音任务异常停止",
                    error=str(exc),
                )
            except Exception:
                pass
        finally:
            with self._lock:
                self._running_jobs.discard(job_id)
                self._cancel_events.pop(job_id, None)

    def export(self, project_id: str) -> dict[str, Any]:
        project = self.store.load(project_id)
        timeline_segments: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for segment in project["segments"]:
            voice_id = segment.get("voice_id")
            if not voice_id:
                raise ValueError(f"片段 {segment['id']} 还没有分配音色。")
            voice = self.load_voice(voice_id)
            fingerprint = self._fingerprint(segment, project, voice)
            render = segment["render"]
            if render.get("status") != "ready" or render.get("fingerprint") != fingerprint:
                raise ValueError(f"片段 {segment['id']} 需要先生成或重新生成。")
            path = self.store.render_path(project_id, render["filename"])
            if not path.is_file():
                raise ValueError(f"片段 {segment['id']} 的渲染文件不存在。")
            slot_duration = max(0.0, segment["end"] - segment["start"])
            overflow = max(0.0, render["duration_seconds"] - slot_duration)
            if overflow > 0.05:
                warnings.append({"segment_id": segment["id"], "overflow_seconds": round(overflow, 3)})
            timeline_segments.append({"path": path, "start": segment["start"], "gain": segment.get("gain", 1.0)})

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        export_id = uuid.uuid4().hex[:8]
        wav_filename = f"timbreloom-dub-{stamp}-{export_id}.wav"
        srt_filename = f"timbreloom-dub-{stamp}-{export_id}.srt"
        export_dir = self.store.project_dir(project_id) / "exports"
        duration = mix_timeline_wav(
            timeline_segments,
            export_dir / wav_filename,
            project_duration_seconds=project["duration_seconds"],
        )
        (export_dir / srt_filename).write_text(render_project_srt(project), encoding="utf-8")
        export_record = {
            "id": export_id,
            "wav_filename": wav_filename,
            "srt_filename": srt_filename,
            "duration_seconds": round(duration, 3),
            "warning_count": len(warnings),
            "warnings": warnings,
            "created_at": _utc_now(),
        }
        project["exports"].append(export_record)
        project["exports"] = project["exports"][-20:]
        self.store.save(project)
        return export_record
