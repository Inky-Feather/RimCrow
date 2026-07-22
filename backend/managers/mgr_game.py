import os
import subprocess
import platform
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - 仅在非 Windows 平台触发
    winreg = None

from backend.paths.game_locations import (
    detect_rimworld_executable,
    find_rimworld_install_from_steam,
    get_default_player_log_paths,
    get_default_steam_data_root_candidates,
    get_default_user_data_paths,
)
from backend.paths.core import unique_paths
from backend.paths.rimworld_layout import normalize_rimworld_install_root, resolve_rimworld_layout
from backend.utils.constants import RIMWORLD_STEAM_APP_ID_STR
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
        steam_roots = cls._detect_steam_root_candidates()

        # Steam 的库配置和 appmanifest 最接近真实安装状态，优先于默认目录猜测。
        for steam_root in steam_roots:
            rimworld_path = find_rimworld_install_from_steam(steam_root, system_name=system_name)
            if rimworld_path and cls.detect_executable(rimworld_path):
                return rimworld_path

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
            for root in steam_roots
        ])

        for install_loc in unique_paths(candidate_paths, system_name=system_name):
            normalized_install = normalize_rimworld_install_root(install_loc, system_name=system_name)
            if install_loc and os.path.exists(normalized_install) and cls.detect_executable(normalized_install):
                return normalize_path_for_storage(normalized_install)
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
