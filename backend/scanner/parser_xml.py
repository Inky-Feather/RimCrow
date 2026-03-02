import os
import re
from typing import TypedDict, Set, Dict, List
from lxml import html
from collections import defaultdict

etree = html.etree

class RelationEntry(TypedDict):
    package_id: str
    version_requirement: Set[str]
    alternatives: List[str]     # 新增：备选包名列表
    is_force: bool

class ModXMLParser:
    """
    解析 Mod 相关的 XML 文件 (About, Manifest, ModSync)
    提取元数据，包括依赖、冲突、存档兼容性等。
    元数据包括依赖、冲突、存档兼容性等。主要负责提取 Mod 的元数据，如 packageId, name, author, version, description 等。
    26-2-19：适配 RimWorld 1.6 规范，支持合并版本限定、强制加载及备用包名。
    返回的元数据字典包含以下字段：
        - package_id: 模组的唯一标识符
        - package_id_raw: 原始包名，保持大小写
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
        - save_breaking: 是否破坏存档 (True: 破坏, None: 未知, False: 不破坏)
    """

    def parse(self, mod_path):
        """
        主解析入口。
        返回提取到的元数据字典，所有列表字段默认为空列表。
        """
        # 初始化数据结构
        data = {
            # --- 基础信息 ---
            "package_id": "",
            "package_id_raw": "",
            "name": "",
            "author": ["Unknown"],
            "version": "",
            "description": "",
            "descriptions_by_version": {},  # 按版本的描述 {'1.4': '...', '1.5': '...'}
            "url": "",
            
            # --- 核心逻辑列表 (对应 xml_metadata) ---
            "supported_versions": [],
            # 格式: [{ "package_id": "xxx", "version_requirement": ["all"|"1.5"], "is_force": False, ... }]
            "dependencies_mods": [],      # 依赖 Mod
            "load_after_mods": [],        # 必须在这些 Mod 之后加载
            "load_before_mods": [],       # 必须在这些 Mod 之前加载
            "incompatible_mods": [],      # 与这些 Mod 不兼容
            
            # --- 附加信息 ---
            "icon_path": "",     # 1.5+ 自定义图标路径
            "save_breaking": None,  # 是否破坏存档 (ModSync)，True: 破坏, None：未知, False: 不破坏
        }

        about_path = os.path.join(mod_path, "About", "About.xml")
        manifest_path = os.path.join(mod_path, "About", "Manifest.xml")
        modsync_path = os.path.join(mod_path, "About", "ModSync.xml")

        # 1. 优先解析 About.xml (官方标准)
        if os.path.exists(about_path):
            self._parse_about(about_path, data)

        # 2. 补充解析 Manifest.xml (旧版本号、依赖补充)
        if os.path.exists(manifest_path):
            self._parse_manifest(manifest_path, data)

        # 3. 补充解析 ModSync.xml (版本号、SaveBreaking)
        if os.path.exists(modsync_path):
            self._parse_modsync(modsync_path, data)
            

        # package_id 去除首尾空格
        # todo ： 当前的 package_id 全部转换为小写，后续需要根据实际情况处理，可能需要保留原始格式
        if data["package_id"]:
            data["package_id"] = data["package_id"].strip().lower()
        
        # 处理 icon_path 相对路径
        if data["icon_path"]:
            # 规范化分隔符
            data["icon_path"] = data["icon_path"].replace("\\", "/")

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
            for li in node.findall("li"):
                if li.text and li.text.strip():
                    text = li.text.strip().lower() if if_lower else li.text.strip()
                    if text=="core": li.text = "ludeon.rimworld" # 补充：有的Mod依赖于Core，但没有写标准包名
                    items.append(text)
        return items

    def _extract_version_from_tag(self, tag_name) -> str:
        """从 <v1.5> 这种标签中提取版本号 1.5"""
        if tag_name.startswith("v"):
            return tag_name[1:]
        return tag_name

    # --- 核心：统一合并逻辑 ---

    def _merge_relations(self, root, tags_config):
        """
        通用的关系合并函数。
        tags_config: list of tuples -> (xml_tag, version_str, is_force)
        例如: [("loadBefore", "all", False), ("forceLoadBefore", "all", True), ("loadBeforeByVersion", "BY_TAG", False)]
        """
        # 使用字典进行去重合并: { package_id: { data... } }
        merged_map: Dict[str, RelationEntry] = defaultdict(lambda: {
            "package_id": "", 
            "version_requirement": set(), 
            "alternatives": [],   # 保证永远有一个空列表兜底
            "is_force": False
        })

        for xml_tag, version_type, is_force_flag in tags_config:
            node = root.find(xml_tag)
            if node is None: continue

            # 情况A: 按版本号嵌套 (ByVersion)
            if version_type == "BY_TAG":
                for ver_node in node:
                    # 提取版本号 <v1.6> -> 1.6
                    ver_str = self._extract_version_from_tag(ver_node.tag)
                    # 遍历内部 li
                    for li in ver_node.findall("li"):
                        pid = li.text.strip() if li.text else None
                        if not pid: continue
                        if pid == "core": pid = "ludeon.rimworld"   # 补充：有的Mod依赖于Core，但没有写标准包名
                        
                        entry = merged_map[pid]
                        entry["package_id"] = pid.lower()
                        entry["version_requirement"].add(ver_str)
                        if is_force_flag: entry["is_force"] = True

            # 情况B: 普通列表 (li string)
            else:
                for li in node.findall("li"):
                    pid = li.text.strip().lower() if li.text else None
                    if not pid: continue
                    if pid == "core": pid = "ludeon.rimworld"
                    
                    entry = merged_map[pid]
                    entry["package_id"] = pid
                    entry["version_requirement"].add(version_type) # "all"
                    if is_force_flag: entry["is_force"] = True

        # 转换为最终列表
        result_list = []
        for pid, data in merged_map.items():
            versions = data["version_requirement"]
            # 策略：如果包含 "all"，则忽略其他特定版本
            if "all" in versions:
                final_versions = ["all"]
            else:
                final_versions = sorted(list(versions))
            
            item = {
                "package_id": pid,
                "version_requirement": final_versions,
                "alternatives": data["alternatives"],
                "is_force": data["is_force"]
            }
            
            result_list.append(item)
        
        return result_list

    def _parse_dependencies(self, root):
        """解析依赖项，包含 1.6 的 alternativePackageIds 和 ByVersion"""
        # 结构: { package_id: { ...data... } }
        merged_deps = {}

        def process_dep_node(li_node, version_str):
            # 获取包名
            pid_node = li_node.find("packageId")
            if pid_node is None or not pid_node.text: return
            pid = pid_node.text.strip().lower()
            if pid == "core": pid = "ludeon.rimworld"   # 补充：有的Mod依赖于Core，但没有写标准包名
            
            if pid not in merged_deps:
                merged_deps[pid] = {
                    "package_id": pid,
                    "display_name": self._get_text(li_node, "displayName"),
                    "workshop_url": self._get_text(li_node, "steamWorkshopUrl").replace("steam://url/CommunityFilePage/", "https://steamcommunity.com/sharedfiles/filedetails/?id="),
                    "download_url": self._get_text(li_node, "downloadUrl"),
                    "alternatives": [],
                    "is_force": True, # 依赖项天然是强约束
                    "version_requirement": set()
                }
            
            # 添加版本
            merged_deps[pid]["version_requirement"].add(version_str)

            # 解析 1.6+ alternativePackageIds
            # 注意：IgnoreIfNoMatchingField 属性不需要在 python 处理，lxml 会直接读到标签
            alts_node = li_node.find("alternativePackageIds")
            if alts_node is not None:
                for alt_li in alts_node.findall("li"):
                    if alt_li.text:
                        alt_id = alt_li.text.strip().lower()
                        if alt_id not in merged_deps[pid]["alternatives"]:
                            merged_deps[pid]["alternatives"].append(alt_id)

        # 1. 通用依赖 <modDependencies>
        deps_node = root.find("modDependencies")
        if deps_node is not None:
            for li in deps_node.findall("li"):
                process_dep_node(li, "all")

        # 2. 版本依赖 <modDependenciesByVersion>
        deps_ver_node = root.find("modDependenciesByVersion")
        if deps_ver_node is not None:
            for ver_node in deps_ver_node:
                ver_str = self._extract_version_from_tag(ver_node.tag)
                for li in ver_node.findall("li"):
                    process_dep_node(li, ver_str)

        # 格式化输出
        final_deps = []
        for pid, data in merged_deps.items():
            versions = data["version_requirement"]
            data["version_requirement"] = ["all"] if "all" in versions else sorted(list(versions))
            final_deps.append(data)
        
        return final_deps

    # --- 各文件解析逻辑 ---

    def _parse_about(self, path, data):
        """解析 about.xml 文件"""
        try:
            tree = etree.parse(path, etree.XMLParser(recover=True)) # recover=True 忽略小错误
            root = tree.getroot()

            # 基础文本
            data["package_id"] = self._get_text(root, "packageId", data["package_id"])
            data["package_id_raw"] = self._get_text(root, "packageId", data["package_id"]).strip()
            data["name"] = self._get_text(root, "name", data["name"])
            data["description"] = self._get_text(root, "description", data["description"])
            data["url"] = self._get_text(root, "url", data["url"])
            
            # 版本号：优先读取 modVersion (1.4+ 标准)
            data["version"] = self._get_text(root, "modVersion", data["version"])

            # 图标路径 (1.5+ 新特性)
            data["icon_path"] = self._get_text(root, "modIconPath", "")
            author = self._get_text(root, "author", "Unknown")
            author_clean = re.split(r"\s*[,;\|&，、\+]\s*", author.strip())
            data["author"] = [name.strip() for name in author_clean if name.strip()]
            # 这里有个坑：authors (复数) 和 author (单数)
            if data["author"] == ["Unknown"]:
                authors_node = root.find("authors")
                if authors_node is not None:
                    authors_list = [li.text for li in authors_node.findall("li") if li.text]
                    if authors_list: data["author"] = authors_list

            # XML结构: <descriptionsByVersion><v1.4>...</v1.4><v1.5>...</v1.5></descriptionsByVersion>
            desc_ver_node = root.find('descriptionsByVersion')
            if desc_ver_node is not None:
                for child in desc_ver_node:
                    # child.tag 通常是 "v1.5", "v1.4" 等，复用 _extract_version_from_tag 去掉 'v'
                    ver_str = self._extract_version_from_tag(child.tag)
                    if child.text and child.text.strip():
                        data['descriptions_by_version'][ver_str] = child.text.strip()

            # 列表数据
            data["supported_versions"] = self._get_list(root, "supportedVersions")
            #data["load_after_mods"] = self._get_list(root, "loadAfter")
            #data["load_before_mods"] = self._get_list(root, "loadBefore")
            
            # 不兼容列表
            #data["incompatible_mods"] = self._get_list(root, "incompatibleWith")
            # 解析 SaveBreaking
            # 通常是 <SaveBreaking>True</SaveBreaking>
            sb_text = self._get_text(root, "SaveBreaking").lower()
            temp_dict = {"true": True, "false": False}    # 是否破坏存档，True: 破坏, None：未知, False: 不破坏
            data["save_breaking"] = temp_dict.get(sb_text, None)

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
            # 1. Load Before (含 force 和 ByVersion)
            data["load_before_mods"] = self._merge_relations(root, [
                ("loadBefore", "all", False),
                ("forceLoadBefore", "all", True),
                ("loadBeforeByVersion", "BY_TAG", False)
            ])

            # 2. Load After (含 force 和 ByVersion)
            data["load_after_mods"] = self._merge_relations(root, [
                ("loadAfter", "all", False),
                ("forceLoadAfter", "all", True),
                ("loadAfterByVersion", "BY_TAG", False)
            ])

            # 3. Incompatible (含 ByVersion)
            data["incompatible_mods"] = self._merge_relations(root, [
                ("incompatibleWith", "all", False),
                ("incompatibleWithByVersion", "BY_TAG", False)
            ])

            # 4. Dependencies (含 alternative 和 ByVersion)
            data["dependencies_mods"] = self._parse_dependencies(root)

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
            if not data["version"]:
                data["version"] = self._get_text(root, "version", "")

            # 补充不兼容列表 (如果 About.xml 里没写，这里可能有)
            if not data["incompatible_mods"]:
                # Manifest 中的标签可能叫 <incompatibleWith> (同 About)
                raw_list = self._get_list(root, "incompatibleWith")
                if raw_list:
                    # 转换为新结构
                    data["incompatible_mods"] = [
                        {"package_id": pid.lower(), "version_requirement": ["all"]} 
                        for pid in raw_list
                    ]
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
            if not data["version"]:
                data["version"] = self._get_text(root, "Version", "")
            
            # 【新】解析 SaveBreaking
            # 通常是 <SaveBreaking>True</SaveBreaking>
            sb_text = self._get_text(root, "SaveBreaking")
            if sb_text.lower() == "true":
                data["save_breaking"] = True
            elif sb_text.lower() == "false":
                data["save_breaking"] = False
            else:
                data["save_breaking"] = None
                
        except Exception:
            pass
        
        
if __name__ == "__main__":
    parser = ModXMLParser()
    # mod_path = r"E:\SteamLibrary\steamapps\workshop\content\294100\3153539856"
    mod_path = r"E:\SteamLibrary\steamapps\workshop\content\294100\3210544395"
    data = parser.parse(mod_path)
    print(data)