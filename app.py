from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from timbreloom.asr_service import ASRService
from timbreloom.live_asr import LiveASRService
from timbreloom.live_asr_api import create_router as create_live_asr_router
from timbreloom.dubbing_api import DubbingContext, create_router as create_dubbing_router
from timbreloom.tts_service import GenerationJob, TTSService
from timbreloom.api_models import (
    TranscriptPatch, GeminiTransformRequest, HistoryRenameRequest,
)
from timbreloom.audio import stitch_wav_files, wav_duration
from timbreloom.dub_projects import (
    DubExportService,
    DubProjectStore,
    DubRenderService,
)
from timbreloom.media import extract_voice_clip
from timbreloom.providers import (
    AcceleratorCoordinator,
    GeminiTextProvider,
    LocalQwenTTSProvider,
    LocalSeedVCProvider,
    LocalWhisperASRProvider,
    TTSRequest,
)
from timbreloom.providers.streaming_asr import LocalStreamingASRProvider
from timbreloom.segmentation import (
    AUDIO_TOKENS_PER_SECOND,
    GENERATION_TOKEN_LIMIT,
    SEGMENT_ESTIMATED_TOKEN_LIMIT,
    segment_text,
)
from timbreloom.transcripts import selected_segment_range
from timbreloom.voice_conversion import VC_PRESETS, VoiceConversionService
from timbreloom.runtime_lock import DataDirectoryLock
from timbreloom.model_store import ModelStore, default_model_root


APP_ROOT = Path(__file__).resolve().parent
STATIC_DIR = APP_ROOT / "static"
DATA_DIR = Path(
    os.getenv("TIMBRELOOM_DATA_DIR", str(APP_ROOT / "data"))
).expanduser().resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"
VOICE_DIR = DATA_DIR / "voices"
JOB_DIR = DATA_DIR / "jobs"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
PROJECT_DIR = DATA_DIR / "projects"
CONVERSION_DIR = DATA_DIR / "conversions"

MODEL_DIR = default_model_root(APP_ROOT, DATA_DIR)
_model_store = ModelStore(MODEL_DIR)
MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
DEFAULT_MODEL_DIR = MODEL_DIR / "Qwen3-TTS-12Hz-0.6B-Base-bf16"
MODEL_SOURCE = os.getenv(
    "TIMBRELOOM_MODEL",
    str(DEFAULT_MODEL_DIR),
)
ASR_MODEL_ID = "mlx-community/whisper-large-v3-turbo-q4"
ASR_MODEL_REVISION = "660c343bbf4e52ac257f0b7d952e5388e6f93bef"
DEFAULT_ASR_MODEL_DIR = MODEL_DIR / "Whisper-large-v3-turbo-q4"
ASR_MODEL_SOURCE = Path(
    os.getenv("TIMBRELOOM_ASR_MODEL", str(DEFAULT_ASR_MODEL_DIR))
)
SEED_VC_RUNTIME_DIR = Path(
    os.getenv("TIMBRELOOM_SEED_VC_RUNTIME", str(APP_ROOT / "runtime" / "seed-vc"))
).expanduser().resolve()
SEED_VC_MODEL_DIR = Path(
    os.getenv("TIMBRELOOM_SEED_VC_MODEL", str(MODEL_DIR / "Seed-VC"))
).expanduser().resolve()
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
    ".ts",
    ".m2ts",
    ".mts",
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

