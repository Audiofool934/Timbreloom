from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from timbreloom.asr_service import ASRService
from timbreloom.audio import stitch_wav_files, wav_duration
from timbreloom.media import extract_voice_clip
from timbreloom.providers import (
    AcceleratorCoordinator,
    GeminiTextProvider,
    LocalQwenTTSProvider,
    LocalWhisperASRProvider,
    TTSRequest,
)
from timbreloom.segmentation import (
    AUDIO_TOKENS_PER_SECOND,
    GENERATION_TOKEN_LIMIT,
    SEGMENT_ESTIMATED_TOKEN_LIMIT,
    TextSegment,
    segment_text,
)
from timbreloom.transcripts import selected_segment_range


APP_ROOT = Path(__file__).resolve().parent
STATIC_DIR = APP_ROOT / "static"
DATA_DIR = APP_ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
VOICE_DIR = DATA_DIR / "voices"
JOB_DIR = DATA_DIR / "jobs"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"

MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
DEFAULT_MODEL_DIR = APP_ROOT / "models" / "Qwen3-TTS-12Hz-0.6B-Base-bf16"
MODEL_SOURCE = os.getenv(
    "TIMBRELOOM_MODEL",
    str(DEFAULT_MODEL_DIR),
)
ASR_MODEL_ID = "mlx-community/whisper-large-v3-turbo-q4"
ASR_MODEL_REVISION = "660c343bbf4e52ac257f0b7d952e5388e6f93bef"
DEFAULT_ASR_MODEL_DIR = APP_ROOT / "models" / "Whisper-large-v3-turbo-q4"
ASR_MODEL_SOURCE = Path(
    os.getenv("TIMBRELOOM_ASR_MODEL", str(DEFAULT_ASR_MODEL_DIR))
)
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_ASR_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MIN_REFERENCE_SECONDS = 2.0
MAX_REFERENCE_SECONDS = 30.0
MAX_REFERENCE_TEXT_CHARS = 2_000
MAX_TARGET_TEXT_CHARS = 200_000
MAX_VOICE_NAME_CHARS = 80
MAX_GENERATION_ATTEMPTS = 2
SAMPLING_TEMPERATURE = 1.0
MAX_SEGMENT_AUDIO_SECONDS = GENERATION_TOKEN_LIMIT / AUDIO_TOKENS_PER_SECOND
ALLOWED_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".caf", ".ogg", ".webm"}
ALLOWED_ASR_SUFFIXES = ALLOWED_SUFFIXES | {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".m4v",
}
ASR_LANGUAGES = {
    "auto": None,
    "zh": "zh",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "de": "de",
    "fr": "fr",
    "es": "es",
    "it": "it",
    "pt": "pt",
    "ru": "ru",
}
LANGUAGES = {
    "auto",
    "chinese",
    "english",
    "japanese",
    "korean",
    "german",
    "french",
    "russian",
    "portuguese",
    "spanish",
    "italian",
}

