from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TRANSCRIPT_SCHEMA_VERSION = 1
SUPPORTED_EXPORT_FORMATS = {"txt", "srt", "vtt"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_words(words: Any) -> list[dict[str, Any]]:
    if not isinstance(words, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for word in words:
        if not isinstance(word, dict):
            continue
        text = str(word.get("word", ""))
        start = max(0.0, _number(word.get("start")))
        end = max(start, _number(word.get("end"), start))
        item: dict[str, Any] = {
            "text": text,
            "start": round(start, 3),
            "end": round(end, 3),
        }
        if word.get("probability") is not None:
            item["probability"] = round(_number(word.get("probability")), 4)
        cleaned.append(item)
    return cleaned


def join_segment_texts(segments: Iterable[dict[str, Any]]) -> str:
    texts = [str(segment.get("text", "")).strip() for segment in segments]
    texts = [text for text in texts if text]
    if not texts:
        return ""

    result = texts[0]
    cjk = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
    for text in texts[1:]:
        previous = result[-1:] if result else ""
        following = text[:1]
        if cjk.match(previous) or cjk.match(following) or previous in "。！？；：，、…":
            result += text
        else:
            result += f" {text}"
    return result.strip()


def build_transcript(
    *,
    transcript_id: str,
    raw_result: dict[str, Any],
    source_filename: str,
    source_bytes: int,
    duration_seconds: float,
    engine: str,
    model: str,
    requested_language: str,
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    raw_segments = raw_result.get("segments", [])
    if isinstance(raw_segments, list):
        for index, raw_segment in enumerate(raw_segments, start=1):
            if not isinstance(raw_segment, dict):
                continue
            text = str(raw_segment.get("text", "")).strip()
            if not text:
                continue
            start = max(0.0, _number(raw_segment.get("start")))
            end = max(start, _number(raw_segment.get("end"), start))
            segments.append(
                {
                    "id": f"seg-{index:05d}",
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "words": _clean_words(raw_segment.get("words")),
                }
            )

    raw_text = str(raw_result.get("text", "")).strip()
    if not segments and raw_text:
        segments.append(
            {
                "id": "seg-00001",
                "start": 0.0,
                "end": round(max(0.0, duration_seconds), 3),
                "text": raw_text,
                "words": [],
            }
        )
    if not segments:
        raise ValueError("The transcript is empty.")

    created_at = _utc_now()
    detected_language = str(raw_result.get("language", "")).strip() or requested_language or "unknown"
    return {
        "schema_version": TRANSCRIPT_SCHEMA_VERSION,
        "id": transcript_id,
        "title": Path(source_filename).stem or "Untitled transcript",
        "source_filename": source_filename,
        "source_bytes": source_bytes,
        "duration_seconds": round(duration_seconds, 3),
        "engine": engine,
        "model": model,
        "requested_language": requested_language or "auto",
        "language": detected_language,
        "created_at": created_at,
        "updated_at": created_at,
        "text": raw_text or join_segment_texts(segments),
        "segments": segments,
        "cloud_processed": False,
    }


def validate_transcript(transcript: dict[str, Any]) -> None:
    if transcript.get("schema_version") != TRANSCRIPT_SCHEMA_VERSION:
        raise ValueError("Unsupported transcript version.")
    if not transcript.get("id"):
        raise ValueError("The transcript is missing an ID.")
    segments = transcript.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("The transcript has no valid segments.")

    previous_start = -1.0
    for segment in segments:
        if not isinstance(segment, dict) or not segment.get("id"):
            raise ValueError("Invalid transcript segment format.")
        start = _number(segment.get("start"), -1.0)
        end = _number(segment.get("end"), -1.0)
        text = str(segment.get("text", "")).strip()
        if start < 0 or end < start or start < previous_start:
            raise ValueError("Invalid transcript timestamp order.")
        if not text:
            raise ValueError("Transcript segment text cannot be empty.")
        previous_start = start


def save_transcript(transcript_dir: Path, transcript: dict[str, Any]) -> Path:
    validate_transcript(transcript)
    transcript_dir.mkdir(parents=True, exist_ok=True)
    destination = transcript_dir / "transcript.json"
    temporary = transcript_dir / "transcript.json.tmp"
    temporary.write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def load_transcript(transcript_dir: Path) -> dict[str, Any]:
    path = transcript_dir / "transcript.json"
    if not path.is_file():
        raise FileNotFoundError("Transcript not found.")
    transcript = json.loads(path.read_text(encoding="utf-8"))
    validate_transcript(transcript)
    return transcript


def public_transcript_summary(transcript: dict[str, Any]) -> dict[str, Any]:
    text = str(transcript.get("text", ""))
    return {
        "id": transcript["id"],
        "title": transcript.get("title", ""),
        "source_filename": transcript.get("source_filename", ""),
        "duration_seconds": transcript.get("duration_seconds", 0.0),
        "language": transcript.get("language", "unknown"),
        "engine": transcript.get("engine", ""),
        "model": transcript.get("model", ""),
        "segment_count": len(transcript.get("segments", [])),
        "created_at": transcript.get("created_at", ""),
        "updated_at": transcript.get("updated_at", ""),
        "text_preview": text[:160],
        "cloud_processed": bool(transcript.get("cloud_processed", False)),
    }


def update_segment_texts(
    transcript: dict[str, Any],
    updates: dict[str, str],
) -> dict[str, Any]:
    if not updates:
        raise ValueError("No transcript changes to save.")
    known_ids = {segment["id"] for segment in transcript["segments"]}
    unknown_ids = set(updates) - known_ids
    if unknown_ids:
        raise ValueError("Includes a missing transcript segment.")

    for segment in transcript["segments"]:
        if segment["id"] not in updates:
            continue
        text = " ".join(str(updates[segment["id"]]).strip().split())
        if not text:
            raise ValueError("Transcript segment text cannot be empty.")
        if len(text) > 10_000:
            raise ValueError("Each transcript segment is limited to 10,000 characters.")
        segment["text"] = text
    transcript["text"] = join_segment_texts(transcript["segments"])
    transcript["updated_at"] = _utc_now()
    return transcript


def selected_segment_range(
    transcript: dict[str, Any],
    segment_ids: list[str],
) -> tuple[float, float, str]:
    if not segment_ids:
        raise ValueError("Select at least one transcript segment.")
    all_segments = transcript["segments"]
    index_by_id = {segment["id"]: index for index, segment in enumerate(all_segments)}
    try:
        indices = sorted({index_by_id[segment_id] for segment_id in segment_ids})
    except KeyError as exc:
        raise ValueError("The selection includes a missing transcript segment.") from exc
    if indices != list(range(indices[0], indices[-1] + 1)):
        raise ValueError("Select consecutive transcript segments to create a voice.")

    selected = all_segments[indices[0] : indices[-1] + 1]
    start = float(selected[0]["start"])
    end = float(selected[-1]["end"])
    text = join_segment_texts(selected)
    return start, end, text


def _timestamp(seconds: float, decimal_marker: str) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1_000)
    return (
        f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"
        f"{decimal_marker}{milliseconds:03d}"
    )


def render_export(transcript: dict[str, Any], export_format: str) -> str:
    export_format = export_format.lower()
    if export_format not in SUPPORTED_EXPORT_FORMATS:
        raise ValueError("Only TXT, SRT, and VTT exports are supported.")
    segments = transcript["segments"]
    if export_format == "txt":
        return "\n".join(segment["text"].strip() for segment in segments) + "\n"
    if export_format == "srt":
        blocks = []
        for index, segment in enumerate(segments, start=1):
            blocks.append(
                f"{index}\n"
                f"{_timestamp(float(segment['start']), ',')} --> "
                f"{_timestamp(float(segment['end']), ',')}\n"
                f"{segment['text'].strip()}"
            )
        return "\n\n".join(blocks) + "\n"

    blocks = ["WEBVTT"]
    for segment in segments:
        blocks.append(
            f"{_timestamp(float(segment['start']), '.')} --> "
            f"{_timestamp(float(segment['end']), '.')}\n"
            f"{segment['text'].strip()}"
        )
    return "\n\n".join(blocks) + "\n"


def write_export(
    transcript_dir: Path,
    transcript: dict[str, Any],
    export_format: str,
) -> Path:
    content = render_export(transcript, export_format)
    exports_dir = transcript_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    destination = exports_dir / f"transcript.{export_format.lower()}"
    destination.write_text(content, encoding="utf-8")
    return destination
