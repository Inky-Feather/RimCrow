import os
import shutil
import glob
import datetime
from backend.utils.logger import logger

# --- 模块测试准备 ---
if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Path(__file__).resolve() 获取当前文件的绝对路径
    # .parents[2] 表示向上跳 3 级 (文件->scanner->backend->项目根目录)
    project_root = Path(__file__).resolve().parents[2]
    # 调试打印，确保路径正确
    print(f"Project Root: {project_root}")
    # sys.path 需要字符串类型，所以要用 str() 转换一下
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from backend.managers.mgr_files import FileManager
from backend.settings import settings
from lxml import html
etree = html.etree

class LoadOrderManager:
    """
    负责管理 ModsConfig.xml (加载顺序)
    功能：读取当前激活列表、保存列表、自动备份
    1. 当天：保留所有操作备份。
    2. 过去：只保留当天的最后一份。
    3. 过期：删除超过 30 天的备份（除了最后一份）。
    4. 兜底：永远保留最新的一份备份。
    """
    
    def __init__(self):
        # 从全局配置获取路径
        self.config_dir = settings.config.game_config_path
        self.mods_config_file = ''
        
        if self.config_dir:
            self.mods_config_file = os.path.join(self.config_dir, "ModsConfig.xml")
            self._init_backup_dirs()

    def _init_backup_dirs(self):
        """初始化备份目录结构"""
        # 在软件目录下用 backups 文件夹存储备份
        self.backup_root = os.path.join(os.getcwd(), "backups")
        self.today_dir = os.path.join(self.backup_root, "today")
        self.earlier_dir = os.path.join(self.backup_root, "earlier")
        self.other_dir = os.path.join(self.backup_root, "other")
        
        # 创建目录
        os.makedirs(self.today_dir, exist_ok=True)
        os.makedirs(self.earlier_dir, exist_ok=True)
        os.makedirs(self.other_dir, exist_ok=True)
        
        # 每次初始化（应用启动）时执行一次轮换检查
        self._rotate_backups()

    def read_active_mods(self, mods_config_file_path=None):
        """
        读取当前的 activeMods 列表
        :return: [package_id, package_id, ...]
        """
        if not mods_config_file_path:
            mods_config_file_path = self.mods_config_file
        if not mods_config_file_path or not os.path.exists(mods_config_file_path):
            logger.warning(f"ModsConfig.xml not found: {mods_config_file_path}")
            return {
                'active_mods': [],
                'modify_time': 0
            }
        modify_time = int(os.path.getmtime(mods_config_file_path)*1000)
        active_list = []
        try:
            # 使用 recover=True 容错解析
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(mods_config_file_path, parser)
            root = tree.getroot()
            # 结构一般是 <ModsConfigData><activeMods><li>id</li>...</activeMods></ModsConfigData>
            active_node = root.xpath("//activeMods") or root.xpath("//modIds")
            # active_node = root.find("./activeMods") or root.find("./modIds")
            if active_node is None: logger.error("无法解析非标准 ModsConfig.xml 文件！")
            active_node = active_node[0]
            if active_node is not None:
                for li in active_node.findall("li"):
                    if li.text:
                        # 统一转小写，因为 XML 中 ID 大小写可能不规范，但 ID 实际上不敏感
                        active_list.append(li.text.strip().lower())
        except Exception as e:
            logger.error(f"读取 ModsConfig.xml 时出错: {e}")
            
        return {
            'active_mods': active_list,
            'modify_time': modify_time
        }

    def save_active_mods(self, active_ids, target_path=None, trigger_dialog=False):
        """
        保存加载顺序。
        :param active_ids: Mod ID 列表
        :param target_path: 指定保存路径（绝对路径）。如果不传，默认覆盖游戏配置。
        :param trigger_dialog: 是否触发系统弹窗让用户选择保存位置。
        """
        # 1. 确定最终写入路径
        write_path = self.mods_config_file
        
        if trigger_dialog:
            # 弹出对话框选择路径
            # 默认文件名带上时间戳或有意义的名字
            default_name = f"ModsConfig_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
            parent_dir = os.path.dirname(str(target_path))
            selected = FileManager.save_file_dialog(
                initial_dir=parent_dir or self.other_dir,
                default_filename=default_name,
            )
            logger.info(f"用户选择保存路径: {selected}")
            if not selected: return 
            write_path = selected
            
        elif target_path:
            # 指定了路径（用于恢复备份等内部逻辑）
            # 确保父目录存在
            parent_dir = os.path.dirname(target_path)
            if not os.path.exists(parent_dir):
                try:
                    os.makedirs(parent_dir)
                except OSError:
                    logger.error(f"无法创建目录: {parent_dir}")
                    raise Exception(f"无法创建目录: {parent_dir}")
            write_path = target_path

        if not write_path:
            raise Exception("未指定有效保存路径")

        # 2. 只有在覆盖默认配置时，才需要自动备份旧文件
        # 如果是另存为，没必要备份目标文件（通常目标文件不存在）
        if write_path == self.mods_config_file and os.path.exists(self.mods_config_file):
            self._create_backup()

        # 3. 准备 XML 结构 (逻辑保持不变)
        current_version = settings.config.game_version
        try:
            # 尝试保留原有的 knownExpansions 等信息
            parser = etree.XMLParser(remove_blank_text=True)
            if os.path.exists(self.mods_config_file):
                tree = etree.parse(self.mods_config_file, parser)
                root = tree.getroot()
            else:
                # 如果文件不存在，创建基本骨架
                root = etree.Element("ModsConfigData")
                # 尝试从 settings 获取版本，或者默认 Unknow
                ver = etree.SubElement(root, "version")
                ver.text = current_version # 这是一个兜底，理想情况应该读 Version.txt
                etree.SubElement(root, "activeMods")
                etree.SubElement(root, "knownExpansions")
                tree = etree.ElementTree(root)

            # 更新 activeMods 节点，没有则创建
            active_node = root.find("activeMods")
            if active_node is None:
                active_node = etree.SubElement(root, "activeMods")
            
            # 清空旧列表
            active_node.clear()
            
            # 写入新列表
            for mod_id in active_ids:
                li = etree.SubElement(active_node, "li")
                li.text = mod_id # 注意：写入时可能需要恢复原始大小写，但RimWorld通常不敏感

            # 4. 格式化写入
            tree.write(write_path, pretty_print=True, xml_declaration=True, encoding="utf-8")
            # 同步备份到 backup_root
            tree.write(os.path.join(self.backup_root, f'Latest_ModsConfig_{settings.config.current_profile_id}.xml'), pretty_print=True, xml_declaration=True, encoding="utf-8")
            logger.info(f"成功保存 {len(active_ids)} 个模组到: {write_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存 ModsConfig.xml 时出错：{e}")
            raise Exception(f"保存 ModsConfig.xml 时出错：{e}")

    def _create_backup(self):
        """创建当前时刻的备份"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ModsConfig_{timestamp}.xml"
        dest = os.path.join(self.today_dir, filename)
        try:
            shutil.copy2(self.mods_config_file, dest)
        except Exception as e:
            logger.error(f"Backup failed: {e}")

    def _rotate_backups(self):
        """
        备份轮换策略：
        - today 文件夹只保留"今天"的文件，过期的移入 earlier。
        - earlier 文件夹里，每一天只保留最后一份备份。
        - 清理超过 retention_days 的备份。
        """
        today_str = datetime.date.today().strftime("%Y%m%d")
        
        # 1. 移动过期的 today -> earlier
        files = glob.glob(os.path.join(self.today_dir, "*.xml"))
        # 按日期分组文件的辅助字典 { "20231101": ["path1", "path2"] }
        files_by_date = {}

        for f in files:
            basename = os.path.basename(f)
            # 解析文件名中的日期 ModsConfig_YYYYMMDD_HHMMSS.xml
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
        
        # 处理非今天的旧文件
        for date_str, file_list in files_by_date.items():
            # 按文件名排序（包含时间，所以最后面的就是最晚的）
            file_list.sort()
            # 保留最后一个，移入 earlier
            last_file = file_list[-1]
            try:
                shutil.move(last_file, os.path.join(self.earlier_dir, os.path.basename(last_file)))
            except: pass
            
            # 删除其余
            for f in file_list[:-1]:
                try: os.remove(f)
                except: pass

        # 2. 清理 earlier 中超过保留天数的文件
        # 假设保留天数在 settings 中
        retention_days = settings.config.backup_retention_days
        earlier_files = glob.glob(os.path.join(self.earlier_dir, "*.xml"))
        
        cutoff_date = datetime.date.today() - datetime.timedelta(days=retention_days)
        cutoff_str = cutoff_date.strftime("%Y%m%d")

        for f in earlier_files:
            basename = os.path.basename(f)
            try:
                parts = basename.split('_')
                if len(parts) >= 2:
                    date_part = parts[1]
                    if date_part < cutoff_str:
                        os.remove(f) # 过期删除
            except:
                pass
            
    def get_all_backups(self):
        """获取所有备份文件路径"""
        today_files = glob.glob(os.path.join(self.today_dir, "*.xml"))
        earlier_files = glob.glob(os.path.join(self.earlier_dir, "*.xml"))
        other_files = glob.glob(os.path.join(self.other_dir, "*.xml"))
        result = {
            "today": [{'path': f,'modify_time': int(os.path.getmtime(f)*1000) } for f in today_files],
            "earlier": [{'path': f,'modify_time': int(os.path.getmtime(f)*1000) } for f in earlier_files],
            "other": [{'path': f,'modify_time': int(os.path.getmtime(f)*1000) } for f in other_files]
        }
        return result



if __name__ == "__main__":
    mgr = LoadOrderManager()
    a = mgr.read_active_mods(r"C:\Users\Administrator\AppData\LocalLow\Ludeon Studios\RimWorld by Ludeon Studios\Saves\林亚.rws")
    print(a)