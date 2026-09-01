from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass


AUDIO_TOKENS_PER_SECOND = 12.5
GENERATION_TOKEN_LIMIT = 1_024
SEGMENT_ESTIMATED_TOKEN_LIMIT = 880

_PRIMARY_ENDINGS = frozenset("。！？.!?")
_SECONDARY_ENDINGS = frozenset("，,；;：:、")
_CLOSERS = frozenset('"\'”’）)]】》」』')


@dataclass(frozen=True, slots=True)
class TextSegment:
    index: int
    start: int
    end: int
    text: str
    estimated_audio_tokens: int

    def public(self) -> dict[str, int | str]:
        return asdict(self)


def _is_cjk(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
        or 0xF900 <= codepoint <= 0xFAFF
    )


def estimate_audio_tokens(text: str) -> int:
    """Estimate Qwen3-TTS codec tokens with a conservative speech-rate model."""
    cjk_count = sum(1 for character in text if _is_cjk(character))
    non_cjk = "".join(" " if _is_cjk(character) else character for character in text)
    word_count = len(re.findall(r"[^\W_]+(?:['’][^\W_]+)?", non_cjk, re.UNICODE))

    seconds = cjk_count / 3.8 + word_count / 2.35
    seconds += sum(text.count(mark) for mark in _PRIMARY_ENDINGS) * 0.24
    seconds += sum(text.count(mark) for mark in _SECONDARY_ENDINGS) * 0.10
    seconds += text.count("\n") * 0.18

    if cjk_count == 0 and word_count == 0:
        seconds += len("".join(text.split())) / 8.0

    return max(1, math.ceil(max(seconds, 0.35) * AUDIO_TOKENS_PER_SECOND))


def _is_decimal_point(text: str, index: int) -> bool:
    return (
        text[index] == "."
        and index > 0
        and index + 1 < len(text)
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    )


def _semantic_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0

    while index < len(text):
        character = text[index]
        boundary = character in _PRIMARY_ENDINGS and not _is_decimal_point(text, index)

        if character == "\n":
            newline_end = index
            while newline_end < len(text) and text[newline_end] == "\n":
                newline_end += 1
            boundary = newline_end - index >= 2
            if boundary:
                index = newline_end - 1

        if boundary:
            end = index + 1
            while end < len(text) and text[end] in _CLOSERS:
                end += 1
            while end < len(text) and text[end].isspace():
                end += 1
            if end > start:
                spans.append((start, end))
            start = end
            index = end
            continue

        index += 1

    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _largest_safe_prefix(text: str, start: int, end: int, token_limit: int) -> int:
    low = start + 1
    high = end
    best = low

    while low <= high:
        middle = (low + high) // 2
        if estimate_audio_tokens(text[start:middle]) <= token_limit:
            best = middle
            low = middle + 1
        else:
            high = middle - 1

    search_floor = start + max(1, int((best - start) * 0.58))
    safe_boundaries = [
        position + 1
        for position in range(search_floor, best)
        if text[position] in _SECONDARY_ENDINGS or text[position].isspace()
    ]
    return safe_boundaries[-1] if safe_boundaries else best


def _split_oversized_span(
    text: str,
    start: int,
    end: int,
    token_limit: int,
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start

    while estimate_audio_tokens(text[cursor:end]) > token_limit:
        cut = _largest_safe_prefix(text, cursor, end, token_limit)
        if cut <= cursor:
            raise RuntimeError("无法为长文本找到安全分段位置。")
        spans.append((cursor, cut))
        cursor = cut

    if cursor < end:
        spans.append((cursor, end))
    return spans


def segment_text(
    text: str,
    token_limit: int = SEGMENT_ESTIMATED_TOKEN_LIMIT,
) -> list[TextSegment]:
    """Create lossless, multi-sentence segments below a conservative token budget."""
    source = text.strip()
    if not source:
        raise ValueError("目标文字不能为空。")
    if token_limit <= 0 or token_limit > GENERATION_TOKEN_LIMIT:
        raise ValueError("分段 token 上限无效。")

    atomic_spans: list[tuple[int, int]] = []
    for start, end in _semantic_spans(source):
        atomic_spans.extend(_split_oversized_span(source, start, end, token_limit))

    packed_spans: list[tuple[int, int]] = []
    current_start: int | None = None
    current_end: int | None = None

    for start, end in atomic_spans:
        if current_start is None:
            current_start, current_end = start, end
            continue

        assert current_end is not None
        if estimate_audio_tokens(source[current_start:end]) <= token_limit:
            current_end = end
        else:
            packed_spans.append((current_start, current_end))
            current_start, current_end = start, end

    if current_start is not None and current_end is not None:
        packed_spans.append((current_start, current_end))

    segments = [
        TextSegment(
            index=index,
            start=start,
            end=end,
            text=source[start:end],
            estimated_audio_tokens=estimate_audio_tokens(source[start:end]),
        )
        for index, (start, end) in enumerate(packed_spans, start=1)
    ]

    if "".join(segment.text for segment in segments) != source:
        raise RuntimeError("分段完整性校验失败，生成已中止。")
    if any(segment.estimated_audio_tokens > token_limit for segment in segments):
        raise RuntimeError("分段超出安全 token 预算，生成已中止。")
    return segments
