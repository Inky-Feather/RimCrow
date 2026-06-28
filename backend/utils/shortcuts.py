import configparser
import os
import platform
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict

from backend.utils.logger import logger


SHORTCUT_SUFFIXES = {
    "lnk": ".lnk",
    "url": ".url",
    "desktop": ".desktop",
    "command": ".command",
}


def get_platform_shortcut_kind(for_url: bool = False) -> str:
    system_name = platform.system()
    if system_name == "Windows":
        return "url" if for_url else "lnk"
    if system_name == "Linux":
        return "desktop"
    if system_name == "Darwin":
        return "command"
    raise OSError(f"当前平台暂不支持快捷方式: {system_name}")


def get_shortcut_suffix(shortcut_kind: str) -> str:
    suffix = SHORTCUT_SUFFIXES.get(str(shortcut_kind or "").strip().lower())
    if not suffix:
        raise ValueError(f"不支持的快捷方式类型: {shortcut_kind}")
    return suffix


def normalize_shortcut_path(shortcut_path: str, shortcut_kind: str) -> str:
    path = os.path.abspath(str(shortcut_path or "").strip())
    if not path:
        raise ValueError("快捷方式路径不能为空")

    suffix = get_shortcut_suffix(shortcut_kind)
    if not path.lower().endswith(suffix):
        path = f"{path}{suffix}"
    return path


def resolve_shortcut_kind(spec: Dict[str, Any], *, for_url: bool = False) -> str:
    kind = str(spec.get("shortcut_kind") or "").strip().lower()
    if kind: return kind

    shortcut_path = str(spec.get("shortcut_path") or "").strip()
    suffix = Path(shortcut_path).suffix.lower()
    for candidate_kind, candidate_suffix in SHORTCUT_SUFFIXES.items():
        if suffix == candidate_suffix: return candidate_kind
    return get_platform_shortcut_kind(for_url=for_url)


def format_shortcut_arguments(args: list[str]) -> str:
    values = [str(arg or "").strip() for arg in args if str(arg or "").strip()]
    if not values: return ""
    if platform.system() == "Windows":
        return subprocess.list2cmdline(values)
    return " ".join(shlex.quote(value) for value in values)


def get_windows_special_folder(folder_name: str) -> str:
    if platform.system() != "Windows":
        raise OSError("特殊目录读取仅支持 Windows")

    from win32com.shell import shell, shellcon

    folder_key = str(folder_name or "").strip().upper()
    csidl_name = f"CSIDL_{folder_key}"
    csidl_value = getattr(shellcon, csidl_name, None)
    if csidl_value is None:
        raise ValueError(f"不支持的特殊目录: {folder_name}")

    path = shell.SHGetFolderPath(0, csidl_value, 0, 0)
    if not path:
        raise FileNotFoundError(f"无法获取特殊目录: {folder_name}")
    return str(path)


def get_desktop_directory() -> str:
    """统一解析桌面目录，避免业务层自己拼平台路径。"""
    system_name = platform.system()
    if system_name == "Windows":
        return get_windows_special_folder("Desktop")

    home_dir = Path.home()
    if system_name == "Linux":
        user_dirs = home_dir / ".config" / "user-dirs.dirs"
        if user_dirs.is_file():
            try:
                for raw_line in user_dirs.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line.startswith("XDG_DESKTOP_DIR="):
                        continue
                    value = line.split("=", 1)[1].strip().strip('"')
                    value = value.replace("$HOME", str(home_dir))
                    return os.path.abspath(os.path.expandvars(value))
            except Exception as e:
                logger.debug(f"解析 XDG_DESKTOP_DIR 失败，将回退到默认桌面路径: {e}")
        return str(home_dir / "Desktop")

    if system_name == "Darwin":
        return str(home_dir / "Desktop")

    raise OSError(f"当前平台暂不支持桌面目录解析: {system_name}")


