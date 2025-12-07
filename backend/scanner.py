import os
from webbrowser import get
from backend.thumbnail import ThumbnailManager
# from lxml import etree
from lxml import html

etree = html.etree

class ModScanner:
    '''扫描 RimWorld Mod 文件夹，提取 Mod 信息的类'''
    def __init__(self):
        self.thumb_mgr = ThumbnailManager() # 初始化
        
    def get_file_times(self, path):
        '''获取文件的创建和修改时间'''
        try:
            stats = os.stat(path)
            return stats.st_ctime, stats.st_mtime
        except:
            return 0, 0

    def parse_list(self, root, tag_name):
        """解析 XML 中的 <li>列表结构"""
        items = []
        node = root.find(tag_name)
        if node is not None:
            for li in node.findall('li'):
                if li.text:
                    items.append(li.text)
        return items

    def determine_mod_type(self, path):
        """根据路径判断 Mod 类型"""
        path = path.lower()
        if "workshop" in path: return "Workshop"
        if "mods" in path: return "Local"
        return "Other"

    def scan_folder_for_batch(self, root_path, existing_mtimes):
        """
        扫描并返回 Mod 数据列表，不操作数据库。
        :param existing_mtimes: 字典 {package_id: mtime}，用于快速跳过未修改的文件
        """
        mods_data = []
        if not os.path.exists(root_path):
            return []

        # 获取当前所有 Mod 文件夹
        try:
            folder_names = os.listdir(root_path)
        except Exception as e:
            print(f"Error accessing {root_path}: {e}")
            return []

        print(f"扫描器: 正在分析 {len(folder_names)} 个文件夹，从 {root_path}...")

        for folder_name in folder_names:
            mod_path = os.path.join(root_path, folder_name)
            about_xml = os.path.join(mod_path, 'About', 'About.xml')
            preview_path = os.path.join(mod_path, 'About', 'Preview.png')
            if not os.path.isfile(preview_path): preview_path = ""
                
            if not os.path.exists(about_xml):
                continue

            # 1. 检查文件修改时间 (增量更新核心)
            ctime, mtime = self.get_file_times(about_xml)
            
            # 这里我们需要解析 ID 才能比对 mtime，但为了极致速度，
            # 我们可以先尝试用文件夹名作为 key 猜一下？
            # 不，为了准确性，还是得解析 XML。但在 SSD 上解析 XML 极快，瓶颈在 DB。
            # 如果要极致优化，可以将 (path -> mtime) 存入数据库，而不只是 package_id。
            # 目前我们先全量解析 XML，但只批量写入 DB，这已经能达到秒级了。
            
            try:
                # 使用 lxml 的 iterparse 或直接 parse
                # 对于几百 KB 的小文件，直接 parse 没问题
                tree = etree.parse(about_xml)
                root = tree.getroot()
                
                # 辅助函数：安全获取文本
                def get_text(tag):
                    node = root.find(tag)
                    return node.text if node is not None else ""
                

                # 获取 packageId，作为唯一标识
                package_id = get_text('packageId').lower() or folder_name.lower()
                workshop_id = ""
                if 'workshop' in mod_path.lower() and folder_name.isdigit():
                    workshop_id = folder_name
                
                # 尝试生成缩略图
                if os.path.exists(preview_path):
                    self.thumb_mgr.ensure_thumbnail(package_id, preview_path)

                # 增量检查：如果 ID 存在且时间一致，跳过加入列表
                # 注意：existing_mtimes 是数据库里的 {id: time}
                if package_id in existing_mtimes:
                    if abs(existing_mtimes[package_id] - mtime) < 0.1: # 允许微小误差
                        continue 
                    
                
                
                # 组装数据
                mod_data = {
                    'package_id': package_id,
                    'workshop_id': workshop_id,
                    'name': get_text('name'),
                    'author': get_text('author'),
                    'description': get_text('description'),
                    'url': f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}" if workshop_id else get_text('url'),
                    'version': "Unknown", # XML 中通常没有标准 version 字段，有的放在 supportedVersions
                    'supported_versions': self.parse_list(root, 'supportedVersions'),
                    'dependencies': [], # 需要处理 modDependencies
                    'load_after': self.parse_list(root, 'loadAfter'),
                    'load_before': self.parse_list(root, 'loadBefore'),
                    'path': mod_path,
                    'preview_path': preview_path,
                    'mod_type': self.determine_mod_type(mod_path),
                    'file_created_time': ctime,
                    'file_modified_time': mtime,
                    'last_active_time': 0, # 这些需要保留原值，这里设0由 DB upsert 处理逻辑决定(需优化SQL)
                }

                # 依赖处理
                deps = []
                mod_deps = root.find('modDependencies')
                if mod_deps is not None:
                    for li in mod_deps.findall('li'):
                        d_id = li.find('packageId')
                        d_name = li.find('displayName') # 只有显示名没有ID的情况比较少见但存在
                        if d_id is not None and d_id.text:
                             deps.append({'packageId': d_id.text, 'displayName': d_name.text if d_name is not None else ""})
                mod_data['dependencies'] = deps

                mods_data.append(mod_data)

            except Exception as e:
                # 容错，跳过损坏的 XML
                print(f"Error parsing {about_xml}: {e}")
                pass

        return mods_data
    
    