for directory in (UPLOAD_DIR, OUTPUT_DIR, VOICE_DIR, JOB_DIR, TRANSCRIPT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

_accelerator = AcceleratorCoordinator()
_tts_provider = LocalQwenTTSProvider(MODEL_ID, MODEL_SOURCE, _accelerator)
_asr_provider = LocalWhisperASRProvider(
    ASR_MODEL_ID,
    ASR_MODEL_SOURCE,
    _accelerator,
    before_load=_tts_provider.unload,
)
_gemini_provider = GeminiTextProvider()
_asr_service = ASRService(TRANSCRIPT_DIR, _asr_provider)
_voice_storage_lock = threading.Lock()
_jobs_lock = threading.Lock()


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
    status: str = "queued"
    phase: str = "queued"
    message: str = "等待生成"
    progress: float = 0.0
    segments_completed: int = 0
    current_segment: int = 0
    current_text: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


class TranscriptSegmentPatch(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=10_000)


class TranscriptPatch(BaseModel):
    segments: list[TranscriptSegmentPatch] = Field(min_length=1, max_length=2_000)


class GeminiTransformRequest(BaseModel):
    segment_id: str = Field(min_length=1, max_length=64)
    task: str = Field(min_length=1, max_length=32)
    target_language: str = Field(default="", max_length=80)
    confirm_cloud: bool = False


_jobs: dict[str, GenerationJob] = {}


def get_model() -> Any:
    """Compatibility wrapper for scripts that preload the local Qwen provider."""
    return _tts_provider.get_model()


def _preload_safely() -> None:
    try:
        _tts_provider.preload()
    except Exception:
        return


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("TIMBRELOOM_PRELOAD", "1") == "1":
        threading.Thread(target=_preload_safely, daemon=True).start()
    yield


app = FastAPI(
    title="Timbreloom",
    version="0.3.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    tts_descriptor = _tts_provider.descriptor
    asr_descriptor = _asr_provider.descriptor
    gemini_descriptor = _gemini_provider.descriptor
    return {
        "ok": _tts_provider.status != "error" and asr_descriptor.configured,
        "model": MODEL_ID,
        "model_source": "project-local" if Path(MODEL_SOURCE).is_dir() else MODEL_SOURCE,
        "model_status": _tts_provider.status,
        "model_loaded": _tts_provider.loaded,
        "error": _tts_provider.error,
        "privacy": "localhost-only",
        "saved_voices": len(_list_voice_profiles()),
        "saved_transcripts": len(_asr_service.list_transcripts()),
        "generation_token_limit": GENERATION_TOKEN_LIMIT,
        "sampling_temperature": SAMPLING_TEMPERATURE,
        "active_local_workload": _accelerator.active,
        "providers": [
            tts_descriptor.public(),
            asr_descriptor.public(),
            gemini_descriptor.public(),
        ],
    }


@app.post("/api/preload")
def preload() -> dict[str, Any]:
    try:
        _tts_provider.preload()
        model = get_model()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"模型加载失败：{exc}") from exc
    return {
        "ok": True,
        "model": MODEL_ID,
        "sample_rate": int(model.sample_rate),
    }


def _normalize_text(value: str, field_name: str, limit: int) -> str:
    value = " ".join(value.strip().split())
    if not value:
        raise ValueError(f"{field_name}不能为空。")
    if len(value) > limit:
        raise ValueError(f"{field_name}不能超过 {limit} 个字符。")
    return value


def _normalize_target_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        raise ValueError("目标文字不能为空。")
    if len(value) > MAX_TARGET_TEXT_CHARS:
        raise ValueError(f"目标文字不能超过 {MAX_TARGET_TEXT_CHARS:,} 个字符。")
    return value


def _normalize_voice_name(value: str) -> str:
    value = " ".join(value.strip().split())
    if not value:
        raise ValueError("音色名称不能为空。")
    if len(value) > MAX_VOICE_NAME_CHARS:
        raise ValueError(f"音色名称不能超过 {MAX_VOICE_NAME_CHARS} 个字符。")
    return value


def _validate_language(language: str) -> str:
    language = language.strip().lower()
    if language not in LANGUAGES:
        raise ValueError("不支持该语言选项。")
    return language


def _validate_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        allowed = "、".join(sorted(ALLOWED_SUFFIXES))
        raise ValueError(f"不支持该文件格式。可用格式：{allowed}")
    return suffix


async def _read_upload(upload: UploadFile) -> bytes:
    try:
        payload = await upload.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await upload.close()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="参考录音不能超过 40 MB。")
    if not payload:
        raise ValueError("参考录音为空。")
    return payload


async def _save_upload_stream(
    upload: UploadFile,
    destination: Path,
    max_bytes: int,
) -> int:
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="转录媒体不能超过 2 GB。",
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    if total == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("转录媒体为空。")
    return total


def _validate_asr_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_ASR_SUFFIXES:
        allowed = "、".join(sorted(ALLOWED_ASR_SUFFIXES))
        raise ValueError(f"不支持该转录格式。可用格式：{allowed}")
    return suffix


