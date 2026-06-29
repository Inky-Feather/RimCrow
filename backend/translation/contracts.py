from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TranslationSegment:
    """一段需要翻译的文本。key 用于把译文稳定映射回业务字段。"""

    key: str
    text: str
    role: str = "body"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranslationSegment":
        return cls(
            key=str(data.get("key") or "").strip(),
            text=str(data.get("text") or ""),
            role=str(data.get("role") or "body").strip() or "body",
        )

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "text": self.text, "role": self.role}


@dataclass(frozen=True)
class TranslationTerm:
    """通用术语提示。调用方可来自游戏、模组或用户词库。"""

    source: str
    target: str = ""
    note: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranslationTerm":
        return cls(
            source=str(data.get("source") or data.get("term") or "").strip(),
            target=str(data.get("target") or data.get("translation") or "").strip(),
            note=str(data.get("note") or data.get("description") or "").strip(),
        )

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "note": self.note}


@dataclass(frozen=True)
class TranslationDocument:
    """通用翻译输入文档。业务字段必须先转换成 segments。"""

    segments: list[TranslationSegment]
    format: str = "plain_text"
    context: str = ""
    glossary: list[TranslationTerm] = field(default_factory=list)

    @classmethod
    def from_segments(
        cls,
        segments: list[dict[str, Any] | TranslationSegment],
        *,
        format: str = "plain_text",
        context: str = "",
        glossary: list[dict[str, Any] | TranslationTerm] | None = None,
    ) -> "TranslationDocument":
        normalized = [
            item if isinstance(item, TranslationSegment) else TranslationSegment.from_dict(item)
            for item in segments
        ]
        normalized = [item for item in normalized if item.key and item.text]
        normalized_terms = [
            item if isinstance(item, TranslationTerm) else TranslationTerm.from_dict(item)
            for item in (glossary or [])
        ]
        normalized_terms = [item for item in normalized_terms if item.source]
        return cls(
            segments=normalized,
            format=str(format or "plain_text").strip() or "plain_text",
            context=str(context or "").strip(),
            glossary=normalized_terms,
        )

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "context": self.context,
            "glossary": [term.to_dict() for term in self.glossary],
            "segments": [segment.to_dict() for segment in self.segments],
        }


@dataclass(frozen=True)
class TranslationResult:
    """通用翻译输出。调用方根据 key 自行落到业务字段。"""

    target_language: str
    source_hash: str
    provider: str
    segments: list[TranslationSegment] = field(default_factory=list)
    updated_at: int = 0

    def segment_map(self) -> dict[str, str]:
        return {segment.key: segment.text for segment in self.segments if segment.key}

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_language": self.target_language,
            "source_hash": self.source_hash,
            "provider": self.provider,
            "updated_at": self.updated_at,
            "segments": [segment.to_dict() for segment in self.segments],
        }