for directory in (
    UPLOAD_DIR,
    OUTPUT_DIR,
    VOICE_DIR,
    JOB_DIR,
    TRANSCRIPT_DIR,
    PROJECT_DIR,
    CONVERSION_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

_accelerator = AcceleratorCoordinator()
_tts_provider = LocalQwenTTSProvider(MODEL_ID, MODEL_SOURCE, _accelerator,
    model_available=(lambda: _model_store.ready("qwen")) if MODEL_SOURCE == str(DEFAULT_MODEL_DIR) else None)
_asr_provider = LocalWhisperASRProvider(
    ASR_MODEL_ID,
    ASR_MODEL_SOURCE,
    _accelerator,
    before_load=_tts_provider.unload,
    model_available=(lambda: _model_store.ready("whisper")) if ASR_MODEL_SOURCE == DEFAULT_ASR_MODEL_DIR else None,
)
STREAMING_ASR_RUNTIME = Path(os.getenv("TIMBRELOOM_STREAMING_ASR_RUNTIME", str(APP_ROOT / "runtime/streaming-asr")))
_streaming_asr_providers = {
    key: LocalStreamingASRProvider(
        key, MODEL_DIR / _model_store.catalog[key]["directory"], STREAMING_ASR_RUNTIME / ".venv/bin/python",
        _accelerator, model_available=lambda model_key=key: _model_store.ready(model_key), before_load=_tts_provider.unload,
    ) for key in ("nemotron", "moonshine-en", "moonshine-zh")
}
_vc_provider = LocalSeedVCProvider(
    runtime_python=SEED_VC_RUNTIME_DIR / ".venv" / "bin" / "python",
    source_dir=SEED_VC_RUNTIME_DIR / "source",
    checkpoint=(
        SEED_VC_MODEL_DIR
        / "v1-offline"
        / "DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth"
    ),
    config=SEED_VC_MODEL_DIR / "v1-offline" / "config_dit_mel_seed_uvit_whisper_small_wavenet.yml",
    coordinator=_accelerator,
    before_load=_tts_provider.unload,
    model_available=(lambda: _model_store.ready("seed-vc")) if SEED_VC_MODEL_DIR == MODEL_DIR / "Seed-VC" else None,
)
_gemini_provider = GeminiTextProvider()
_asr_service = ASRService(TRANSCRIPT_DIR, _asr_provider, _streaming_asr_providers)
_live_asr_service = LiveASRService(_asr_service)
_dub_store = DubProjectStore(PROJECT_DIR)
_voice_storage_lock = threading.Lock()


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
    with DataDirectoryLock(DATA_DIR):
        recovered_tts = _tts_jobs.recover()
        recovered_asr = _asr_service.recover()
        _vc_service.recover()
        recovered_jobs = _dub_render_service.recover()
        recovered_exports = _dub_export_service.recover()
        if os.getenv("TIMBRELOOM_PRELOAD", "1") == "1" and not (recovered_tts or recovered_asr or recovered_jobs or recovered_exports):
            threading.Thread(target=_preload_safely, daemon=True).start()
        try:
            yield
        finally:
            await asyncio.to_thread(_live_asr_service.close)
            _model_store.close()


app = FastAPI(
    title="Timbreloom",
    version="1.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def local_workspace_only(request: Request, call_next):
    """Reject browser requests from other sites and DNS rebinding onto the local API."""
    try:
        target = request.url
        if target.hostname not in {"127.0.0.1", "localhost", "::1"}:
            return JSONResponse({"detail": "Access is restricted to the local Timbreloom address."}, status_code=403)
        if origin := request.headers.get("origin"):
            source = urlsplit(origin)
            if (source.scheme, source.hostname, source.port or 80) != (target.scheme, target.hostname, target.port or 80):
                return JSONResponse({"detail": "Other websites cannot access the local library."}, status_code=403)
    except ValueError:
        return JSONResponse({"detail": "Invalid local request address."}, status_code=400)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.include_router(create_live_asr_router(_live_asr_service, set(ASR_LANGUAGES)))


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health(library: bool = True) -> dict[str, Any]:
    tts_descriptor = _tts_provider.descriptor
    asr_descriptor = _asr_provider.descriptor
    gemini_descriptor = _gemini_provider.descriptor
    vc_descriptor = _vc_provider.descriptor
    snapshot = {
        "ok": True,
        "version": app.version,
        "model": MODEL_ID,
        "model_source": "local" if Path(MODEL_SOURCE).is_dir() else "not-downloaded",
        "model_status": _tts_provider.status if tts_descriptor.configured else "missing",
        "model_loaded": _tts_provider.loaded,
        "error": _tts_provider.error,
        "privacy": "localhost-only",
        "generation_token_limit": GENERATION_TOKEN_LIMIT,
        "sampling_temperature": SAMPLING_TEMPERATURE,
        "active_local_workload": _accelerator.active,
        "providers": [
            tts_descriptor.public(),
            asr_descriptor.public(),
            *(provider.descriptor.public() for provider in _streaming_asr_providers.values()),
            vc_descriptor.public(),
            gemini_descriptor.public(),
        ],
    }
    if library:
        snapshot.update(
            saved_voices=len(_list_voice_profiles()),
            saved_transcripts=len(_asr_service.list_transcripts()),
            saved_dub_projects=len(_dub_store.list()),
            saved_voice_conversions=len(_vc_service.list()),
        )
    return snapshot


@app.get("/api/runtime")
def runtime_status() -> dict[str, Any]:
    """Cheap desktop handshake and quit guard, without walking the media library."""
    return {
        "app": "timbreloom",
        "version": app.version,
        "project_root": str(APP_ROOT),
        "data_root": str(DATA_DIR),
        "pid": os.getpid(),
        "busy": bool(_accelerator.active) or _model_store.has_active_jobs() or any(service.has_active_jobs() for service in (
            _tts_jobs, _asr_service, _vc_service, _dub_render_service, _dub_export_service,
        )),
    }


@app.get("/api/models")
def list_models() -> dict[str, Any]:
    return _model_store.snapshot()


@app.get("/api/asr/models")
def asr_models() -> dict[str, Any]:
    models = []
    for key in ("whisper", "nemotron", "moonshine-en", "moonshine-zh"):
        provider = _asr_service.provider_for(key)
        catalog = _model_store.catalog[key]
        language = key.rsplit("-", 1)[1] if key.startswith("moonshine-") else None
        models.append({"id": key, "name": provider.descriptor.name, "ready": provider.descriptor.ready,
                       "description": catalog["description"], "bytes": catalog["bytes"],
                       "languages": [language] if language else list(ASR_LANGUAGES),
                       "supports_hints": key != "nemotron",
                       "timestamps": "word" if key == "whisper" else "segment"})
    return {"default": "whisper", "models": models}


@app.post("/api/models/{model_id}/download", status_code=202)
def download_model(model_id: str) -> dict[str, Any]:
    try:
        return _model_store.start(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="This model is not available for download.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Cannot write to the models folder. Check disk space and permissions.") from exc


@app.post("/api/models/{model_id}/pause")
def pause_model_download(model_id: str) -> dict[str, Any]:
    try:
        return _model_store.pause(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="This model is not available for download.") from exc


@app.post("/api/preload")
def preload() -> dict[str, Any]:
    try:
        _tts_provider.preload()
        model = get_model()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Model loading failed: {exc}") from exc
    return {
        "ok": True,
        "version": app.version,
        "model": MODEL_ID,
        "sample_rate": int(model.sample_rate),
    }


def _normalize_text(value: str, field_name: str, limit: int) -> str:
    value = " ".join(value.strip().split())
    if not value:
        raise ValueError(f"{field_name} cannot be empty.")
    if len(value) > limit:
        raise ValueError(f"{field_name} cannot exceed {limit} characters.")
    return value


def _normalize_target_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        raise ValueError("Enter the text to generate.")
    if len(value) > MAX_TARGET_TEXT_CHARS:
        raise ValueError(f"Target text cannot exceed {MAX_TARGET_TEXT_CHARS:,} characters.")
    return value


def _normalize_voice_name(value: str) -> str:
    value = " ".join(value.strip().split())
    if not value:
        raise ValueError("Enter a voice name.")
    if len(value) > MAX_VOICE_NAME_CHARS:
        raise ValueError(f"Voice names cannot exceed {MAX_VOICE_NAME_CHARS} characters.")
    return value


def _validate_language(language: str) -> str:
    language = language.strip().lower()
    if language not in LANGUAGES:
        raise ValueError("This language is not supported.")
    return language


def _validate_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_SUFFIXES))
        raise ValueError(f"Unsupported file format. Supported formats: {allowed}")
    return suffix


