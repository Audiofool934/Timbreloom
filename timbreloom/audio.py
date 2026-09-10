from __future__ import annotations

import wave
from pathlib import Path


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio_file:
        return audio_file.getnframes() / float(audio_file.getframerate())


def stitch_wav_files(
    sources: list[Path],
    destination: Path,
    gap_seconds: float = 0.14,
) -> float:
    """Concatenate PCM WAV files with constant memory and a short safe pause."""
    if not sources:
        raise ValueError("No audio segments to join.")

    total_frames = 0
    expected_params: tuple[int, int, int] | None = None

    with wave.open(str(destination), "wb") as output:
        for index, source in enumerate(sources):
            with wave.open(str(source), "rb") as current:
                params = (
                    current.getnchannels(),
                    current.getsampwidth(),
                    current.getframerate(),
                )
                if expected_params is None:
                    expected_params = params
                    output.setnchannels(params[0])
                    output.setsampwidth(params[1])
                    output.setframerate(params[2])
                elif params != expected_params:
                    raise ValueError("Audio segment formats differ and cannot be joined safely.")

                while frames := current.readframes(65_536):
                    output.writeframesraw(frames)
                total_frames += current.getnframes()

            if index < len(sources) - 1:
                assert expected_params is not None
                gap_frames = round(expected_params[2] * gap_seconds)
                output.writeframesraw(
                    b"\x00" * gap_frames * expected_params[0] * expected_params[1]
                )
                total_frames += gap_frames

        output.writeframes(b"")

    assert expected_params is not None
    return total_frames / expected_params[2]