def create_windows_shortcut(
    shortcut_path: str,
    target_path: str,
    arguments: str = "",
    working_directory: str = "",
    icon_location: str = "",
    description: str = "",
) -> Dict[str, Any]:
    if platform.system() != "Windows":
        raise OSError("快捷方式创建仅支持 Windows")

    normalized_shortcut = normalize_shortcut_path(shortcut_path, "lnk")
    normalized_target = os.path.abspath(str(target_path or "").strip())
    if not normalized_target or not os.path.exists(normalized_target):
        raise FileNotFoundError(f"快捷方式目标不存在: {normalized_target}")

    normalized_workdir = os.path.abspath(str(working_directory or "").strip()) if str(working_directory or "").strip() else ""
    normalized_icon = str(icon_location or "").strip()
    shortcut_dir = os.path.dirname(normalized_shortcut)
    if shortcut_dir:
        os.makedirs(shortcut_dir, exist_ok=True)

    from win32com.client import Dispatch

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(normalized_shortcut)
    shortcut.TargetPath = normalized_target
    shortcut.Arguments = str(arguments or "")
    if normalized_workdir:
        shortcut.WorkingDirectory = normalized_workdir
    if normalized_icon:
        shortcut.IconLocation = normalized_icon
    if str(description or "").strip():
        shortcut.Description = str(description).strip()
    shortcut.Save()

    return {
        "shortcut_path": normalized_shortcut,
        "target_path": normalized_target,
        "arguments": str(arguments or ""),
        "working_directory": normalized_workdir,
        "icon_location": normalized_icon,
        "description": str(description or "").strip(),
        "shortcut_kind": "lnk",
    }


def create_windows_url_shortcut(
    shortcut_path: str,
    url: str,
    icon_location: str = "",
) -> Dict[str, Any]:
    if platform.system() != "Windows":
        raise OSError("快捷方式创建仅支持 Windows")

    normalized_shortcut = normalize_shortcut_path(shortcut_path, "url")
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise ValueError("快捷方式 URL 不能为空")

    shortcut_dir = os.path.dirname(normalized_shortcut)
    if shortcut_dir:
        os.makedirs(shortcut_dir, exist_ok=True)

    config = configparser.ConfigParser()
    config.optionxform = str  # type: ignore
    config["InternetShortcut"] = {"URL": normalized_url}
    if str(icon_location or "").strip():
        config["InternetShortcut"]["IconFile"] = str(icon_location).strip()
        config["InternetShortcut"]["IconIndex"] = "0"

    with open(normalized_shortcut, "w", encoding="utf-8") as f:
        config.write(f, space_around_delimiters=False)

    return {
        "shortcut_path": normalized_shortcut,
        "url": normalized_url,
        "icon_location": str(icon_location or "").strip(),
        "shortcut_kind": "url",
    }


