"""Desktop-owned service supervisor. No shell, dependency install, or model download."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7865)
    parser.add_argument("--parent", type=int, required=True)
    args = parser.parse_args()
    # A private process group lets quit clean up FFmpeg / ASR / VC descendants too.
    # Foundation.Process already makes the child a process-group leader on macOS.
    if os.getpgrp() != os.getpid():
        os.setsid()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print("Timbreloom: runtime supervisor starting", flush=True)
    worker = subprocess.Popen([
        sys.executable, "-m", "timbreloom.desktop_worker", "--port", str(args.port),
    ])
    while worker.poll() is None and not stopping:
        if os.getppid() != args.parent:
            stopping = True
            break
        time.sleep(0.25)
    # Always clean descendants, including when the main worker crashed.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    os.killpg(os.getpgrp(), signal.SIGTERM)
    try:
        worker.wait(timeout=4)
    except subprocess.TimeoutExpired:
        pass
    # Children may have survived their parent. This group belongs only to this runner.
    os.killpg(os.getpgrp(), signal.SIGKILL)
    return worker.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
