from __future__ import annotations

import os
import platform
from pathlib import Path

import vdf

try:
    import winreg
except ImportError:  # pragma: no cover - 仅在非 Windows 平台触发
    winreg = None

from backend.paths.core import normalize_path_for_storage, unique_paths
from backend.utils.constants import RIMWORLD_APPMANIFEST_NAME, RIMWORLD_STEAM_APP_ID_STR


def _resolved_system_name(system_name: str | None = None) -> str:
    return str(system_name or platform.system() or "").strip()


def _read_windows_registry_value(root, key_path: str, value_name: str) -> str:
    if winreg is None:
        return ""
    try:
        with winreg.OpenKey(root, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
        return str(value or "").strip()
    except OSError:
        return ""


def get_default_user_data_paths(system_name: str | None = None) -> list[str]:
    resolved_system_name = _resolved_system_name(system_name)
    if resolved_system_name == "Windows":
        user_profile = os.getenv("USERPROFILE") or os.path.expanduser("~")
        return unique_paths([
            os.path.join(user_profile, "AppData", "LocalLow", "Ludeon Studios", "RimWorld by Ludeon Studios"),
        ], system_name=resolved_system_name)

    home = os.path.expanduser("~")
    if resolved_system_name == "Darwin":
        return unique_paths([
            os.path.join(home, "Library", "Application Support", "RimWorld"),
        ], system_name=resolved_system_name)

    return unique_paths([
        os.path.join(home, ".config", "unity3d", "Ludeon Studios", "RimWorld by Ludeon Studios"),
        os.path.join(home, ".var", "app", "com.valvesoftware.Steam", "config", "unity3d", "Ludeon Studios", "RimWorld by Ludeon Studios"),
    ], system_name=resolved_system_name)


def get_default_player_log_paths(filename: str = "Player.log", system_name: str | None = None) -> list[str]:
    target_name = os.path.basename(str(filename or "").strip()) or "Player.log"
    resolved_system_name = _resolved_system_name(system_name)
    if resolved_system_name == "Darwin":
        home = os.path.expanduser("~")
        return unique_paths([
            os.path.join(home, "Library", "Logs", "Ludeon Studios", "RimWorld by Ludeon Studios", target_name),
            os.path.join(home, "Library", "Logs", "Unity", target_name),
        ], system_name=resolved_system_name)

    return unique_paths([
        os.path.join(root, target_name)
        for root in get_default_user_data_paths(system_name=resolved_system_name)
    ], system_name=resolved_system_name)


def get_default_steam_root_candidates(system_name: str | None = None) -> list[str]:
    resolved_system_name = _resolved_system_name(system_name)
    candidates: list[str] = []
    if resolved_system_name == "Windows":
        if winreg is not None:
            for key_path in [r"SOFTWARE\WOW6432Node\Valve\Steam", r"SOFTWARE\Valve\Steam"]:
                for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    install_path = _read_windows_registry_value(root, key_path, "InstallPath")
                    if install_path:
                        candidates.append(install_path)
        candidates.extend([
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
        ])
    elif resolved_system_name == "Darwin":
        home = os.path.expanduser("~")
        candidates.extend([
            "/Applications",
            os.path.join(home, "Applications"),
        ])
    else:
        home = os.path.expanduser("~")
        xdg_data_home = os.getenv("XDG_DATA_HOME")
        candidates.extend([
            os.path.join(home, ".steam", "steam"),
            os.path.join(home, ".local", "share", "Steam"),
            os.path.join(home, "snap", "steam", "common", ".local", "share", "Steam"),
            os.path.join(home, ".var", "app", "com.valvesoftware.Steam", ".local", "share", "Steam"),
        ])
        if xdg_data_home:
            candidates.append(os.path.join(xdg_data_home, "Steam"))

    return unique_paths([
        normalize_path_for_storage(path) for path in candidates if path
    ], system_name=resolved_system_name)


def get_default_steam_data_root_candidates(system_name: str | None = None) -> list[str]:
    resolved_system_name = _resolved_system_name(system_name)
    if resolved_system_name == "Darwin":
        home = os.path.expanduser("~")
        return unique_paths([
            os.path.join(home, "Library", "Application Support", "Steam"),
        ], system_name=resolved_system_name)
    return get_default_steam_root_candidates(system_name=resolved_system_name)


def find_app_bundle_path(executable_or_install_path: str) -> str:
    path = Path(str(executable_or_install_path or "").strip())
    if not str(path):
        return ""
    if path.suffix.lower() == ".app":
        return str(path)
    for candidate in [path, *path.parents]:
        if candidate.suffix.lower() == ".app":
            return str(candidate)
    return ""


def detect_rimworld_executable(install_path: str, system_name: str | None = None) -> str:
    resolved_system_name = _resolved_system_name(system_name)
    candidates_by_system = {
        "Windows": ["RimWorldWin64.exe", "RimWorldWin.exe"],
        "Darwin": ["RimWorldMac.app", "RimWorldMac"],
        "Linux": ["RimWorldLinux", "RimWorldLinux.x86_64", "start_RimWorld.sh"],
    }
    candidates = list(candidates_by_system.get(resolved_system_name, []))
    for other_system, other_candidates in candidates_by_system.items():
        if other_system != resolved_system_name:
            candidates.extend(other_candidates)

    for executable_name in candidates:
        target_path = os.path.join(install_path, executable_name)
        if executable_name.endswith(".app") and os.path.exists(target_path):
            return target_path
        if os.path.isfile(target_path):
            return target_path
    return ""


def resolve_steam_executable_path(steam_root: str, system_name: str | None = None) -> str:
    root = str(steam_root or "").strip()
    if not root:
        return ""
    resolved_system_name = _resolved_system_name(system_name)
    if resolved_system_name == "Windows":
        candidate = Path(root) / "steam.exe"
        return str(candidate) if candidate.exists() else ""
    if resolved_system_name == "Darwin":
        candidate = Path(root) / "Steam.app" / "Contents" / "MacOS" / "steam_osx"
        return str(candidate) if candidate.exists() else ""

    for candidate in [Path(root) / "steam.sh", Path(root) / "steam"]:
        if candidate.exists():
            return str(candidate)
    return ""


def normalize_steam_root(path: str, system_name: str | None = None) -> str:
    raw_value = normalize_path_for_storage(path)
    if not raw_value:
        return ""

    resolved_system_name = _resolved_system_name(system_name)
    target = Path(raw_value)

    if resolved_system_name == "Darwin":
        if target.name == "steam_osx" and target.parent.name == "MacOS":
            app_bundle = target.parents[2]
            if app_bundle.name == "Steam.app":
                return normalize_path_for_storage(app_bundle.parent)
        if target.name == "Steam.app":
            return normalize_path_for_storage(target.parent)
        return raw_value

    if resolved_system_name == "Windows" and target.name.lower() == "steam.exe":
        return normalize_path_for_storage(target.parent)

    if resolved_system_name != "Windows" and target.name in {"steam.sh", "steam"}:
        return normalize_path_for_storage(target.parent)

    return raw_value


def resolve_steamcmd_executable_path(steamcmd_dir: str, system_name: str | None = None) -> str:
    root = str(steamcmd_dir or "").strip()
    if not root:
        return ""
    resolved_system_name = _resolved_system_name(system_name)
    executable_name = "steamcmd.exe" if resolved_system_name == "Windows" else "steamcmd.sh"
    return str(Path(root) / executable_name)


def _library_contains_rimworld(library_path: str, folder_data: dict | None = None) -> bool:
    apps = (folder_data or {}).get("apps", {}) if isinstance(folder_data, dict) else {}
    if isinstance(apps, dict) and RIMWORLD_STEAM_APP_ID_STR in apps:
        return True
    return os.path.exists(os.path.join(library_path, "steamapps", RIMWORLD_APPMANIFEST_NAME))


def _read_steam_appmanifest_install_dir(library_path: str) -> str:
    manifest_path = Path(library_path) / "steamapps" / RIMWORLD_APPMANIFEST_NAME
    if not manifest_path.is_file():
        return ""
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="ignore") as handle:
            data = vdf.load(handle)
    except Exception:
        return ""

    app_state = data.get("AppState") if isinstance(data, dict) else None
    if not isinstance(app_state, dict):
        return ""
    appid = str(app_state.get("appid") or "").strip()
    if appid and appid != RIMWORLD_STEAM_APP_ID_STR:
        return ""
    return str(app_state.get("installdir") or "").strip()


