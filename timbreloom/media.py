from __future__ import annotations

import json
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
        raise RuntimeError(f"没有找到 {name}。请先运行 brew install ffmpeg。")
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
        detail = result.stderr.strip() or "无法读取媒体文件。"
        raise ValueError(f"媒体检查失败：{detail}")

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
        detail = result.stderr.strip() or "无法提取音频。"
        raise ValueError(f"音频准备失败：{detail}")


def extract_voice_clip(
    source: Path,
    destination: Path,
    start_seconds: float,
    end_seconds: float,
) -> None:
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError("音色片段时间范围无效。")
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
        detail = result.stderr.strip() or "无法截取音色片段。"
        raise ValueError(f"音色片段提取失败：{detail}")
