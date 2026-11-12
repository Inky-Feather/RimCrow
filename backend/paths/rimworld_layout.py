from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from .core import normalize_path_for_storage


@dataclass(frozen=True)
class RimWorldLayout:
    install_root: str = ""
    app_bundle_path: str = ""
    executable_path: str = ""
    local_mods_root: str = ""
    official_data_root: str = ""
    core_root: str = ""
    resource_data_root: str = ""
    layout_kind: str = "unknown"


def _resolved_system_name(system_name: str | None = None) -> str:
    return str(system_name or platform.system() or "").strip()


def _normalized_path(path_str: str) -> str:
    return normalize_path_for_storage(path_str)


def _path_if_exists(path: Path) -> str:
    return _normalized_path(path) if path.exists() else ""


MAC_BUNDLE_NAMES = ("RimWorld.app", "RimWorldMac.app")
MAC_EXECUTABLE_NAMES = ("RimWorld", "RimWorldMac")


def _find_macos_bundle(path: Path) -> Path | None:
    if path.suffix.lower() == ".app":
        return path
    for candidate in [path, *path.parents]:
        if candidate.suffix.lower() == ".app":
            return candidate
    # RimWorld 1.7 (Waylith engine) 的 macOS 包名为 RimWorld.app，1.6 及更早为 RimWorldMac.app。
    for bundle_name in MAC_BUNDLE_NAMES:
        if (path / bundle_name).exists():
            return path / bundle_name
    try:
        for child in sorted(path.iterdir()):
            if child.suffix.lower() == ".app":
                return child
    except OSError:
        pass
    return None


def _mac_official_data_root(install_root: Path, bundle: Path) -> Path:
    """1.7 起 Data 位于安装根目录；1.6 及更早位于 .app 内。"""
    for candidate in (install_root / "Data", bundle / "Data"):
        if candidate.exists():
            return candidate
    return install_root / "Data"


def _mac_executable(bundle: Path) -> Path:
    for name in MAC_EXECUTABLE_NAMES:
        candidate = bundle / "Contents" / "MacOS" / name
        if candidate.exists():
            return candidate
    return bundle / "Contents" / "MacOS" / MAC_EXECUTABLE_NAMES[0]


def resolve_rimworld_layout(install_path: str, system_name: str | None = None) -> RimWorldLayout:
    raw_path = str(install_path or "").strip()
    if not raw_path:
        return RimWorldLayout()

    resolved_system_name = _resolved_system_name(system_name)
    normalized_input = _normalized_path(raw_path)
    path = Path(normalized_input)
    if not path.exists():
        if resolved_system_name == "Darwin":
            bundle = path if path.suffix.lower() == ".app" else next(
                (path / name for name in MAC_BUNDLE_NAMES if (path / name).exists()),
                path / MAC_BUNDLE_NAMES[0],
            )
            install_root = bundle.parent if bundle.suffix.lower() == ".app" else path
            official_data_root = _mac_official_data_root(install_root, bundle)
            resource_data_root = bundle / "Contents" / "Resources" / "Data"
            executable = bundle / "Contents" / "MacOS" / MAC_EXECUTABLE_NAMES[0]
            return RimWorldLayout(
                install_root=_normalized_path(install_root),
                app_bundle_path=_normalized_path(bundle),
                executable_path=_normalized_path(bundle) if bundle.suffix.lower() == ".app" else _normalized_path(executable),
                local_mods_root=_normalized_path(install_root / "Mods"),
                official_data_root=_normalized_path(official_data_root),
                core_root=_normalized_path(official_data_root / "Core"),
                resource_data_root=_normalized_path(resource_data_root),
                layout_kind="mac_bundle",
            )
        layout_kind = "windows" if resolved_system_name == "Windows" else "linux" if resolved_system_name == "Linux" else "unknown"
        official_data_root = path / "Data"
        return RimWorldLayout(
            install_root=normalized_input,
            app_bundle_path="",
            executable_path="",
            local_mods_root=_normalized_path(path / "Mods"),
            official_data_root=_normalized_path(official_data_root),
            core_root=_normalized_path(official_data_root / "Core"),
            resource_data_root="",
            layout_kind=layout_kind,
        )

    if resolved_system_name == "Darwin":
        bundle = _find_macos_bundle(path)
        if bundle:
            install_root = bundle.parent
            executable = _mac_executable(bundle)
            official_data_root = _mac_official_data_root(install_root, bundle)
            resource_data_root = bundle / "Contents" / "Resources" / "Data"
            return RimWorldLayout(
                install_root=_normalized_path(install_root),
                app_bundle_path=_normalized_path(bundle),
                executable_path=_path_if_exists(executable),
                local_mods_root=_normalized_path(install_root / "Mods"),
                official_data_root=_normalized_path(official_data_root),
                core_root=_normalized_path(official_data_root / "Core"),
                resource_data_root=_normalized_path(resource_data_root),
                layout_kind="mac_bundle",
            )

    install_root = path
    layout_kind = "windows" if resolved_system_name == "Windows" else "linux" if resolved_system_name == "Linux" else "unknown"
    executable_candidates = {
        # RimWorld 1.7 (Waylith engine) renamed the Windows executable to RimWorld.exe;
        # keep the legacy names so 1.6 and earlier installs keep resolving.
        "Windows": [
            install_root / "RimWorld.exe",
            install_root / "RimWorldWin64.exe",
            install_root / "RimWorldWin.exe",
        ],
        "Linux": [install_root / "RimWorldLinux", install_root / "RimWorldLinux.x86_64"],
    }.get(resolved_system_name, [])
    executable_path = ""
    for candidate in executable_candidates:
        if candidate.is_file():
            executable_path = _normalized_path(candidate)
            break

    official_data_root = install_root / "Data"
    return RimWorldLayout(
        install_root=_normalized_path(install_root),
        app_bundle_path="",
        executable_path=executable_path,
        local_mods_root=_normalized_path(install_root / "Mods"),
        official_data_root=_normalized_path(official_data_root),
        core_root=_normalized_path(official_data_root / "Core"),
        resource_data_root="",
        layout_kind=layout_kind,
    )


def normalize_rimworld_install_root(path_str: str, system_name: str | None = None) -> str:
    layout = resolve_rimworld_layout(path_str, system_name=system_name)
    return layout.install_root or _normalized_path(path_str)