async def _read_upload(upload: UploadFile) -> bytes:
    try:
        payload = await upload.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await upload.close()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Reference recordings cannot exceed 40 MB.")
    if not payload:
        raise ValueError("The reference recording is empty.")
    return payload


async def _save_upload_stream(
    upload: UploadFile,
    destination: Path,
    max_bytes: int,
    oversize_detail: str = "Transcription media cannot exceed 2 GB.",
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
                        detail=oversize_detail,
                    )
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    if total == 0:
        destination.unlink(missing_ok=True)
        raise ValueError("The transcription media file is empty.")
    return total


def _validate_asr_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_ASR_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_ASR_SUFFIXES))
        raise ValueError(f"Unsupported media format. Supported formats: {allowed}")
    return suffix


def _validate_asr_language(language: str) -> str:
    normalized = language.strip().lower()
    if normalized not in ASR_LANGUAGES:
        raise ValueError("This transcription language is not supported.")
    return normalized


def _normalize_audio(source: Path, destination: Path) -> float:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg was not found. Run brew install ffmpeg first.")

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
        detail = result.stderr.strip() or "Cannot read this audio file."
        raise ValueError(f"Audio conversion failed: {detail}")

    duration = wav_duration(destination)
    if duration < MIN_REFERENCE_SECONDS:
        raise ValueError(
            f"The reference recording is {duration:.1f} seconds long. At least {MIN_REFERENCE_SECONDS:.0f} seconds are required."
        )
    if duration > MAX_REFERENCE_SECONDS:
        raise ValueError(
            f"The reference recording is {duration:.1f} seconds long. The limit is {MAX_REFERENCE_SECONDS:.0f} seconds."
        )
    return duration


