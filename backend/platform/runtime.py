import os
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform == "win32"


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def supports_win32_ctypes() -> bool:
    return is_windows()


def monitoring_mode() -> str:
    return "windows" if is_windows() else "disabled"


def supports_process_monitoring() -> bool:
    return monitoring_mode() != "disabled"


def open_uri(uri: str) -> None:
    if is_windows():
        os.startfile(uri)  # type: ignore[attr-defined]
        return
    if is_macos():
        subprocess.Popen(["open", uri])
        return
    subprocess.Popen(["xdg-open", uri])


def get_restart_command(executable_path: str = "", *, main_script: str | Path | None = None) -> list[str]:
    if executable_path:
        return [os.path.abspath(executable_path)]
    if getattr(sys, "frozen", False):
        return [os.path.abspath(sys.executable)]

    python_executable = Path(sys.executable).resolve()
    target_script = str(main_script) if main_script is not None else ""
    if is_windows():
        pythonw_executable = python_executable.with_name("pythonw.exe")
        if pythonw_executable.exists():
            return [str(pythonw_executable), target_script]
    return [str(python_executable), target_script]
