from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import mlx_whisper


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Timbreloom local Whisper worker")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--language", default="")
    parser.add_argument("--initial-prompt", default="")
    arguments = parser.parse_args()

    result = mlx_whisper.transcribe(
        arguments.audio,
        path_or_hf_repo=arguments.model,
        language=arguments.language or None,
        initial_prompt=arguments.initial_prompt or None,
        word_timestamps=True,
        condition_on_previous_text=True,
        hallucination_silence_threshold=2.0,
        verbose=False,
    )

    output_path = Path(arguments.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


if __name__ == "__main__":
    main()
