from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Protocol

from backend.i18n.language_registry import get_language_label, normalize_language_code
from backend.translation.contracts import TranslationDocument, TranslationResult, TranslationSegment


TRANSLATION_SOURCE_HASH_PREFIX = "translation_document"
DEFAULT_TRANSLATION_PROVIDER = "ai.default"


class TranslationProvider(Protocol):
    id: str
    label: str
    type: str

    def translate(self, document: TranslationDocument, target_language: str) -> list[TranslationSegment]: ...


class AITranslationProvider:
    id = DEFAULT_TRANSLATION_PROVIDER
    label = "AI 翻译"
    type = "ai"

    def __init__(self, ai_mgr: Any):
        self.ai_mgr = ai_mgr

    def _request_translation(self, document: TranslationDocument, target_label: str, glossary_lines: list[str], required_keys: list[str], retry_note: str = "") -> Any:
        context = document.context
        if retry_note:
            context = f"{context}\n{retry_note}".strip()
        return self.ai_mgr.execute_structured_task(
            "task.translation",
            {
                "variables": {
                    "target_lang": target_label,
                    "source_format": document.format,
                    "translation_context": context,
                    "glossary_block": "\n".join(glossary_lines),
                    "required_segment_keys": ", ".join(required_keys),
                    "translation_input_json": json.dumps(document.to_prompt_payload(), ensure_ascii=False),
                }
            },
        )

    def _parse_segments(self, raw_segments: Any, document: TranslationDocument) -> tuple[list[TranslationSegment], list[str]]:
        if not isinstance(raw_segments, list):
            raise ValueError("翻译器返回格式无效")
        source_roles = {segment.key: segment.role for segment in document.segments}
        source_keys = set(source_roles)
        translated: list[TranslationSegment] = []
        translated_text: dict[str, str] = {}
        seen_keys: set[str] = set()
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key or key not in source_keys or key in seen_keys:
                continue
            text = str(item.get("text") or "")
            seen_keys.add(key)
            translated_text[key] = text
            translated.append(TranslationSegment(key=key, text=text, role=source_roles.get(key, "body")))
        missing = [segment.key for segment in document.segments if not translated_text.get(segment.key, "").strip()]
        return translated, missing

    def translate(self, document: TranslationDocument, target_language: str) -> list[TranslationSegment]:
        target_label = get_language_label(target_language, default=target_language)
        required_keys = [segment.key for segment in document.segments]
        glossary_lines = [
            f"- {term.source} => {term.target or '(按上下文处理)'}{f'；{term.note}' if term.note else ''}"
            for term in document.glossary
        ]
        parsed = self._request_translation(document, target_label, glossary_lines, required_keys)
        if not isinstance(parsed, dict):
            raise ValueError("翻译器返回格式无效")

        translated, missing = self._parse_segments(parsed.get("segments"), document)
        if missing:
            # ponytail: 只对缺字段重试一次，避免为偶发模型漏 key 引入复杂修复流程。
            retry_note = f"上次输出缺少这些 key 或译文为空：{', '.join(missing)}。这次必须返回所有 required keys。"
            parsed = self._request_translation(document, target_label, glossary_lines, required_keys, retry_note=retry_note)
            if not isinstance(parsed, dict):
                raise ValueError("翻译器返回格式无效")
            translated, missing = self._parse_segments(parsed.get("segments"), document)
        if missing:
            raise ValueError(f"翻译器未返回完整译文: {', '.join(missing)}")
        return translated


class TranslationManager:
    """通用翻译入口；调用方传入文档，管理器返回同 key 的译文段。"""

    def __init__(self, ai_mgr: Any):
        self.providers: dict[str, TranslationProvider] = {
            DEFAULT_TRANSLATION_PROVIDER: AITranslationProvider(ai_mgr),
        }

    def list_providers(self) -> list[dict[str, str]]:
        return [
            {"id": provider.id, "label": provider.label, "type": provider.type}
            for provider in self.providers.values()
        ]

    def provider_requires_ai(self, provider_id: str) -> bool:
        provider_key = str(provider_id or "").strip() or DEFAULT_TRANSLATION_PROVIDER
        provider = self.providers.get(provider_key)
        return bool(provider and provider.type == "ai")

    @staticmethod
    def build_source_hash(document: TranslationDocument) -> str:
        payload = {
            "segments": [
                {
                    "key": segment.key,
                    "text": str(segment.text or "").replace("\r\n", "\n").strip(),
                }
                for segment in document.segments
            ],
        }
        source_text = f"{TRANSLATION_SOURCE_HASH_PREFIX}\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        return hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    def translate_document(self, document: TranslationDocument, target_language: Any, *, provider_id: str = DEFAULT_TRANSLATION_PROVIDER) -> TranslationResult:
        language_code = normalize_language_code(target_language)
        if not language_code:
            raise ValueError("目标语言不能为空")
        if not document.segments:
            raise ValueError("没有可翻译的文本")
        provider_key = str(provider_id or "").strip() or DEFAULT_TRANSLATION_PROVIDER
        provider = self.providers.get(provider_key)
        if not provider:
            raise ValueError("当前翻译器不可用")

        source_hash = self.build_source_hash(document)
        segments = provider.translate(document, language_code)
        return TranslationResult(
            target_language=language_code,
            source_hash=source_hash,
            provider=provider.id,
            segments=segments,
            updated_at=int(time.time() * 1000),
        )
