from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx


REFERENCE_TEXT = (
    "你好，这是用于验证声音克隆的参考录音。"
    "今天的天气很好，我们正在测试一个本地语音工作台。"
    "请确保每句话都能清楚完整地读出来。"
)
SOURCE_TEXT = (
    "第一段台词用来检查本地转录和时间线。"
    "第二段台词会测试角色、声音缓存以及安全时长适配。"
    "最后，我们会导出一段带有新声音的视频。"
)


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Missing required command: {name}")
    return path


def _run(command: list[str], timeout: int = 120) -> None:
    subprocess.run(command, check=True, timeout=timeout)


def _poll(client: httpx.Client, path: str, *, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_phase = ""
    while time.monotonic() < deadline:
        response = client.get(path)
        response.raise_for_status()
        payload = response.json()
        phase = str(payload.get("phase", payload.get("status", "")))
        if phase != last_phase:
            print(f"{path}: {phase} {payload.get('message', '')}", flush=True)
            last_phase = phase
        if payload.get("status") not in {"queued", "running"}:
            return payload
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for {path}")


def run(base_url: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="timbreloom-e2e-") as temporary:
        work = Path(temporary)
        reference_say = work / "reference.aiff"
        source_say = work / "source.aiff"
        reference = work / "reference.wav"
        source_audio = work / "source.wav"
        source_video = work / "source.mp4"
        _run([_tool("say"), "-v", "Tingting", "-r", "165", "-o", str(reference_say), REFERENCE_TEXT])
        _run([_tool("say"), "-v", "Tingting", "-r", "175", "-o", str(source_say), SOURCE_TEXT])
        for raw, wav in ((reference_say, reference), (source_say, source_audio)):
            _run(
                [
                    _tool("ffmpeg"),
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(raw),
                    "-ac",
                    "1",
                    "-ar",
                    "24000",
                    "-c:a",
                    "pcm_s16le",
                    str(wav),
                ]
            )
        _run(
            [
                _tool("ffmpeg"),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x161817:s=640x360:r=24",
                "-i",
                str(source_audio),
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(source_video),
            ],
            timeout=300,
        )

        with httpx.Client(base_url=base_url, timeout=120.0) as client:
            health = client.get("/api/health")
            health.raise_for_status()
            if health.json().get("version") != "1.0.0":
                raise RuntimeError("The target service is not Timbreloom 1.0.0")

            with reference.open("rb") as audio:
                voice_response = client.post(
                    "/api/voices",
                    data={"name": "V1 E2E Voice", "reference_text": REFERENCE_TEXT},
                    files={"reference_audio": (reference.name, audio, "audio/aiff")},
                )
            voice_response.raise_for_status()
            voice = voice_response.json()["voice"]

            with source_video.open("rb") as media:
                asr_response = client.post(
                    "/api/asr/jobs",
                    data={"language": "zh", "initial_prompt": "本地语音工作台，时间线，角色，声音缓存"},
                    files={"media": (source_video.name, media, "video/mp4")},
                )
            asr_response.raise_for_status()
            asr_job = asr_response.json()
            asr_done = _poll(
                client,
                f"/api/asr/jobs/{asr_job['job_id']}",
                timeout=1_800,
            )
            if asr_done["status"] != "complete":
                raise RuntimeError(f"ASR failed: {asr_done.get('error')}")
            transcript_id = asr_done["result"]["id"]

            project_response = client.post(
                "/api/dub/projects",
                json={
                    "transcript_id": transcript_id,
                    "title": "Timbreloom 1.0 E2E",
                    "target_language": "chinese",
                    "default_voice_id": voice["id"],
                },
            )
            project_response.raise_for_status()
            project = project_response.json()["project"]
            project_id = project["id"]

            waveform = client.get(f"/api/dub/projects/{project_id}/waveform?points=600")
            waveform.raise_for_status()
            if not waveform.json().get("peaks"):
                raise RuntimeError("Waveform extraction returned no peaks")

            first = project["segments"][0]
            if first["end"] - first["start"] >= 0.3 and len(first["active_text"]) >= 2:
                split_at = round((first["start"] + first["end"]) / 2, 3)
                split_response = client.post(
                    f"/api/dub/projects/{project_id}/segments/{first['id']}/split",
                    json={"split_at": split_at},
                )
                split_response.raise_for_status()
                split_project = split_response.json()["project"]
                pair = [split_project["segments"][0]["id"], split_project["segments"][1]["id"]]
                merge_response = client.post(
                    f"/api/dub/projects/{project_id}/segments/merge",
                    json={"segment_ids": pair},
                )
                merge_response.raise_for_status()
                project = merge_response.json()["project"]

            role_response = client.post(
                f"/api/dub/projects/{project_id}/roles",
                json={"name": "旁白", "voice_id": voice["id"]},
            )
            role_response.raise_for_status()
            project = role_response.json()["project"]
            role = project["roles"][-1]
            patch_response = client.patch(
                f"/api/dub/projects/{project_id}",
                json={
                    "segments": [
                        {
                            "id": segment["id"],
                            "role_id": role["id"],
                            "voice_id": voice["id"],
                            "fit_mode": "slot",
                        }
                        for segment in project["segments"]
                    ]
                },
            )
            patch_response.raise_for_status()

            render_response = client.post(
                f"/api/dub/projects/{project_id}/jobs",
                json={"mode": "all", "segment_ids": []},
            )
            render_response.raise_for_status()
            render_job = render_response.json()
            render_done = _poll(
                client,
                f"/api/dub/projects/{project_id}/jobs/{render_job['job_id']}",
                timeout=3_600,
            )
            if render_done["status"] != "complete":
                raise RuntimeError(f"TTS render failed: {render_done.get('error')}")

            export_response = client.post(
                f"/api/dub/projects/{project_id}/export-jobs",
                json={"original_audio_gain": 0.15},
            )
            export_response.raise_for_status()
            export_job = export_response.json()
            export_done = _poll(
                client,
                f"/api/dub/projects/{project_id}/export-jobs/{export_job['job_id']}",
                timeout=1_800,
            )
            if export_done["status"] != "complete":
                raise RuntimeError(f"Export failed: {export_done.get('error')}")
            result = export_done["result"]

            downloaded: dict[str, str] = {}
            for kind in ("mp4", "wav", "srt"):
                url = result.get(f"{kind}_url")
                if not url:
                    continue
                target = output_dir / f"e2e-output.{kind}"
                target.write_bytes(client.get(url).content)
                downloaded[kind] = str(target)

            bundle_response = client.get(f"/api/dub/projects/{project_id}/bundle")
            bundle_response.raise_for_status()
            bundle_path = output_dir / "e2e-project.timbreloom"
            bundle_path.write_bytes(bundle_response.content)
            with bundle_path.open("rb") as bundle:
                imported_response = client.post(
                    "/api/dub/projects/import",
                    files={"bundle": (bundle_path.name, bundle, "application/zip")},
                )
            imported_response.raise_for_status()
            imported = imported_response.json()["project"]

            return {
                "version": health.json()["version"],
                "voice_id": voice["id"],
                "transcript_id": transcript_id,
                "project_id": project_id,
                "imported_project_id": imported["id"],
                "segment_count": len(project["segments"]),
                "render_job": render_done,
                "export_job": export_done,
                "outputs": downloaded,
                "bundle": str(bundle_path),
            }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Timbreloom 1.0 real local end-to-end validation")
    parser.add_argument("--base-url", default="http://127.0.0.1:7865")
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.base_url, arguments.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
