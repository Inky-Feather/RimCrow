from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Iterable
from xml.etree import ElementTree

from backend.settings import CACHE_DIR
from backend.utils.tools import normalize_package_id

from .models import CandidateFile, SearchRequest, SearchRoot, matches_all_file_types

if TYPE_CHECKING:
    from backend.managers.mgr_profile import ProfileContext


VERSION_PATTERN = re.compile(r"^[vV]?(\d+)\.(\d+)$")
MOD_IDENTITY_FILES = (
    Path("About") / "About.xml",
    Path("About") / "About.xml.disabled",
)
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    ".idea",
    ".vscode",
    "node_modules",
    ".vs",
}
TEXTURE_DIR_NAMES = {
    "textures",
    "texturesexpanded",
}
LANGUAGE_DIR_NAMES = {
    "languages",
}
SOURCE_DIR_NAMES = {
    "source",
}
KNOWN_DLC_KEYS = {
    "royalty",
    "ideology",
    "biotech",
    "anomaly",
    "odyssey",
}
SEARCH_MOD_ROOT_CACHE_DIR = CACHE_DIR / "file_search_mod_roots"
MAX_SEARCH_MOD_ROOT_CACHE_FILES = 256
MAX_SEARCH_ROOT_PLANNING_WORKERS = 6
MOD_ROOT_CACHE_SCHEMA_VERSION = 3
MOD_ROOT_CACHE_PRUNE_INTERVAL_SECONDS = 30.0


_MOD_ROOT_CACHE_LOCK = threading.Lock()
_last_mod_root_cache_prune_monotonic = 0.0


class SearchBuildCancelled(RuntimeError):
    """前置有效搜索根整理被取消。"""


def _is_mod_root(path: Path) -> bool:
    return any((path / marker).is_file() for marker in MOD_IDENTITY_FILES)


def _normalize_store(mod: dict[str, Any]) -> str:
    store = str(mod.get("store") or "").strip().lower()
    if store:
        return store
    source = str(mod.get("source") or "").strip().lower()
    if source in {"core", "dlc"}:
        return source
    return "unknown"


def _normalize_mod_name(mod: dict[str, Any]) -> str:
    return (
        str(mod.get("alias_name") or "").strip()
        or str(mod.get("display_name") or "").strip()
        or str(mod.get("name") or "").strip()
        or str(mod.get("package_id") or "").strip()
        or "未知模组"
    )


def _active_ids_for_context(context: ProfileContext | None, load_order_mgr) -> set[str]:
    if not context or not load_order_mgr:
        return set()
    try:
        result = load_order_mgr.read_active_mods()
    except Exception:
        return set()
    active_ids = set()
    for package_id in result.get("active_mods", []) or []:
        normalized = normalize_package_id(package_id)
        if normalized:
            active_ids.add(normalized)
    return active_ids


def _build_search_planning_context(context: ProfileContext | None, load_order_mgr) -> _SearchPlanningContext:
    active_ids = _active_ids_for_context(context, load_order_mgr)
    active_tokens = set(active_ids)
    for package_id in list(active_ids):
        if package_id.endswith("_steam"):
            active_tokens.add(package_id.removesuffix("_steam"))
        else:
            active_tokens.add(f"{package_id}_steam")

    active_dlc_keys = {"core"}
    for package_id in active_ids:
        if package_id == "ludeon.rimworld":
            active_dlc_keys.add("core")
            continue
        if not package_id.startswith("ludeon.rimworld."):
            continue
        suffix = package_id.split(".")[-1].strip().lower()
        if suffix:
            active_dlc_keys.add(suffix)

    return _SearchPlanningContext(
        active_ids=frozenset(active_ids),
        active_mod_tokens=frozenset(token.lower() for token in active_tokens if token),
        active_dlc_keys=frozenset(active_dlc_keys),
    )


def _is_profile_self_mod(path: str, self_root: str) -> bool:
    if not path or not self_root:
        return False
    normalized = os.path.normpath(path).lower()
    return normalized.startswith(os.path.normpath(self_root).lower())


