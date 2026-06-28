from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from pathlib import Path
from typing import Any


DEFAULT_FILE_TYPES = (
    ".xml",
)

DEFAULT_EXCLUDE_OPTIONS = {
    "skip_hidden": True,
    "skip_git": True,
    "skip_languages": True,
    "skip_source": True,
    "skip_textures": True,
    "skip_binary_like": True,
}

SEARCH_SCOPES = {
    "current-effective",
    "current-active",
    "workshop",
    "local",
    "self",
}


def normalize_file_types(values: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or DEFAULT_FILE_TYPES:
        ext = str(value or "").strip().lower()
        if not ext: continue
        if ext in {".", "*", "*.*"}: return (".",)
        if ext.startswith("*"): ext = ext.lstrip("*")
        if not ext.startswith("."): ext = f".{ext}"
        if ext in seen: continue
        seen.add(ext)
        normalized.append(ext)
    return tuple(normalized or DEFAULT_FILE_TYPES)


def matches_all_file_types(file_types: tuple[str, ...] | list[str] | None) -> bool:
    return "." in set(file_types or ())


@dataclass(frozen=True)
class SearchRequest:
    query: str
    scope: str = "current-active"
    effective_only: bool = True
    use_regex: bool = False
    case_sensitive: bool = False
    file_types: tuple[str, ...] = field(default_factory=lambda: DEFAULT_FILE_TYPES)
    exclude_options: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_EXCLUDE_OPTIONS))

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None):
        data = dict(payload or {})
        query = str(data.get("query") or "").strip()
        if not query:
            raise ValueError("搜索词不能为空")

        scope = str(data.get("scope") or "current-active").strip().lower()
        if scope not in SEARCH_SCOPES:
            raise ValueError(f"不支持的搜索范围: {scope}")

        exclude_options = dict(DEFAULT_EXCLUDE_OPTIONS)
        extra_excludes = data.get("exclude_options")
        if isinstance(extra_excludes, dict):
            exclude_options.update(extra_excludes)

        return cls(
            query=query,
            scope=scope,
            effective_only=bool(data.get("effective_only", True)),
            use_regex=bool(data.get("use_regex", False)),
            case_sensitive=bool(data.get("case_sensitive", False)),
            file_types=normalize_file_types(data.get("file_types")),
            exclude_options=exclude_options,
        )

    def cache_key(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "effective_only": self.effective_only,
        }

    def compile_pattern(self) -> re.Pattern[str]:
        flags = 0 if self.case_sensitive else re.IGNORECASE
        if self.use_regex: return re.compile(self.query, flags)
        return re.compile(re.escape(self.query), flags)


@dataclass(frozen=True)
class CandidateFile:
    package_id: str
    mod_name: str
    store: str
    mod_path: str
    file_path: str

    @property
    def file_name(self) -> str:
        return Path(self.file_path).name


@dataclass(frozen=True)
class SearchRoot:
    package_id: str
    mod_name: str
    store: str
    mod_path: str
    root_path: str
    root_kind: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SearchResult:
    package_id: str
    mod_name: str
    store: str
    mod_path: str
    file_path: str
    file_name: str
    line_number: int
    matched_line: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
