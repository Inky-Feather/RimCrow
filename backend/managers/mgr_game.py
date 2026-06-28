import os
import sys
import winreg
import subprocess
import platform
from pathlib import Path
from backend.settings import settings

class GameManager:
    """
    游戏管理：路径检测、启动游戏
    """

    def auto_detect_paths(self):
        """
        尝试自动检测 RimWorld 的关键路径。
        返回字典: {
            'game_install_path': str,
            'local_mods_path': str,
            'workshop_mods_path': str,
            'game_config_path': str
        }
        """
        paths = {
            'game_install_path': '',
            'game_data_path': '',
            'local_mods_path': '',
            'workshop_mods_path': '',
            'game_config_path': ''
        }
        
        # 1. 检测 Config 路径 (各平台固定)
        paths['game_data_path'] = self._detect_gamedata_path()
        paths['game_config_path'] = os.path.join(paths['game_data_path'], 'Config')

        # 2. 检测 安装路径 (主要针对 Windows Steam)
        install_loc = self._detect_steam_install_path()
        
        if install_loc and os.path.exists(install_loc):
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

        return paths

    def launch_game(self):
        """
        启动 RimWorld 可执行文件
        """
        install_path = settings.config.game_install_path
        if not install_path or not os.path.exists(install_path):
            return {"status": "error", "message": "游戏安装路径未配置或不存在"}

        # 寻找可执行文件
        target_exe = None
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
                target_exe = p
                break
            # 其他情况找文件
            if os.path.isfile(p):
                target_exe = p
                break
        
        if not target_exe:
             return {"status": "error", "message": f"在安装目录下找不到可执行文件: {candidates}"}

        try:
            # 非阻塞启动
            if system_name == 'Windows':
                # CREATE_NEW_CONSOLE 防止关闭管理器时游戏也被关闭
                subprocess.Popen([target_exe], cwd=install_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
            elif system_name == 'Darwin':
                subprocess.Popen(['open', target_exe])
            else:
                subprocess.Popen([target_exe], cwd=install_path)
                
            return {"status": "success", "message": "游戏启动指令已发送"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_game_version(self):
        """获取游戏版本号"""
        version_file = os.path.join(settings.config.game_install_path, 'Version.txt')
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

    def _detect_gamedata_path(self):
        """检测 Config 文件夹位置 (%APPDATA%/LocalLow/Ludeon Studios/...)"""
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