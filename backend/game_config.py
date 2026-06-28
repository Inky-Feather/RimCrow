# backend/game_config.py
import os
import shutil
import glob
import datetime
try:
    from backend.settings import SettingsManager
except ImportError:
    from settings import SettingsManager
from lxml import html

etree = html.etree
class ConfigManager:
    """
    执行复杂的备份策略：
    1. 当天：保留所有操作备份。
    2. 过去：只保留当天的最后一份。
    3. 过期：删除超过 30 天的备份（除了最后一份）。
    4. 兜底：永远保留最新的一份备份。
    """
    def __init__(self, config_path, backup_root="backups"):
        self.settings = SettingsManager()
        self.config_path = config_path # RimWorld Config 文件夹路径
        self.mods_config_file = os.path.join(config_path, "ModsConfig.xml")
        self.backup_root = backup_root
        self.today_dir = os.path.join(backup_root, "today")
        self.earlier_dir = os.path.join(backup_root, "earlier")
        self._ensure_dirs()
        self._rotate_backups() # 启动时执行归档轮换

    def _ensure_dirs(self):
        os.makedirs(self.today_dir, exist_ok=True)
        os.makedirs(self.earlier_dir, exist_ok=True)

    def _rotate_backups(self):
        """
        检查 today 文件夹，将不是“今天”的文件归档到 earlier。
        保留非今天日期的最后一份，删除其余。
        """
        today_str = datetime.date.today().strftime("%Y%m%d")
        
        # 获取 today 文件夹下所有 xml
        files = glob.glob(os.path.join(self.today_dir, "*.xml"))
        
        # 按日期分组文件的辅助字典 { "20231101": ["path1", "path2"] }
        files_by_date = {}
        
        for f in files:
            # 假设文件名格式 ModsConfig_YYYYMMDD_HHMMSS.xml
            basename = os.path.basename(f)
            try:
                # 提取 YYYYMMDD (索引 11到19)
                parts = basename.split('_')
                if len(parts) >= 2:
                    date_part = parts[1] # YYYYMMDD
                    if date_part != today_str: # 只处理旧文件
                        if date_part not in files_by_date:
                            files_by_date[date_part] = []
                        files_by_date[date_part].append(f)
            except:
                continue

        # 处理每一天
        for date_str, file_list in files_by_date.items():
            # 按文件名排序（包含时间，所以最后面的就是最晚的）
            file_list.sort()
            last_file = file_list[-1]
            
            # 移动最后一份到 earlier
            try:
                shutil.move(last_file, os.path.join(self.earlier_dir, os.path.basename(last_file)))
                print(f"Archive backup: {os.path.basename(last_file)} moved to earlier.")
            except Exception as e:
                print(f"Archive error: {e}")

            # 删除该日期的其他文件
            for f in file_list[:-1]:
                try:
                    os.remove(f)
                except:
                    pass

    def create_backup(self):
        """创建一个新的备份到 today 文件夹"""
        if not os.path.exists(self.mods_config_file):
            return
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"ModsConfig_{timestamp}.xml"
        dest = os.path.join(self.today_dir, backup_name)
        try:
            shutil.copy2(self.mods_config_file, dest)
            print(f"Backup created: {backup_name}")
        except Exception as e:
            print(f"Backup failed: {e}")

    def read_active_mods(self):
        """读取当前的 activeMods，返回列表"""
        if not os.path.exists(self.mods_config_file):
            return []
        
        active_list = []
        try:
            # 使用 recover=True 容错解析
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(self.mods_config_file, parser)
            root = tree.getroot()
            # 结构一般是 <ModsConfigData><activeMods><li>id</li>...</activeMods></ModsConfigData>
            active_mods_node = root.find("activeMods")
            if active_mods_node is not None:
                for li in active_mods_node.findall("li"):
                    if li.text:
                        # 统一转小写，因为 XML 中 ID 大小写可能不规范，但 ID 实际上不敏感
                        active_list.append(li.text.strip()) 
        except Exception as e:
            print(f"Error reading ModsConfig.xml: {e}")
        return active_list

    def save_active_mods(self, active_ids):
        """
        安全保存 Active 列表
        1. 备份
        2. 读取原文件结构
        3. 清空 activeMods 节点并重新填充
        4. 写入
        """
        self.create_backup()
        
        # 1. 尝试读取现有文件以保留 Version 信息
        current_version = self.settings.get('game_version','Unknow') # 默认兜底
        try:
            parser = etree.XMLParser(remove_blank_text=True)
            if os.path.exists(self.mods_config_file):
                tree = etree.parse(self.mods_config_file, parser)
                root = tree.getroot()
            else:
                # 如果文件不存在，创建基本骨架
                root = etree.Element("ModsConfigData")
                etree.SubElement(root, "version").text = current_version
                etree.SubElement(root, "activeMods")
                etree.SubElement(root, "knownExpansions")
                tree = etree.ElementTree(root)

            # 找到 activeMods 节点，没有则创建
            active_node = root.find("activeMods")
            if active_node is None:
                active_node = etree.SubElement(root, "activeMods")
            
            # 清空旧列表
            active_node.clear()
            
            print(active_ids)
            
            # 写入新列表
            for mod_id in active_ids:
                li = etree.SubElement(active_node, "li")
                li.text = mod_id # 注意：写入时可能需要恢复原始大小写，但RimWorld通常不敏感

            # 格式化写入
            tree.write(self.mods_config_file, pretty_print=True, xml_declaration=True, encoding="utf-8")
            print(f"Successfully saved {len(active_ids)} active mods.")
            return True
        except Exception as e:
            print(f"Error writing ModsConfig.xml: {e}")
            return False
        
        
if __name__ == "__main__":
    from settings import SettingsManager
    settings = SettingsManager()
    
    config_path = settings.get("game_config_path")
    print("配置路径:", config_path)
    
    if not (config_path and os.path.exists(config_path)):
        print("配置路径未设置或不存在。")
        exit(1)
    
    config_mgr = ConfigManager(config_path)
    active_mods = config_mgr.read_active_mods()
    
    # config_mgr.create_backup()
    
    print("Active Mods:", active_mods)
    # 修改 active mods 测试保存
    # if active_mods:
    #     active_mods = active_mods[::-1] # 反转列表作为测试
    #     config_mgr.save_active_mods(active_mods)