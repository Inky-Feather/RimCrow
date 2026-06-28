import json
import os

CONFIG_FILE = 'config.json'

DEFAULT_CONFIG = {
    "game_install_path": "",
    "local_mods_path": "",
    "workshop_mods_path": "",
    "game_config_path": "", # ModsConfig.xml 所在文件夹
    "game_version": "",
    "window_width": 1400,
    "window_height": 900,
    "backup_retention_days": 30, # 历史备份保留天数
}

class SettingsManager:
    '''管理应用程序设置的类，负责加载和保存配置文件'''
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config.update(data)
            except Exception as e:
                print(f"Error loading config: {e}")

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default="") -> str:
        return self.config.get(key) or default

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def update_paths(self, paths_dict):
        """一次性更新所有路径"""
        if paths_dict:
            self.config["game_install_path"] = paths_dict.get("game_install_path", "")
            self.config["local_mods_path"] = paths_dict.get("local_mods_path", "")
            self.config["workshop_mods_path"] = paths_dict.get("workshop_mods_path", "")
            self.config["game_config_path"] = paths_dict.get("game_config_path", "")
            self.save()