def _steam_library_candidates_from_vdf(steam_root: str, library_folders: dict, system_name: str) -> list[tuple[str, dict | None]]:
    candidates: list[tuple[str, dict | None]] = [(normalize_path_for_storage(steam_root), None)]
    for folder_data in library_folders.values():
        if isinstance(folder_data, dict):
            library_path = normalize_path_for_storage(folder_data.get("path"))
            if library_path:
                candidates.append((library_path, folder_data))
        elif isinstance(folder_data, str):
            library_path = normalize_path_for_storage(folder_data)
            if library_path:
                candidates.append((library_path, None))
    deduped: list[tuple[str, dict | None]] = []
    seen: set[str] = set()
    for library_path, folder_data in candidates:
        if not library_path:
            continue
        key = library_path.lower() if system_name == "Windows" else library_path
        if key in seen:
            continue
        seen.add(key)
        deduped.append((library_path, folder_data))
    return deduped


def _resolve_rimworld_install_from_library(library_path: str, folder_data: dict | None = None, system_name: str | None = None) -> str:
    if not library_path or not _library_contains_rimworld(library_path, folder_data):
        return ""

    install_dirs = unique_paths([
        _read_steam_appmanifest_install_dir(library_path),
        "RimWorld",
    ], system_name=system_name)
    for install_dir in install_dirs:
        install_path = normalize_path_for_storage(Path(library_path) / "steamapps" / "common" / install_dir)
        if os.path.exists(install_path):
            return install_path
    return ""


def find_rimworld_install_from_steam(steam_root: str, system_name: str | None = None) -> str:
    resolved_system_name = _resolved_system_name(system_name)
    normalized_steam_root = normalize_path_for_storage(steam_root)
    install_path = _resolve_rimworld_install_from_library(
        normalized_steam_root,
        system_name=resolved_system_name,
    )
    if install_path:
        return install_path

    library_files = [
        Path(normalized_steam_root) / "config" / "libraryfolders.vdf",
        Path(normalized_steam_root) / "steamapps" / "libraryfolders.vdf",
    ]
    for library_file in library_files:
        if not library_file.is_file():
            continue
        try:
            with open(library_file, "r", encoding="utf-8", errors="ignore") as handle:
                data = vdf.load(handle)
        except Exception:
            continue

        library_folders = data.get("libraryfolders") if isinstance(data, dict) else None
        if not isinstance(library_folders, dict):
            continue

        for library_path, folder_data in _steam_library_candidates_from_vdf(
            normalized_steam_root,
            library_folders,
            resolved_system_name,
        ):
            install_path = _resolve_rimworld_install_from_library(
                library_path,
                folder_data,
                system_name=resolved_system_name,
            )
            if install_path:
                return install_path
    return ""
