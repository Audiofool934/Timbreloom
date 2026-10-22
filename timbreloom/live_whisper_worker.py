"""A session-scoped Whisper process; JSON lines carry requests and results."""
from __future__ import annotations

import argparse
import contextlib
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    output = sys.stdout

    def emit(value):
        output.write(json.dumps(value, ensure_ascii=False) + "\n")
        output.flush()

    # Keep native/library diagnostics out of the JSON protocol.
    with contextlib.redirect_stdout(sys.stderr):
        import mlx.core as mx
        import mlx_whisper
        from mlx_whisper.transcribe import ModelHolder
        from timbreloom.whisper_worker import _json_default

        ModelHolder.get_model(args.model, mx.float16)
        emit({"ready": True})
        for line in sys.stdin:
            request = json.loads(line)
            try:
                result = mlx_whisper.transcribe(
                    request["audio"], path_or_hf_repo=args.model,
                    language=request.get("language") or None,
                    initial_prompt=request.get("prompt") or None,
                    word_timestamps=True, condition_on_previous_text=False,
                    temperature=0.0, hallucination_silence_threshold=1.0,
                    verbose=False,
                )
                emit(json.loads(json.dumps(result, default=_json_default)))
            except Exception as exc:
                emit({"error": str(exc)})


if __name__ == "__main__":
    main()
