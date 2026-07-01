import os
import subprocess
import sys
from typing import Dict

from backend.platform.runtime import get_restart_command, is_windows
from backend.settings import HOME_DIR
from backend.utils.logger import logger

# PyInstaller onefile 重启场景下，必须清理/重置这些运行时环境变量；
# 否则新进程可能被误判为旧实例派生出的 worker，继承已失效的解包环境。
PYINSTALLER_ENV_VARS_TO_CLEAR = (
    "_MEIPASS",
    "_MEIPASS2",
    "_PYI_APPLICATION_HOME_DIR",
    "_PYI_ARCHIVE_FILE",
    "_PYI_PARENT_PROCESS_LEVEL",
    "_PYI_SPLASH_IPC",
    "PYI_EXPLODE_PATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYINSTALLER_SUPPRESS_SPLASH_SCREEN",
    "PYINSTALLER_STRICT_UNPACK_MODE",
)

# 重启后的新实例只需要尽量干净的系统环境，避免把当前进程的脏运行时状态继续传下去。
RESTART_ENV_WHITELIST = (
    "ALLUSERSPROFILE",
    "APPDATA",
    "CommonProgramFiles",
    "CommonProgramFiles(x86)",
    "CommonProgramW6432",
    "COMSPEC",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "PROCESSOR_LEVEL",
    "PROCESSOR_REVISION",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "PUBLIC",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERNAME",
    "USERPROFILE",
    "WINDIR",
)


def _build_restart_environment() -> Dict[str, str]:
    """
    为重启后的新进程构造一份干净环境变量。
    原因：更新重启和手动重启都可能发生在 PyInstaller onefile 运行时环境里，
    若直接继承当前环境，可能把失效的解包路径和内部状态一并带给新实例。
    """
    if not is_windows():
        clean_env = dict(os.environ)
        for key in PYINSTALLER_ENV_VARS_TO_CLEAR:
            clean_env.pop(key, None)
        clean_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        return clean_env

    clean_env: Dict[str, str] = {}

    for key in RESTART_ENV_WHITELIST:
        value = os.environ.get(key)
        if value:
            clean_env[key] = value

    # 某些环境变量名大小写不一致，这里做一次兼容兜底。
    if "COMSPEC" not in clean_env:
        clean_env["COMSPEC"] = os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe")
    if "SYSTEMROOT" not in clean_env:
        clean_env["SYSTEMROOT"] = os.environ.get("SystemRoot", r"C:\Windows")
    if "WINDIR" not in clean_env:
        clean_env["WINDIR"] = os.environ.get("WINDIR", clean_env["SYSTEMROOT"])

    clean_env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

    for key in PYINSTALLER_ENV_VARS_TO_CLEAR:
        clean_env.pop(key, None)

    return clean_env


def _reset_windows_dll_directory():
    """
    恢复 Windows 默认 DLL 搜索路径。
    原因：PyInstaller onefile 会临时改写 DLL 搜索目录，不重置的话，
    当前进程拉起的更新器或新实例可能继续引用已经失效的临时目录。
    """
    if not is_windows():
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    except Exception as e:
        logger.warning(f"重启前重置 Windows DLL 目录失败：{e}")


def _resolve_restart_command(executable_path: str = ""):
    """
    解析当前环境下的新实例启动命令。
    原则：
    1. 打包环境直接启动当前 exe。
    2. 开发环境优先使用 pythonw.exe，避免重启时弹出控制台窗口。
    """
    return get_restart_command(executable_path, main_script=HOME_DIR / "main.py")


def launch_new_application(executable_path: str = ""):
    """
    静默拉起新实例。
    目的：统一所有“重启当前应用”的入口，避免在 Windows 下弹出 cmd 窗口。
    """
    command = _resolve_restart_command(executable_path)
    clean_env = _build_restart_environment()
    _reset_windows_dll_directory()

    popen_kwargs = {
        "cwd": str(HOME_DIR),
        "env": clean_env,
    }

    if os.name == 'nt':
        popen_kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)

    logger.info(f"正在静默拉起新实例: {command[0]}")
    subprocess.Popen(command, **popen_kwargs)
