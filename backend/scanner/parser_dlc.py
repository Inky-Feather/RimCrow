import os
import tarfile
import json
import glob
from backend.utils.logger import logger
import xml.etree.ElementTree as ET  # <-- 使用标准库
from backend.settings import CACHE_DIR

# --- 模块测试准备 ---
if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Path(__file__).resolve() 获取当前文件的绝对路径
    # .parents[2] 表示向上跳 3 级 (文件->scanner->backend->项目根目录)
    project_root = Path(__file__).resolve().parents[2]
    # 调试打印，确保路径对不对
    print(f"Project Root: {project_root}")
    # sys.path 需要字符串类型，所以要用 str() 转换一下
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
from backend.utils.constants import normalize_language_code


CACHE_FILE = os.path.join(CACHE_DIR, 'dlc_i18n_all.json')

class DLCParser:
    """
    RimWorld DLC 解析器 (全量缓存版)。
    自动扫描 Core/Languages 下所有 tar 包，维护一个全语言的翻译缓存。
    """

    def __init__(self, game_dlc_path):
        """
        初始化时即完成缓存同步。
        """
        self.data_path = game_dlc_path
        self.core_path = os.path.join(game_dlc_path, 'Core')
        self.languages_dir = os.path.join(self.core_path, 'Languages')
        
        # 1. 加载官方基础定义 (英文)
        self.official_defs = self._load_official_defs()
        
        # 2. 同步并加载翻译缓存 (核心逻辑)
