"""Small adapters for the pinned, isolated streaming ASR runtime."""
from __future__ import annotations

import re
from pathlib import Path

from .transcripts import join_segment_texts


NEMOTRON_LANGUAGES = {
    "auto": "auto", "en": "en-US", "zh": "zh-CN", "ja": "ja-JP", "ko": "ko-KR",
    "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "it": "it-IT", "pt": "pt-BR", "ru": "ru-RU",
}


def merge_moonshine_lines(lines: list[dict]) -> list[dict]:
    """Remove repeated context only when the SDK's adjacent audio spans overlap.

    Prefer the newer line's wording and punctuation for the shared suffix.
    Matching is bounded; repeated speech in nonoverlapping spans stays intact.
    """
    token_pattern = r"[\u3400-\u9fff]|[a-zA-Z0-9]+(?:['’][a-zA-Z0-9]+)*|[^\W_]"
    merged = []
    for source in sorted(lines, key=lambda line: (line["start"], line.get("line_id", 0))):
        line = dict(source)
        if not line["text"].strip():
            continue
        if merged and line["start"] < merged[-1]["end"]:
            previous = merged[-1]
            left = list(re.finditer(token_pattern, previous["text"]))
            right = list(re.finditer(token_pattern, line["text"]))
            for count in range(min(12, len(left), len(right)), 0, -1):
                if ([token.group().casefold() for token in left[-count:]]
                        == [token.group().casefold() for token in right[:count]]):
                    previous["text"] = previous["text"][:left[-count].start()].rstrip()
                    if not previous["text"]:
                        merged.pop()
                    break
            if merged:
                merged[-1]["end"] = max(merged[-1]["start"], min(merged[-1]["end"], line["start"]))
        merged.append(line)
    return merged


def snapshot(segments: list[dict], language: str, *, final: bool) -> dict:
    clean = [{key: segment[key] for key in ("start", "end", "text")} for segment in segments]
    # Retain the newest sentence as revisable, including Moonshine's overlap.
    boundary = len(clean) if final else max(0, len(clean) - 1)
    return {"language": language, "segments": clean, "text": join_segment_texts(clean),
            "stable_text": join_segment_texts(clean[:boundary]),
            "draft": join_segment_texts(clean[boundary:])}


class MoonshineStream:
    def __init__(self, model: Path, language: str, prompt: str = "") -> None:
        from moonshine_voice import ModelArch, Transcriber

        arch = ModelArch.SMALL_STREAMING if language == "en" else ModelArch.TINY_STREAMING
        options = {"max_tokens_per_second": 13} if language == "zh" else {}
        self.language = language
        self.transcriber = Transcriber(model, arch, update_interval=.5, options=options)
        self.stream = None
        self.lines = {}
        self.errors = []
        try:
            if prompt:
                self.transcriber.set_context(prompt)
            self.stream = self.transcriber.create_stream(update_interval=.5)
            self.stream.add_listener(self._receive)
            self.stream.start()
        except BaseException:
            self.close()
            raise

    def _receive(self, event) -> None:
        if hasattr(event, "error"):
            self.errors.append(event.error)
        elif getattr(event, "line", None) is not None:
            self._line(event.line)

    def _line(self, line) -> None:
        self.lines[line.line_id] = {"line_id": line.line_id, "text": line.text,
                                   "start": max(0, line.start_time),
                                   "end": max(0, line.start_time + line.duration)}

    def push(self, pcm: bytes, *, final: bool = False) -> dict:
        import numpy as np

        if pcm:
            self.stream.add_audio((np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768).tolist(), 16000)
        if final:
            transcript = self.stream.stop()
            if transcript is None:
                raise RuntimeError("Moonshine could not finalize the transcript.")
            for line in transcript.lines:
                self._line(line)
        if self.errors:
            raise RuntimeError("Moonshine could not transcribe this audio.") from self.errors[0]
        return snapshot(merge_moonshine_lines(list(self.lines.values())), self.language, final=final)

    def close(self) -> None:
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        self.transcriber.close()


class NemotronStream:
    """Use upstream cached frontend, encoder and decoder with emission timestamps.

    The upstream high-level live session exposes text only. These same pinned
    components also preserve timestamps for the saved transcript and subtitles.
    """
    def __init__(self, model: Path, language: str, prompt: str = "") -> None:
        from mlx_audio.stt.utils import load_model
        from mlx_audio.stt.models.nemotron_asr.audio import StreamingLogMelSpectrogram
        from mlx_audio.stt.models.nemotron_asr.streaming import ConformerStreamingState
        from mlx_audio.stt.models.nemotron_asr.rnnt import GreedyDecoderState

        self.language = language
        self.prompt_language = NEMOTRON_LANGUAGES[language]
        self.model = load_model(str(model))
        if self.prompt_language not in self.model.prompt_dictionary:
            raise ValueError("This Nemotron model does not support the selected language.")
        self.frontend = StreamingLogMelSpectrogram(self.model.preprocessor_config)
        self.encoder = ConformerStreamingState(self.model.encoder, att_context_size=[56, 3])
        self.decoder = GreedyDecoderState(self.model)
        self.frames = 0
        self.samples = 0
        self.tokens = []

    def push(self, pcm: bytes, *, final: bool = False) -> dict:
        import mlx.core as mx
        import numpy as np
        from mlx_audio.stt.models.nemo.alignment import tokens_to_sentences

        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        self.samples += len(audio)
        if self.samples:
            mel = self.frontend.push(mx.array(audio), final=final)
            for encoded in self.encoder.push(mel, final=final):
                features = self.model.apply_prompt(encoded, self.prompt_language)
                self.encoder.materialize(features)
                self.tokens.extend(self.decoder.decode(features, self.frames))
                self.frames += features.shape[1]
        duration = self.samples / 16000
        segments = [{"start": min(duration, sentence.start), "end": min(duration, sentence.end),
                     "text": sentence.text.strip()} for sentence in tokens_to_sentences(self.tokens)
                    if sentence.text.strip()]
        return snapshot(segments, self.language, final=final)

    def close(self) -> None:
        # The owning inference process exits; no accelerator state survives it.
        pass


def open_stream(engine: str, model: Path, language: str, prompt: str = ""):
    if engine == "nemotron":
        return NemotronStream(model, language, prompt)
    if engine in {"moonshine-en", "moonshine-zh"}:
        return MoonshineStream(model, engine.rsplit("-", 1)[1], prompt)
    raise ValueError("Unknown streaming transcription model.")