def _validate_asr_language(language: str) -> str:
    normalized = language.strip().lower()
    if normalized not in ASR_LANGUAGES:
        raise ValueError("不支持该 ASR 语言选项。")
    return normalized


def _normalize_audio(source: Path, destination: Path) -> float:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("没有找到 ffmpeg。请先运行 brew install ffmpeg。")

    result = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "无法读取该音频文件。"
        raise ValueError(f"音频转换失败：{detail}")

    duration = wav_duration(destination)
    if duration < MIN_REFERENCE_SECONDS:
        raise ValueError(
            f"参考录音只有 {duration:.1f} 秒，至少需要 {MIN_REFERENCE_SECONDS:.0f} 秒。"
        )
    if duration > MAX_REFERENCE_SECONDS:
        raise ValueError(
            f"参考录音有 {duration:.1f} 秒，当前版本最多接受 {MAX_REFERENCE_SECONDS:.0f} 秒。"
        )
    return duration


def _valid_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}", value))


def _voice_profile_path(voice_id: str) -> Path:
    if not _valid_identifier(voice_id):
        raise FileNotFoundError("音色不存在。")
    return VOICE_DIR / voice_id / "profile.json"


def _load_voice_profile(voice_id: str) -> dict[str, Any]:
    profile_path = _voice_profile_path(voice_id)
    if not profile_path.is_file():
        raise FileNotFoundError("音色不存在。")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    audio_path = profile_path.parent / "reference.wav"
    if not audio_path.is_file():
        raise FileNotFoundError("音色参考录音不存在。")
    profile["audio_path"] = audio_path
    return profile


def _public_voice_profile(profile: dict[str, Any]) -> dict[str, Any]:
    transcript = str(profile.get("reference_text", ""))
    return {
        "id": profile["id"],
        "name": profile["name"],
        "original_filename": profile.get("original_filename", ""),
        "duration_seconds": profile["duration_seconds"],
        "created_at": profile["created_at"],
        "transcript_preview": transcript[:120],
    }


def _list_voice_profiles() -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    if not VOICE_DIR.exists():
        return profiles
    for profile_path in VOICE_DIR.glob("*/profile.json"):
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if (profile_path.parent / "reference.wav").is_file():
                profiles.append(profile)
        except (OSError, ValueError, KeyError):
            continue
    profiles.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return profiles


