import winreg
import os
from pathlib import Path


class GameDetector:
    def __init__(self):
        # 推导 APPDATA 
        self.appdata_path = Path(os.getenv('APPDATA', Path.home())).parent
            
    '''用于检测 RimWorld 游戏及 Mod 路径的类'''
    def get_rimworld_paths(self):
        """
        尝试获取 RimWorld 的安装路径、本地 Mod 路径、工坊 Mod 路径
        返回: {'install': str, 'local_mods': str, 'workshop_mods': str} 或 None
        """
        try:
            # 打开注册表 HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 294100
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 294100"
            # 注意：如果是64位系统，Steam可能在WOW6432Node下，但在Python winreg中通常能自动处理或需要指定标志
            # 先尝试默认读取
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            except FileNotFoundError:
                # 尝试 WOW6432Node (针对64位系统上的32位程序)
                key_path = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 294100"
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)

            install_loc, _ = winreg.QueryValueEx(key, "InstallLocation")
            winreg.CloseKey(key)

            if install_loc and os.path.exists(install_loc):
                paths = {
                    "game_install_path": install_loc,
                    "local_mods_path": os.path.join(install_loc, "Mods"),
                    # 工坊路径通常在 steamapps/common/RimWorld 的上两级 steamapps/workshop/content/294100
                    "workshop_mods_path": os.path.abspath(os.path.join(install_loc, "../../workshop/content/294100")),
                    "game_config_path": str(self.appdata_path / 'LocalLow' / 'Ludeon Studios' / 'RimWorld by Ludeon Studios' / 'Config')
                }
                print(f"自动检测到 RimWorld 路径: {paths}")
                return paths
        except Exception as e:
            print(f"自动检测路径失败: {e}")
            return None

if __name__ == "__main__":
    detector = GameDetector()
    paths = detector.get_rimworld_paths()
    print("检测结果:", paths)