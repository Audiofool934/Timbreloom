#!/usr/bin/env python3
"""Measure fresh backend processes and local page delivery, without loading models."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def measure(python: Path, root: Path, limit: float) -> dict:
    with tempfile.TemporaryDirectory(prefix="timbreloom-startup-") as temporary:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        environment = {
            **os.environ, "TIMBRELOOM_DATA_DIR": temporary, "TIMBRELOOM_PRELOAD": "0",
            "PYTHONUNBUFFERED": "1", "HF_HUB_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base_url = f"http://127.0.0.1:{port}"
        log_path = Path(temporary) / "startup.log"
        worker_pid = None
        with log_path.open("w") as log:
            started = time.perf_counter()
            process = subprocess.Popen(
                [str(python), "-m", "timbreloom.desktop_server", "--port", str(port),
                 "--parent", str(os.getpid())],
                cwd=root, env=environment, stdout=log, stderr=log, start_new_session=True,
            )
            try:
                while time.perf_counter() - started < max(30, limit * 2):
                    if process.poll() is not None:
                        raise RuntimeError(log_path.read_text()[-4000:])
                    try:
                        with opener.open(base_url + "/api/runtime", timeout=.25) as response:
                            runtime = json.load(response)
                        break
                    except (OSError, urllib.error.URLError):
                        time.sleep(.025)
                else:
                    raise TimeoutError("The backend did not become ready within the measurement window")
                service_seconds = time.perf_counter() - started
                if Path(runtime["data_root"]).resolve() != Path(temporary).resolve():
                    raise RuntimeError("The benchmark connected to a different data library")
                worker_pid = runtime["pid"]
                with opener.open(base_url + "/", timeout=5) as response:
                    page = response.read()
                    if b"Timbreloom" not in page:
                        raise RuntimeError("The local workspace page was not served")
                page_seconds = time.perf_counter() - started
                with opener.open(base_url + "/api/health?library=false", timeout=5) as response:
                    health = json.load(response)
                if health["model_loaded"] or runtime["busy"]:
                    raise RuntimeError("Startup unexpectedly started model work")
                rss = int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(worker_pid)], text=True))
                return {
                    "service_ready_seconds": round(service_seconds, 4),
                    "page_served_seconds": round(page_seconds, 4),
                    "backend_rss_mib": round(rss / 1024, 2),
                    "model_loaded": False,
                }
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                if worker_pid:
                    try:
                        os.kill(worker_pid, 0)
                    except ProcessLookupError:
                        pass
                    else:
                        raise RuntimeError("A benchmark backend survived supervisor shutdown")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--max-ready-seconds", type=float, default=5)
    parser.add_argument("--output", type=Path, default=ROOT / "build/release-validation/startup.json")
    args = parser.parse_args()
    if args.iterations < 3 or args.max_ready_seconds <= 0:
        parser.error("Use at least three samples and a positive ready-time budget")
    samples = []
    for index in range(args.iterations):
        sample = measure(args.python.absolute(), args.root.resolve(), args.max_ready_seconds)
        samples.append(sample)
        print(f"Startup {index + 1}/{args.iterations}: {sample['page_served_seconds']:.3f}s", flush=True)
    seconds = sorted(item["page_served_seconds"] for item in samples)
    result = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Fresh backend processes, empty isolated libraries; filesystem cache is not purged. Page delivery is not a native paint measurement.",
        "platform": platform.platform(), "python": platform.python_version(),
        "samples": samples,
        "p50_seconds": seconds[math.ceil(len(seconds) * .5) - 1],
        "p95_seconds": seconds[math.ceil(len(seconds) * .95) - 1],
        "maximum_seconds": max(seconds), "budget_seconds": args.max_ready_seconds,
        "passed": max(seconds) <= args.max_ready_seconds,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"Evidence: {args.output}")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
