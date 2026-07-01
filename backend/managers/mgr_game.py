import os
import subprocess
import platform
from pathlib import Path

import vdf

try:
    import winreg
except ImportError:  # pragma: no cover - 仅在非 Windows 平台触发
    winreg = None

from backend.paths.game_locations import (
    detect_rimworld_executable,
    find_rimworld_install_from_steam,
    get_default_player_log_paths,
    get_default_steam_root_candidates,
    get_default_steam_data_root_candidates,
    get_default_user_data_paths,
)
from backend.paths.core import unique_paths
from backend.paths.rimworld_layout import normalize_rimworld_install_root, resolve_rimworld_layout
from backend.utils.constants import RIMWORLD_APPMANIFEST_NAME, RIMWORLD_STEAM_APP_ID_STR
from backend.utils.tools import normalize_path_for_storage

class GameManager:
    """
    游戏管理：路径检测、启动游戏
    """

    PROCESS_NAMES_BY_SYSTEM = {
        'Windows': ("RimWorldWin64.exe", "RimWorldWin.exe"),
        'Darwin': ("RimWorldMac",),
        'Linux': ("RimWorldLinux", "RimWorldLinux.x86_64", "RimWorldWin64.exe", "RimWorldWin.exe"),
    }

    @classmethod
    def get_default_user_data_paths(cls) -> list[str]:
        """返回与 Profile 环境无关的默认用户数据目录候选。"""
        return get_default_user_data_paths(system_name=platform.system())

    @classmethod
    def get_default_player_log_paths(cls, filename: str = "Player.log") -> list[str]:
        """返回各平台默认 Player 日志文件候选位置。"""
        return get_default_player_log_paths(filename=filename, system_name=platform.system())

    @classmethod
    def resolve_default_user_data_path(cls) -> str:
        """优先返回存在的默认用户数据目录，否则返回首选候选。"""
        candidates = cls.get_default_user_data_paths()
        for path in candidates:
            if os.path.exists(path):
                return path
        return candidates[0] if candidates else ""

    @classmethod
    def auto_detect_paths(cls):
        """
        尝试自动检测 RimWorld 的关键路径。
        返回字典: {
            'game_install_path': str,
            'user_data_path': str,
            'local_mods_path': str,
            'workshop_mods_path': str,
            'game_config_path': str
        }
        """
        paths = {
            'game_install_path': '',
            'user_data_path': '',
            'local_mods_path': '',
            'workshop_mods_path': '',
            'game_config_path': ''
        }
        
        # 1. 检测 Config 路径 (各平台固定)
        paths['user_data_path'] = cls._detect_userdata_path()
        paths['game_config_path'] = os.path.join(paths['user_data_path'], 'Config') if paths['user_data_path'] else ''

        # 2. 检测安装路径。
        # 这里只覆盖“当前平台最常见的 Steam 默认安装位”，
        # 找不到时仍允许用户手动配置，不把自动探测做成唯一入口。
        install_loc = cls._detect_steam_install_path()
        
        # 3. 检测 安装路径
        if install_loc and os.path.exists(install_loc):
            paths['game_install_path'] = ''
            # 检测 可执行文件是否存在(多平台)
            normalized_install = normalize_rimworld_install_root(install_loc, system_name=platform.system())
            if cls.detect_executable(normalized_install):
                paths['game_install_path'] = normalized_install
            
            layout = resolve_rimworld_layout(normalized_install, system_name=platform.system())
            if layout.local_mods_root and os.path.exists(layout.local_mods_root):
                paths['local_mods_path'] = layout.local_mods_root
            
            # 推导 Workshop Mods
            # Steam 结构: steamapps/common/RimWorld -> RimWorld 工坊内容目录
            # 回退两级找到 workshop 目录
            workshop_base = os.path.abspath(os.path.join(normalized_install, "../../workshop/content", RIMWORLD_STEAM_APP_ID_STR))
            if os.path.exists(workshop_base):
                paths['workshop_mods_path'] = normalize_path_for_storage(workshop_base)

        # 如果所有路径都为空，返回 None
        if not any(paths.values()): return {}
        
        return paths
    
    @staticmethod
    def detect_executable(install_path):
        """检测游戏可执行文件"""
        layout = resolve_rimworld_layout(install_path, system_name=platform.system())
        normalized_install = normalize_rimworld_install_root(install_path, system_name=platform.system())
        if not os.path.exists(normalized_install):
            return None
        if layout.app_bundle_path and os.path.exists(layout.app_bundle_path):
            return layout.app_bundle_path
        if layout.executable_path and os.path.exists(layout.executable_path):
            return layout.executable_path
        return detect_rimworld_executable(normalized_install, system_name=platform.system()) or None
    
    @classmethod
    def launch_game(cls, game_install_path, custom_args: list = []):
        """
        启动 RimWorld。
        :param custom_args: 启动参数列表，例如 ['-savedatafolder=D:/Profile1']
        """
        target_exe = cls.detect_executable(game_install_path)
        if not target_exe:
            raise Exception(f"在安装目录下找不到可执行文件")
        system_name = platform.system()
        # 确保 custom_args 是列表
        args = custom_args if custom_args else []
        try:
            if system_name == 'Windows':
                # Windows 拼接方式：[exe_path, arg1, arg2]
                cmd = [target_exe] + args
                # creationflags=subprocess.CREATE_NEW_CONSOLE 确保游戏进程独立于管理器
                subprocess.Popen(cmd, cwd=game_install_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
            elif system_name == 'Darwin': # macOS
                # macOS 下如果是 .app 文件夹，需要使用 open 命令
                if target_exe.endswith('.app'):
                    # open -a "Path/To/RimWorld.app" --args -savedatafolder="..."
                    cmd = ['open', '-a', target_exe, '--args'] + args
                else:
                    cmd = [target_exe] + args
                subprocess.Popen(cmd)
            else: # Linux
                if target_exe.lower().endswith(".exe"):
                    raise Exception("Linux 下检测到 Windows 版 RimWorld，请通过 Steam/Proton 启动。")
                cmd = [target_exe] + args
                subprocess.Popen(cmd, cwd=game_install_path)
            from backend.utils.logger import logger 
            logger.debug(f"通过游戏本体命令启动 RimWorld: {cmd}")
            return True
        except Exception as e:
            raise Exception(f"执行启动指令失败: {str(e)}")

    @staticmethod
    def get_game_version(game_install_path):
        """获取游戏版本号"""
        normalized_install = normalize_rimworld_install_root(game_install_path, system_name=platform.system())
        version_file = os.path.join(normalized_install, 'Version.txt')
        if os.path.exists(version_file):
            try:
                with open(version_file, 'r', encoding='utf-8-sig') as f: 
                    # 使用 'utf-8-sig' 可以自动去除 BOM 头 (\ufeff)
                    content = f.read().strip()
                    if content: return content
            except:
                return ""
        return ""

    # --- 内部辅助方法 ---
    @staticmethod
    def _detect_userdata_path():
        """检测 Config 文件夹位置"""
        return GameManager.resolve_default_user_data_path()
    
    @classmethod
    def _detect_steam_install_path(cls):
        """
        检测各平台常见的 Steam 版 RimWorld 安装路径。

        注意这里只收口 Steam 已登记的安装位置和常见默认位置，不递归扫描磁盘。
        """
        system_name = platform.system()
        candidate_paths = []
        if system_name == 'Windows' and winreg is not None:
            keys = [
                rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {RIMWORLD_STEAM_APP_ID_STR}",
                rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {RIMWORLD_STEAM_APP_ID_STR}",
            ]
            for key_path in keys:
                for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    install_loc = cls._read_windows_registry_value(root, key_path, "InstallLocation")
                    if install_loc:
                        candidate_paths.append(install_loc)
        candidate_paths.extend([
            os.path.join(root, "steamapps", "common", "RimWorld")
            for root in get_default_steam_data_root_candidates(system_name=system_name)
        ])

        for install_loc in unique_paths(candidate_paths, system_name=system_name):
            if install_loc and os.path.exists(install_loc):
                return normalize_path_for_storage(install_loc)

        # 兜底：读取 Steam 多库配置，支持用户把 RimWorld 安装到非默认库。
        for steam_root in cls._detect_steam_root_candidates():
            rimworld_path = cls._find_rimworld_from_steam_libraries(steam_root)
            if rimworld_path:
                return rimworld_path
        return None

    @staticmethod
    def _read_windows_registry_value(root, key_path: str, value_name: str) -> str:
        if winreg is None:
            return ""
        try:
            with winreg.OpenKey(root, key_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
            return str(value or "").strip()
        except OSError:
            return ""

    @staticmethod
    def _detect_steam_root_candidates() -> list[str]:
        return get_default_steam_data_root_candidates(system_name=platform.system())

    @staticmethod
    def _library_contains_rimworld(library_path: str, folder_data: dict | None = None) -> bool:
        apps = (folder_data or {}).get("apps", {}) if isinstance(folder_data, dict) else {}
        if isinstance(apps, dict) and RIMWORLD_STEAM_APP_ID_STR in apps:
            return True
        return os.path.exists(os.path.join(library_path, "steamapps", RIMWORLD_APPMANIFEST_NAME))

    @staticmethod
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

    @staticmethod
    def _steam_library_candidates_from_vdf(steam_root: str, library_folders: dict) -> list[tuple[str, dict | None]]:
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
        return candidates

    @staticmethod
    def _resolve_rimworld_install_from_library(library_path: str, folder_data: dict | None = None) -> str:
        return find_rimworld_install_from_steam(library_path, system_name=platform.system())

    @staticmethod
    def _find_rimworld_from_steam_libraries(steam_root: str) -> str:
        return find_rimworld_install_from_steam(steam_root, system_name=platform.system())
