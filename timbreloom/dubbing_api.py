from __future__ import annotations

import asyncio
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .api_models import (
    DubExportRequest,
    DubJobCreateRequest,
    DubMergeRequest,
    DubProjectCreateRequest,
    DubProjectPatch,
    DubRoleRequest,
    DubSplitRequest,
    GeminiBatchRequest,
    GeminiTransformRequest,
)
from .asr_service import ASRService
from .dub_projects import (
    DubExportService,
    DubProjectStore,
    DubRenderService,
    project_quality,
)
from .media import probe_media
from .providers import GeminiTextProvider


@dataclass(frozen=True)
class DubbingContext:
    store: DubProjectStore
    render: DubRenderService
    exports: DubExportService
    asr: ASRService
    gemini: GeminiTextProvider
    load_voice: Callable[[str], dict[str, Any]]
    validate_language: Callable[[str], str]
    save_upload: Callable[[UploadFile, Path, int], Awaitable[int]]
    upload_dir: Path
    max_upload_bytes: int


def _public_dub_job(
    context: DubbingContext,
    project_id: str,
    job: dict[str, Any],
    project: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(job)
    if payload.get("kind", "render") != "render":
        return payload
    current_project = project if project is not None else context.store.load(project_id)
    segments = {segment["id"]: segment for segment in current_project["segments"]}
    processed_ids = list(payload.get("segment_ids", []))[
        : int(payload.get("processed", 0))
    ]
    chunks = []
    for order, segment_id in enumerate(processed_ids, start=1):
        segment = segments.get(segment_id)
        if segment is None:
            continue
        render = segment.get("render", {})
        filename = str(render.get("filename", ""))
        path = context.store.render_path(project_id, filename) if filename else None
        if render.get("status") != "ready" or path is None or (not path.is_file()):
            continue
        chunks.append(
            {
                "index": order,
                "duration_seconds": float(render.get("duration_seconds", 0.0)),
                "label": str(segment.get("active_text", ""))[:180],
                "audio_url": f"/api/dub/projects/{project_id}/segments/{segment_id}/audio",
            }
        )
    payload["stream"] = {
        "kind": "generated",
        "available": len(chunks),
        "total": int(payload.get("total", 0)),
        "complete": payload.get("status") in {"complete", "partial"},
        "chunks": chunks,
    }
    return payload


def _public_dub_project(
    context: DubbingContext, project: dict[str, Any]
) -> dict[str, Any]:
    project_id = project["id"]
    project["source_audio_url"] = f"/api/dub/projects/{project_id}/audio"
    if project.get("source_has_video"):
        project["source_media_url"] = f"/api/dub/projects/{project_id}/media"
    for index, segment in enumerate(project["segments"]):
        render = segment["render"]
        slot_duration = max(0.0, float(segment["end"]) - float(segment["start"]))
        natural_duration = float(render.get("duration_seconds", 0.0))
        requested_speed = natural_duration / slot_duration if slot_duration > 0 else 1.0
        applied_speed = min(1.25, max(0.8, requested_speed))
        fitted_duration = (
            natural_duration / applied_speed
            if segment.get("fit_mode") == "slot" and natural_duration > 0
            else natural_duration
        )
        overflow = max(0.0, fitted_duration - slot_duration)
        next_start = (
            float(project["segments"][index + 1]["start"])
            if index + 1 < len(project["segments"])
            else None
        )
        rendered_end = float(segment["start"]) + fitted_duration
        overlap_next = (
            max(0.0, rendered_end - next_start) if next_start is not None else 0.0
        )
        render["slot_duration_seconds"] = round(slot_duration, 3)
        render["overflow_seconds"] = round(overflow, 3)
        render["natural_overflow_seconds"] = round(
            max(0.0, natural_duration - slot_duration), 3
        )
        render["fitted_duration_seconds"] = round(fitted_duration, 3)
        render["fit_speed"] = (
            round(applied_speed, 3) if segment.get("fit_mode") == "slot" else 1.0
        )
        render["fit_limited"] = bool(
            segment.get("fit_mode") == "slot"
            and abs(requested_speed - applied_speed) > 0.001
        )
        render["overlap_next_seconds"] = round(overlap_next, 3)
        if render.get("filename"):
            render["audio_url"] = (
                f"/api/dub/projects/{project_id}/segments/{segment['id']}/audio"
            )
    for export in project.get("exports", []):
        export["wav_url"] = (
            f"/api/dub/projects/{project_id}/exports/{export['wav_filename']}"
        )
        export["srt_url"] = (
            f"/api/dub/projects/{project_id}/exports/{export['srt_filename']}"
        )
        if export.get("mp4_filename"):
            export["mp4_url"] = (
                f"/api/dub/projects/{project_id}/exports/{export['mp4_filename']}"
            )
    if project.get("last_job_id"):
        try:
            project["last_job"] = _public_dub_job(
                context,
                project_id,
                context.render.get_job(project_id, project["last_job_id"]),
                project,
            )
        except (FileNotFoundError, ValueError):
            project["last_job"] = None
    else:
        project["last_job"] = None
    if project.get("last_export_job_id"):
        try:
            project["last_export_job"] = context.exports.get_job(
                project_id, project["last_export_job_id"]
            )
        except (FileNotFoundError, ValueError):
            project["last_export_job"] = None
    else:
        project["last_export_job"] = None
    project["quality"] = project_quality(project)
    return project


def create_router(get_context: Callable[[], DubbingContext]) -> APIRouter:
    router = APIRouter(tags=["dubbing"])

    @router.get("/api/dub/projects")
    def list_dub_projects(
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        return {"projects": context.store.list()}

    @router.post("/api/dub/projects", status_code=201)
    async def create_dub_project(
        request: DubProjectCreateRequest, context: DubbingContext = Depends(get_context)
    ) -> dict[str, Any]:
        try:
            target_language = context.validate_language(request.target_language)
            transcript = context.asr.get_transcript(request.transcript_id)
            source_audio = (
                context.asr.transcript_dir(request.transcript_id) / "audio.wav"
            )
            source_media = context.asr.source_media(request.transcript_id)
            source_media_info = await asyncio.to_thread(probe_media, source_media)
            if request.default_voice_id:
                context.load_voice(request.default_voice_id)
            project = await asyncio.to_thread(
                context.store.create,
                transcript=transcript,
                source_audio=source_audio,
                source_media=source_media if source_media_info.has_video else None,
                title=request.title,
                target_language=target_language,
                default_voice_id=request.default_voice_id,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Could not create dubbing project: {exc}"
            ) from exc
        return {"ok": True, "project": _public_dub_project(context, project)}

    @router.get("/api/dub/projects/{project_id}")
    def get_dub_project(
        project_id: str, context: DubbingContext = Depends(get_context)
    ) -> dict[str, Any]:
        try:
            return _public_dub_project(context, context.store.load(project_id))
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.patch("/api/dub/projects/{project_id}")
    def update_dub_project(
        project_id: str,
        patch: DubProjectPatch,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        try:
            target_language = (
                context.validate_language(patch.target_language)
                if patch.target_language is not None
                else None
            )
            updates = [item.model_dump(exclude_unset=True) for item in patch.segments]
            for update in updates:
                voice_id = update.get("voice_id")
                if voice_id:
                    context.load_voice(voice_id)
            project = context.store.update(
                project_id,
                title=patch.title,
                target_language=target_language,
                segment_updates=updates,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "project": _public_dub_project(context, project)}

    @router.post("/api/dub/projects/{project_id}/roles")
    def upsert_dub_role(
        project_id: str,
        request: DubRoleRequest,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        try:
            if request.voice_id:
                context.load_voice(request.voice_id)
            project = context.store.upsert_role(
                project_id,
                role_id=request.id,
                name=request.name,
                voice_id=request.voice_id,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "project": _public_dub_project(context, project)}

    @router.post("/api/dub/projects/{project_id}/segments/{segment_id}/split")
    def split_dub_segment(
        project_id: str,
        segment_id: str,
        request: DubSplitRequest,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        try:
            project = context.store.split_segment(
                project_id, segment_id, split_at=request.split_at
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "project": _public_dub_project(context, project)}

    @router.post("/api/dub/projects/{project_id}/segments/merge")
    def merge_dub_segments(
        project_id: str,
        request: DubMergeRequest,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        try:
            project = context.store.merge_segments(project_id, request.segment_ids)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "project": _public_dub_project(context, project)}

    @router.get("/api/dub/projects/{project_id}/waveform")
    def get_dub_waveform(
        project_id: str,
        points: int = 1600,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        try:
            return context.store.waveform(project_id, points=points)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/dub/projects/{project_id}/audio")
    def get_dub_source_audio(
        project_id: str, context: DubbingContext = Depends(get_context)
    ) -> FileResponse:
        try:
            path = context.store.source_audio(project_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, media_type="audio/wav")

    @router.get("/api/dub/projects/{project_id}/media")
    def get_dub_source_media(
        project_id: str, context: DubbingContext = Depends(get_context)
    ) -> FileResponse:
        try:
            path = context.store.source_media(project_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    @router.get("/api/dub/projects/{project_id}/segments/{segment_id}/audio")
    def get_dub_segment_audio(
        project_id: str, segment_id: str, context: DubbingContext = Depends(get_context)
    ) -> FileResponse:
        try:
            project = context.store.load(project_id)
            segment = next(
                (item for item in project["segments"] if item["id"] == segment_id)
            )
            filename = str(segment["render"].get("filename", ""))
            if not filename:
                raise FileNotFoundError("This segment has no audio to preview yet.")
            path = context.store.render_path(project_id, filename)
            if not path.is_file():
                raise FileNotFoundError("The segment preview file was not found.")
        except StopIteration as exc:
            raise HTTPException(status_code=404, detail="Dubbing segment not found.") from exc
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, media_type="audio/wav")

    @router.post("/api/dub/projects/{project_id}/jobs", status_code=202)
    def create_dub_job(
        project_id: str,
        request: DubJobCreateRequest,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        try:
            return _public_dub_job(
                context,
                project_id,
                context.render.create_job(
                    project_id, mode=request.mode, segment_ids=request.segment_ids
                ),
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/api/dub/projects/{project_id}/jobs/{job_id}")
    def get_dub_job(
        project_id: str, job_id: str, context: DubbingContext = Depends(get_context)
    ) -> dict[str, Any]:
        try:
            return _public_dub_job(
                context, project_id, context.render.get_job(project_id, job_id)
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/dub/projects/{project_id}/jobs/{job_id}/cancel")
    def cancel_dub_job(
        project_id: str, job_id: str, context: DubbingContext = Depends(get_context)
    ) -> dict[str, Any]:
        try:
            return _public_dub_job(
                context, project_id, context.render.cancel(project_id, job_id)
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/api/dub/projects/{project_id}/export")
    async def export_dub_project(
        project_id: str,
        request: DubExportRequest | None = None,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        try:
            original_audio_gain = request.original_audio_gain if request else 0.0
            export = await asyncio.to_thread(
                context.render.export,
                project_id,
                original_audio_gain=original_audio_gain,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Could not export dubbing project: {exc}"
            ) from exc
        export["wav_url"] = (
            f"/api/dub/projects/{project_id}/exports/{export['wav_filename']}"
        )
        export["srt_url"] = (
            f"/api/dub/projects/{project_id}/exports/{export['srt_filename']}"
        )
        if export.get("mp4_filename"):
            export["mp4_url"] = (
                f"/api/dub/projects/{project_id}/exports/{export['mp4_filename']}"
            )
        return {"ok": True, "export": export}

    @router.post("/api/dub/projects/{project_id}/export-jobs", status_code=202)
    def create_dub_export_job(
        project_id: str,
        request: DubExportRequest | None = None,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        try:
            return context.exports.create_job(
                project_id,
                original_audio_gain=request.original_audio_gain if request else 0.0,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/api/dub/projects/{project_id}/export-jobs/{job_id}")
    def get_dub_export_job(
        project_id: str, job_id: str, context: DubbingContext = Depends(get_context)
    ) -> dict[str, Any]:
        try:
            job = context.exports.get_job(project_id, job_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if job.get("result"):
            result = job["result"]
            result["wav_url"] = (
                f"/api/dub/projects/{project_id}/exports/{result['wav_filename']}"
            )
            result["srt_url"] = (
                f"/api/dub/projects/{project_id}/exports/{result['srt_filename']}"
            )
            if result.get("mp4_filename"):
                result["mp4_url"] = (
                    f"/api/dub/projects/{project_id}/exports/{result['mp4_filename']}"
                )
        return job

    @router.get("/api/dub/projects/{project_id}/bundle")
    def download_dub_project_bundle(
        project_id: str, context: DubbingContext = Depends(get_context)
    ) -> FileResponse:
        try:
            path = context.store.create_bundle(project_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return FileResponse(path, media_type="application/zip", filename=path.name)

    @router.post("/api/dub/projects/import", status_code=201)
    async def import_dub_project_bundle(
        bundle: UploadFile = File(...), context: DubbingContext = Depends(get_context)
    ) -> dict[str, Any]:
        upload_id = uuid.uuid4().hex
        path = context.upload_dir / f"dub-bundle-{upload_id}.timbreloom"
        try:
            await context.save_upload(
                bundle,
                path,
                context.max_upload_bytes,
                "Timbreloom project bundles cannot exceed 2 GB.",
            )
            project = await asyncio.to_thread(context.store.import_bundle, path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            path.unlink(missing_ok=True)
        return {"ok": True, "project": _public_dub_project(context, project)}

    @router.get("/api/dub/projects/{project_id}/exports/{filename}")
    def get_dub_export(
        project_id: str, filename: str, context: DubbingContext = Depends(get_context)
    ) -> FileResponse:
        try:
            project = context.store.load(project_id)
            allowed = {
                value
                for item in project.get("exports", [])
                for key in ("wav_filename", "srt_filename", "mp4_filename")
                if (value := item.get(key))
            }
            if filename not in allowed or Path(filename).name != filename:
                raise FileNotFoundError("Dubbing export file not found.")
            path = context.store.project_dir(project_id) / "exports" / filename
            if not path.is_file():
                raise FileNotFoundError("Dubbing export file not found.")
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        media_types = {
            ".wav": "audio/wav",
            ".srt": "application/x-subrip; charset=utf-8",
            ".mp4": "video/mp4",
        }
        media_type = media_types.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=media_type, filename=filename)

    @router.post("/api/dub/projects/{project_id}/gemini")
    async def transform_dub_segment_with_gemini(
        project_id: str,
        request: GeminiTransformRequest,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        if not request.confirm_cloud:
            raise HTTPException(
                status_code=400, detail="Explicit confirmation is required before sending selected text to Gemini."
            )
        if not context.gemini.configured:
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured.")
        try:
            project = context.store.load(project_id)
            segment = next(
                (
                    item
                    for item in project["segments"]
                    if item["id"] == request.segment_id
                )
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except StopIteration as exc:
            raise HTTPException(status_code=404, detail="Dubbing segment not found.") from exc
        try:
            result = await asyncio.to_thread(
                context.gemini.transform,
                segment["active_text"],
                request.task,
                request.target_language,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Gemini processing failed: {exc}"
            ) from exc
        result["segment_id"] = request.segment_id
        result["cloud_request"] = True
        return result

    @router.post("/api/dub/projects/{project_id}/gemini-batch")
    async def transform_dub_segments_with_gemini(
        project_id: str,
        request: GeminiBatchRequest,
        context: DubbingContext = Depends(get_context),
    ) -> dict[str, Any]:
        if not request.confirm_cloud:
            raise HTTPException(
                status_code=400, detail="Explicit confirmation is required before sending selected text to Gemini."
            )
        if not context.gemini.configured:
            raise HTTPException(status_code=503, detail="GEMINI_API_KEY is not configured.")
        try:
            project = context.store.load(project_id)
            by_id = {item["id"]: item for item in project["segments"]}
            segment_ids = list(dict.fromkeys(request.segment_ids))
            if not set(segment_ids).issubset(by_id):
                raise ValueError("The selection includes a missing dubbing segment.")
            total_chars = sum((len(by_id[item]["active_text"]) for item in segment_ids))
            if total_chars > 60000:
                raise ValueError("Batch Gemini requests cannot exceed 60,000 characters.")

            def run_batch() -> list[dict[str, Any]]:
                results = []
                for segment_id in segment_ids:
                    result = context.gemini.transform(
                        by_id[segment_id]["active_text"],
                        request.task,
                        request.target_language,
                    )
                    results.append({"segment_id": segment_id, "text": result["text"]})
                return results

            results = await asyncio.to_thread(run_batch)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Gemini batch processing failed: {exc}"
            ) from exc
        return {
            "ok": True,
            "provider": "gemini-text",
            "cloud_request": True,
            "task": request.task,
            "results": results,
        }

    return router