def _valid_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}", value))


def _voice_profile_path(voice_id: str) -> Path:
    if not _valid_identifier(voice_id):
        raise FileNotFoundError("Voice not found.")
    return VOICE_DIR / voice_id / "profile.json"


def _load_voice_profile(voice_id: str) -> dict[str, Any]:
    profile_path = _voice_profile_path(voice_id)
    if not profile_path.is_file():
        raise FileNotFoundError("Voice not found.")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    audio_path = profile_path.parent / "reference.wav"
    if not audio_path.is_file():
        raise FileNotFoundError("The voice reference recording was not found.")
    profile["audio_path"] = audio_path
    return profile


def _public_voice_profile(profile: dict[str, Any]) -> dict[str, Any]:
    transcript = str(profile.get("reference_text", ""))
    preview = transcript
    if len(transcript) > 120:
        preview = re.sub(r"\s+\S*$", "", transcript[:120]).rstrip() + "…"
    return {
        "id": profile["id"],
        "name": profile["name"],
        "original_filename": profile.get("original_filename", ""),
        "duration_seconds": profile["duration_seconds"],
        "created_at": profile["created_at"],
        "transcript_preview": preview,
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


_vc_service = VoiceConversionService(
    CONVERSION_DIR,
    _vc_provider,
    load_voice=_load_voice_profile,
)


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
            raise FileExistsError("A voice with this name already exists.")

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
            "Reference transcript",
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
        raise HTTPException(status_code=500, detail=f"Could not save voice: {exc}") from exc
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


@app.delete("/api/voices/{voice_id}")
def delete_voice(voice_id: str) -> dict[str, Any]:
    try:
        profile = _load_voice_profile(voice_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if _tts_jobs.voice_in_use(voice_id):
        raise HTTPException(status_code=409, detail="This voice is being used for generation and cannot be deleted yet.")
    if _vc_service.voice_in_use(voice_id):
        raise HTTPException(status_code=409, detail="This voice is being used for voice conversion and cannot be deleted yet.")

    for project_summary in _dub_store.list():
        try:
            project = _dub_store.load(project_summary["id"])
        except (FileNotFoundError, ValueError):
            continue
        if any(segment.get("voice_id") == voice_id for segment in project["segments"]) or any(
            role.get("voice_id") == voice_id for role in project.get("roles", [])
        ):
            raise HTTPException(
                status_code=409,
                detail=f"This voice is still used by the dubbing project {project['title']}.",
            )

    shutil.rmtree(Path(profile["audio_path"]).parent)
    return {"ok": True}


@app.get("/api/providers")
def list_providers() -> dict[str, Any]:
    return {
        "providers": [
            _tts_provider.descriptor.public(),
            _asr_provider.descriptor.public(),
            *(provider.descriptor.public() for provider in _streaming_asr_providers.values()),
            _vc_provider.descriptor.public(),
            _gemini_provider.descriptor.public(),
        ],
        "active_local_workload": _accelerator.active,
    }


@app.post("/api/providers/gemini/check")
async def check_gemini_provider() -> dict[str, Any]:
    if not _gemini_provider.configured:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured.")
    try:
        return await asyncio.to_thread(_gemini_provider.check_connection)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gemini connection check failed: {exc}") from exc


def _public_voice_conversion(job: Any) -> dict[str, Any]:
    payload = _vc_service.snapshot(job)
    job_id = payload["id"]
    payload["source_url"] = f"/api/voice-conversions/{job_id}/source"
    chunks = []
    for chunk in payload.pop("stream_chunks", []):
        chunk_payload = dict(chunk)
        chunk_payload["audio_url"] = (
            f"/api/voice-conversions/{job_id}/chunks/{chunk['index']}/audio"
        )
        chunks.append(chunk_payload)
    payload["stream"] = {
        "kind": "generated",
        "available": len(chunks),
        "total": payload.get("chunk_total", 0),
        "complete": payload.get("status") == "complete",
        "chunks": chunks,
    }
    if payload.get("status") == "complete" and payload.get("result"):
        payload["result"]["audio_url"] = f"/api/voice-conversions/{job_id}/audio"
        if payload["result"].get("video_filename"):
            payload["result"]["video_url"] = f"/api/voice-conversions/{job_id}/video"
    return payload


@app.get("/api/voice-conversions/presets")
def list_voice_conversion_presets() -> dict[str, Any]:
    return {
        "presets": [
            {"id": preset_id, **settings}
            for preset_id, settings in VC_PRESETS.items()
        ],
        "default": "balanced",
    }


@app.post("/api/voice-conversions", status_code=202)
async def create_voice_conversion(
    media: UploadFile = File(...),
    voice_id: str = Form(...),
    preset: str = Form("balanced"),
    confirm_rights: bool = Form(False),
) -> dict[str, Any]:
    if not confirm_rights:
        await media.close()
        raise HTTPException(
            status_code=400,
            detail="Confirm that you have permission to use the source media and target voice.",
        )
    if not _vc_provider.descriptor.configured:
        await media.close()
        raise HTTPException(
            status_code=503,
            detail="Download Seed-VC from Models before starting voice conversion.",
        )
    try:
        voice = _load_voice_profile(voice_id.strip())
        suffix = _validate_asr_suffix(media.filename)
        if preset not in VC_PRESETS:
            raise ValueError("Invalid voice conversion quality preset.")
    except FileNotFoundError as exc:
        await media.close()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        await media.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    job_dir = CONVERSION_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    source_path = job_dir / f"source{suffix}"
    source_filename = Path(media.filename or f"media{suffix}").name
    try:
        source_bytes = await _save_upload_stream(
            media,
            source_path,
            MAX_ASR_UPLOAD_BYTES,
            oversize_detail="Voice conversion media cannot exceed 2 GB.",
        )
        job = _vc_service.create_job(
            job_id=job_id,
            source_path=source_path,
            source_filename=source_filename,
            source_bytes=source_bytes,
            voice_id=voice["id"],
            voice_name=voice["name"],
            preset=preset,
        )
        _vc_service.launch(job)
        return _public_voice_conversion(job)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    except ValueError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Could not create voice conversion job: {exc}") from exc


@app.get("/api/voice-conversions")
def list_voice_conversions() -> dict[str, Any]:
    jobs = []
    for item in _vc_service.list():
        try:
            jobs.append(_public_voice_conversion(_vc_service.get_job(item["id"])))
        except FileNotFoundError:
            continue
    return {"conversions": jobs}


@app.get("/api/voice-conversions/{job_id}")
def get_voice_conversion(job_id: str) -> dict[str, Any]:
    try:
        return _public_voice_conversion(_vc_service.get_job(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/voice-conversions/{job_id}")
def rename_voice_conversion(job_id: str, request: HistoryRenameRequest) -> dict[str, Any]:
    try:
        return _public_voice_conversion(_vc_service.rename(job_id, request.title.strip()))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/voice-conversions/{job_id}")
def delete_voice_conversion(job_id: str) -> dict[str, bool]:
    try:
        _vc_service.delete(job_id)
        return {"ok": True}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/voice-conversions/{job_id}/cancel")
def cancel_voice_conversion(job_id: str) -> dict[str, Any]:
    try:
        return _public_voice_conversion(_vc_service.cancel(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/voice-conversions/{job_id}/retry", status_code=202)
def retry_voice_conversion(job_id: str) -> dict[str, Any]:
    try:
        return _public_voice_conversion(_vc_service.retry(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/voice-conversions/{job_id}/source")
def get_voice_conversion_source(job_id: str) -> FileResponse:
    try:
        path = _vc_service.source_media(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@app.get("/api/voice-conversions/{job_id}/audio")
def get_voice_conversion_audio(job_id: str) -> FileResponse:
    try:
        path = _vc_service.result_audio(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="audio/wav", filename=f"{job_id}-converted.wav")


@app.get("/api/voice-conversions/{job_id}/chunks/{chunk_index}/audio")
def get_voice_conversion_stream_chunk(job_id: str, chunk_index: int) -> FileResponse:
    try:
        path = _vc_service.stream_chunk(job_id, chunk_index)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/voice-conversions/{job_id}/video")
def get_voice_conversion_video(job_id: str) -> FileResponse:
    try:
        path = _vc_service.result_video(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}-converted.mp4")


@app.post("/api/asr/jobs", status_code=202)
async def create_asr_job(
    media: UploadFile = File(...),
    language: str = Form("auto"),
    initial_prompt: str = Form(""),
    model: str = Form("whisper"),
) -> dict[str, Any]:
    try:
        language = _validate_asr_language(language)
        suffix = _validate_asr_suffix(media.filename)
        initial_prompt = " ".join(initial_prompt.strip().split())
        if len(initial_prompt) > 1_000:
            raise ValueError("Vocabulary hints cannot exceed 1,000 characters.")
        provider = _asr_service.validate_model(model, language, initial_prompt)
    except ValueError as exc:
        await media.close()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not provider.descriptor.configured:
        await media.close()
        raise HTTPException(status_code=409, detail=f"Download {provider.descriptor.name} from Models before starting transcription.")

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
            model_key=model,
        )
        _asr_service.launch(job)
        return _public_asr_job(job)
    except HTTPException:
        shutil.rmtree(transcript_dir, ignore_errors=True)
        raise
    except ValueError as exc:
        shutil.rmtree(transcript_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(transcript_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Could not create transcription job: {exc}") from exc


@app.get("/api/asr/jobs/{job_id}")
def get_asr_job(job_id: str) -> dict[str, Any]:
    try:
        job = _asr_service.get_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _public_asr_job(job)


@app.post("/api/asr/jobs/{job_id}/cancel")
def cancel_asr_job(job_id: str) -> dict[str, Any]:
    try:
        job = _asr_service.cancel(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _public_asr_job(job)


def _public_asr_job(job: Any) -> dict[str, Any]:
    payload = _asr_service.snapshot(job)
    audio_path = job.transcript_dir / "audio.wav"
    chunks = []
    if payload.get("audio_ready") and audio_path.is_file():
        chunks.append(
            {
                "index": 1,
                "duration_seconds": payload.get("duration_seconds", 0),
                "label": "Original audio",
                "audio_url": f"/api/asr/jobs/{job.job_id}/audio",
            }
        )
    payload["stream"] = {
        "kind": "source",
        "available": len(chunks),
        "total": 1,
        "complete": bool(chunks),
        "chunks": chunks,
    }
    return payload


@app.get("/api/asr/jobs/{job_id}/audio")
def get_asr_job_audio(job_id: str) -> FileResponse:
    try:
        job = _asr_service.get_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audio_path = job.transcript_dir / "audio.wav"
    if not getattr(job, "audio_ready", False) or not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Transcription audio is still being prepared.")
    return FileResponse(audio_path, media_type="audio/wav")


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
        raise HTTPException(status_code=404, detail="Transcription audio not found.")
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
            raise ValueError("Invalid transcript segment selection.")
        transcript = _asr_service.get_transcript(transcript_id)
        start, end, reference_text = selected_segment_range(transcript, parsed_ids)
        reference_text = _normalize_text(
            reference_text,
            "Reference transcript",
            MAX_REFERENCE_TEXT_CHARS,
        )
        duration = end - start
        if duration < MIN_REFERENCE_SECONDS:
            raise ValueError(
                f"The selection is {duration:.1f} seconds long. At least {MIN_REFERENCE_SECONDS:.0f} seconds are required."
            )
        if duration > MAX_REFERENCE_SECONDS:
            raise ValueError(
                f"The selection is {duration:.1f} seconds long. Select at most {MAX_REFERENCE_SECONDS:.0f} seconds."
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
        raise HTTPException(status_code=500, detail=f"Could not create voice from transcript: {exc}") from exc
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
            detail="Explicit confirmation is required before sending selected text to Gemini.",
        )
    if not _gemini_provider.configured:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured.")
    try:
        transcript = _asr_service.get_transcript(transcript_id)
        segment = next(
            item for item in transcript["segments"] if item["id"] == request.segment_id
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Transcript segment not found.") from exc

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
        raise HTTPException(status_code=502, detail=f"Gemini processing failed: {exc}") from exc
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


_tts_jobs = TTSService(
    JOB_DIR, OUTPUT_DIR,
    generate_segment=lambda *args: _generate_segment(*args),
    normalize_audio=_normalize_audio,
    model_id=MODEL_ID,
    settings={"temperature": SAMPLING_TEMPERATURE, "max_tokens": GENERATION_TOKEN_LIMIT},
    max_attempts=MAX_GENERATION_ATTEMPTS,
)


_dub_render_service = DubRenderService(
    _dub_store,
    load_voice=_load_voice_profile,
    generate_segment=_generate_segment,
    model_id=MODEL_ID,
    settings={
        "temperature": SAMPLING_TEMPERATURE,
        "max_tokens": GENERATION_TOKEN_LIMIT,
        "max_audio_seconds": MAX_SEGMENT_AUDIO_SECONDS,
        "semantic_segmentation": True,
    },
    max_attempts=MAX_GENERATION_ATTEMPTS,
)
_dub_export_service = DubExportService(_dub_store, _dub_render_service)


def _dubbing_context() -> DubbingContext:
    return DubbingContext(
        store=_dub_store, render=_dub_render_service, exports=_dub_export_service,
        asr=_asr_service, gemini=_gemini_provider, load_voice=_load_voice_profile,
        validate_language=_validate_language, save_upload=_save_upload_stream,
        upload_dir=UPLOAD_DIR, max_upload_bytes=MAX_ASR_UPLOAD_BYTES,
    )


app.include_router(create_dubbing_router(_dubbing_context))


@app.post("/api/jobs", status_code=202)
async def create_generation_job(
    target_text: str = Form(...),
    language: str = Form("auto"),
    voice_id: str = Form(""),
    reference_text: str = Form(""),
    reference_audio: UploadFile | None = File(None),
) -> dict[str, Any]:
    if not _tts_provider.descriptor.configured:
        if reference_audio is not None:
            await reference_audio.close()
        raise HTTPException(status_code=409, detail="Download Qwen3-TTS from Models before generating speech.")
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
                raise HTTPException(status_code=400, detail="Choose a reference recording or a saved voice.")
            try:
                reference_text = _normalize_text(
                    reference_text,
                    "Reference transcript",
                    MAX_REFERENCE_TEXT_CHARS,
                )
                suffix = _validate_suffix(reference_audio.filename)
                payload = await _read_upload(reference_audio)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            reference_source = job_dir / f"source{suffix}"
            reference_source.write_bytes(payload)
            voice_name = reference_audio.filename or "Uploaded reference"

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
            message=f"Text ready with every word preserved. Segments: {len(segments)}",
        )
        _tts_jobs.add(job)
        _tts_jobs.launch(job)
        return _tts_jobs.snapshot(job)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


@app.get("/api/jobs")
def list_generation_jobs() -> dict[str, Any]:
    return {"jobs": _tts_jobs.list()}


@app.patch("/api/jobs/{job_id}")
def rename_generation_job(job_id: str, request: HistoryRenameRequest) -> dict[str, Any]:
    try:
        return _tts_jobs.snapshot(_tts_jobs.rename(job_id, request.title.strip()))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/jobs/{job_id}")
def delete_generation_job(job_id: str) -> dict[str, bool]:
    try:
        _tts_jobs.delete(job_id)
        return {"ok": True}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/reference")
def get_generation_reference(job_id: str) -> FileResponse:
    try:
        job = _tts_jobs.get_job(job_id)
        if not job.reference_source.is_file():
            raise FileNotFoundError("The reference recording is no longer available.")
        return FileResponse(job.reference_source)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}")
def get_generation_job(job_id: str) -> dict[str, Any]:
    try:
        return _tts_jobs.snapshot(_tts_jobs.get_job(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/segments/{segment_index}/audio")
def get_generation_stream_chunk(job_id: str, segment_index: int) -> FileResponse:
    try:
        job = _tts_jobs.get_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    available = {chunk["index"] for chunk in _tts_jobs.snapshot(job)["stream"]["chunks"]}
    path = job.job_dir / f"segment-{segment_index:05d}.wav"
    if segment_index not in available or not path.is_file():
        raise HTTPException(status_code=404, detail="This generated segment is not ready yet.")
    return FileResponse(path, media_type="audio/wav")


@app.post("/api/jobs/{job_id}/cancel")
def cancel_generation_job(job_id: str) -> dict[str, Any]:
    try:
        return _tts_jobs.snapshot(_tts_jobs.cancel(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
            "Reference transcript",
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
            "Reference transcript",
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
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}") from exc
    finally:
        upload_path.unlink(missing_ok=True)