def create_linux_desktop_shortcut(
    shortcut_path: str,
    target_path: str = "",
    arguments: str = "",
    working_directory: str = "",
    icon_location: str = "",
    description: str = "",
    url: str = "",
    **_: Any,
) -> Dict[str, Any]:
    if platform.system() != "Linux":
        raise OSError("Linux 快捷方式创建仅支持 Linux")

    normalized_shortcut = normalize_shortcut_path(shortcut_path, "desktop")
    normalized_target = os.path.abspath(str(target_path or "").strip()) if str(target_path or "").strip() else ""
    normalized_workdir = os.path.abspath(str(working_directory or "").strip()) if str(working_directory or "").strip() else ""
    normalized_icon = str(icon_location or "").strip()
    normalized_url = str(url or "").strip()
    shortcut_dir = os.path.dirname(normalized_shortcut)
    if shortcut_dir:
        os.makedirs(shortcut_dir, exist_ok=True)

    if normalized_url:
        exec_value = f"xdg-open {shlex.quote(normalized_url)}"
    else:
        if not normalized_target or not os.path.exists(normalized_target):
            raise FileNotFoundError(f"快捷方式目标不存在: {normalized_target}")
        exec_value = shlex.quote(normalized_target)
        if str(arguments or "").strip():
            exec_value = f"{exec_value} {str(arguments).strip()}"

    lines = [
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        f"Name={Path(normalized_shortcut).stem}",
        f"Exec={exec_value}",
        "Terminal=false",
    ]
    if str(description or "").strip():
        lines.append(f"Comment={str(description).strip()}")
    if normalized_workdir:
        lines.append(f"Path={normalized_workdir}")
    if normalized_icon:
        lines.append(f"Icon={normalized_icon}")

    with open(normalized_shortcut, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(normalized_shortcut, 0o755)

    return {
        "shortcut_path": normalized_shortcut,
        "target_path": normalized_target,
        "arguments": str(arguments or ""),
        "working_directory": normalized_workdir,
        "icon_location": normalized_icon,
        "description": str(description or "").strip(),
        "url": normalized_url,
        "shortcut_kind": "desktop",
    }


def create_macos_command_shortcut(
    shortcut_path: str,
    target_path: str = "",
    arguments: str = "",
    working_directory: str = "",
    icon_location: str = "",
    description: str = "",
    url: str = "",
    **_: Any,
) -> Dict[str, Any]:
    if platform.system() != "Darwin":
        raise OSError("macOS 快捷方式创建仅支持 macOS")

    normalized_shortcut = normalize_shortcut_path(shortcut_path, "command")
    normalized_target = os.path.abspath(str(target_path or "").strip()) if str(target_path or "").strip() else ""
    normalized_workdir = os.path.abspath(str(working_directory or "").strip()) if str(working_directory or "").strip() else ""
    normalized_icon = str(icon_location or "").strip()
    normalized_url = str(url or "").strip()
    shortcut_dir = os.path.dirname(normalized_shortcut)
    if shortcut_dir:
        os.makedirs(shortcut_dir, exist_ok=True)

    script_lines = ["#!/bin/sh"]
    if normalized_workdir:
        script_lines.append(f"cd {shlex.quote(normalized_workdir)} || exit 1")

    if normalized_url:
        script_lines.append(f"exec open {shlex.quote(normalized_url)}")
    else:
        if not normalized_target or not os.path.exists(normalized_target):
            raise FileNotFoundError(f"快捷方式目标不存在: {normalized_target}")
        command = f"exec {shlex.quote(normalized_target)}"
        if str(arguments or "").strip():
            command = f"{command} {str(arguments).strip()}"
        script_lines.append(command)

    with open(normalized_shortcut, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(script_lines) + "\n")
    os.chmod(normalized_shortcut, 0o755)

    return {
        "shortcut_path": normalized_shortcut,
        "target_path": normalized_target,
        "arguments": str(arguments or ""),
        "working_directory": normalized_workdir,
        "icon_location": normalized_icon,
        "description": str(description or "").strip(),
        "url": normalized_url,
        "shortcut_kind": "command",
    }


def create_shortcut(spec: Dict[str, Any]) -> Dict[str, Any]:
    """统一创建快捷方式，让业务层只关心 spec，不关心平台细节。"""
    kind = resolve_shortcut_kind(spec, for_url=bool(str(spec.get("url") or "").strip()))
    payload = {
        "shortcut_path": str(spec.get("shortcut_path") or "").strip(),
        "target_path": str(spec.get("target_path") or "").strip(),
        "arguments": str(spec.get("arguments") or ""),
        "working_directory": str(spec.get("working_directory") or "").strip(),
        "icon_location": str(spec.get("icon_location") or "").strip(),
        "description": str(spec.get("description") or "").strip(),
        "url": str(spec.get("url") or "").strip(),
        "shortcut_kind": kind,
    }

    if kind == "lnk":
        return create_windows_shortcut(
            shortcut_path=payload["shortcut_path"],
            target_path=payload["target_path"],
            arguments=payload["arguments"],
            working_directory=payload["working_directory"],
            icon_location=payload["icon_location"],
            description=payload["description"],
        )
    if kind == "url":
        return create_windows_url_shortcut(
            shortcut_path=payload["shortcut_path"],
            url=payload["url"],
            icon_location=payload["icon_location"],
        )
    if kind == "desktop":
        return create_linux_desktop_shortcut(**payload)
    if kind == "command":
        return create_macos_command_shortcut(**payload)
    raise ValueError(f"不支持的快捷方式类型: {kind}")


def remove_shortcut_variants(shortcut_path: str):
    """删除同名不同后缀的快捷方式，避免保留旧入口。"""
    base_path = Path(os.path.abspath(str(shortcut_path or "").strip()))
    if not base_path.name: return

    for suffix in SHORTCUT_SUFFIXES.values():
        candidate = base_path.with_suffix(suffix)
        if candidate == base_path:
            continue
        try:
            candidate.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"清理旧快捷方式失败: {candidate} - {e}")
