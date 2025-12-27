import os
import re
from lxml import html

etree = html.etree
class ModXMLParser:
    """
    解析 Mod 相关的 XML 文件 (About, Manifest, ModSync)
    提取元数据，包括依赖、冲突、存档兼容性等。
    元数据包括依赖、冲突、存档兼容性等。主要负责提取 Mod 的元数据，如 packageId, name, author, version, description 等。
    返回的元数据字典包含以下字段：
        - package_id: 模组的唯一标识符
        - name: 模组名称
        - author: 模组作者
        - version: 模组版本号
        - description: 模组描述
        - url: 模组主页 URL
        - supported_versions: 支持的 RimWorld 版本列表
        - dependencies_mods: 依赖的其他模组列表
        - load_after_mods: 必须在这些模组后加载
        - load_before_mods: 必须在这些模组前加载
        - incompatible_mods: 与这些模组不兼容的列表
        - icon_path: 模组图标路径
        - save_breaking: 是否破坏存档 (-1: 破坏, 0: 未知, 1: 不破坏)
    """

    def parse(self, mod_path):
        """
        主解析入口。
        返回提取到的元数据字典，所有列表字段默认为空列表。
        """
        # 初始化数据结构
        data = {
            # --- 基础信息 ---
            'package_id': '',
            'name': '',
            'author': ['Unknown'],
            'version': '',
            'description': '',
            'url': '',
            
            # --- 核心逻辑列表 (对应 xml_metadata) ---
            'supported_versions': [],
            'dependencies_mods': [],      # 依赖 Mod
            'load_after_mods': [],        # 必须在这些 Mod 之后加载
            'load_before_mods': [],       # 必须在这些 Mod 之前加载
            'incompatible_mods': [], # 与这些 Mod 不兼容 (重要!)
            
            # --- 附加信息 ---
            'icon_path': '',     # 1.5+ 自定义图标路径
            'save_breaking': 0,  # 是否破坏存档 (ModSync)，-1: 破坏, 0：未知, 1: 不破坏
        }

        about_path = os.path.join(mod_path, 'About', 'About.xml')
        manifest_path = os.path.join(mod_path, 'About', 'Manifest.xml')
        modsync_path = os.path.join(mod_path, 'About', 'ModSync.xml')

        # 1. 优先解析 About.xml (官方标准)
        if os.path.exists(about_path):
            self._parse_about(about_path, data)

        # 2. 补充解析 Manifest.xml (旧版本号、依赖补充)
        if os.path.exists(manifest_path):
            self._parse_manifest(manifest_path, data)

        # 3. 补充解析 ModSync.xml (版本号、SaveBreaking)
        if os.path.exists(modsync_path):
            self._parse_modsync(modsync_path, data)
            

        # 数据清洗：确保 package_id 全小写 (RimWorld 内部逻辑不区分大小写)
        if data['package_id']:
            data['package_id'] = data['package_id'].lower()
        
        # 处理 icon_path 相对路径
        if data['icon_path']:
             # 规范化分隔符
            data['icon_path'] = data['icon_path'].replace('\\', '/')

        return data

    # --- 辅助方法 ---

    def _get_text(self, root, tag, default=""):
        """安全获取标签文本"""
        node = root.find(tag)
        return node.text.strip() if node is not None and node.text else default

    def _get_list(self, root, tag, if_lower=True):
        """解析简单的 <li>string</li> 列表"""
        items = []
        node = root.find(tag)
        if node is not None:
            for li in node.findall('li'):
                # 补充：有的Mod依赖于Core，但没有写标准包名
                if li.text and li.text.strip():
                    text = li.text.strip().lower() if if_lower else li.text.strip()
                    if text=='core':
                        li.text = 'ludeon.rimworld' # 补充：有的Mod依赖于Core，但没有写标准包名
                    items.append(text)
        return items

    # --- 各文件解析逻辑 ---

    def _parse_about(self, path, data):
        try:
            tree = etree.parse(path, etree.XMLParser(recover=True)) # recover=True 忽略小错误
            root = tree.getroot()

            # 基础文本
            data['package_id'] = self._get_text(root, 'packageId', data['package_id'])
            data['name'] = self._get_text(root, 'name', data['name'])
            author = self._get_text(root, 'author', 'Unknown')
            author_clean = re.split(r'[,;|&，、]', author.strip())
            data['author'] = [name.strip() for name in author_clean if name.strip()]
            # 这里有个坑：authors (复数) 和 author (单数)
            if data['author'] == ['Unknown']:
                authors_node = root.find('authors')
                if authors_node is not None:
                    authors_list = [li.text for li in authors_node.findall('li') if li.text]
                    if authors_list: data['author'] = authors_list

            data['description'] = self._get_text(root, 'description', data['description'])
            data['url'] = self._get_text(root, 'url', data['url'])
            
            # 版本号：优先读取 modVersion (1.4+ 标准)
            data['version'] = self._get_text(root, 'modVersion', data['version'])

            # 图标路径 (1.5+ 新特性)
            data['icon_path'] = self._get_text(root, 'modIconPath', '')

            # 列表数据
            data['supported_versions'] = self._get_list(root, 'supportedVersions')
            data['load_after_mods'] = self._get_list(root, 'loadAfter')
            data['load_before_mods'] = self._get_list(root, 'loadBefore')
            
            # 【新】不兼容列表
            data['incompatible_mods'] = self._get_list(root, 'incompatibleWith')
            # 【新】解析 SaveBreaking
            # 通常是 <SaveBreaking>True</SaveBreaking>
            sb_text = self._get_text(root, 'SaveBreaking').lower()
            temp_dict = {'true': -1, 'false': 1}    # 是否破坏存档，-1: 破坏, 0：未知, 1: 不破坏
            data['save_breaking'] = temp_dict.get(sb_text, 0)

            # 依赖解析 (结构较为复杂)
            # 格式：
            # <modDependencies>
            #   <li>
            #     <packageId>brrainz.harmony</packageId>
            #     <displayName>Harmony</displayName>
            #     <steamWorkshopUrl>...</steamWorkshopUrl>
            #     <downloadUrl>...</downloadUrl>
            #   </li>
            # </modDependencies>
            deps_node = root.find('modDependencies')
            if deps_node is not None:
                for li in deps_node.findall('li'):
                    pkg_id = self._get_text(li, 'packageId')
                    if pkg_id:
                        dep_item = {
                            'package_id': pkg_id.lower(),
                            'display_name': self._get_text(li, 'displayName'),
                            'workshop_url': self._get_text(li, 'steamWorkshopUrl').replace('steam://url/CommunityFilePage/', 'https://steamcommunity.com/sharedfiles/filedetails/?id='),
                            'download_url': self._get_text(li, 'downloadUrl')
                        }
                        data['dependencies_mods'].append(dep_item)

        except Exception as e:
            print(f"XML Parse Error (About) {path}: {e}")

    def _parse_manifest(self, path, data):
        """
        Manifest.xml 是老牌 Mod 管理器用的，包含一些 About.xml 没有的信息。
        """
        try:
            tree = etree.parse(path, etree.XMLParser(recover=True))
            root = tree.getroot()
            
            # 补充版本号
            if not data['version']:
                data['version'] = self._get_text(root, 'version', '')

            # 补充不兼容列表 (如果 About.xml 里没写，这里可能有)
            if not data['incompatible_mods']:
                # Manifest 中的标签可能叫 <incompatibleWith> (同 About)
                manifest_incompat = self._get_list(root, 'incompatibleWith')
                if manifest_incompat:
                    data['incompatible_mods'] = manifest_incompat

        except Exception:
            pass

    def _parse_modsync(self, path, data):
        """
        ModSync.xml 主要用于版本检查，但含有 SaveBreaking 信息。
        """
        try:
            tree = etree.parse(path, etree.XMLParser(recover=True))
            root = tree.getroot()
            
            # 补充版本号
            if not data['version']:
                data['version'] = self._get_text(root, 'Version', '')
            
            # 【新】解析 SaveBreaking
            # 通常是 <SaveBreaking>True</SaveBreaking>
            sb_text = self._get_text(root, 'SaveBreaking')
            if sb_text.lower() == 'true':
                data['save_breaking'] = -1
            elif sb_text.lower() == 'false':
                data['save_breaking'] = 1
                
        except Exception:
            pass
        
        
if __name__ == '__main__':
    parser = ModXMLParser()
    mod_path = r'E:\SteamLibrary\steamapps\workshop\content\294100\3030499331'
    data = parser.parse(mod_path)
    print(data)