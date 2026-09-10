"""Start the local service with bounded startup diagnostics before optional imports."""

from __future__ import annotations

import argparse
import faulthandler
import time


def main() -> None:
    started = time.perf_counter()
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    print("Timbreloom: Python worker starting", flush=True)
    faulthandler.enable()
    faulthandler.dump_traceback_later(15)
    from app import app
    import uvicorn

    faulthandler.cancel_dump_traceback_later()
    print(f"Timbreloom: service imports ready in {time.perf_counter() - started:.3f}s", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, timeout_graceful_shutdown=3)


if __name__ == "__main__":
    main()
