"""Offline file and live ASR protocol for an isolated inference process."""
from __future__ import annotations

import argparse
import base64
import json
import sys
import wave
from contextlib import redirect_stdout
from pathlib import Path

from .asr_streams import open_stream
from .job_storage import atomic_json


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stream = None
    try:
        with redirect_stdout(sys.stderr):
            stream = open_stream(args.engine, args.model, args.language, args.prompt)
        if args.audio:
            if args.output is None:
                raise ValueError("File transcription needs an output path.")
            with wave.open(str(args.audio)) as audio, redirect_stdout(sys.stderr):
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                    raise ValueError("Expected mono 16 kHz PCM16 audio.")
                while pcm := audio.readframes(16000):
                    stream.push(pcm)
                result = stream.push(b"", final=True)
            atomic_json(args.output, result)
            return
        emit({"ready": True})
        for line in sys.stdin:
            message = json.loads(line)
            pcm = base64.b64decode(message.get("pcm", ""), validate=True)
            if len(pcm) % 2 or len(pcm) > 32000:
                raise ValueError("Invalid live PCM packet.")
            final = message.get("final") is True
            with redirect_stdout(sys.stderr):
                result = stream.push(pcm, final=final)
            emit(result)
            if final:
                break
    except Exception as error:
        if args.audio:
            raise
        emit({"error": str(error)})
    finally:
        if stream is not None:
            stream.close()


if __name__ == "__main__":
    main()