def _persist_voice_profile(
    *,
    name: str,
    reference_text: str,
    normalized_audio: Path,
    original_filename: str,
    duration_seconds: float,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _voice_storage_lock:
        if any(
            profile.get("name", "").casefold() == name.casefold()
            for profile in _list_voice_profiles()
        ):
            raise FileExistsError("已经存在同名音色。")

        voice_id = uuid.uuid4().hex
        profile_dir = VOICE_DIR / voice_id
        profile_dir.mkdir(parents=True, exist_ok=False)
        try:
            shutil.copyfile(normalized_audio, profile_dir / "reference.wav")
            profile = {
                "id": voice_id,
                "name": name,
                "original_filename": original_filename,
                "reference_text": reference_text,
                "duration_seconds": round(duration_seconds, 2),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if source:
                profile["source"] = source
            temporary = profile_dir / "profile.json.tmp"
            temporary.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(profile_dir / "profile.json")
            return profile
        except Exception:
            shutil.rmtree(profile_dir, ignore_errors=True)
            raise


@app.get("/api/voices")
def list_voices() -> dict[str, Any]:
    return {"voices": [_public_voice_profile(profile) for profile in _list_voice_profiles()]}


@app.post("/api/voices", status_code=201)
async def create_voice(
    name: str = Form(...),
    reference_text: str = Form(...),
    reference_audio: UploadFile = File(...),
) -> dict[str, Any]:
    try:
        name = _normalize_voice_name(name)
        reference_text = _normalize_text(
            reference_text,
            "参考录音文字",
            MAX_REFERENCE_TEXT_CHARS,
        )
        suffix = _validate_suffix(reference_audio.filename)
        payload = await _read_upload(reference_audio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    temporary_dir = UPLOAD_DIR / f"voice-{uuid.uuid4().hex}"
    temporary_dir.mkdir(parents=True, exist_ok=False)
    source_path = temporary_dir / f"source{suffix}"
    reference_path = temporary_dir / "reference.wav"
    source_path.write_bytes(payload)

    try:
        duration = await asyncio.to_thread(_normalize_audio, source_path, reference_path)
        profile = await asyncio.to_thread(
            _persist_voice_profile,
            name=name,
            reference_text=reference_text,
            normalized_audio=reference_path,
            original_filename=reference_audio.filename or f"reference{suffix}",
            duration_seconds=duration,
        )
        return {"ok": True, "voice": _public_voice_profile(profile)}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存音色失败：{exc}") from exc
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


@app.delete("/api/voices/{voice_id}")
def delete_voice(voice_id: str) -> dict[str, Any]:
    try:
        profile = _load_voice_profile(voice_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with _jobs_lock:
        in_use = any(
            job.voice_id == voice_id and job.status in {"queued", "running"}
            for job in _jobs.values()
        )
    if in_use:
        raise HTTPException(status_code=409, detail="该音色正在用于生成，暂时不能删除。")

    shutil.rmtree(Path(profile["audio_path"]).parent)
    return {"ok": True}


@app.get("/api/providers")
def list_providers() -> dict[str, Any]:
    return {
        "providers": [
            _tts_provider.descriptor.public(),
            _asr_provider.descriptor.public(),
            _gemini_provider.descriptor.public(),
        ],
        "active_local_workload": _accelerator.active,
    }


@app.post("/api/providers/gemini/check")
async def check_gemini_provider() -> dict[str, Any]:
    if not _gemini_provider.configured:
        raise HTTPException(status_code=503, detail="没有配置 GEMINI_API_KEY。")
    try:
        return await asyncio.to_thread(_gemini_provider.check_connection)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini 连接检查失败：{exc}") from exc


@app.post("/api/asr/jobs", status_code=202)
async def create_asr_job(
    media: UploadFile = File(...),
    language: str = Form("auto"),
    initial_prompt: str = Form(""),
) -> dict[str, Any]:
    try:
        language = _validate_asr_language(language)
        suffix = _validate_asr_suffix(media.filename)
        initial_prompt = " ".join(initial_prompt.strip().split())
        if len(initial_prompt) > 1_000:
            raise ValueError("词汇提示不能超过 1,000 个字符。")
    except ValueError as exc:
        await media.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    transcript_dir = TRANSCRIPT_DIR / job_id
    transcript_dir.mkdir(parents=True, exist_ok=False)
    source_path = transcript_dir / f"source{suffix}"
    source_filename = Path(media.filename or f"media{suffix}").name
    try:
        source_bytes = await _save_upload_stream(
            media,
            source_path,
            MAX_ASR_UPLOAD_BYTES,
        )
        job = _asr_service.create_job(
            job_id=job_id,
            transcript_dir=transcript_dir,
            source_path=source_path,
            source_filename=source_filename,
            source_bytes=source_bytes,
            requested_language=language,
            initial_prompt=initial_prompt,
        )
        _asr_service.launch(job)
        return _asr_service.snapshot(job)
    except HTTPException:
        shutil.rmtree(transcript_dir, ignore_errors=True)
        raise
    except ValueError as exc:
        shutil.rmtree(transcript_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(transcript_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"建立转录任务失败：{exc}") from exc


@app.get("/api/asr/jobs/{job_id}")
def get_asr_job(job_id: str) -> dict[str, Any]:
    try:
        job = _asr_service.get_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _asr_service.snapshot(job)


@app.post("/api/asr/jobs/{job_id}/cancel")
def cancel_asr_job(job_id: str) -> dict[str, Any]:
    try:
        job = _asr_service.cancel(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _asr_service.snapshot(job)


@app.get("/api/transcripts")
def list_transcripts() -> dict[str, Any]:
    return {"transcripts": _asr_service.list_transcripts()}


@app.get("/api/transcripts/{transcript_id}")
def get_transcript(transcript_id: str) -> dict[str, Any]:
    try:
        transcript = _asr_service.get_transcript(transcript_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    transcript["audio_url"] = f"/api/transcripts/{transcript_id}/audio"
    transcript["export_urls"] = {
        export_format: f"/api/transcripts/{transcript_id}/export/{export_format}"
        for export_format in ("txt", "srt", "vtt")
    }
    return transcript


@app.patch("/api/transcripts/{transcript_id}")
def update_transcript(
    transcript_id: str,
    patch: TranscriptPatch,
) -> dict[str, Any]:
    updates = {segment.id: segment.text for segment in patch.segments}
    try:
        transcript = _asr_service.update_transcript(transcript_id, updates)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "transcript": transcript}


@app.get("/api/transcripts/{transcript_id}/audio")
def get_transcript_audio(transcript_id: str) -> FileResponse:
    try:
        transcript_dir = _asr_service.transcript_dir(transcript_id)
        _asr_service.get_transcript(transcript_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audio_path = transcript_dir / "audio.wav"
    if not audio_path.is_file():
        raise HTTPException(status_code=404, detail="转录音频不存在。")
    return FileResponse(audio_path, media_type="audio/wav")


@app.get("/api/transcripts/{transcript_id}/export/{export_format}")
def export_transcript(transcript_id: str, export_format: str) -> FileResponse:
    try:
        path = _asr_service.export(transcript_id, export_format)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    media_types = {
        "txt": "text/plain; charset=utf-8",
        "srt": "application/x-subrip; charset=utf-8",
        "vtt": "text/vtt; charset=utf-8",
    }
    return FileResponse(
        path,
        media_type=media_types[export_format.lower()],
        filename=f"{transcript_id}.{export_format.lower()}",
    )


@app.post("/api/transcripts/{transcript_id}/voices", status_code=201)
async def create_voice_from_transcript(
    transcript_id: str,
    name: str = Form(...),
    segment_ids: str = Form(...),
) -> dict[str, Any]:
    try:
        name = _normalize_voice_name(name)
        parsed_ids = json.loads(segment_ids)
        if not isinstance(parsed_ids, list) or not all(
            isinstance(segment_id, str) for segment_id in parsed_ids
        ):
            raise ValueError("转录片段选择格式无效。")
        transcript = _asr_service.get_transcript(transcript_id)
        start, end, reference_text = selected_segment_range(transcript, parsed_ids)
        reference_text = _normalize_text(
            reference_text,
            "参考录音文字",
            MAX_REFERENCE_TEXT_CHARS,
        )
        duration = end - start
        if duration < MIN_REFERENCE_SECONDS:
            raise ValueError(
                f"所选片段只有 {duration:.1f} 秒，至少需要 {MIN_REFERENCE_SECONDS:.0f} 秒。"
            )
        if duration > MAX_REFERENCE_SECONDS:
            raise ValueError(
                f"所选片段有 {duration:.1f} 秒，最多选择 {MAX_REFERENCE_SECONDS:.0f} 秒。"
            )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    temporary_dir = UPLOAD_DIR / f"transcript-voice-{uuid.uuid4().hex}"
    temporary_dir.mkdir(parents=True, exist_ok=False)
    clip_path = temporary_dir / "reference.wav"
    try:
        source_audio = _asr_service.transcript_dir(transcript_id) / "audio.wav"
        await asyncio.to_thread(
            extract_voice_clip,
            source_audio,
            clip_path,
            start,
            end,
        )
        actual_duration = wav_duration(clip_path)
        profile = await asyncio.to_thread(
            _persist_voice_profile,
            name=name,
            reference_text=reference_text,
            normalized_audio=clip_path,
            original_filename=f"{transcript['source_filename']}-clip.wav",
            duration_seconds=actual_duration,
            source={
                "type": "transcript",
                "transcript_id": transcript_id,
                "segment_ids": parsed_ids,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
            },
        )
        return {"ok": True, "voice": _public_voice_profile(profile)}
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"从转录创建音色失败：{exc}") from exc
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


@app.post("/api/transcripts/{transcript_id}/gemini")
async def transform_transcript_with_gemini(
    transcript_id: str,
    request: GeminiTransformRequest,
) -> dict[str, Any]:
    if not request.confirm_cloud:
        raise HTTPException(
            status_code=400,
            detail="必须明确确认后才能把所选文字发送到 Gemini。",
        )
    if not _gemini_provider.configured:
        raise HTTPException(status_code=503, detail="没有配置 GEMINI_API_KEY。")
    try:
        transcript = _asr_service.get_transcript(transcript_id)
        segment = next(
            item for item in transcript["segments"] if item["id"] == request.segment_id
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="转录片段不存在。") from exc

    try:
        result = await asyncio.to_thread(
            _gemini_provider.transform,
            segment["text"],
            request.task,
            request.target_language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini 处理失败：{exc}") from exc
    result["segment_id"] = request.segment_id
    result["cloud_request"] = True
    return result


@app.post("/api/segments/preview")
def preview_segments(target_text: str = Form(...)) -> dict[str, Any]:
    try:
        target_text = _normalize_target_text(target_text)
        segments = segment_text(target_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    estimated_tokens = sum(segment.estimated_audio_tokens for segment in segments)
    return {
        "ok": True,
        "characters": len(target_text),
        "segments": len(segments),
        "estimated_duration_seconds": round(estimated_tokens / AUDIO_TOKENS_PER_SECOND),
        "generation_token_limit_per_segment": GENERATION_TOKEN_LIMIT,
        "segment_estimated_token_limit": SEGMENT_ESTIMATED_TOKEN_LIMIT,
    }


def _generate_segment(
    reference_path: Path,
    reference_text: str,
    target_text: str,
    language: str,
    output_path: Path,
) -> dict[str, float]:
    result = _tts_provider.synthesize(
        TTSRequest(
            reference_audio=reference_path,
            reference_text=reference_text,
            text=target_text,
            language=language,
            output_path=output_path,
            temperature=SAMPLING_TEMPERATURE,
            max_tokens=GENERATION_TOKEN_LIMIT,
            max_audio_seconds=MAX_SEGMENT_AUDIO_SECONDS,
        )
    )
    return {
        "duration_seconds": result.duration_seconds,
        "generation_seconds": result.generation_seconds,
        "peak_memory_gb": result.peak_memory_gb,
    }


def _job_snapshot(job: GenerationJob) -> dict[str, Any]:
    with _jobs_lock:
        snapshot = {
            "job_id": job.job_id,
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
        }
    return snapshot


def _update_job(job: GenerationJob, **changes: Any) -> None:
    with _jobs_lock:
        for key, value in changes.items():
            setattr(job, key, value)


def _process_job(job: GenerationJob) -> None:
    started = time.perf_counter()
    segment_paths: list[Path] = []
    peak_memory = 0.0
    reference_path = job.reference_source

    try:
        _update_job(
            job,
            status="running",
            phase="preparing",
            message="正在准备参考音色",
            progress=0.02,
        )

        if not job.reference_is_normalized:
            reference_path = job.job_dir / "reference.wav"
            duration = _normalize_audio(job.reference_source, reference_path)
            _update_job(job, reference_duration_seconds=duration)

        if job.cancel_event.is_set():
            raise InterruptedError("生成已取消。")

        total = len(job.segments)
        for index, segment in enumerate(job.segments, start=1):
            if job.cancel_event.is_set():
                raise InterruptedError("生成已取消。")

            preview = " ".join(segment.text.split())
            preview_text = preview if len(preview) <= 180 else f"{preview[:177]}..."
            _update_job(
                job,
                phase="generating",
                message=f"正在生成第 {index} / {total} 段",
                current_segment=index,
                current_text=preview_text,
                progress=0.04 + 0.88 * ((index - 1) / total),
            )

            segment_path = job.job_dir / f"segment-{index:05d}.wav"
            last_error: Exception | None = None
            metrics: dict[str, float] | None = None
            for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
                try:
                    metrics = _generate_segment(
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
                            "生成音频明显短于本段文字，可能存在漏读。"
                        )
                    break
                except Exception as exc:
                    last_error = exc
                    metrics = None
                    if attempt < MAX_GENERATION_ATTEMPTS:
                        _update_job(job, message=f"第 {index} 段正在重试")
                        time.sleep(0.25)

            if metrics is None:
                raise RuntimeError(f"第 {index} 段生成失败：{last_error}")

            segment_paths.append(segment_path)
            peak_memory = max(peak_memory, metrics["peak_memory_gb"])
            _update_job(
                job,
                segments_completed=index,
                progress=0.04 + 0.88 * (index / total),
            )

        if job.cancel_event.is_set():
            raise InterruptedError("生成已取消。")

        _update_job(
            job,
            phase="assembling",
            message="正在无损拼接所有分段",
            progress=0.95,
            current_text="",
        )
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"timbreloom-long-{stamp}-{job.job_id[:6]}.wav"
        output_path = OUTPUT_DIR / filename
        generated_duration = stitch_wav_files(segment_paths, output_path)
        elapsed = time.perf_counter() - started
        result = {
            "ok": True,
            "audio_url": f"/outputs/{filename}",
            "filename": filename,
            "model": MODEL_ID,
            "voice_name": job.voice_name,
            "reference_duration_seconds": round(job.reference_duration_seconds or 0.0, 2),
            "audio_duration_seconds": round(generated_duration, 2),
            "generation_seconds": round(elapsed, 2),
            "peak_memory_gb": round(peak_memory, 2),
            "segment_count": len(job.segments),
            "text_characters": sum(len(segment.text) for segment in job.segments),
            "generation_token_limit_per_segment": GENERATION_TOKEN_LIMIT,
        }
        _update_job(
            job,
            status="complete",
            phase="complete",
            message="全部分段已生成并拼接完成",
            progress=1.0,
            current_segment=len(job.segments),
            result=result,
        )
    except InterruptedError as exc:
        _update_job(
            job,
            status="cancelled",
            phase="cancelled",
            message=str(exc),
            error=str(exc),
        )
    except Exception as exc:
        _update_job(
            job,
            status="error",
            phase="error",
            message="生成停止，没有跳过失败分段",
            error=str(exc),
        )
    finally:
        shutil.rmtree(job.job_dir, ignore_errors=True)


def _launch_job(job: GenerationJob) -> None:
    threading.Thread(
        target=_process_job,
        args=(job,),
        name=f"voice-job-{job.job_id[:8]}",
        daemon=True,
    ).start()


@app.post("/api/jobs", status_code=202)
async def create_generation_job(
    target_text: str = Form(...),
    language: str = Form("auto"),
    voice_id: str = Form(""),
    reference_text: str = Form(""),
    reference_audio: UploadFile | None = File(None),
) -> dict[str, Any]:
    try:
        target_text = _normalize_target_text(target_text)
        language = _validate_language(language)
        segments = segment_text(target_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    job_dir = JOB_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    normalized = False
    reference_duration: float | None = None

    try:
        if voice_id:
            try:
                profile = _load_voice_profile(voice_id)
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            reference_source = Path(profile["audio_path"])
            reference_text = profile["reference_text"]
            reference_duration = float(profile["duration_seconds"])
            voice_name = profile["name"]
            normalized = True
        else:
            if reference_audio is None:
                raise HTTPException(status_code=400, detail="请选择参考录音或已保存音色。")
            try:
                reference_text = _normalize_text(
                    reference_text,
                    "参考录音文字",
                    MAX_REFERENCE_TEXT_CHARS,
                )
                suffix = _validate_suffix(reference_audio.filename)
                payload = await _read_upload(reference_audio)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            reference_source = job_dir / f"source{suffix}"
            reference_source.write_bytes(payload)
            voice_name = reference_audio.filename or "本次上传"

        job = GenerationJob(
            job_id=job_id,
            voice_id=voice_id or None,
            voice_name=voice_name,
            reference_source=reference_source,
            reference_is_normalized=normalized,
            reference_text=reference_text,
            reference_duration_seconds=reference_duration,
            language=language,
            segments=segments,
            job_dir=job_dir,
            created_at=datetime.now(timezone.utc).isoformat(),
            message=f"已完成无丢字分段，共 {len(segments)} 段",
        )
        with _jobs_lock:
            _jobs[job_id] = job
        _launch_job(job)
        return _job_snapshot(job)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


@app.get("/api/jobs/{job_id}")
def get_generation_job(job_id: str) -> dict[str, Any]:
    if not _valid_identifier(job_id):
        raise HTTPException(status_code=404, detail="生成任务不存在。")
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="生成任务不存在或服务已经重启。")
    return _job_snapshot(job)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_generation_job(job_id: str) -> dict[str, Any]:
    if not _valid_identifier(job_id):
        raise HTTPException(status_code=404, detail="生成任务不存在。")
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="生成任务不存在。")
    if job.status not in {"queued", "running"}:
        return _job_snapshot(job)
    job.cancel_event.set()
    _update_job(job, message="将在当前分段结束后取消")
    return _job_snapshot(job)


def _run_generation(
    reference_path: Path,
    reference_text: str,
    target_text: str,
    language: str,
) -> dict[str, Any]:
    """Synchronous compatibility path used by the local smoke test."""
    work_dir = JOB_DIR / f"sync-{uuid.uuid4().hex}"
    work_dir.mkdir(parents=True, exist_ok=False)
    normalized_path = work_dir / "reference.wav"
    started = time.perf_counter()
    segment_paths: list[Path] = []
    peak_memory = 0.0

    try:
        reference_duration = _normalize_audio(reference_path, normalized_path)
        segments = segment_text(_normalize_target_text(target_text))
        normalized_reference_text = _normalize_text(
            reference_text,
            "参考录音文字",
            MAX_REFERENCE_TEXT_CHARS,
        )
        normalized_language = _validate_language(language)
        for segment in segments:
            segment_path = work_dir / f"segment-{segment.index:05d}.wav"
            metrics = _generate_segment(
                normalized_path,
                normalized_reference_text,
                segment.text,
                normalized_language,
                segment_path,
            )
            segment_paths.append(segment_path)
            peak_memory = max(peak_memory, metrics["peak_memory_gb"])

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"timbreloom-{stamp}-{uuid.uuid4().hex[:6]}.wav"
        output_path = OUTPUT_DIR / filename
        generated_duration = stitch_wav_files(segment_paths, output_path)
        return {
            "ok": True,
            "audio_url": f"/outputs/{filename}",
            "filename": filename,
            "model": MODEL_ID,
            "reference_duration_seconds": round(reference_duration, 2),
            "audio_duration_seconds": round(generated_duration, 2),
            "generation_seconds": round(time.perf_counter() - started, 2),
            "peak_memory_gb": round(peak_memory, 2),
            "segment_count": len(segments),
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


@app.post("/api/generate")
async def generate_legacy(
    reference_audio: UploadFile = File(...),
    reference_text: str = Form(...),
    target_text: str = Form(...),
    language: str = Form("auto"),
) -> dict[str, Any]:
    try:
        suffix = _validate_suffix(reference_audio.filename)
        reference_text = _normalize_text(
            reference_text,
            "参考录音文字",
            MAX_REFERENCE_TEXT_CHARS,
        )
        target_text = _normalize_target_text(target_text)
        language = _validate_language(language)
        payload = await _read_upload(reference_audio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    upload_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    upload_path.write_bytes(payload)
    try:
        return await asyncio.to_thread(
            _run_generation,
            upload_path,
            reference_text,
            target_text,
            language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成失败：{exc}") from exc
    finally:
        upload_path.unlink(missing_ok=True)
