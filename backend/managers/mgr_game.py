import os
import subprocess
import platform
from pathlib import Path

import vdf

try:
    import winreg
except ImportError:  # pragma: no cover - 仅在非 Windows 平台触发
    winreg = None

from backend.utils.constants import RIMWORLD_APPMANIFEST_NAME, RIMWORLD_STEAM_APP_ID_STR
from backend.utils.tools import normalize_path_for_storage

class GameManager:
    """
    游戏管理：路径检测、启动游戏
    """

    @staticmethod
    def _unique_paths(candidates: list[str]) -> list[str]:
        """按顺序去重并规范化路径。"""
        result: list[str] = []
        seen: set[str] = set()
        for raw_path in candidates:
            path = str(raw_path or "").strip()
            if not path: continue
            normalized = os.path.normpath(path)
            key = normalized.lower() if platform.system() == 'Windows' else normalized
            if key in seen: continue
            seen.add(key)
            result.append(normalized)
        return result

    @classmethod
    def get_default_user_data_paths(cls) -> list[str]:
        """返回与 Profile 环境无关的默认用户数据目录候选。"""
        system_name = platform.system()

        if system_name == 'Windows':
            user_profile = os.getenv('USERPROFILE') or os.path.expanduser('~')
            return cls._unique_paths([
                os.path.join(user_profile, 'AppData', 'LocalLow', 'Ludeon Studios', 'RimWorld by Ludeon Studios')
            ])

        home = os.path.expanduser('~')
        if system_name == 'Darwin':
            return cls._unique_paths([
                os.path.join(home, 'Library', 'Application Support', 'RimWorld'),
            ])

        return cls._unique_paths([
            os.path.join(home, '.config', 'unity3d', 'Ludeon Studios', 'RimWorld by Ludeon Studios'),
            os.path.join(home, '.var', 'app', 'com.valvesoftware.Steam', 'config', 'unity3d', 'Ludeon Studios', 'RimWorld by Ludeon Studios'),
        ])

    @classmethod
    def get_default_player_log_paths(cls, filename: str = "Player.log") -> list[str]:
        """返回各平台默认 Player 日志文件候选位置。"""
        target_name = os.path.basename(str(filename or "").strip()) or "Player.log"
        system_name = platform.system()

        if system_name == 'Darwin':
            home = os.path.expanduser('~')
            return cls._unique_paths([
                os.path.join(home, 'Library', 'Logs', 'Ludeon Studios', 'RimWorld by Ludeon Studios', target_name),
                os.path.join(home, 'Library', 'Logs', 'Unity', target_name),
            ])

        return cls._unique_paths([
            os.path.join(root, target_name)
            for root in cls.get_default_user_data_paths()
        ])

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
            normalized_install = normalize_path_for_storage(install_loc)
            if cls.detect_executable(normalized_install):
                paths['game_install_path'] = normalized_install
            
            # 推导 Local Mods
            local_mods = os.path.join(normalized_install, "Mods")
            if os.path.exists(local_mods):
                paths['local_mods_path'] = normalize_path_for_storage(local_mods)
            
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
        system_name = platform.system()
        
        if system_name == 'Windows':
            candidates = ["RimWorldWin64.exe", "RimWorldWin.exe"]
        elif system_name == 'Darwin': # macOS
            # macOS 下通常是 RimWorldMac.app，执行里面的 binary
            candidates = ["RimWorldMac.app", "RimWorldMac"] 
        else: # Linux
            candidates = ["RimWorldLinux", "RimWorldLinux.x86_64"]

        for exe in candidates:
            p = os.path.join(install_path, exe)
            # macOS 特殊处理: 如果是 .app 文件夹，用 open 命令
            if system_name == 'Darwin' and exe.endswith('.app') and os.path.exists(p): return p
            # 其他情况找文件
            if os.path.isfile(p): return p
        return None
    
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
        version_file = os.path.join(game_install_path, 'Version.txt')
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

        if system_name == 'Windows':
            if winreg is not None:
                keys = [
                    rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {RIMWORLD_STEAM_APP_ID_STR}",
                    rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {RIMWORLD_STEAM_APP_ID_STR}",
                ]
                for key_path in keys:
                    for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                        install_loc = cls._read_windows_registry_value(root, key_path, "InstallLocation")
                        if install_loc:
                            candidate_paths.append(install_loc)
        elif system_name == 'Darwin':
            home = os.path.expanduser('~')
            candidate_paths.extend([
                os.path.join(home, 'Library', 'Application Support', 'Steam', 'steamapps', 'common', 'RimWorld'),
            ])
        else:
            home = os.path.expanduser('~')
            candidate_paths.extend([
                os.path.join(home, '.steam', 'steam', 'steamapps', 'common', 'RimWorld'),
                os.path.join(home, '.local', 'share', 'Steam', 'steamapps', 'common', 'RimWorld'),
                os.path.join(home, 'snap', 'steam', 'common', '.local', 'share', 'Steam', 'steamapps', 'common', 'RimWorld'),
            ])

        for install_loc in cls._unique_paths(candidate_paths):
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
        system_name = platform.system()
        candidates: list[str] = []

        if system_name == 'Windows':
            if winreg is not None:
                for key_path in [r"SOFTWARE\WOW6432Node\Valve\Steam", r"SOFTWARE\Valve\Steam"]:
                    for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                        install_path = GameManager._read_windows_registry_value(root, key_path, "InstallPath")
                        if install_path:
                            candidates.append(install_path)
            candidates.extend([
                r"C:\Program Files (x86)\Steam",
                r"C:\Program Files\Steam",
            ])
        elif system_name == 'Darwin':
            home = os.path.expanduser('~')
            candidates.append(os.path.join(home, 'Library', 'Application Support', 'Steam'))
        else:
            home = os.path.expanduser('~')
            xdg_data_home = os.getenv("XDG_DATA_HOME")
            candidates.extend([
                os.path.join(home, '.steam', 'steam'),
                os.path.join(home, '.local', 'share', 'Steam'),
                os.path.join(home, 'snap', 'steam', 'common', '.local', 'share', 'Steam'),
                os.path.join(home, '.var', 'app', 'com.valvesoftware.Steam', '.local', 'share', 'Steam'),
            ])
            if xdg_data_home:
                candidates.append(os.path.join(xdg_data_home, 'Steam'))

        return GameManager._unique_paths([normalize_path_for_storage(path) for path in candidates if path])

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
        if not library_path or not GameManager._library_contains_rimworld(library_path, folder_data):
            return ""

        install_dirs = [GameManager._read_steam_appmanifest_install_dir(library_path), "RimWorld"]
        for install_dir in GameManager._unique_paths(install_dirs):
            install_path = normalize_path_for_storage(Path(library_path) / "steamapps" / "common" / install_dir)
            if os.path.exists(install_path):
                return install_path
        return ""

    @staticmethod
    def _find_rimworld_from_steam_libraries(steam_root: str) -> str:
        library_files = [
            Path(steam_root) / "config" / "libraryfolders.vdf",
            Path(steam_root) / "steamapps" / "libraryfolders.vdf",
        ]
        install_path = GameManager._resolve_rimworld_install_from_library(normalize_path_for_storage(steam_root))
        if install_path:
            return install_path

        seen_libraries: set[str] = set()
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

            for library_path, folder_data in GameManager._steam_library_candidates_from_vdf(steam_root, library_folders):
                library_key = os.path.normcase(library_path)
                if not library_path or library_key in seen_libraries:
                    continue
                seen_libraries.add(library_key)
                install_path = GameManager._resolve_rimworld_install_from_library(library_path, folder_data)
                if install_path:
                    return install_path
        return ""



