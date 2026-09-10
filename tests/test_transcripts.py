from pathlib import Path

import pytest

from timbreloom.transcripts import (
    build_transcript,
    load_transcript,
    render_export,
    save_transcript,
    selected_segment_range,
    update_segment_texts,
    join_segment_texts,
)


def _transcript() -> dict:
    return build_transcript(
        transcript_id="a" * 32,
        raw_result={
            "text": "First sentence. Second sentence. Third sentence.",
            "language": "en",
            "segments": [
                {"start": 0.0, "end": 2.1, "text": "First sentence."},
                {"start": 2.1, "end": 4.4, "text": "Second sentence."},
                {"start": 4.4, "end": 6.8, "text": "Third sentence."},
            ],
        },
        source_filename="sample.wav",
        source_bytes=1_024,
        duration_seconds=6.8,
        engine="local-whisper-asr",
        model="test-model",
        requested_language="auto",
    )


def test_transcript_round_trip_preserves_timestamps(tmp_path: Path) -> None:
    transcript = _transcript()
    original_times = [
        (segment["start"], segment["end"]) for segment in transcript["segments"]
    ]
    update_segment_texts(
        transcript,
        {"seg-00002": "Second sentence, manually corrected."},
    )
    save_transcript(tmp_path, transcript)
    loaded = load_transcript(tmp_path)

    assert loaded["segments"][1]["text"] == "Second sentence, manually corrected."
    assert [
        (segment["start"], segment["end"]) for segment in loaded["segments"]
    ] == original_times


def test_subtitle_exports_use_provider_timestamps() -> None:
    transcript = _transcript()
    srt = render_export(transcript, "srt")
    vtt = render_export(transcript, "vtt")

    assert "00:00:02,100 --> 00:00:04,400" in srt
    assert "00:00:02.100 --> 00:00:04.400" in vtt
    assert vtt.startswith("WEBVTT\n")


def test_voice_selection_requires_contiguous_segments() -> None:
    transcript = _transcript()
    start, end, text = selected_segment_range(
        transcript,
        ["seg-00001", "seg-00002"],
    )
    assert (start, end) == (0.0, 4.4)
    assert text == "First sentence. Second sentence."

    with pytest.raises(ValueError, match="consecutive"):
        selected_segment_range(
            transcript,
            ["seg-00001", "seg-00003"],
        )


@pytest.mark.parametrize(("parts", "expected"), [
    (["Hello.", "Welcome back."], "Hello. Welcome back."),
    (["\u4f60\u597d\u3002", "\u6b22\u8fce\u3002"], "\u4f60\u597d\u3002\u6b22\u8fce\u3002"),
])
def test_joining_preserves_language_specific_spacing(parts: list[str], expected: str) -> None:
    assert join_segment_texts({"text": part} for part in parts) == expected
