from __future__ import annotations

import os
from typing import Any

from google import genai

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

    def _client(self) -> genai.Client:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("没有配置 GEMINI_API_KEY。")
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
            raise ValueError("需要处理的转录文字不能为空。")
        if len(source) > MAX_GEMINI_TEXT_CHARS:
            raise ValueError(
                f"单次 Gemini 处理不能超过 {MAX_GEMINI_TEXT_CHARS:,} 个字符。"
            )

        if task == "punctuation":
            instruction = (
                "为下面的语音转录补充准确标点和自然分段。"
                "必须保留全部原词、重复、语气词、数字和专有名词，不能总结、改写、增删或解释。"
                "只返回处理后的转录纯文本，不要使用 Markdown。"
            )
        elif task == "cleanup":
            instruction = (
                "整理下面的语音转录，使标点、段落和明显的 ASR 断句更易读。"
                "不要总结，不要增加原文没有的信息。"
                "如果无法确定某个词，保留原词。只返回处理后的纯文本。"
            )
        elif task == "translate":
            language = target_language.strip()
            if not language:
                raise ValueError("翻译任务需要目标语言。")
            instruction = (
                f"将下面的语音转录完整翻译为{language}。"
                "保留语气、段落、数字、名称和重复，不要总结或解释。"
                "只返回翻译后的纯文本，不要使用 Markdown。"
            )
        else:
            raise ValueError("不支持该 Gemini 文本任务。")

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
            raise RuntimeError("Gemini 没有返回文本。")
        return {
            "ok": True,
            "provider": "gemini-text",
            "model": self.model,
            "task": task,
            "text": result_text,
        }
