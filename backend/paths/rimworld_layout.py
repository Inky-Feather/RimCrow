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


def _find_macos_bundle(path: Path) -> Path | None:
    if path.suffix.lower() == ".app":
        return path
    for candidate in [path, *path.parents]:
        if candidate.suffix.lower() == ".app":
            return candidate
    if (path / "RimWorldMac.app").exists():
        return path / "RimWorldMac.app"
    return None


def resolve_rimworld_layout(install_path: str, system_name: str | None = None) -> RimWorldLayout:
    raw_path = str(install_path or "").strip()
    if not raw_path:
        return RimWorldLayout()

    resolved_system_name = _resolved_system_name(system_name)
    normalized_input = _normalized_path(raw_path)
    path = Path(normalized_input)
    if not path.exists():
        if resolved_system_name == "Darwin":
            bundle = path if path.suffix.lower() == ".app" else path / "RimWorldMac.app"
            install_root = bundle.parent if bundle.suffix.lower() == ".app" else path
            official_data_root = bundle / "Data"
            resource_data_root = bundle / "Contents" / "Resources" / "Data"
            executable = bundle / "Contents" / "MacOS" / "RimWorldMac"
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
            executable = bundle / "Contents" / "MacOS" / "RimWorldMac"
            official_data_root = bundle / "Data"
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
        "Windows": [install_root / "RimWorldWin64.exe", install_root / "RimWorldWin.exe"],
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
