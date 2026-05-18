import os
import subprocess
import platform

try:
    import winreg
except ImportError:  # pragma: no cover - 仅在非 Windows 平台触发
    winreg = None

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
            if cls.detect_executable(install_loc):
                paths['game_install_path'] = install_loc
            
            # 推导 Local Mods
            local_mods = os.path.join(install_loc, "Mods")
            if os.path.exists(local_mods):
                paths['local_mods_path'] = local_mods
            
            # 推导 Workshop Mods
            # Steam 结构: steamapps/common/RimWorld -> steamapps/workshop/content/294100
            # 回退两级找到 workshop 目录
            workshop_base = os.path.abspath(os.path.join(install_loc, "../../workshop/content/294100"))
            if os.path.exists(workshop_base):
                paths['workshop_mods_path'] = workshop_base

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
    
    @staticmethod
    def _detect_steam_install_path():
        """
        检测各平台常见的 Steam 版 RimWorld 安装路径。

        注意这里只收口最常见默认位置，不递归扫描磁盘：
        - Windows 走 Steam App 注册表；
        - macOS / Linux 走 Steam 默认库目录；
        - 多 Steam Library / 自定义磁盘库仍交给用户手动指定。
        """
        system_name = platform.system()
        candidate_paths = []

        if system_name == 'Windows':
            if winreg is None:
                return None
            keys = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 294100",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 294100"
            ]
            for key_path in keys:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                        install_loc, _ = winreg.QueryValueEx(key, "InstallLocation")
                        if install_loc:
                            candidate_paths.append(install_loc)
                except OSError:
                    continue
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

        for install_loc in candidate_paths:
            if install_loc and os.path.exists(install_loc):
                return install_loc
        return None