# self.translations 结构: { 'zh-CN': {'Royalty': {...}}, 'fr': {...} }
        self.translations = self._sync_cache()
        self._translate_cache = {}

    def translate_record(self, mod_record, target_lang_code):
        """
        根据目标语言代码，即时翻译 Mod 记录。
        """
        # 初步筛选
        pkg_id = mod_record.get('package_id', '').lower()
        cached_trans = self._translate_cache.get(pkg_id)
        if cached_trans: return cached_trans
        
        if mod_record.get('source') != 'dlc' and 'ludeon.rimworld' not in pkg_id: return mod_record

        # 确定 DLC Key (Core, Royalty, Ideology...)
        def_key = None
        if pkg_id == 'ludeon.rimworld':  def_key = 'Core'    # Core 特殊处理
        elif pkg_id.startswith('ludeon.rimworld.'):
            # ludeon.rimworld.royalty -> Royalty (首字母大写)
            def_key = pkg_id.split('.')[-1].capitalize()
        
        if not def_key: return mod_record

        # 1. 先应用官方英文 (作为底板)
        if def_key in self.official_defs:
            official = self.official_defs[def_key]
            mod_record['name'] = official.get('label', mod_record['name'])
            mod_record['description'] = official.get('description', mod_record['description'])

        # 2. 再应用目标语言翻译 (覆盖)
        # 归一化语言代码 (zh-CN / ChineseSimplified -> zh-CN)
        lang_key = self._resolve_lang_key(target_lang_code)
        
        if lang_key in self.translations:
            lang_data = self.translations[lang_key]
            if def_key in lang_data:
                trans = lang_data[def_key]
                if trans.get('label'):
                    mod_record['name'] = trans['label']
                if trans.get('description'):
                    mod_record['description'] = trans['description']

        self._translate_cache[pkg_id] = mod_record
        return mod_record

    def enrich_data(self, mod_data, mod_path):
        
        """
        接收现有的 mod_data，注入官方定义。
        """
        folder_name = os.path.basename(mod_path)
        
        # 1. 强制修正一些 DLC 特有的元数据
        mod_data['source'] = 'dlc'
        mod_data['url'] = f"https://rimworldgame.com/{folder_name.lower()}"
        
        # Core 特殊处理：About.xml 里的名字通常就是 Core，但包名是 ludeon.rimworld
        if folder_name.lower() == 'core':
            # 确保 Core 的 ID 正确（防止 About.xml 有误）
            mod_data['package_id'] = "ludeon.rimworld"
            mod_data['package_id_raw'] = "Ludeon.RimWorld"
            mod_data['url'] = "https://rimworldgame.com"
            mod_data['source'] = 'core'
        # 2. 匹配官方定义 (ExpansionDefs)
        # 官方的 Key 通常就是文件夹名 (Core, Royalty, Ideology...)
        def_key = folder_name 
        
        # 3. 尝试获取官方定义
        # 优先级：官方英文定义 > About.xml 原有内容
        
        label = None
        desc = None
        
        # 找官方定义 (通常是英文)
        if def_key in self.official_defs:
            label = self.official_defs[def_key].get('label')
        
        if def_key in self.official_defs:
            desc = self.official_defs[def_key].get('description')

        # 4. 应用修改
        if label:
            mod_data['name'] = label
        if desc:
            mod_data['description'] = desc
            
        return mod_data

    # =========================================================================
    #  核心缓存同步逻辑
    # =========================================================================

    def _sync_cache(self):
        """
        检查所有 tar 文件，增量更新缓存。
        """
        if not os.path.exists(self.languages_dir): return {}

        # 1. 读取旧缓存
        cache_data = {'translations': {}, 'meta': {}}
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    cache_data = loaded
            except Exception:
                logger.info("[DLCParser] 缓存已损坏，正在全部重建。")

        current_trans = {}
        current_meta = cache_data.get('meta', {}) # 记录文件名对应的时间戳
        
        is_dirty = False
        for lang_key, translations in (cache_data.get('translations', {}) or {}).items():
            normalized_key = normalize_language_code(lang_key)
            if not normalized_key:
                continue
            if normalized_key != lang_key:
                is_dirty = True
            if normalized_key not in current_trans:
                current_trans[normalized_key] = {}
            if isinstance(translations, dict):
                current_trans[normalized_key].update(translations)

        # 2. 扫描磁盘上的所有 tar 文件
        tar_files = glob.glob(os.path.join(self.languages_dir, "*.tar"))
        found_filenames = set()

        for tar_path in tar_files:
            filename = os.path.basename(tar_path)
            found_filenames.add(filename)
            
            try:
                mtime = os.path.getmtime(tar_path)
            except OSError:
                continue

            # 3. 检查是否需要更新 (新文件 OR 修改过的文件)
            # 记录的时间戳不一致，或者缓存里根本没有这个语言的数据
            lang_code = self._filename_to_lang_code(filename)
            
            if (filename not in current_meta) or \
               (abs(current_meta[filename] - mtime) > 1.0) or \
               (lang_code not in current_trans):
                
                logger.info(f"[DLCParser] 正在更新缓存：{filename}")
                # 解析该文件
                trans_map = self._extract_translations_from_tar(tar_path)
                
                # 更新内存数据
                current_trans[lang_code] = trans_map
                current_meta[filename] = mtime
                is_dirty = True

        # 4. 清理已删除的文件 (磁盘上没了，但缓存里还有)
        # 注意：如果多个文件映射到同一个 lang_code (罕见)，删除逻辑要小心。
        # 这里简化处理：如果 meta 里的 filename 在磁盘找不到了，就尝试清理。
        existing_filenames_in_meta = list(current_meta.keys())
        for fname in existing_filenames_in_meta:
            if fname not in found_filenames:
                logger.info(f"[DLCParser] 正在移除过期缓存：{fname}")
                del current_meta[fname]
                # 尝试移除对应的翻译数据 (可能比较困难，因为 key 转换了)
                # 简单做法：如果是清理，因为这一步比较少见，不处理 trans 里的残留脏数据也不会崩，
                # 下次全量重建自然没了。或者可以反向存一个 mapping。
                is_dirty = True

        cache_data['translations'] = current_trans
        cache_data['meta'] = current_meta

        # 5. 如果有变动，写入磁盘
        if is_dirty:
            self._save_cache(cache_data)

        return current_trans

    def _save_cache(self, data):
        if not os.path.exists(CACHE_DIR):
            os.makedirs(CACHE_DIR, exist_ok=True)
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[DLCParser] 保存缓存失败：{e}")

    # =========================================================================
    #  辅助工具方法
    # =========================================================================

    def _filename_to_lang_code(self, filename):
        """
        从文件名映射到 ISO 语言代码。
        ChineseSimplified.tar -> zh-CN
        French (Fr).tar -> fr
        """
        # 去掉 .tar
        name_no_ext = os.path.splitext(filename)[0]
        # 取空格前缀: "ChineseSimplified (简体中文)" -> "ChineseSimplified"
        prefix = name_no_ext.split(' ')[0].strip()
        
        return normalize_language_code(prefix)

    def _resolve_lang_key(self, input_code):
        """
        将输入的 code (可能是 zh-CN，也可能是 ChineseSimplified) 统一为缓存里的 key
        """
        return normalize_language_code(input_code)

    def _load_official_defs(self):
        """读取 Core 的 ExpansionDefs (英文原版)"""
        defs = {}
        xml_path = os.path.join(self.core_path, 'Defs', 'Misc', 'ExpansionDefs', 'ExpansionDefs.xml')
        if not os.path.exists(xml_path): return defs

        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            for node in root.findall('ExpansionDef'):
                def_name = node.findtext('defName')
                if def_name:
                    defs[def_name] = {
                        'label': node.findtext('label'),
                        'description': node.findtext('description')
                    }
        except Exception: 
            logger.error(f"[DLCParser] 解析失败：{xml_path}")
        return defs

    def _extract_translations_from_tar(self, tar_path):
        """解析单个 tar 包"""
        trans_map = {} # { 'Royalty': {label: ...}, 'Core': ... }
        try:
            with tarfile.open(tar_path, "r") as tar:
                for member in tar.getmembers():
                    if member.isfile() and \
                       'DefInjected' in member.name and \
                       'ExpansionDef' in member.name and \
                       member.name.endswith('.xml'):
                        
                        f = tar.extractfile(member)
                        if f:
                            self._parse_translation_xml(f.read(), trans_map)
        except Exception as e:
            logger.error(f"[DLCParser] 解压失败：{tar_path}，错误：{e}")
        return trans_map

    def _parse_translation_xml(self, xml_bytes, trans_map):
        # logger.info(f"[DLCParser] Parsing XML with {len(xml_bytes)} bytes")
        try:
            if isinstance(xml_bytes, bytes):
                # 尝试检测编码，或者默认 utf-8
                xml_str = xml_bytes.decode('utf-8', errors='replace')
            else:
                xml_str = xml_bytes
            root = ET.fromstring(xml_str)
            for child in root:
                tag = child.tag # Core.label
                text = child.text
                # 某些时候 tag 可能是 {namespace}tag 的格式，这里 RimWorld 翻译文件通常没有 namespace
                if not text or '.' not in tag: continue
                
                def_name, prop = tag.split('.', 1)
                if def_name not in trans_map: trans_map[def_name] = {}
                trans_map[def_name][prop] = text.strip().replace('\\n', '\n')
            # logger.debug(f"[DLCParser] Parsed trans_map: {trans_map}")
        except Exception as e:
            logger.error(f"[DLCParser] 解析 XML 失败：{e}")
            pass
        

if __name__ == '__main__':
    dlc_parser = DLCParser(r'E:\SteamLibrary\steamapps\common\RimWorld\Data')
    data = dlc_parser.translate_record({
        'package_id': 'ludeon.rimworld',
        'source': 'dlc',
        'name': 'RimWorld 基础扩展',
        'description': 'RimWorld 基础扩展的描述'
    },target_lang_code='zh-CN')
    print(data)
