from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
import wave
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


from .audio import stitch_wav_files, wav_duration
from .media import mux_dubbed_video, tempo_fit_wav
from .segmentation import AUDIO_TOKENS_PER_SECOND, segment_text


DUB_PROJECT_SCHEMA_VERSION = 4
DUB_JOB_SCHEMA_VERSION = 1
PROJECT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
RENDER_STATUSES = {"missing", "stale", "rendering", "ready", "error"}
JOB_STATUSES = {"queued", "running", "complete", "partial", "cancelled", "error"}
ACTIVE_JOB_STATUSES = {"queued", "running"}
MAX_SEGMENT_TEXT_CHARS = 200_000
ROLE_COLORS = ("#D9FF57", "#9FD8FF", "#FFC58F", "#D7B5FF", "#9FE3C2", "#FFB7C5")
FIT_MODES = {"natural", "slot"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_title(value: str, fallback: str) -> str:
    title = " ".join(str(value).strip().split()) or fallback
    if len(title) > 160:
        raise ValueError("Dubbing project names cannot exceed 160 characters.")
    return title


def _clean_text(value: str) -> str:
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("Dubbing text cannot be empty.")
    if len(text) > MAX_SEGMENT_TEXT_CHARS:
        raise ValueError(f"Each dubbing segment is limited to {MAX_SEGMENT_TEXT_CHARS:,} characters.")
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
        raise ValueError("Invalid project filename.")
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


def _upgrade_project(project: dict[str, Any]) -> bool:
    version = project.get("schema_version")
    if version == DUB_PROJECT_SCHEMA_VERSION:
        changed = False
        for segment in project.get("segments", []):
            source_ids = segment.get("source_segment_ids", [segment.get("id", "")])
            unique_source_ids = list(dict.fromkeys(str(source_id) for source_id in source_ids))
            if source_ids != unique_source_ids:
                segment["source_segment_ids"] = unique_source_ids
                changed = True
        return changed
    if version == 1:
        project["schema_version"] = 2
        project.setdefault("source_media_filename", "")
        project.setdefault("source_has_video", False)
        for export in project.get("exports", []):
            export.setdefault("mp4_filename", "")
            export.setdefault("original_audio_gain", 0.0)
            export.setdefault("video_codec_mode", "")
        version = 2
    if version in {2, 3}:
        roles = project.setdefault("roles", [])
        role_by_voice: dict[str, str] = {}
        for segment in project.get("segments", []):
            voice_id = segment.get("voice_id")
            role_id = None
            if voice_id:
                role_id = role_by_voice.get(str(voice_id))
                if role_id is None:
                    role_id = uuid.uuid4().hex
                    role_by_voice[str(voice_id)] = role_id
                    roles.append(
                        {
                            "id": role_id,
                            "name": "Default role" if not roles else f"Role {len(roles) + 1}",
                            "voice_id": voice_id,
                            "color": ROLE_COLORS[len(roles) % len(ROLE_COLORS)],
                        }
                    )
            segment.setdefault("role_id", role_id)
            segment.setdefault("fit_mode", "natural")
            segment.setdefault("source_segment_ids", [segment.get("id", "")])
        project.setdefault("last_export_job_id", None)
        project["schema_version"] = DUB_PROJECT_SCHEMA_VERSION
        return True
    raise ValueError("Unsupported dubbing project version.")


def validate_project(project: dict[str, Any]) -> None:
    if project.get("schema_version") != DUB_PROJECT_SCHEMA_VERSION:
        raise ValueError("Unsupported dubbing project version.")
    project_id = str(project.get("id", ""))
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise ValueError("Invalid dubbing project ID.")
    _safe_filename(str(project.get("source_audio_filename", "")))
    source_media_filename = str(project.get("source_media_filename", ""))
    if source_media_filename:
        _safe_filename(source_media_filename)
    if bool(project.get("source_has_video")) and not source_media_filename:
        raise ValueError("The video dubbing project is missing its original media file.")
    segments = project.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("The dubbing project has no valid segments.")

    roles = project.get("roles")
    if not isinstance(roles, list):
        raise ValueError("Invalid project role format.")
    role_ids: set[str] = set()
    for role in roles:
        role_id = str(role.get("id", ""))
        if not PROJECT_ID_PATTERN.fullmatch(role_id) or role_id in role_ids:
            raise ValueError("Invalid or duplicate role ID.")
        role_ids.add(role_id)
        _clean_title(str(role.get("name", "")), "Untitled role")
        voice_id = role.get("voice_id")
        if voice_id is not None and not PROJECT_ID_PATTERN.fullmatch(str(voice_id)):
            raise ValueError("Invalid voice ID for this role.")

    seen_ids: set[str] = set()
    previous_start = -1.0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError("Invalid dubbing segment format.")
        segment_id = str(segment.get("id", ""))
        if not segment_id or segment_id in seen_ids:
            raise ValueError("Invalid or duplicate dubbing segment ID.")
        seen_ids.add(segment_id)
        if int(segment.get("order", -1)) != index:
            raise ValueError("Invalid dubbing segment order.")
        start = _number(segment.get("start"), -1.0)
        end = _number(segment.get("end"), -1.0)
        if start < 0 or end < start or start < previous_start:
            raise ValueError("Invalid dubbing segment timestamps.")
        previous_start = start
        if not str(segment.get("source_text", "")).strip():
            raise ValueError("Original ASR text cannot be empty.")
        _clean_text(str(segment.get("active_text", "")))
        voice_id = segment.get("voice_id")
        if voice_id is not None and not PROJECT_ID_PATTERN.fullmatch(str(voice_id)):
            raise ValueError("Invalid voice ID for this dubbing segment.")
        role_id = segment.get("role_id")
        if role_id is not None and str(role_id) not in role_ids:
            raise ValueError("The dubbing segment refers to a missing role.")
        if segment.get("fit_mode") not in FIT_MODES:
            raise ValueError("Invalid segment duration fit mode.")
        gain = _number(segment.get("gain"), 1.0)
        if not 0.0 <= gain <= 2.0:
            raise ValueError("Segment gain must be between 0 and 2.")
        render = segment.get("render")
        if not isinstance(render, dict) or render.get("status") not in RENDER_STATUSES:
            raise ValueError("Invalid segment render state.")
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
        "source_has_video": bool(project.get("source_has_video", False)),
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


def project_quality(project: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    counts = {
        "missing": 0,
        "stale": 0,
        "error": 0,
        "unassigned": 0,
        "overflow": 0,
        "overlap": 0,
        "fit_limited": 0,
    }
    segments = project["segments"]
    for index, segment in enumerate(segments):
        render = segment["render"]
        status = render.get("status", "missing")
        if status in {"missing", "stale", "error"}:
            counts[status] += 1
        if not segment.get("voice_id"):
            counts["unassigned"] += 1
            issues.append({"type": "unassigned", "segment_id": segment["id"], "severity": "error"})
        rendered_duration = max(0.0, _number(render.get("duration_seconds")))
        slot = max(0.0, segment["end"] - segment["start"])
        requested_speed = rendered_duration / slot if slot else 999.0
        effective_duration = rendered_duration
        if segment.get("fit_mode") == "slot" and rendered_duration > 0:
            applied_speed = min(1.25, max(0.8, requested_speed))
            effective_duration = rendered_duration / applied_speed
        overflow = max(0.0, effective_duration - slot)
        if overflow > 0.05:
            counts["overflow"] += 1
            limited = segment.get("fit_mode") == "slot" and requested_speed > 1.25
            if limited:
                counts["fit_limited"] += 1
            issues.append(
                {
                    "type": "fit-limited" if limited else "overflow",
                    "segment_id": segment["id"],
                    "severity": "warning",
                    "seconds": round(overflow, 3),
                    "requested_speed": round(requested_speed, 3),
                }
            )
        next_start = segments[index + 1]["start"] if index + 1 < len(segments) else None
        if next_start is not None:
            overlap = max(0.0, segment["start"] + effective_duration - next_start)
            if overlap > 0.05:
                counts["overlap"] += 1
                issues.append(
                    {
                        "type": "overlap",
                        "segment_id": segment["id"],
                        "severity": "warning",
                        "seconds": round(overlap, 3),
                    }
                )
    export_ready = bool(segments) and all(
        segment["render"].get("status") == "ready" and segment.get("voice_id")
        for segment in segments
    )
    return {
        "export_ready": export_ready,
        "issue_count": len(issues),
        "counts": counts,
        "issues": issues,
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


def _reindex_segments(project: dict[str, Any]) -> None:
    for index, segment in enumerate(project["segments"]):
        segment["order"] = index


def _split_text_near(text: str, ratio: float) -> tuple[str, str]:
    value = str(text).strip()
    if len(value) < 2:
        raise ValueError("The text is too short to split safely.")
    target = min(len(value) - 1, max(1, round(len(value) * ratio)))
    boundaries = [
        index + 1
        for index, char in enumerate(value[:-1])
        if char in "。！？!?；;，,：:\n" or char.isspace()
    ]
    split_at = min(boundaries, key=lambda item: abs(item - target)) if boundaries else target
    left = value[:split_at].strip()
    right = value[split_at:].strip()
    if not left or not right:
        left, right = value[:target].strip(), value[target:].strip()
    if not left or not right:
        raise ValueError("Cannot split this segment without losing text.")
    return left, right


def _join_segment_text(values: Iterable[str]) -> str:
    result = ""
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        separator = (
            " "
            if result
            and result[-1:].isascii()
            and result[-1:].isalnum()
            and value[:1].isascii()
            and value[:1].isalnum()
            else ""
        )
        result += separator + value
    return _clean_text(result)


class DubProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def project_dir(self, project_id: str) -> Path:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise FileNotFoundError("Dubbing project not found.")
        return self.root / project_id

    def _project_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"

    def create(
        self,
        *,
        transcript: dict[str, Any],
        source_audio: Path,
        source_media: Path | None = None,
        title: str = "",
        target_language: str = "auto",
        default_voice_id: str | None = None,
    ) -> dict[str, Any]:
        if not source_audio.is_file():
            raise FileNotFoundError("Transcript source audio not found.")
        if source_media is not None and not source_media.is_file():
            raise FileNotFoundError("Original transcript media not found.")
        transcript_segments = transcript.get("segments")
        if not isinstance(transcript_segments, list) or not transcript_segments:
            raise ValueError("The transcript has no usable segments.")
        if default_voice_id is not None and not PROJECT_ID_PATTERN.fullmatch(default_voice_id):
            raise ValueError("Invalid default voice ID.")

        project_id = uuid.uuid4().hex
        created_at = _utc_now()
        fallback_title = str(transcript.get("title", "")).strip() or "Untitled dubbing project"
        source_media_filename = f"source-media{source_media.suffix.lower()}" if source_media else ""
        project = {
            "schema_version": DUB_PROJECT_SCHEMA_VERSION,
            "id": project_id,
            "title": _clean_title(title, fallback_title),
            "source_transcript_id": str(transcript.get("id", "")),
            "source_filename": str(transcript.get("source_filename", "")),
            "source_audio_filename": "source.wav",
            "source_media_filename": source_media_filename,
            "source_has_video": bool(source_media),
            "duration_seconds": round(max(0.0, _number(transcript.get("duration_seconds"))), 3),
            "source_language": str(transcript.get("language", "unknown")),
            "target_language": target_language,
            "status": "draft",
            "created_at": created_at,
            "updated_at": created_at,
            "last_job_id": None,
            "last_export_job_id": None,
            "roles": [],
            "segments": [],
            "exports": [],
        }
        default_role_id = None
        if default_voice_id:
            default_role_id = uuid.uuid4().hex
            project["roles"].append(
                {
                    "id": default_role_id,
                    "name": "Default role",
                    "voice_id": default_voice_id,
                    "color": ROLE_COLORS[0],
                }
            )
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
                    "role_id": default_role_id,
                    "fit_mode": "natural",
                    "source_segment_ids": [str(source.get("id", f"seg-{index + 1:05d}"))],
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
                if source_media is not None:
                    media_destination = project_dir / source_media_filename
                    try:
                        os.link(source_media, media_destination)
                    except OSError:
                        shutil.copy2(source_media, media_destination)
                _atomic_json(project_dir / "project.json", project)
            except Exception:
                shutil.rmtree(project_dir, ignore_errors=True)
                raise
        return project

    def load(self, project_id: str) -> dict[str, Any]:
        path = self._project_path(project_id)
        with self._lock:
            if not path.is_file():
                raise FileNotFoundError("Dubbing project not found.")
            project = json.loads(path.read_text(encoding="utf-8"))
            upgraded = _upgrade_project(project)
            if upgraded:
                _atomic_json(path, project)
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
                project = self.load(project_path.parent.name)
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
                    raise ValueError("The changes include a missing dubbing segment.")
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
                        raise ValueError("Invalid voice ID.")
                    if voice_id != segment["voice_id"]:
                        segment["voice_id"] = voice_id
                        segment["role_id"] = None
                        invalidated = True
                if "role_id" in update:
                    role_id = update["role_id"] or None
                    role = next(
                        (item for item in project["roles"] if item["id"] == role_id),
                        None,
                    ) if role_id else None
                    if role_id and role is None:
                        raise ValueError("Invalid role ID.")
                    voice_id = role.get("voice_id") if role else segment.get("voice_id")
                    previous_voice = segment.get("voice_id")
                    if role_id != segment.get("role_id") or voice_id != previous_voice:
                        segment["role_id"] = role_id
                        segment["voice_id"] = voice_id
                    if voice_id != previous_voice:
                        invalidated = True
                if "gain" in update:
                    gain = _number(update["gain"], -1.0)
                    if not 0.0 <= gain <= 2.0:
                        raise ValueError("Segment gain must be between 0 and 2.")
                    segment["gain"] = round(gain, 3)
                if "fit_mode" in update:
                    fit_mode = str(update["fit_mode"])
                    if fit_mode not in FIT_MODES:
                        raise ValueError("Invalid duration fit mode.")
                    segment["fit_mode"] = fit_mode
                if "start" in update:
                    segment["start"] = round(_number(update["start"], -1.0), 3)
                if "end" in update:
                    segment["end"] = round(_number(update["end"], -1.0), 3)
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

    def upsert_role(
        self,
        project_id: str,
        *,
        name: str,
        voice_id: str | None,
        role_id: str | None = None,
    ) -> dict[str, Any]:
        if voice_id is not None and not PROJECT_ID_PATTERN.fullmatch(voice_id):
            raise ValueError("Invalid voice ID.")
        with self._lock:
            project = self.load(project_id)
            role = next(
                (item for item in project["roles"] if item["id"] == role_id),
                None,
            ) if role_id else None
            if role_id and role is None:
                raise ValueError("Role not found.")
            if role is None:
                role = {
                    "id": uuid.uuid4().hex,
                    "name": _clean_title(name, "Untitled role"),
                    "voice_id": voice_id,
                    "color": ROLE_COLORS[len(project["roles"]) % len(ROLE_COLORS)],
                }
                project["roles"].append(role)
            else:
                previous_voice = role.get("voice_id")
                role["name"] = _clean_title(name, role["name"])
                role["voice_id"] = voice_id
                if previous_voice != voice_id:
                    for segment in project["segments"]:
                        if segment.get("role_id") == role["id"]:
                            segment["voice_id"] = voice_id
                            segment["revision"] = int(segment.get("revision", 0)) + 1
                            self._mark_stale(segment)
                    project["status"] = "draft"
            return self.save(project)

    def split_segment(
        self,
        project_id: str,
        segment_id: str,
        *,
        split_at: float,
    ) -> dict[str, Any]:
        with self._lock:
            project = self.load(project_id)
            try:
                index = next(i for i, item in enumerate(project["segments"]) if item["id"] == segment_id)
            except StopIteration as exc:
                raise ValueError("Dubbing segment not found.") from exc
            segment = project["segments"][index]
            split_at = round(float(split_at), 3)
            if split_at <= segment["start"] + 0.05 or split_at >= segment["end"] - 0.05:
                raise ValueError("The split point must be at least 0.05 seconds from either end.")
            ratio = (split_at - segment["start"]) / (segment["end"] - segment["start"])
            source_left, source_right = _split_text_near(segment["source_text"], ratio)
            active_left, active_right = _split_text_near(segment["active_text"], ratio)
            common = {
                "role_id": segment.get("role_id"),
                "voice_id": segment.get("voice_id"),
                "gain": segment.get("gain", 1.0),
                "fit_mode": segment.get("fit_mode", "natural"),
                "source_segment_ids": list(segment.get("source_segment_ids", [segment["id"]])),
            }
            left = {
                **segment,
                **common,
                "end": split_at,
                "source_text": source_left,
                "active_text": active_left,
                "revision": int(segment.get("revision", 0)) + 1,
                "render": _blank_render(),
            }
            right = {
                **common,
                "id": uuid.uuid4().hex,
                "order": index + 1,
                "start": split_at,
                "end": segment["end"],
                "source_text": source_right,
                "active_text": active_right,
                "revision": 1,
                "render": _blank_render(),
            }
            project["segments"][index:index + 1] = [left, right]
            _reindex_segments(project)
            project["status"] = "draft"
            return self.save(project)

    def merge_segments(self, project_id: str, segment_ids: list[str]) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(segment_ids))
        if len(unique_ids) < 2:
            raise ValueError("Select at least two segments to merge.")
        with self._lock:
            project = self.load(project_id)
            by_id = {item["id"]: item for item in project["segments"]}
            if not set(unique_ids).issubset(by_id):
                raise ValueError("The selection includes a missing dubbing segment.")
            selected = sorted((by_id[item] for item in unique_ids), key=lambda item: item["order"])
            orders = [item["order"] for item in selected]
            if orders != list(range(orders[0], orders[-1] + 1)):
                raise ValueError("Only consecutive timeline segments can be merged.")
            if len({item.get("role_id") for item in selected}) > 1 or len({item.get("voice_id") for item in selected}) > 1:
                raise ValueError("Assign the same role and voice to all selected segments before merging.")
            first = selected[0]
            merged = {
                **first,
                "end": selected[-1]["end"],
                "source_text": _join_segment_text(item["source_text"] for item in selected),
                "active_text": _join_segment_text(item["active_text"] for item in selected),
                "source_segment_ids": list(
                    dict.fromkeys(
                        source_id
                        for item in selected
                        for source_id in item.get("source_segment_ids", [item["id"]])
                    )
                ),
                "revision": max(int(item.get("revision", 0)) for item in selected) + 1,
                "render": _blank_render(),
            }
            project["segments"][orders[0]:orders[-1] + 1] = [merged]
            _reindex_segments(project)
            project["status"] = "draft"
            return self.save(project)

    def waveform(self, project_id: str, *, points: int = 1600) -> dict[str, Any]:
        points = min(4000, max(200, int(points)))
        project = self.load(project_id)
        source = self.source_audio(project_id)
        cache = self.project_dir(project_id) / f"waveform-{points}.json"
        source_stamp = source.stat().st_mtime_ns
        if cache.is_file():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                if payload.get("source_stamp") == source_stamp:
                    return payload
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        import numpy as np

        with wave.open(str(source), "rb") as audio_file:
            frames = audio_file.getnframes()
            sample_rate = audio_file.getframerate()
            channels = audio_file.getnchannels()
            sample_width = audio_file.getsampwidth()
            if sample_width != 2 or channels not in {1, 2}:
                raise ValueError("The project source audio is not a supported PCM WAV file.")
            bucket = max(1, (frames + points - 1) // points)
            peaks = []
            for start in range(0, frames, bucket):
                raw = audio_file.readframes(min(bucket, frames - start))
                chunk = np.frombuffer(raw, dtype="<i2")
                if channels == 2:
                    chunk = chunk.reshape(-1, 2).mean(axis=1)
                peaks.append(round(float(np.max(np.abs(chunk.astype(np.int32)))) / 32768.0, 4))
        payload = {
            "points": len(peaks),
            "sample_rate": sample_rate,
            "duration_seconds": round(frames / sample_rate, 3),
            "peaks": peaks,
            "source_stamp": source_stamp,
        }
        _atomic_json(cache, payload)
        return payload

    def create_bundle(self, project_id: str) -> Path:
        project = self.load(project_id)
        project_dir = self.project_dir(project_id)
        bundle_dir = project_dir / "bundles"
        bundle_dir.mkdir(exist_ok=True)
        path = bundle_dir / f"timbreloom-{project_id[:8]}.timbreloom"
        temporary = path.with_suffix(".tmp")
        allowed_roots = ("renders", "exports")
        referenced_renders = {
            str(segment.get("render", {}).get("filename", ""))
            for segment in project["segments"]
            if segment.get("render", {}).get("filename")
        }
        referenced_exports = {
            str(filename)
            for export in project.get("exports", [])
            for key in ("wav_filename", "srt_filename", "mp4_filename")
            if (filename := export.get(key))
        }
        voice_root = self.root.parent / "voices"
        requested_voice_ids = sorted(
            {
                str(voice_id)
                for voice_id in [
                    *(segment.get("voice_id") for segment in project["segments"]),
                    *(role.get("voice_id") for role in project.get("roles", [])),
                ]
                if voice_id
            }
        )
        bundled_voice_ids = [
            voice_id
            for voice_id in requested_voice_ids
            if (voice_root / voice_id / "profile.json").is_file()
            and (voice_root / voice_id / "reference.wav").is_file()
        ]
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        {
                            "format": "timbreloom-project",
                            "version": 2,
                            "voice_ids": bundled_voice_ids,
                        },
                        ensure_ascii=False,
                    ),
                )
                archive.write(project_dir / "project.json", "project.json")
                for filename in (project["source_audio_filename"], project.get("source_media_filename", "")):
                    if filename and (project_dir / filename).is_file():
                        archive.write(project_dir / filename, filename)
                for root_name in allowed_roots:
                    root = project_dir / root_name
                    if root.is_dir():
                        for item in root.iterdir():
                            referenced = referenced_renders if root_name == "renders" else referenced_exports
                            if item.is_file() and item.name in referenced:
                                archive.write(item, f"{root_name}/{item.name}")
                for voice_id in bundled_voice_ids:
                    for filename in ("profile.json", "reference.wav"):
                        archive.write(
                            voice_root / voice_id / filename,
                            f"voices/{voice_id}/{filename}",
                        )
            temporary.replace(path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return path

    def import_bundle(self, bundle: Path) -> dict[str, Any]:
        if not zipfile.is_zipfile(bundle):
            raise ValueError("The imported file is not a valid Timbreloom project bundle.")
        import_root = self.root / ".imports" / uuid.uuid4().hex
        import_root.mkdir(parents=True, exist_ok=False)
        try:
            with zipfile.ZipFile(bundle) as archive:
                members = archive.infolist()
                if len(members) > 10_000 or sum(item.file_size for item in members) > 8 * 1024**3:
                    raise ValueError("The project bundle is too large or contains too many files.")
                for member in members:
                    relative = Path(member.filename)
                    if relative.is_absolute() or ".." in relative.parts or member.is_dir():
                        if member.is_dir():
                            continue
                        raise ValueError("The project bundle contains an unsafe file path.")
                    if len(relative.parts) > 1:
                        media_file = len(relative.parts) == 2 and relative.parts[0] in {"renders", "exports"}
                        voice_file = (
                            len(relative.parts) == 3
                            and relative.parts[0] == "voices"
                            and PROJECT_ID_PATTERN.fullmatch(relative.parts[1])
                            and relative.parts[2] in {"profile.json", "reference.wav"}
                        )
                        if not media_file and not voice_file:
                            raise ValueError("The project bundle contains an unknown file.")
                    destination = import_root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
            manifest = json.loads((import_root / "manifest.json").read_text(encoding="utf-8"))
            if (
                not isinstance(manifest, dict)
                or manifest.get("format") != "timbreloom-project"
                or manifest.get("version") not in {1, 2}
            ):
                raise ValueError("Unsupported Timbreloom project bundle version.")
            bundled_voice_ids = list(dict.fromkeys(manifest.get("voice_ids", [])))
            if any(not PROJECT_ID_PATTERN.fullmatch(str(item)) for item in bundled_voice_ids):
                raise ValueError("Invalid project bundle voice manifest.")
            project = json.loads((import_root / "project.json").read_text(encoding="utf-8"))
            _upgrade_project(project)
            allowed_top_level = {
                "manifest.json",
                "project.json",
                str(project.get("source_audio_filename", "")),
                str(project.get("source_media_filename", "")),
            }
            unknown_top_level = {
                item.name
                for item in import_root.iterdir()
                if item.is_file() and item.name not in allowed_top_level
            }
            if unknown_top_level:
                raise ValueError("The bundle contains files not declared in the project manifest.")
            project["id"] = uuid.uuid4().hex
            project["title"] = _clean_title(f"{project.get('title', 'Imported project')} - Imported", "Imported project")
            project["last_job_id"] = None
            project["last_export_job_id"] = None
            project["created_at"] = _utc_now()
            project["updated_at"] = project["created_at"]
            validate_project(project)
            required_files = {str(project["source_audio_filename"])}
            if project.get("source_has_video"):
                required_files.add(str(project["source_media_filename"]))
            required_files.update(
                f"renders/{segment['render']['filename']}"
                for segment in project["segments"]
                if segment["render"].get("status") == "ready"
                and segment["render"].get("filename")
            )
            required_files.update(
                f"exports/{filename}"
                for export in project.get("exports", [])
                for key in ("wav_filename", "srt_filename", "mp4_filename")
                if (filename := export.get(key))
            )
            if any(not (import_root / relative).is_file() for relative in required_files):
                raise ValueError("The bundle is missing media or render files referenced in its manifest.")
            for voice_id in bundled_voice_ids:
                voice_dir = import_root / "voices" / voice_id
                profile_path = voice_dir / "profile.json"
                reference_path = voice_dir / "reference.wav"
                if not profile_path.is_file() or not reference_path.is_file():
                    raise ValueError("The bundle is missing a voice profile or reference recording.")
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                if profile.get("id") != voice_id or not str(profile.get("reference_text", "")).strip():
                    raise ValueError("Invalid voice profile in the project bundle.")
            destination = self.project_dir(project["id"])
            for name in ("renders", "exports", "jobs", "bundles"):
                (import_root / name).mkdir(exist_ok=True)
            _atomic_json(import_root / "project.json", project)
            voice_staging = import_root / "voices"
            if voice_staging.exists():
                voice_staging.rename(import_root / ".voices")
            import_root.replace(destination)
            staged_voices = destination / ".voices"
            installed_voices: list[Path] = []
            try:
                voice_root = self.root.parent / "voices"
                voice_root.mkdir(parents=True, exist_ok=True)
                for voice_id in bundled_voice_ids:
                    source_voice = staged_voices / voice_id
                    target_voice = voice_root / voice_id
                    if target_voice.exists():
                        for filename in ("profile.json", "reference.wav"):
                            source_digest = hashlib.sha256(
                                (source_voice / filename).read_bytes()
                            ).digest()
                            target_digest = hashlib.sha256(
                                (target_voice / filename).read_bytes()
                            ).digest()
                            if source_digest != target_digest:
                                raise ValueError("Import stopped because a local voice has the same ID but different content.")
                        continue
                    source_voice.replace(target_voice)
                    installed_voices.append(target_voice)
                shutil.rmtree(staged_voices, ignore_errors=True)
            except Exception:
                shutil.rmtree(destination, ignore_errors=True)
                for installed in installed_voices:
                    shutil.rmtree(installed, ignore_errors=True)
                raise
            return self.load(project["id"])
        except Exception:
            shutil.rmtree(import_root, ignore_errors=True)
            raise

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
            raise FileNotFoundError("Dubbing project source audio not found.")
        return path

    def source_media(self, project_id: str) -> Path:
        project = self.load(project_id)
        filename = str(project.get("source_media_filename", ""))
        if not filename or not project.get("source_has_video"):
            raise FileNotFoundError("This dubbing project has no original video.")
        path = self.project_dir(project_id) / filename
        if not path.is_file():
            raise FileNotFoundError("Dubbing project original video not found.")
        return path

    def render_path(self, project_id: str, filename: str) -> Path:
        _safe_filename(filename)
        return self.project_dir(project_id) / "renders" / filename

    def job_path(self, project_id: str, job_id: str) -> Path:
        if not PROJECT_ID_PATTERN.fullmatch(job_id):
            raise FileNotFoundError("Dubbing job not found.")
        return self.project_dir(project_id) / "jobs" / f"{job_id}.json"

    def save_job(self, job: dict[str, Any]) -> dict[str, Any]:
        if job.get("schema_version") != DUB_JOB_SCHEMA_VERSION:
            raise ValueError("Invalid dubbing job version.")
        if job.get("status") not in JOB_STATUSES:
            raise ValueError("Invalid dubbing job state.")
        job["updated_at"] = _utc_now()
        with self._lock:
            _atomic_json(self.job_path(job["project_id"], job["job_id"]), job)
        return job

    def load_job(self, project_id: str, job_id: str) -> dict[str, Any]:
        path = self.job_path(project_id, job_id)
        with self._lock:
            if not path.is_file():
                raise FileNotFoundError("Dubbing job not found.")
            job = json.loads(path.read_text(encoding="utf-8"))
        if job.get("schema_version") != DUB_JOB_SCHEMA_VERSION:
            raise ValueError("Unsupported dubbing job version.")
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
    import numpy as np

    if not segments:
        raise ValueError("No dubbing segments are available to export.")

    sources: list[dict[str, Any]] = []
    total_frames = round(max(0.0, project_duration_seconds) * sample_rate)
    for segment in segments:
        path = Path(segment["path"])
        with wave.open(str(path), "rb") as audio_file:
            if audio_file.getsampwidth() != 2:
                raise ValueError("Dubbing segments must use 16-bit PCM WAV.")
            if audio_file.getframerate() != sample_rate:
                raise ValueError("Dubbing segment sample rates do not match.")
            frames = audio_file.getnframes()
            channels = audio_file.getnchannels()
            if channels not in {1, 2}:
                raise ValueError("Dubbing segments must be mono or stereo WAV.")
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
        mux_video: Callable[..., dict[str, object]] = mux_dubbed_video,
    ) -> None:
        self.store = store
        self.load_voice = load_voice
        self.generate_segment = generate_segment
        self.model_id = model_id
        self.settings = settings
        self.max_attempts = max_attempts
        self.mux_video = mux_video
        self._lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._running_jobs: set[str] = set()

    def _fingerprint(self, segment: dict[str, Any], project: dict[str, Any], voice: dict[str, Any]) -> str:
        return content_fingerprint(segment, project, voice, self.model_id, self.settings)

    def has_active_jobs(self) -> bool:
        with self._lock:
            return bool(self._running_jobs)

    def create_job(
        self,
        project_id: str,
        *,
        mode: str,
        segment_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        project = self.store.load(project_id)
        if mode not in {"all", "selected", "failed"}:
            raise ValueError("Unsupported dubbing job mode.")
        with self._lock:
            if any(job.get("status") in ACTIVE_JOB_STATUSES for job in self.store.list_jobs(project_id)):
                raise RuntimeError("This project already has an active generation or export job.")
            known_ids = {segment["id"] for segment in project["segments"]}
            if mode == "all":
                selected_ids = [segment["id"] for segment in project["segments"]]
            elif mode == "failed":
                selected_ids = [segment["id"] for segment in project["segments"] if segment["render"]["status"] == "error"]
            else:
                selected_ids = list(dict.fromkeys(segment_ids or []))
                if not selected_ids:
                    raise ValueError("Select at least one segment to generate.")
                if not set(selected_ids).issubset(known_ids):
                    raise ValueError("The selection includes a missing dubbing segment.")
                order = {segment["id"]: segment["order"] for segment in project["segments"]}
                selected_ids.sort(key=order.__getitem__)
            if not selected_ids:
                raise ValueError("No dubbing segments match the selection.")

            job_id = uuid.uuid4().hex
            created_at = _utc_now()
            job = {
                "schema_version": DUB_JOB_SCHEMA_VERSION,
                "kind": "render",
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
                "message": "Waiting to generate",
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
                if job.get("kind", "render") != "render":
                    continue
                if job.get("status") not in ACTIVE_JOB_STATUSES:
                    continue
                if job.get("cancel_requested"):
                    job["status"] = "cancelled"
                    job["phase"] = "cancelled"
                    job["message"] = "Previous stop request confirmed after service restart"
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
                job["message"] = "Resuming generation after service restart"
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
            job["message"] = "Stopping after the current model call"
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
                            raise RuntimeError("The generated audio is too short for this text and may contain skipped words.")
                        break
                    except Exception as exc:
                        last_error = exc
                        metrics = None
                        if attempt < self.max_attempts:
                            time.sleep(0.25)
                if metrics is None:
                    raise RuntimeError(str(last_error or "The model did not return audio."))
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
                message="Generating dubbing segments",
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
                    raise InterruptedError("Dubbing job stopped.")
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
                    message=f"Processing segment {index} of {total}",
                )

                try:
                    if not segment.get("voice_id"):
                        raise ValueError("This segment has no voice assigned.")
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
                            fresh_render["error"] = "Text or voice changed during generation. Generate this segment again."
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
                message="Selected segments generated" if not failed else f"Completed. Segments to retry: {failed}",
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
                    message="Dubbing job stopped unexpectedly",
                    error=str(exc),
                )
            except Exception:
                pass
        finally:
            with self._lock:
                self._running_jobs.discard(job_id)
                self._cancel_events.pop(job_id, None)

    def export(
        self,
        project_id: str,
        *,
        original_audio_gain: float = 0.0,
        progress: Callable[[str, float, str], None] | None = None,
    ) -> dict[str, Any]:
        if not 0.0 <= original_audio_gain <= 1.0:
            raise ValueError("Original audio volume must be between 0 and 1.")
        project = self.store.load(project_id)
        timeline_segments: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        validated: list[tuple[dict[str, Any], Path]] = []
        if progress:
            progress("validating", 0.05, "Checking cached segments and timeline")
        for segment in project["segments"]:
            voice_id = segment.get("voice_id")
            if not voice_id:
                raise ValueError(f"Segment {segment['id']} has no voice assigned.")
            voice = self.load_voice(voice_id)
            fingerprint = self._fingerprint(segment, project, voice)
            render = segment["render"]
            if render.get("status") != "ready" or render.get("fingerprint") != fingerprint:
                raise ValueError(f"Generate or regenerate segment {segment['id']} first.")
            path = self.store.render_path(project_id, render["filename"])
            if not path.is_file():
                raise ValueError(f"Render file for segment {segment['id']} not found.")
            validated.append((segment, path))

        fit_dir = self.store.project_dir(project_id) / "exports" / f".fit-{uuid.uuid4().hex}"
        fit_dir.mkdir(parents=True, exist_ok=False)
        try:
            for index, (segment, path) in enumerate(validated, start=1):
                render = segment["render"]
                slot_duration = max(0.0, segment["end"] - segment["start"])
                mix_path = path
                fitted_metrics: dict[str, Any] | None = None
                if segment.get("fit_mode") == "slot" and slot_duration > 0:
                    mix_path = fit_dir / f"{segment['id']}.wav"
                    fitted_metrics = tempo_fit_wav(
                        path,
                        mix_path,
                        target_duration_seconds=slot_duration,
                    )
                effective_duration = (
                    float(fitted_metrics["output_duration_seconds"])
                    if fitted_metrics
                    else float(render["duration_seconds"])
                )
                overflow = max(0.0, effective_duration - slot_duration)
                if overflow > 0.05:
                    warnings.append(
                        {
                            "type": "fit-limited" if fitted_metrics and fitted_metrics["limited"] else "overflow",
                            "segment_id": segment["id"],
                            "overflow_seconds": round(overflow, 3),
                            "fit": fitted_metrics,
                        }
                    )
                timeline_segments.append(
                    {
                        "path": mix_path,
                        "start": segment["start"],
                        "gain": segment.get("gain", 1.0),
                    }
                )
                if progress:
                    progress(
                        "fitting",
                        0.05 + 0.35 * index / len(project["segments"]),
                        f"Preparing segment {index} of {len(project['segments'])}",
                    )
        except Exception:
            shutil.rmtree(fit_dir, ignore_errors=True)
            raise

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        export_id = uuid.uuid4().hex[:8]
        wav_filename = f"timbreloom-dub-{stamp}-{export_id}.wav"
        srt_filename = f"timbreloom-dub-{stamp}-{export_id}.srt"
        mp4_filename = (
            f"timbreloom-dub-{stamp}-{export_id}.mp4"
            if project.get("source_has_video")
            else ""
        )
        export_dir = self.store.project_dir(project_id) / "exports"
        wav_path = export_dir / wav_filename
        srt_path = export_dir / srt_filename
        mp4_path = export_dir / mp4_filename if mp4_filename else None
        video_metrics: dict[str, object] = {}
        try:
            if progress:
                progress("mixing", 0.5, "Mixing the full dubbing timeline")
            duration = mix_timeline_wav(
                timeline_segments,
                wav_path,
                project_duration_seconds=project["duration_seconds"],
            )
            srt_path.write_text(render_project_srt(project), encoding="utf-8")
            if mp4_path is not None:
                if progress:
                    progress("muxing", 0.72, "Combining video and audio")
                video_metrics = self.mux_video(
                    self.store.source_media(project_id),
                    wav_path,
                    mp4_path,
                    original_audio_gain=original_audio_gain,
                )
        except Exception:
            wav_path.unlink(missing_ok=True)
            srt_path.unlink(missing_ok=True)
            if mp4_path is not None:
                mp4_path.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(fit_dir, ignore_errors=True)
        export_record = {
            "id": export_id,
            "wav_filename": wav_filename,
            "srt_filename": srt_filename,
            "mp4_filename": mp4_filename,
            "duration_seconds": round(duration, 3),
            "warning_count": len(warnings),
            "warnings": warnings,
            "original_audio_gain": round(original_audio_gain, 3) if mp4_filename else 0.0,
            "video_codec_mode": str(video_metrics.get("video_codec_mode", "")),
            "video_size_bytes": int(video_metrics.get("size_bytes", 0)),
            "created_at": _utc_now(),
        }
        project["exports"].append(export_record)
        project["exports"] = project["exports"][-20:]
        self.store.save(project)
        if progress:
            progress("complete", 1.0, "Export complete")
        return export_record


class DubExportService:
    """Persistent background export jobs with restart recovery."""

    def __init__(self, store: DubProjectStore, render_service: DubRenderService) -> None:
        self.store = store
        self.render_service = render_service
        self._lock = threading.RLock()
        self._running_jobs: set[str] = set()

    def has_active_jobs(self) -> bool:
        with self._lock:
            return bool(self._running_jobs)

    def create_job(self, project_id: str, *, original_audio_gain: float = 0.0) -> dict[str, Any]:
        if not 0.0 <= original_audio_gain <= 1.0:
            raise ValueError("Original audio volume must be between 0 and 1.")
        project = self.store.load(project_id)
        if not project_quality(project)["export_ready"]:
            raise ValueError("Assign voices and generate up-to-date audio for every segment before exporting.")
        with self._lock:
            active = [
                item
                for item in self.store.list_jobs(project_id)
                if item.get("status") in ACTIVE_JOB_STATUSES
            ]
            if active:
                raise RuntimeError("This project already has an active generation or export job.")
            job_id = uuid.uuid4().hex
            created_at = _utc_now()
            job = {
                "schema_version": DUB_JOB_SCHEMA_VERSION,
                "kind": "export",
                "job_id": job_id,
                "project_id": project_id,
                "status": "queued",
                "phase": "queued",
                "progress": 0.0,
                "message": "Export job saved",
                "original_audio_gain": round(original_audio_gain, 3),
                "result": None,
                "error": None,
                "created_at": created_at,
                "updated_at": created_at,
            }
            self.store.save_job(job)
            project["last_export_job_id"] = job_id
            self.store.save(project)
            self.launch(project_id, job_id)
            return job

    def launch(self, project_id: str, job_id: str) -> None:
        with self._lock:
            if job_id in self._running_jobs:
                return
            self._running_jobs.add(job_id)
        threading.Thread(
            target=self._process,
            args=(project_id, job_id),
            name=f"dub-export-{job_id[:8]}",
            daemon=True,
        ).start()

    def recover(self) -> int:
        recovered = 0
        for project in self.store.list():
            for job in self.store.list_jobs(project["id"]):
                if job.get("kind") != "export" or job.get("status") not in ACTIVE_JOB_STATUSES:
                    continue
                job["status"] = "queued"
                job["phase"] = "queued"
                job["progress"] = 0.0
                job["message"] = "Restarting export safely after service restart"
                job["error"] = None
                self.store.save_job(job)
                self.launch(project["id"], job["job_id"])
                recovered += 1
        return recovered

    def get_job(self, project_id: str, job_id: str) -> dict[str, Any]:
        job = self.store.load_job(project_id, job_id)
        if job.get("kind") != "export":
            raise FileNotFoundError("Export job not found.")
        return job

    def _process(self, project_id: str, job_id: str) -> None:
        def progress(phase: str, value: float, message: str) -> None:
            current = self.store.load_job(project_id, job_id)
            current.update(
                {
                    "status": "running",
                    "phase": phase,
                    "progress": round(value, 4),
                    "message": message,
                }
            )
            self.store.save_job(current)

        try:
            job = self.store.load_job(project_id, job_id)
            progress("validating", 0.02, "Checking whether the project is ready to export")
            result = self.render_service.export(
                project_id,
                original_audio_gain=float(job.get("original_audio_gain", 0.0)),
                progress=progress,
            )
            completed = self.store.load_job(project_id, job_id)
            completed.update(
                {
                    "status": "complete",
                    "phase": "complete",
                    "progress": 1.0,
                    "message": "Export complete",
                    "result": result,
                    "error": None,
                }
            )
            self.store.save_job(completed)
        except Exception as exc:
            try:
                failed = self.store.load_job(project_id, job_id)
                failed.update(
                    {
                        "status": "error",
                        "phase": "error",
                        "message": "Export failed",
                        "error": str(exc),
                    }
                )
                self.store.save_job(failed)
            except Exception:
                pass
        finally:
            with self._lock:
                self._running_jobs.discard(job_id)
