import os
import re
from dataclasses import dataclass
# 引入通用常量
from backend.utils.constants import LANGUAGE_MAP



BASE_IGNORED_PATHS = [
    'Backups',
    'Cache',
    'Logs',
    'Temp',
    'Source',
    '.git',
    '.vscode',
]

@dataclass(frozen=True)
class ModAboutState:
    about_xml: str
    disabled_xml: str
    resolved_path: str | None
    is_disabled: bool
    has_about: bool
    has_disabled: bool
    cleaned_conflict: bool = False

class ModAnalyzer:
    def __init__(self):
        # 匹配版本号文件夹，如 "1.0", "1.1", "v1.4"
        self.version_pattern = re.compile(r'^[vV]?(\d+\.\d+)$')

    def analyze(self, mod_path):
        """
        全量递归扫描，但排除过旧的版本文件夹。
        智能区分文件用途。
        深度分析 Mod 文件夹，检测 Mod 类型、支持的语言、文件统计等
        :param mod_path: Mod 根目录绝对路径
        返回: {
            'mod_type': 'XML'|'Assembly'|'LanguagePack',
            'supported_languages': ['ZH-cn', 'EN'],
            'file_stats': {'code_dll': 0, 'game_xml': 0, 'patch_xml': 0, 'lang_xml': 0, 'image': 0, 'audio': 0},
            'has_defs': False
            'has_assemblies': False,
            'has_tip': False
        }
        """
        info = {
            'mod_type': 'Unknown',
            'supported_languages': set(),
            'file_stats': {
                'code_dll': 0,    # 程序集
                'game_xml': 0,    # Defs (游戏性定义)
                'patch_xml': 0,   # Patches (补丁)
                'lang_xml': 0,    # 翻译文件
                'image': 0,       # 贴图
                'audio': 0,       # 音频
            },
            'has_assemblies': False,
            'has_defs': False,
            'has_tip': False
        }

        if not os.path.exists(mod_path):
            return self._finalize(info)

        # 1. 计算要忽略的路径 (黑名单)
        local_ignored_paths = list(BASE_IGNORED_PATHS)
        local_ignored_paths.extend(self._get_ignored_version_paths(mod_path))

        # 2. 递归遍历
        for root, dirs, files in os.walk(mod_path):
            # --- 剪枝逻辑 (Pruning) ---
            # 如果当前路径在忽略列表中，清空 dirs 以停止向下递归，并跳过当前层的文件
            # 注意：os.walk 中修改 dirs 列表会影响后续遍历
            if any(self._is_subpath(root, ignore) for ignore in local_ignored_paths):
                dirs[:] = [] # 停止递归
                continue
            
            # --- 上下文判断 ---
            # 判断当前文件夹的性质
            rel_path = os.path.relpath(root, mod_path).replace('\\', '/')
            path_parts = rel_path.split('/')
            lower_path_parts = [part.lower() for part in path_parts]
            
            is_about_dir = 'about' in lower_path_parts
            is_lang_dir = 'languages' in lower_path_parts
            is_defs_dir = 'defs' in lower_path_parts
            is_patches_dir = 'patches' in lower_path_parts
            is_assemblies_dir = 'assemblies' in lower_path_parts

            # --- 语言探测 ---
            # 只要在 Languages 文件夹下，尝试提取语言代码
            if is_lang_dir:
                self._extract_languages(path_parts, info['supported_languages'])

            # --- 文件统计 ---
            for f in files:
                ext = f.split('.')[-1].lower()
                if f.endswith('Tips.xml'): info['has_tip'] = True
                # XML 分类统计
                if ext == 'xml':
                    if is_about_dir:
                        pass # 忽略 About.xml, Manifest.xml 等元数据
                    elif is_lang_dir:
                        info['file_stats']['lang_xml'] += 1
                    elif is_patches_dir:
                        info['file_stats']['patch_xml'] += 1
                    elif is_defs_dir:
                        info['file_stats']['game_xml'] += 1
                        info['has_defs'] = True
                    else:
                        # 既不在 Defs 也不在 Languages 的 XML (如根目录的 LoadFolders.xml)
                        # 暂时不计入核心计数，或可视情况处理
                        pass

                # DLL 统计
                elif ext == 'dll':
                    # 通常只认 Assemblies 目录，但有的 Mod 放根目录，放宽限制
                    info['file_stats']['code_dll'] += 1
                    info['has_assemblies'] = True
                
                # 资源统计
                elif ext in ('png', 'jpg', 'jpeg', 'gif', 'dds'):
                    if not is_about_dir: # 排除 Preview.png
                        info['file_stats']['image'] += 1
                
                elif ext in ('ogg', 'wav', 'mp3'):
                    info['file_stats']['audio'] += 1

        return self._finalize(info)

    def _get_ignored_version_paths(self, mod_path):
        """
        找出所有"非最大版本"的版本号文件夹路径。
        例如：有 1.3, 1.4, 1.5 -> 返回 [path/to/1.3, path/to/1.4]
        """
        try:
            items = os.listdir(mod_path)
        except OSError:
            return []

        version_map = {} # { 1.4: "1.4", 1.5: "v1.5" }
        
        for d in items:
            full_path = os.path.join(mod_path, d)
            if os.path.isdir(full_path):
                match = self.version_pattern.match(d)
                if match:
                    try:
                        v_num = float(match.group(1))
                        version_map[v_num] = full_path
                    except ValueError:
                        pass
        
        ignored = []
        if version_map:
            max_ver = max(version_map.keys())
            # 将除了最大版本以外的所有版本文件夹加入黑名单
            for ver, path in version_map.items():
                if ver != max_ver:
                    ignored.append(path)
        
        return ignored

    def _is_subpath(self, target, parent):
        """判断 target 是否是 parent 的子路径或本身"""
        # 使用 os.path.abspath 统一路径格式
        target = os.path.abspath(target)
        parent = os.path.abspath(parent)
        return target == parent or target.startswith(parent + os.sep)

    def _extract_languages(self, path_parts, lang_set):
        """
        从 Languages 文件夹路径中提取语言。
        支持格式：
        Languages/English
        Languages/ChineseSimplified (简体中文)
        """
        try:
            # 找到 Languages 后的第一个文件夹
            lower_path_parts = [part.lower() for part in path_parts]
            # 查找小写的 'languages' 位置（支持任意大小写的原文件夹名）
            idx = lower_path_parts.index('languages')
            if idx + 1 < len(path_parts):
                folder_name = path_parts[idx+1]
                # 处理 "ChineseSimplified (简体中文)" -> "ChineseSimplified"
                key = folder_name.split(' ')[0].strip()
                
                # 映射到标准代码
                if key in LANGUAGE_MAP:
                    lang_set.add(LANGUAGE_MAP[key])
                else:
                    # 如果没有映射，直接保留原名 (或统一转小写)
                    lang_set.add(key)
        except ValueError:
            pass

    def _finalize(self, info):
        """根据统计结果判定 Mod 类型并清理数据"""
        c = info['file_stats']
        
        # 类型判定优先级
        if info['has_assemblies']:
            mod_type = 'Assembly' # 包含代码 (通常也是最复杂的)
        elif c['lang_xml'] > 0 and ((c['game_xml'] == 0 and c['code_dll'] == 0) or (c['patch_xml']+c['game_xml'] == 1 and info['has_tip'])):
            mod_type = 'LanguagePack' # 纯翻译（部分翻译包还有Tip文件）
        elif c['image'] > 0 and c['game_xml'] == 0 and c['code_dll'] == 0:
            mod_type = 'Texture'  # 纯贴图
        elif c['audio'] > 0 and c['patch_xml']+c['game_xml'] == 1:
            mod_type = 'Audio'    # 纯音乐包 (较少见)
        elif (c['game_xml'] > 0 and c['image'] > 0 and c['audio'] > 0) :
            mod_type = 'Mixed' 
        elif info['has_defs'] or c['patch_xml'] > 0:
            mod_type = 'XML'      # 只有数据定义
        else: 
            mod_type = 'Unknown'

        # 转换 set 为 list
        info['supported_languages'] = list(info['supported_languages'])
        info['mod_type'] = mod_type
        
        # 移除中间状态字段 (可选)
        del info['has_assemblies']
        del info['has_defs']
        
        return info
    
    @staticmethod
    def resolve_mod_about_state(mod_path: str, cleanup_dual_files: bool = False) -> ModAboutState:
        """
        统一解析 Mod 的 About 文件状态。

        规则：
        - `About.xml` 存在时视为启用。
        - 仅存在 `About.xml.disabled` 时视为禁用。
        - 两者同时存在时，以 `About.xml` 为准；如允许修复，则自动删除残留的 `.disabled`。
        """
        about_xml = os.path.join(mod_path, 'About', 'About.xml')
        disabled_xml = about_xml + '.disabled'

        has_about = os.path.exists(about_xml)
        has_disabled = os.path.exists(disabled_xml)
        cleaned_conflict = False

        if has_about and has_disabled and cleanup_dual_files:
            os.remove(disabled_xml)
            has_disabled = False
            cleaned_conflict = True

        if has_about:
            return ModAboutState(
                about_xml=about_xml,
                disabled_xml=disabled_xml,
                resolved_path=about_xml,
                is_disabled=False,
                has_about=True,
                has_disabled=has_disabled,
                cleaned_conflict=cleaned_conflict,
            )

        if has_disabled:
            return ModAboutState(
                about_xml=about_xml,
                disabled_xml=disabled_xml,
                resolved_path=disabled_xml,
                is_disabled=True,
                has_about=False,
                has_disabled=True,
                cleaned_conflict=cleaned_conflict,
            )

        return ModAboutState(
            about_xml=about_xml,
            disabled_xml=disabled_xml,
            resolved_path=None,
            is_disabled=False,
            has_about=False,
            has_disabled=False,
            cleaned_conflict=cleaned_conflict,
        )

