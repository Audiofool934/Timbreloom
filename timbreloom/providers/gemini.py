from __future__ import annotations

import os
from typing import Any

from .base import ProviderDescriptor, TextModelProvider


MAX_GEMINI_TEXT_CHARS = 60_000


class GeminiTextProvider(TextModelProvider):
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("TIMBRELOOM_GEMINI_MODEL", "gemini-2.5-flash")

    @property
    def configured(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY", "").strip())

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id="gemini-text",
            name="Gemini",
            provider_type="text",
            local=False,
            capabilities=("punctuation", "transcript-cleanup", "translation"),
            configured=self.configured,
            ready=self.configured,
            detail=self.model if self.configured else "missing-api-key",
        )

    def _client(self) -> Any:
        from google import genai

        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        return genai.Client(api_key=api_key)

    def check_connection(self) -> dict[str, Any]:
        client = self._client()
        try:
            model_info = client.models.get(model=self.model)
            return {
                "ok": True,
                "provider": "gemini-text",
                "model": getattr(model_info, "name", self.model),
            }
        finally:
            client.close()

    def transform(
        self,
        text: str,
        task: str,
        target_language: str = "",
    ) -> dict[str, Any]:
        source = text.strip()
        if not source:
            raise ValueError("Enter transcript text to process.")
        if len(source) > MAX_GEMINI_TEXT_CHARS:
            raise ValueError(
                f"Each Gemini request is limited to {MAX_GEMINI_TEXT_CHARS:,} characters."
            )

        if task == "punctuation":
            instruction = (
                "Add accurate punctuation and natural paragraph breaks to the following transcript. "
                "Preserve every original word, repetition, filler, number, and proper noun. Do not summarize, rewrite, add, remove, or explain content. "
                "Return only the processed transcript as plain text, without Markdown."
            )
        elif task == "cleanup":
            instruction = (
                "Clean up the following transcript for readable punctuation, paragraphs, and obvious ASR sentence breaks. "
                "Do not summarize or add information absent from the original. "
                "Keep the original word when uncertain. Return only the processed plain text."
            )
        elif task == "translate":
            language = target_language.strip()
            if not language:
                raise ValueError("Choose a target language for translation.")
            instruction = (
                f"Translate the entire following transcript into {language}. "
                "Preserve tone, paragraphs, numbers, names, and repetitions. Do not summarize or explain. "
                "Return only the translation as plain text, without Markdown."
            )
        else:
            raise ValueError("Unsupported Gemini text task.")

        client = self._client()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=f"{instruction}\n\n<transcript>\n{source}\n</transcript>",
                config={
                    "temperature": 0.1,
                    "max_output_tokens": 32_768,
                },
            )
        finally:
            client.close()
        result_text = (response.text or "").strip()
        if not result_text:
            raise RuntimeError("Gemini did not return text.")
        return {
            "ok": True,
            "provider": "gemini-text",
            "model": self.model,
            "task": task,
            "text": result_text,
        }
