import os
import winreg
import subprocess
import platform

class GameManager:
    """
    游戏管理：路径检测、启动游戏
    """

    def auto_detect_paths(self):
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
        paths['user_data_path'] = self._detect_userdata_path()
        paths['game_config_path'] = os.path.join(paths['user_data_path'], 'Config') if paths['user_data_path'] else ''

        # 2. 检测 安装路径 (主要针对 Windows Steam)
        install_loc = self._detect_steam_install_path()
        
        # 3. 检测 安装路径
        if install_loc and os.path.exists(install_loc):
            paths['game_install_path'] = ''
            # 检测 可执行文件是否存在(多平台)
            if self.detect_executable(install_loc):
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
        if not any(paths.values()): return None
        
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
            if system_name == 'Darwin' and exe.endswith('.app') and os.path.exists(p):
                return p
            # 其他情况找文件
            if os.path.isfile(p):
                return p
        return None

    def launch_game(self, game_install_path, custom_args: list = []):
        """
        启动 RimWorld。
        :param custom_args: 启动参数列表，例如 ['-savedatafolder=D:/Profile1']
        """
        target_exe = self.detect_executable(game_install_path)
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

    def _detect_userdata_path(self):
        """检测 Config 文件夹位置 (%USERPROFILE%\Appdata\LocalLow\Ludeon Studios\RimWorld by Ludeon Studios)"""
        if platform.system() == 'Windows':
            user_profile = os.getenv('USERPROFILE')
            # 这里的 APPDATA 环境变量通常指向 Roaming，但 RimWorld 在 LocalLow
            # 所以最好手动拼 LocalLow
            if user_profile:
                base = os.path.join(user_profile, 'AppData', 'LocalLow')
                path = os.path.join(base, 'Ludeon Studios', 'RimWorld by Ludeon Studios')
                if os.path.exists(path):
                    return path
        elif platform.system() == 'Darwin':
            home = os.path.expanduser('~')
            path = os.path.join(home, 'Library', 'Application Support', 'RimWorld')
            if os.path.exists(path):
                return path
        else: # Linux
            home = os.path.expanduser('~')
            path = os.path.join(home, '.config', 'unity3d', 'Ludeon Studios', 'RimWorld by Ludeon Studios')
            if os.path.exists(path):
                return path
        return ''

    def _detect_steam_install_path(self):
        """通过 Windows 注册表查找 Steam 安装路径"""
        if platform.system() != 'Windows':
            return None
            
        # 常见注册表位置
        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 294100",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 294100"
        ]
        
        for key_path in keys:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    install_loc, _ = winreg.QueryValueEx(key, "InstallLocation")
                    if install_loc:
                        return install_loc
            except OSError:
                continue
        return None



