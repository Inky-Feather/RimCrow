import os
import platform
import posixpath
import re
import ntpath
from typing import Any


def _system_name(system_name: str | None = None) -> str:
    return str(system_name or platform.system() or "").strip()


def _path_module(system_name: str | None = None):
    return ntpath if _system_name(system_name) == "Windows" else posixpath


def canonicalize_path_text(path: str, system_name: str | None = None) -> str:
    raw_value = str(path or "").strip().strip('"')
    if not raw_value:
        return ""
    expanded = os.path.expanduser(raw_value) if raw_value.startswith("~") else raw_value
    expanded = os.path.expandvars(expanded)
    path_mod = _path_module(system_name)
    if re.match(r"^[A-Za-z]:[\\/]", expanded):
        return ntpath.normpath(expanded)
    if _system_name(system_name) == "Windows" or system_name is None:
        return os.path.normpath(os.path.abspath(expanded))
    return path_mod.normpath(expanded)


def path_key(path: str, system_name: str | None = None) -> str:
    value = str(path or "").strip()
    if not value:
        return ""
    normalized = _path_module(system_name).normpath(value)
    if _system_name(system_name) == "Windows":
        return normalized.lower()
    return normalized


def unique_paths(paths: list[str], system_name: str | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_path in paths or []:
        value = str(raw_path or "").strip()
        if not value:
            continue
        normalized = _path_module(system_name).normpath(value)
        key = path_key(normalized, system_name=system_name)
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def normalize_path_for_storage(path: Any, system_name: str | None = None) -> str:
    return canonicalize_path_text(str(path or ""), system_name=system_name)


def normalize_path_for_compare(path: Any, system_name: str | None = None) -> str:
    normalized = normalize_path_for_storage(path, system_name=system_name)
    return path_key(normalized, system_name=system_name) if normalized else ""


def same_path(left: Any, right: Any, system_name: str | None = None) -> bool:
    left_key = normalize_path_for_compare(left, system_name=system_name)
    right_key = normalize_path_for_compare(right, system_name=system_name)
    return bool(left_key and right_key and left_key == right_key)


def join_if_base(base: str, *parts: str) -> str:
    text = str(base or "").strip()
    if not text:
        return ""
    return os.path.join(text, *parts)
