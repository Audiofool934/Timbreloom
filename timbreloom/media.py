from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MediaInfo:
    duration_seconds: float
    has_audio: bool
    has_video: bool
    format_name: str


def _tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        instruction = "Reinstall Timbreloom." if os.getenv("TIMBRELOOM_EMBEDDED") == "1" else "Run brew install ffmpeg first."
        raise RuntimeError(f"{name} was not found. {instruction}")
    return executable


def probe_media(source: Path) -> MediaInfo:
    result = subprocess.run(
        [
            _tool("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration,format_name:stream=codec_type",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "Cannot read the media file."
        raise ValueError(f"Media inspection failed: {detail}")

    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    format_data = payload.get("format", {})
    try:
        duration = float(format_data.get("duration", 0.0))
    except (TypeError, ValueError):
        duration = 0.0
    return MediaInfo(
        duration_seconds=max(0.0, duration),
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
        has_video=any(stream.get("codec_type") == "video" for stream in streams),
        format_name=str(format_data.get("format_name", "")),
    )


def prepare_asr_audio(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _tool("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=21_600,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "Cannot extract audio."
        raise ValueError(f"Audio preparation failed: {detail}")


def prepare_vc_audio(source: Path, destination: Path) -> None:
    """Extract the primary audio track for voice conversion without clipping it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _tool("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=21_600,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "Cannot extract audio for voice conversion."
        raise ValueError(f"Voice conversion audio preparation failed: {detail}")


def detect_silence_midpoints(source: Path) -> list[float]:
    """Return safe cut candidates at the middle of speech pauses."""
    result = subprocess.run(
        [
            _tool("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(source),
            "-vn",
            "-af",
            "silencedetect=noise=-35dB:d=0.30",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=21_600,
        check=False,
    )
    if result.returncode != 0:
        return []

    silence_start: float | None = None
    midpoints: list[float] = []
    for line in result.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match is not None:
            silence_start = float(start_match.group(1))
        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match is not None and silence_start is not None:
            silence_end = float(end_match.group(1))
            if silence_end > silence_start:
                midpoints.append((silence_start + silence_end) / 2.0)
            silence_start = None
    return midpoints


def extract_vc_chunk(
    source: Path,
    destination: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    """Extract one non-overlapping 22.05 kHz PCM chunk for Seed-VC."""
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError("Invalid voice conversion segment time range.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _tool("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-ss",
            f"{start_seconds:.3f}",
            "-t",
            f"{end_seconds - start_seconds:.3f}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=21_600,
        check=False,
    )
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        detail = result.stderr.strip() or "Cannot extract the voice conversion audio segment."
        raise ValueError(f"Voice conversion audio segmentation failed: {detail}")


def normalize_vc_audio(source: Path, destination: Path) -> None:
    """Normalize a converter result to Timbreloom's 24 kHz mono WAV contract."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _tool("ffmpeg"),
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
        timeout=21_600,
        check=False,
    )
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        detail = result.stderr.strip() or "Cannot normalize the converted audio."
        raise ValueError(f"Converted audio processing failed: {detail}")


def extract_voice_clip(
    source: Path,
    destination: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError("Invalid voice reference time range.")
    duration = end_seconds - start_seconds
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _tool("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-ss",
            f"{start_seconds:.3f}",
            "-t",
            f"{duration:.3f}",
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
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "Cannot extract the voice reference clip."
        raise ValueError(f"Voice reference extraction failed: {detail}")


def tempo_fit_wav(
    source: Path,
    destination: Path,
    *,
    target_duration_seconds: float,
    min_speed: float = 0.8,
    max_speed: float = 1.25,
) -> dict[str, object]:
    """Fit speech toward a timeline slot without truncating audio.

    FFmpeg's atempo filter preserves pitch. The requested speed is clamped to a
    deliberately conservative range so timing correction does not turn into an
    inaudible quality failure. The caller can surface ``limited`` to the user.
    """
    if not source.is_file():
        raise FileNotFoundError("The dubbing segment to fit was not found.")
    if target_duration_seconds <= 0:
        raise ValueError("The target slot duration must be greater than 0.")
    if min_speed <= 0 or max_speed < min_speed:
        raise ValueError("Invalid safe playback speed range.")

    info = probe_media(source)
    if not info.has_audio or info.duration_seconds <= 0:
        raise ValueError("The dubbing segment has no usable audio.")
    requested_speed = info.duration_seconds / target_duration_seconds
    applied_speed = min(max_speed, max(min_speed, requested_speed))
    limited = not math.isclose(requested_speed, applied_speed, rel_tol=0.0, abs_tol=0.001)

    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            _tool("ffmpeg"),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-filter:a",
            f"atempo={applied_speed:.6f}",
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
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        detail = result.stderr.strip() or "Cannot safely fit the dubbing duration."
        raise ValueError(f"Dubbing duration fit failed: {detail}")
    fitted = probe_media(destination)
    return {
        "source_duration_seconds": round(info.duration_seconds, 3),
        "target_duration_seconds": round(target_duration_seconds, 3),
        "output_duration_seconds": round(fitted.duration_seconds, 3),
        "requested_speed": round(requested_speed, 4),
        "applied_speed": round(applied_speed, 4),
        "limited": limited,
    }


def mux_dubbed_video(
    source_video: Path,
    dubbed_audio: Path,
    destination: Path,
    *,
    original_audio_gain: float = 0.0,
) -> dict[str, object]:
    if not source_video.is_file():
        raise FileNotFoundError("The original dubbing project video was not found.")
    if not dubbed_audio.is_file():
        raise FileNotFoundError("Dubbing timeline audio not found.")
    if not 0.0 <= original_audio_gain <= 1.0:
        raise ValueError("Original audio volume must be between 0 and 1.")

    media_info = probe_media(source_video)
    if not media_info.has_video:
        raise ValueError("The dubbing source media has no video track.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    audio_options: list[str]
    if original_audio_gain > 0 and media_info.has_audio:
        filter_graph = (
            f"[0:a:0]asetpts=PTS-STARTPTS,volume={original_audio_gain:.6f}[original];"
            "[1:a:0]asetpts=PTS-STARTPTS[dub];"
            "[original][dub]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
            "alimiter=limit=0.95[aout]"
        )
        audio_options = ["-filter_complex", filter_graph, "-map", "0:v:0", "-map", "[aout]"]
    else:
        audio_options = ["-map", "0:v:0", "-map", "1:a:0"]

    common = [
        _tool("ffmpeg"),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_video),
        "-i",
        str(dubbed_audio),
        *audio_options,
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-sn",
        "-dn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-metadata:s:a:0",
        "title=Timbreloom Dub",
        "-movflags",
        "+faststart",
        "-avoid_negative_ts",
        "make_zero",
    ]

    encoder = os.getenv("TIMBRELOOM_H264_ENCODER", "libx264")
    if encoder not in {"libx264", "h264_videotoolbox"}:
        raise ValueError("Unsupported video encoder configuration.")
    quality = ["-q:v", "75"] if encoder == "h264_videotoolbox" else ["-preset", "medium", "-crf", "18"]
    attempts = [
        ("copy", [*common, "-c:v", "copy", str(destination)]),
        (
            "h264",
            [
                *common,
                "-c:v",
                encoder,
                *quality,
                "-pix_fmt",
                "yuv420p",
                str(destination),
            ],
        ),
    ]
    errors: list[str] = []
    codec_mode = ""
    for mode, command in attempts:
        destination.unlink(missing_ok=True)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=21_600,
            check=False,
        )
        if result.returncode == 0 and destination.is_file():
            codec_mode = mode
            break
        errors.append(result.stderr.strip() or f"{mode} video mux failed")
    else:
        detail = "; ".join(errors)
        raise ValueError(f"Video dubbing export failed: {detail}")

    output_info = probe_media(destination)
    if not output_info.has_video or not output_info.has_audio:
        destination.unlink(missing_ok=True)
        raise ValueError("The dubbed video export is missing a video or audio track.")
    return {
        "duration_seconds": round(output_info.duration_seconds, 3),
        "original_audio_gain": round(original_audio_gain, 3),
        "video_codec_mode": codec_mode,
        "size_bytes": destination.stat().st_size,
    }