def resolve_scope_mods(
    context: ProfileContext | None,
    load_order_mgr,
    request: SearchRequest,
    self_mods_path: str = "",
    active_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    # 这里按需导入 DAO，避免纯搜索规划测试在模块导入阶段被数据库依赖拖住。
    from backend.database.dao import ModDAO

    mods = list(ModDAO.get_profile_mods(context) if context else [])
    if not mods:
        return []

    resolved_active_ids = active_ids if active_ids is not None else _active_ids_for_context(context, load_order_mgr)

    if request.scope == "current-effective":
        return mods

    if request.scope == "current-active":
        return [
            mod for mod in mods
            if normalize_package_id(mod.get("package_id")) in resolved_active_ids
        ]

    if request.scope == "workshop":
        return [mod for mod in mods if _normalize_store(mod) == "workshop"]

    if request.scope == "self":
        return [
            mod for mod in mods
            if _normalize_store(mod) == "self" or _is_profile_self_mod(str(mod.get("path") or ""), self_mods_path)
        ]

    if request.scope == "local":
        return [mod for mod in mods if _normalize_store(mod) in {"local", "core", "dlc"}]

    return mods


def _normalize_version_key(raw_value: str | None) -> tuple[int, int] | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    match = VERSION_PATTERN.match(value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _current_game_version_key(context: ProfileContext | None) -> tuple[int, int] | None:
    raw_version = str(getattr(context, "game_version", "") or "")
    match = re.search(r"(\d+)\.(\d+)", raw_version)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _choose_best_version(available_versions: Iterable[tuple[int, int]], current_version: tuple[int, int] | None) -> tuple[int, int] | None:
    versions = sorted(set(available_versions))
    if not versions:
        return None
    if current_version is None:
        return versions[-1]
    lower_or_equal = [version for version in versions if version <= current_version]
    if lower_or_equal:
        return lower_or_equal[-1]
    return versions[0]


def _normalize_loadfolders_path(raw_path: str | None) -> str:
    path = str(raw_path or "").strip().replace("\\", "/")
    if path in {"", ".", "./", "/"}:
        return ""
    while "//" in path:
        path = path.replace("//", "/")
    return path.lstrip("/").rstrip("/")


def _parse_condition_values(attr_value: str | None) -> list[str]:
    return [
        normalized
        for raw_item in str(attr_value or "").split(",")
        if (normalized := normalize_package_id(raw_item))
    ]


def _match_legacy_condition(attr_name: str, active_dlc_keys: set[str]) -> bool | None:
    name = str(attr_name or "").strip().lower()
    if not name.startswith("if"):
        return None

    expected_active = None
    token = ""
    if "notactive" in name:
        token = name.removeprefix("if").replace("notactive", "")
        expected_active = False
    elif name.endswith("active"):
        token = name.removeprefix("if").replace("active", "")
        expected_active = True

    token = token.strip("-_ ").lower()
    if token.endswith("dlc"):
        token = token[:-3]
    if token.startswith("dlc"):
        token = token[3:]
    token = token.strip("-_ ").lower()
    if not token or expected_active is None:
        return None
    if token not in KNOWN_DLC_KEYS and token not in {"core"}:
        return None
    return (token in active_dlc_keys) == expected_active


def _entry_is_active(entry: ElementTree.Element, active_mod_tokens: set[str], active_dlc_keys: set[str]) -> bool:
    attr_map = {str(name or "").strip().lower(): str(value or "").strip() for name, value in entry.attrib.items()}

    mod_active_values = _parse_condition_values(attr_map.get("ifmodactive"))
    if mod_active_values and not any(value in active_mod_tokens for value in mod_active_values):
        return False

    mod_not_active_values = _parse_condition_values(attr_map.get("ifmodnotactive"))
    if mod_not_active_values and not any(value not in active_mod_tokens for value in mod_not_active_values):
        return False

    mod_active_all_values = _parse_condition_values(attr_map.get("ifmodactiveall"))
    if mod_active_all_values and not all(value in active_mod_tokens for value in mod_active_all_values):
        return False

    for attr_name in entry.attrib:
        lowered = str(attr_name or "").strip().lower()
        if lowered in {"ifmodactive", "ifmodnotactive", "ifmodactiveall"}:
            continue
        legacy_result = _match_legacy_condition(lowered, active_dlc_keys)
        if legacy_result is False:
            return False
    return True


@dataclass(frozen=True)
class _LoadFoldersPlan:
    included_paths: list[str]
    selected_version: tuple[int, int] | None


@dataclass(frozen=True)
class _SearchPlanningContext:
    active_ids: frozenset[str]
    active_mod_tokens: frozenset[str]
    active_dlc_keys: frozenset[str]


def _version_key_to_text(version_key: tuple[int, int]) -> str:
    return f"{version_key[0]}.{version_key[1]}"


def _parse_loadfolders_versions(loadfolders_path: Path) -> dict[tuple[int, int], list[dict[str, Any]]]:
    try:
        root = ElementTree.parse(loadfolders_path).getroot()
    except (OSError, ElementTree.ParseError):
        return {}

    version_entries: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for child in list(root):
        version_key = _normalize_version_key(child.tag.split("}", 1)[-1])
        if version_key is None:
            continue
        entries: list[dict[str, Any]] = []
        for entry in child.findall("li"):
            normalized_path = _normalize_loadfolders_path(entry.text) or "/"
            attr_map = {
                str(name or "").strip().lower(): str(value or "").strip()
                for name, value in entry.attrib.items()
            }
            entries.append({
                "path": normalized_path,
                "attrs": attr_map,
            })
        if entries:
            version_entries[version_key] = entries
    return version_entries


def _build_static_mod_root_cache_payload(mod: dict[str, Any]) -> dict[str, Any] | None:
    mod_path = Path(str(mod.get("path") or "")).resolve()
    if not _is_mod_root(mod_path):
        return None

    root_level_dirs: list[str] = []
    version_dir_map: dict[str, str] = {}
    try:
        children = sorted(mod_path.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        children = []

    for child in children:
        if not child.is_dir():
            continue
        root_level_dirs.append(child.name)
        version_key = _normalize_version_key(child.name)
        if version_key is not None:
            version_dir_map[_version_key_to_text(version_key)] = child.name

    loadfolders_versions: dict[str, list[dict[str, Any]]] = {}
    loadfolders_path = mod_path / "LoadFolders.xml"
    if loadfolders_path.is_file():
        for version_key, entries in _parse_loadfolders_versions(loadfolders_path).items():
            loadfolders_versions[_version_key_to_text(version_key)] = entries

    return {
        "version": MOD_ROOT_CACHE_SCHEMA_VERSION,
        "root_path": str(mod_path),
        "root_level_dirs": root_level_dirs,
        "version_dirs": version_dir_map,
        "loadfolders_versions": loadfolders_versions,
    }


def _resolve_loadfolders_plan_from_cache(
    cache_payload: dict[str, Any],
    context: ProfileContext | None,
    planning_context: _SearchPlanningContext,
) -> _LoadFoldersPlan | None:
    raw_versions = cache_payload.get("loadfolders_versions")
    if not isinstance(raw_versions, dict) or not raw_versions:
        return None

    version_entries: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for version_text, entries in raw_versions.items():
        version_key = _normalize_version_key(version_text)
        if version_key is None or not isinstance(entries, list):
            continue
        normalized_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip() or "/"
            attrs = entry.get("attrs", {}) if isinstance(entry.get("attrs", {}), dict) else {}
            normalized_entries.append({
                "path": path,
                "attrs": {str(k).lower(): str(v) for k, v in attrs.items()},
            })
        if normalized_entries:
            version_entries[version_key] = normalized_entries

    if not version_entries:
        return None

    selected_version = _choose_best_version(version_entries.keys(), _current_game_version_key(context))
    if selected_version is None:
        return None

    included_paths: list[str] = []
    seen_included_paths: set[str] = set()
    for entry in version_entries[selected_version]:
        attrs = entry.get("attrs", {}) if isinstance(entry.get("attrs", {}), dict) else {}
        probe = ElementTree.Element("li", attrs)
        if not _entry_is_active(probe, set(planning_context.active_mod_tokens), set(planning_context.active_dlc_keys)):
            continue
        normalized_path = str(entry.get("path") or "/").strip() or "/"
        key = normalized_path.lower()
        if key in seen_included_paths:
            continue
        seen_included_paths.add(key)
        included_paths.append(normalized_path)

    return _LoadFoldersPlan(
        included_paths=included_paths,
        selected_version=selected_version,
    )


def _version_dir_names_from_cache(cache_payload: dict[str, Any]) -> dict[tuple[int, int], str]:
    raw_version_dirs = cache_payload.get("version_dirs")
    if not isinstance(raw_version_dirs, dict):
        return {}
    result: dict[tuple[int, int], str] = {}
    for version_text, folder_name in raw_version_dirs.items():
        version_key = _normalize_version_key(version_text)
        if version_key is None:
            continue
        normalized_folder = str(folder_name or "").strip()
        if normalized_folder:
            result[version_key] = normalized_folder
    return result


def _build_root_version_excludes(version_dir_map: dict[tuple[int, int], str], context: ProfileContext | None, selected_version: tuple[int, int] | None) -> set[str]:
    excludes: set[str] = set()
    current_version = _current_game_version_key(context)
    chosen_version = selected_version or _choose_best_version(version_dir_map.keys(), current_version)
    for version_key, folder_name in version_dir_map.items():
        if version_key != chosen_version:
            excludes.add(folder_name.lower())
    return excludes


def _should_skip_dir(relative_parts: tuple[str, ...], request: SearchRequest) -> bool:
    if not relative_parts:
        return False
    names = [part.lower() for part in relative_parts]
    if request.exclude_options.get("skip_git", True) and any(name == ".git" for name in names):
        return True
    if any(name in EXCLUDED_DIR_NAMES for name in names):
        return True
    if request.exclude_options.get("skip_languages", True) and any(name in LANGUAGE_DIR_NAMES for name in names):
        return True
    if request.exclude_options.get("skip_source", True) and any(name in SOURCE_DIR_NAMES for name in names):
        return True
    if request.exclude_options.get("skip_textures", True) and any(name in TEXTURE_DIR_NAMES for name in names):
        return True
    if request.exclude_options.get("skip_hidden", True) and any(name.startswith(".") and name not in {".git"} for name in names):
        return True
    return False


def _should_skip_file(file_path: Path, request: SearchRequest) -> bool:
    if not matches_all_file_types(request.file_types) and file_path.suffix.lower() not in request.file_types:
        return True
    if request.exclude_options.get("skip_hidden", True) and any(part.startswith(".") for part in file_path.parts):
        return True
    return False


def _check_cancelled(cancel_event) -> None:
    if cancel_event is not None and hasattr(cancel_event, "is_set") and cancel_event.is_set():
        raise SearchBuildCancelled("有效搜索根整理已取消")


def _normalize_relative_key(relative_path: str | Path) -> str:
    return str(relative_path or "").replace("\\", "/").strip("/").lower()


def _should_skip_root_level_dir(dir_name: str) -> bool:
    lowered = str(dir_name or "").strip().lower()
    if not lowered:
        return True
    if lowered in EXCLUDED_DIR_NAMES:
        return True
    if lowered.startswith(".") and lowered != ".git":
        return True
    return False


def _relative_top_level(relative_path: str) -> str:
    normalized = _normalize_relative_key(relative_path)
    return normalized.split("/", 1)[0] if normalized else ""


def _list_root_level_common_dirs(cache_payload: dict[str, Any], version_dir_names: set[str], cancel_event=None) -> list[str]:
    root_path = Path(str(cache_payload.get("root_path") or "")).resolve()
    raw_root_dirs = cache_payload.get("root_level_dirs")
    if not isinstance(raw_root_dirs, list):
        return []

    common_dir_paths: list[str] = []
    for child_name_raw in raw_root_dirs:
        _check_cancelled(cancel_event)
        child_name = str(child_name_raw or "").strip()
        if not child_name:
            continue
        child_name_lower = child_name.lower()
        child_path = (root_path / child_name).resolve()
        if not child_path.is_dir():
            continue
        if child_name_lower in version_dir_names:
            continue
        if _should_skip_root_level_dir(child_name):
            continue
        common_dir_paths.append(str(child_path))
    return common_dir_paths


def _resolve_directory_path(cache_payload: dict[str, Any], relative_path: str, excluded_version_dirs: set[str], cancel_event=None) -> list[str]:
    _check_cancelled(cancel_event)
    root_path = Path(str(cache_payload.get("root_path") or "")).resolve()
    version_dir_names = {name.lower() for name in _version_dir_names_from_cache(cache_payload).values()}
    if relative_path == "/":
        return _list_root_level_common_dirs(cache_payload, version_dir_names, cancel_event=cancel_event)

    absolute_path = (root_path / Path(relative_path)).resolve()
    if not absolute_path.is_dir():
        return []
    top_level = _relative_top_level(relative_path)
    if top_level and top_level in excluded_version_dirs:
        return []
    return [str(absolute_path)]


def _selected_top_level_paths(paths: list[str]) -> set[str]:
    top_levels: set[str] = set()
    for path in paths:
        top_level = _relative_top_level(path)
        if top_level:
            top_levels.add(top_level)
    return top_levels


def _dedupe_root_entries(entries: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    normalized_entries = []
    seen: set[str] = set()
    for path, root_kind in entries:
        key = str(path.resolve()).lower()
        if key in seen or not path.exists():
            continue
        seen.add(key)
        normalized_entries.append((path.resolve(), root_kind))

    normalized_entries.sort(key=lambda item: (len(item[0].parts), 0 if item[1] == "dir" else 1, str(item[0]).lower()))
    deduped: list[tuple[Path, str]] = []
    deduped_keys: list[str] = []
    for path, root_kind in normalized_entries:
        normalized_path = str(path).lower()
        if any(
            existing_kind == "dir" and (normalized_path == existing_key or normalized_path.startswith(f"{existing_key}{os.sep}"))
            for (existing_path, existing_kind), existing_key in zip(deduped, deduped_keys, strict=False)
        ):
            continue
        if root_kind == "dir":
            next_deduped: list[tuple[Path, str]] = []
            next_keys: list[str] = []
            for existing, existing_key in zip(deduped, deduped_keys, strict=False):
                if existing_key == normalized_path or existing_key.startswith(f"{normalized_path}{os.sep}"):
                    continue
                next_deduped.append(existing)
                next_keys.append(existing_key)
            deduped = next_deduped
            deduped_keys = next_keys
        deduped.append((path, root_kind))
        deduped_keys.append(normalized_path)
    return deduped


def _build_effective_roots_for_plan(
    *,
    cache_payload: dict[str, Any],
    package_id: str,
    mod_name: str,
    store: str,
    plan: _LoadFoldersPlan,
    context: ProfileContext | None,
    cancel_event=None,
) -> list[SearchRoot]:
    _check_cancelled(cancel_event)
    version_dir_map = _version_dir_names_from_cache(cache_payload)
    excluded_version_dirs = _build_root_version_excludes(version_dir_map, context, plan.selected_version)
    version_dir_names = {name.lower() for name in version_dir_map.values()}
    root_entries: list[tuple[Path, str]] = []
    selected_top_levels = _selected_top_level_paths(plan.included_paths)

    for common_dir_text in _list_root_level_common_dirs(cache_payload, version_dir_names, cancel_event=cancel_event):
        common_dir = Path(common_dir_text)
        if common_dir.name.lower() in selected_top_levels:
            continue
        root_entries.append((common_dir, "dir"))

    for relative_path in plan.included_paths:
        for resolved_dir in _resolve_directory_path(
            cache_payload,
            relative_path,
            excluded_version_dirs,
            cancel_event=cancel_event,
        ):
            root_entries.append((Path(resolved_dir), "dir"))

    root_entries = _dedupe_root_entries(root_entries)
    return [
        SearchRoot(
            package_id=package_id,
            mod_name=mod_name,
            store=store,
            mod_path=str(Path(str(cache_payload.get("root_path") or "")).resolve()),
            root_path=str(path),
            root_kind=root_kind,
        )
        for path, root_kind in root_entries
    ]


def _build_default_effective_roots(
    *,
    cache_payload: dict[str, Any],
    package_id: str,
    mod_name: str,
    store: str,
    context: ProfileContext | None,
    cancel_event=None,
) -> list[SearchRoot]:
    _check_cancelled(cancel_event)
    root_entries: list[tuple[Path, str]] = []
    root_path = Path(str(cache_payload.get("root_path") or "")).resolve()
    version_dir_map = _version_dir_names_from_cache(cache_payload)
    version_dir_names = {name.lower() for name in version_dir_map.values()}
    for child_text in _list_root_level_common_dirs(cache_payload, version_dir_names, cancel_event=cancel_event):
        root_entries.append((Path(child_text), "dir"))

    selected_version = _choose_best_version(version_dir_map.keys(), _current_game_version_key(context))
    if selected_version is not None:
        folder_name = version_dir_map.get(selected_version)
        if folder_name:
            version_path = (root_path / folder_name).resolve()
            if version_path.is_dir():
                root_entries.append((version_path, "dir"))

    deduped = _dedupe_root_entries(root_entries)
    return [
        SearchRoot(
            package_id=package_id,
            mod_name=mod_name,
            store=store,
            mod_path=str(root_path),
            root_path=str(path),
            root_kind=root_kind,
        )
        for path, root_kind in deduped
    ]


def _build_mod_search_roots(
    *,
    cache_payload: dict[str, Any],
    package_id: str,
    mod_name: str,
    store: str,
    context: ProfileContext | None,
    planning_context: _SearchPlanningContext,
    request: SearchRequest,
    cancel_event=None,
) -> list[SearchRoot]:
    _check_cancelled(cancel_event)
    if not request.effective_only:
        return [
            SearchRoot(
                package_id=package_id,
                mod_name=mod_name,
                store=store,
                mod_path=str(Path(str(cache_payload.get("root_path") or "")).resolve()),
                root_path=str(Path(str(cache_payload.get("root_path") or "")).resolve()),
                root_kind="dir",
            )
        ]

    plan = _resolve_loadfolders_plan_from_cache(cache_payload, context, planning_context)
    if plan is None:
        return _build_default_effective_roots(
            cache_payload=cache_payload,
            package_id=package_id,
            mod_name=mod_name,
            store=store,
            context=context,
            cancel_event=cancel_event,
        )

    return _build_effective_roots_for_plan(
        cache_payload=cache_payload,
        package_id=package_id,
        mod_name=mod_name,
        store=store,
        plan=plan,
        context=context,
        cancel_event=cancel_event,
    )


def _build_direct_mod_roots(mods: list[dict[str, Any]], cancel_event=None) -> tuple[list[SearchRoot], dict[str, Any]]:
    """
    关闭“只搜索实际生效文件”时直接使用模组根目录。

    这里不再解析 LoadFolders、版本目录或 DLC 条件，剩余过滤统一交给 ripgrep
    的文件类型与排除规则处理，避免无意义的前置整理。
    """
    ordered_roots: list[SearchRoot] = []
    skipped_mods = 0
    for mod in mods:
        _check_cancelled(cancel_event)
        mod_path = Path(str(mod.get("path") or "")).resolve()
        if not _is_mod_root(mod_path):
            skipped_mods += 1
            continue
        ordered_roots.append(
            SearchRoot(
                package_id=normalize_package_id(mod.get("package_id")),
                mod_name=_normalize_mod_name(mod),
                store=_normalize_store(mod),
                mod_path=str(mod_path),
                root_path=str(mod_path),
                root_kind="dir",
            )
        )
    return ordered_roots, {
        "cache_hit": False,
        "cache_hits": 0,
        "fresh_builds": 0,
        "cache_source": "direct-mod-dirs",
        "skipped_mods": skipped_mods,
    }


def _resolve_search_root_planning_workers(total_mods: int) -> int:
    if total_mods <= 1:
        return 1
    cpu_count = os.cpu_count() or 4
    suggested = max(2, min(MAX_SEARCH_ROOT_PLANNING_WORKERS, cpu_count))
    return max(1, min(total_mods, suggested))


def _plan_single_mod_roots(
    *,
    index: int,
    mod: dict[str, Any],
    context: ProfileContext | None,
    planning_context: _SearchPlanningContext,
    request: SearchRequest,
    cancel_event=None,
) -> tuple[int, str, list[SearchRoot], str]:
    _check_cancelled(cancel_event)
    mod_name = _normalize_mod_name(mod)
    cache_payload = _build_static_mod_root_cache_payload(mod)
    if cache_payload is None:
        return index, mod_name, [], "skipped"

    cache_key = build_mod_root_cache_key(mod)
    cached_payload = load_mod_root_cache(cache_key)
    if cached_payload is not None:
        touch_mod_root_cache(cache_key)
        cache_payload = cached_payload
        cache_source = "disk"
    else:
        save_mod_root_cache(cache_key, cache_payload)
        cache_source = "fresh"

    search_roots = _build_mod_search_roots(
        cache_payload=cache_payload,
        package_id=normalize_package_id(mod.get("package_id")),
        mod_name=mod_name,
        store=_normalize_store(mod),
        context=context,
        planning_context=planning_context,
        request=request,
        cancel_event=cancel_event,
    )
    return index, mod_name, search_roots, cache_source


def build_mod_root_cache_key(mod: dict[str, Any]) -> str:
    mod_path = str(mod.get("path") or "")
    payload = {
        "schema_version": MOD_ROOT_CACHE_SCHEMA_VERSION,
        "package_id": normalize_package_id(mod.get("package_id")),
        "store": _normalize_store(mod),
        "path": mod_path,
        "child_entries": _safe_child_entries_signature(mod_path),
        "loadfolders_mtime_ns": _safe_stat_mtime_ns(str(Path(mod_path) / "LoadFolders.xml")),
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def build_search_roots(
    context: ProfileContext | None,
    load_order_mgr,
    request: SearchRequest,
    self_mods_path: str = "",
    mods: list[dict[str, Any]] | None = None,
    on_mod_progress=None,
    cancel_event=None,
) -> tuple[list[dict[str, Any]], list[SearchRoot], dict[str, Any]]:
    planning_context = _build_search_planning_context(context, load_order_mgr)
    resolved_mods = list(mods) if mods is not None else resolve_scope_mods(
        context,
        load_order_mgr,
        request,
        self_mods_path=self_mods_path,
        active_ids=set(planning_context.active_ids),
    )
    if not request.effective_only:
        ordered_roots, direct_meta = _build_direct_mod_roots(resolved_mods, cancel_event=cancel_event)
        if callable(on_mod_progress):
            total_mods = len(resolved_mods)
            for index, mod in enumerate(resolved_mods, start=1):
                _check_cancelled(cancel_event)
                on_mod_progress(index, total_mods, _normalize_mod_name(mod))
        return resolved_mods, ordered_roots, {
            "mod_count": len(resolved_mods),
            "root_count": len(ordered_roots),
            **direct_meta,
        }

    total_mods = len(resolved_mods)
    worker_count = _resolve_search_root_planning_workers(total_mods)
    completed_roots: dict[int, list[SearchRoot]] = {}
    cache_hits = 0
    fresh_builds = 0

    if worker_count == 1:
        for index, mod in enumerate(resolved_mods, start=1):
            _, mod_name, search_roots, cache_source = _plan_single_mod_roots(
                index=index,
                mod=mod,
                context=context,
                planning_context=planning_context,
                request=request,
                cancel_event=cancel_event,
            )
            completed_roots[index] = search_roots
            if cache_source == "disk":
                cache_hits += 1
            elif cache_source == "fresh":
                fresh_builds += 1
            if callable(on_mod_progress):
                on_mod_progress(index, total_mods, mod_name)
    else:
        completed_mods = 0
        future_map: dict[Future[tuple[int, str, list[SearchRoot], str]], int] = {}
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="search-root-plan") as executor:
            for index, mod in enumerate(resolved_mods, start=1):
                _check_cancelled(cancel_event)
                future = executor.submit(
                    _plan_single_mod_roots,
                    index=index,
                    mod=mod,
                    context=context,
                    planning_context=planning_context,
                    request=request,
                    cancel_event=cancel_event,
                )
                future_map[future] = index

            pending_futures = set(future_map.keys())
            while pending_futures:
                _check_cancelled(cancel_event)
                done_futures, pending_futures = wait(
                    pending_futures,
                    timeout=0.1,
                    return_when=FIRST_COMPLETED,
                )
                if not done_futures:
                    continue
                for future in done_futures:
                    _check_cancelled(cancel_event)
                    index, mod_name, search_roots, cache_source = future.result()
                    completed_roots[index] = search_roots
                    if cache_source == "disk":
                        cache_hits += 1
                    elif cache_source == "fresh":
                        fresh_builds += 1
                    completed_mods += 1
                    if callable(on_mod_progress):
                        on_mod_progress(completed_mods, total_mods, mod_name)

    ordered_roots: list[SearchRoot] = []
    for index in range(1, total_mods + 1):
        ordered_roots.extend(completed_roots.get(index, []))

    return resolved_mods, ordered_roots, {
        "mod_count": len(resolved_mods),
        "root_count": len(ordered_roots),
        "cache_hit": cache_hits > 0,
        "cache_hits": cache_hits,
        "fresh_builds": fresh_builds,
        "cache_source": "mod-roots",
    }


def iter_root_candidate_files(search_root: SearchRoot, request: SearchRequest, cancel_event=None):
    root_path = Path(search_root.root_path)
    if search_root.root_kind == "file":
        _check_cancelled(cancel_event)
        if not root_path.is_file() or _should_skip_file(root_path, request):
            return
        yield CandidateFile(
            package_id=search_root.package_id,
            mod_name=search_root.mod_name,
            store=search_root.store,
            mod_path=search_root.mod_path,
            file_path=str(root_path),
        )
        return

    if not root_path.exists():
        return

    for current_root, dir_names, file_names in os.walk(root_path):
        _check_cancelled(cancel_event)
        current_path = Path(current_root)
        relative_parts = current_path.relative_to(root_path).parts if current_path != root_path else ()
        dir_names[:] = [
            name for name in dir_names
            if not _should_skip_dir(relative_parts + (name,), request)
        ]
        if _should_skip_dir(relative_parts, request):
            dir_names[:] = []
            continue

        for file_name in file_names:
            _check_cancelled(cancel_event)
            file_path = current_path / file_name
            if _should_skip_file(file_path, request):
                continue
            # 目录型搜索根最终在这里逐个落到文件级候选集。
            # 这一步必须稳定产出 CandidateFile，否则 Python 回退搜索会扫空。
            yield CandidateFile(
                package_id=search_root.package_id,
                mod_name=search_root.mod_name,
                store=search_root.store,
                mod_path=search_root.mod_path,
                file_path=str(file_path),
            )


def build_candidate_files(
    context: ProfileContext | None,
    load_order_mgr,
    request: SearchRequest,
    self_mods_path: str = "",
    mods: list[dict[str, Any]] | None = None,
    on_mod_progress=None,
    cancel_event=None,
) -> tuple[list[dict[str, Any]], list[CandidateFile], dict[str, Any]]:
    resolved_mods, search_roots, fingerprint_meta = build_search_roots(
        context=context,
        load_order_mgr=load_order_mgr,
        request=request,
        self_mods_path=self_mods_path,
        mods=mods,
        on_mod_progress=on_mod_progress,
        cancel_event=cancel_event,
    )
    candidate_files: list[CandidateFile] = []
    for search_root in search_roots:
        candidate_files.extend(list(iter_root_candidate_files(search_root, request, cancel_event=cancel_event)))
    fingerprint_meta["file_count"] = len(candidate_files)
    return resolved_mods, candidate_files, fingerprint_meta


def _deserialize_mod_root_cache(payload: dict[str, Any]) -> dict[str, Any] | None:
    if int(payload.get("version") or 0) != MOD_ROOT_CACHE_SCHEMA_VERSION:
        return None
    root_path = Path(str(payload.get("root_path") or "")).resolve()
    root_level_dirs = payload.get("root_level_dirs")
    version_dirs = payload.get("version_dirs")
    loadfolders_versions = payload.get("loadfolders_versions")
    if (
        not root_path.exists()
        or not isinstance(root_level_dirs, list)
        or not isinstance(version_dirs, dict)
        or not isinstance(loadfolders_versions, dict)
    ):
        return None
    return {
        "version": MOD_ROOT_CACHE_SCHEMA_VERSION,
        "root_path": str(root_path),
        "root_level_dirs": [str(item) for item in root_level_dirs if str(item).strip()],
        "version_dirs": {str(k): str(v) for k, v in version_dirs.items() if str(k).strip() and str(v).strip()},
        "loadfolders_versions": loadfolders_versions,
    }


def load_mod_root_cache(cache_key: str) -> dict[str, Any] | None:
    cache_path = SEARCH_MOD_ROOT_CACHE_DIR / f"{cache_key}.json"
    if not cache_path.is_file():
        return None
    try:
        with cache_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    return _deserialize_mod_root_cache(payload)


def save_mod_root_cache(cache_key: str, payload: dict[str, Any]) -> None:
    SEARCH_MOD_ROOT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = SEARCH_MOD_ROOT_CACHE_DIR / f"{cache_key}.json"
    temp_path = cache_path.with_suffix(".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp_path, cache_path)
    except OSError:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        return
    _schedule_mod_root_cache_prune(cache_path, force=False)


def touch_mod_root_cache(cache_key: str) -> None:
    cache_path = SEARCH_MOD_ROOT_CACHE_DIR / f"{cache_key}.json"
    if not cache_path.exists():
        return
    try:
        cache_path.touch()
    except OSError:
        return


def _schedule_mod_root_cache_prune(preferred_path: Path | None = None, *, force: bool) -> None:
    global _last_mod_root_cache_prune_monotonic
    now = time.monotonic()
    with _MOD_ROOT_CACHE_LOCK:
        if not force and (now - _last_mod_root_cache_prune_monotonic) < MOD_ROOT_CACHE_PRUNE_INTERVAL_SECONDS:
            return
        _last_mod_root_cache_prune_monotonic = now
        _prune_mod_root_cache(preferred_path)


def _prune_mod_root_cache(preferred_path: Path | None = None) -> None:
    try:
        entries = [item for item in SEARCH_MOD_ROOT_CACHE_DIR.glob("*.json") if item.is_file()]
    except OSError:
        return
    if len(entries) <= MAX_SEARCH_MOD_ROOT_CACHE_FILES:
        return

    entries.sort(
        key=lambda item: (
            1 if preferred_path and item == preferred_path else 0,
            _safe_stat_mtime_ns(str(item)),
        ),
    )
    overflow = len(entries) - MAX_SEARCH_MOD_ROOT_CACHE_FILES
    for path in entries[:overflow]:
        if preferred_path and path == preferred_path:
            continue
        try:
            path.unlink()
        except OSError:
            continue


def _safe_stat_mtime_ns(path: str) -> int:
    try:
        return int(Path(path).stat().st_mtime_ns)
    except OSError:
        return 0


def _safe_child_entries_signature(path: str) -> list[dict[str, Any]]:
    base_path = Path(path)
    try:
        entries = sorted(base_path.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return []

    signature: list[dict[str, Any]] = []
    for entry in entries:
        signature.append({
            "name": entry.name,
            "is_dir": entry.is_dir(),
        })
    return signature
