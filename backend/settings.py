# backend/settings.py

import json
import os
import shutil
import threading
from datetime import datetime
from dataclasses import dataclass, asdict, field, fields, is_dataclass
from pathlib import Path
import sys
from typing import Dict, Any, List, Optional, Tuple
from backend.utils.constants import normalize_language_code


# 1. 资源目录：存放前端文件、内置工具 (对应开发时的项目根目录)
if getattr(sys, 'frozen', False):
    # 打包后，指向临时解压目录
    BASE_RESOURCE_DIR = Path(getattr(sys, '_MEIPASS'))
else:
    # 开发时，指向当前文件所在目录的上一级（项目根目录）
    BASE_RESOURCE_DIR = Path(__file__).resolve().parent.parent

# 配置文件路径
HOME_DIR = Path(os.getcwd())
# 获取 exe 所在的真实目录
if getattr(sys, 'frozen', False):
    # PyInstaller 打包模式 时，指向 exe 所在目录
    HOME_DIR = Path(sys.executable).parent
else:
    # 开发模式, 指向当前文件所在目录的上一级（项目根目录）
    HOME_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = HOME_DIR / "data"                # 数据目录
CONFIG_PATH = DATA_DIR / "config.json"      # 配置文件路径
CONFIG_UPDATE_BACKUP_PATH = DATA_DIR / "config.json.update.bak"
UPDATE_DIR = HOME_DIR / "updates"     # 更新目录
TOOLS_DIR = HOME_DIR / "tools"                # 工具目录
MODS_DIR = HOME_DIR / "mods"                # 模组目录
TOOL_MODS_DIR = HOME_DIR / "toolmods"    # 工具模组目录
CACHE_DIR = HOME_DIR / "cache"                # 缓存目录
BACKUP_DIR = HOME_DIR / "backups"                # 备份目录
# 定义缓存目录
GALLERY_CACHE_DIR = CACHE_DIR / "gallery"       # 定义画廊缓存目录
THUMBNAIL_CACHE_DIR = CACHE_DIR / "thumbnails"  # 定义缩略图缓存目录
# 规则存放路径
RULES_DIR = DATA_DIR / "rules"
USER_RULES_PATH = RULES_DIR / "user_rules.json"             # 用户规则路径
COMMUNITY_RULES_PATH = RULES_DIR / "communityRules.json"    # 社区库规则路径
# 外置数据库路径
COMMUNITY_WORKSHOP_DB_PATH = DATA_DIR / "steamDB.json"         # 社区库数据库路径
COMMUNITY_INSTEAD_DB_PATH = DATA_DIR / "replacements.json.gz"  # 替代Mod数据库路径


@dataclass
class ProxyConfig:
    enabled: bool = False
    # 代理类型: 'http' 或 'socks5'
    type: str = 'http' 
    host: str = ''
    port: int = 0
    username: str = ''
    password: str = ''
    # 排除列表 (不走代理的域名/IP)
    bypass_list: List[str] = field(default_factory=lambda: [
        "127.0.0.1", "localhost", "::1", 
    ])

@dataclass
class NetworkConfig:
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    # 自定义 Hosts (域名 -> IP 映射)
    hosts: Dict[str, str] = field(default_factory=dict) 
    write_to_system_hosts: bool = False         # 是否将自定义 Hosts 写入系统 hosts 文件
    use_proxy_on_steamcmd: bool = False         # SteamCMD 是否使用代理
    use_proxy_on_ai: bool = False               # AI 是否使用代理

@dataclass
class AIConfig:
    enabled: bool = False
    provider: str = "openai_compatible"  # openai, anthropic, google
    # OpenAI-compatible 的 endpoint 选择策略
    endpoint_mode: str = "auto"     # auto / chat_completions / responses
    base_url: str = "https://api.openai.com/v1"  # 允许自定义，如 DeepSeek, LocalAI
    api_key: str = ""
    model: str = "gpt-3.5-turbo"
    temperature: Optional[float] = 0.7     # 温度参数（控制输出随机性）允许“不传”
    max_output_tokens: int = 0     # 单次请求最大输出 Token；0 表示按模型自动
    max_input_tokens: int = 0      # 高级输入预算；0 表示自动按上下文窗口或输出预算推导
    context_window_tokens: int = 0 # 模型上下文窗口；0 表示按模型预设
    max_concurrency: int = 3     # 最大并发请求数（避免被API封锁）

    def model_token_budget(self) -> dict[str, Any]:
        """返回当前模型的 token 预算预设。"""
        from backend.ai.def_model_capabilities import resolve_model_token_budget

        base_url = self.base_url
        if not base_url and str(self.provider or "").strip().lower() == "ollama":
            base_url = "http://127.0.0.1:11434"
        return resolve_model_token_budget(self.model, base_url)

    def resolved_context_window_tokens(self) -> int:
        """解析模型上下文窗口，用户显式配置优先，否则走模型预设。"""
        try:
            explicit_context = int(self.context_window_tokens or 0)
        except (TypeError, ValueError):
            explicit_context = 0
        if explicit_context > 0:
            return explicit_context
        return int(self.model_token_budget().get("context_window_tokens") or 32768)

    def resolved_max_output_tokens(self) -> int:
        """解析单次请求输出上限，用户显式配置优先，否则走模型预设。"""
        try:
            explicit_output = int(self.max_output_tokens or 0)
        except (TypeError, ValueError):
            explicit_output = 0
        if explicit_output > 0:
            return explicit_output
        return int(self.model_token_budget().get("default_output_tokens") or 4096)

    def resolved_max_input_tokens(self) -> int:
        """解析输入预算，避免把输出上限误当上下文窗口。"""
        try:
            explicit_input = int(self.max_input_tokens or 0)
        except (TypeError, ValueError):
            explicit_input = 0
        if explicit_input > 0:
            return explicit_input

        output_budget = self.resolved_max_output_tokens()
        context_window = self.resolved_context_window_tokens()
        if context_window > 0:
            return max(1000, context_window - output_budget - 512)

        from backend.ai.def_model_capabilities import DEFAULT_INPUT_TOKENS
        return max(2000, min(DEFAULT_INPUT_TOKENS, output_budget * 2))

@dataclass
class UIConfig:
    theme: str = "system"       # light, dark, system
    font_size: int = 16
    drag_delay: int = 30            # 拖动判定延迟 (毫秒)
    detail_delay: int = 200         # Mod 详情页加载延迟 (毫秒)
    tooltip_hover_time: int = 1000  # 鼠标悬停显示提示时间 (毫秒)
    show_mod_hover_panel: bool = True  # 是否显示 Mod 悬停面板
    double_click_active_mod: bool = True  # 是否双击启用/停用 Mod
    
    # 主界面布局配置
    main_layout: List[Dict[str, Any]] = field(default_factory=lambda: [
        { 'id': 'details', 'visible': True },
        { 'id': 'library', 'visible': True },
        { 'id': 'active', 'visible': True },
        { 'id': 'sidebar', 'visible': True },
    ])
    
    show_icons_cloud: bool = True  # 是否显示动态图标云
    
    # Mod 详情面板布局配置
    mod_details_layout: List[Dict[str, Any]] = field(default_factory=lambda: [
        { 'id': 'basic_info', 'visible': True }, # 包ID、作者、链接、路径
        { 'id': 'files_info', 'visible': True },
        { 'id': 'time_info', 'visible': True },
        { 'id': 'relations_info', 'visible': True },
        { 'id': 'user_info', 'visible': True }, # 标签、备注、分组
        { 'id': 'description', 'visible': True },
    ])

    show_dependency_graph: bool = True  # 是否显示依赖关系图
    enable_active_section_collapse: bool = False  # 是否启用启用列表标题分组折叠（仅 active 列表使用）
    default_collapse_active_sections: bool = False  # 在没有历史折叠状态时，是否让标题分组首次默认折叠
    show_list_index: bool = True  # 是否显示列表索引列
    show_list_icon: bool = True  # 是否显示 Mod 图标
    show_list_mod_icon: bool = True  # 是否显示 Mod 图标
    show_list_modtype_icon: bool = True  # 是否显示 Mod 类型图标
    
    show_group_index: bool = True  # 是否显示分组索引列
    show_group_icon: bool = True  # 是否显示分组图标
    
# 贴图优化配置类
@dataclass
class TextureOptConfig:
    texture_tools_path: str = str(TOOLS_DIR / "texture_tools")  # 贴图工具目录
    process_mode: str = "scaled_only_overwrite"
    generate_mipmaps: bool = True            # 是否生成 Mipmap
    scale_factor: float = 1.0                # 缩放倍率，小于1时会缩小贴图
    max_size: int = 128                      # 最低清晰度
    skip_small_textures: bool = True         # 超出建议范围时不参与缩放
    min_dimension: int = 128                 # 最短边低于该值时不参与缩放
    max_source_dimension: int = 2048         # 最长边高于该值时不参与缩放
    encode_batch_timeout_seconds: int = 480  # todds 批处理超时


@dataclass
class AppConfig:
    """
    配置数据结构定义。
    在这里定义字段和默认值，类型安全且清晰。
    """
    # --- 路径设置 ---
    # game_install_path: str = ""    # RimWorld 安装路径
    # user_data_path: str = ""       # 用户数据文件夹
    # game_config_path: str = ""     # RimWorld 配置文件夹
    # game_saves_path: str = ""      # RimWorld 存档文件夹
    # game_dlc_path: str = ""        # RimWorld DLC 文件夹
    # local_mods_path: str = ""      # RimWorld 本地模组文件夹
    workshop_mods_path: str = ""   # RimWorld 公共工坊模组文件夹
    # use_workshop_mods: bool = True  # 是否使用公共工坊模组
    steam_path: str = ""          # Steam 安装路径
    home_path: str = str(HOME_DIR) # 本程序路径
    
    ripgrep_path: str = str(TOOLS_DIR / "ripgrep")
    
    # steamcmd 下载路径
    steamcmd_path: str = str(TOOLS_DIR / "steamcmd")
    steamcmd_mods_path: str = str(TOOLS_DIR / "steamcmd" / "steamapps" / "workshop" / "content" / "294100")
    self_mods_path: str = str(MODS_DIR)  # 本程序默认模组路径
    # use_self_mods: bool = True          # 是否使用本程序模组
    move_old_self_mods: bool = False    # 修改路径后是否移动原有模组
    load_order_import_dir_mode: str = "default"    # 导入文件选择器初始目录策略: default / remember / custom
    load_order_import_custom_path: str = ""        # 导入文件选择器自定义目录（全局）
    load_order_import_last_path: str = ""          # 导入文件选择器上次成功目录（全局）
    load_order_export_dir_mode: str = "default"    # 导出文件选择器初始目录策略: default / remember / custom
    load_order_export_custom_path: str = ""        # 导出文件选择器自定义目录（全局）
    load_order_export_last_path: str = ""          # 导出文件选择器上次成功目录（全局）
    
    # --- 游戏设置 ---
    # game_version: str = ""               # RimWorld 版本
    current_profile_id: str = "default"   # 当前激活的环境ID
    # run_commands: List[str] = field(default_factory=list)   # 启动时运行的命令
    enable_tool_mods: bool = False           # 是否启用 ToolMods 目录下的伴生模组
    link_deployment_mode_full: bool = False # 链接部署模式: true=完全重建, false=增量部署
    
    # --- 高级设置 ---
    backup_retention_days: int = 30           # 备份保留天数
    enable_auto_scan: bool = True             # 启动时自动扫描
    enable_file_size_scan: bool = False         # 扫描时是否检查文件大小
    delete_missing_mods_data: bool = False     # 是否删除数据库中缺失的 Mod 数据
    open_url_on_system: bool = False          # 是否在系统默认浏览器打开链接
    auto_sort_strategy: str = "edge_enhanced_sort_logic" # 自动排序策略: classic_sort_logic, edge_enhanced_sort_logic
    sort_mods_by: str = "name"                # 排序方式: name, id, alias
    coexist_mod_folder_name_type: str = "workshop_id" # 共存Mod生成方式: workshop_id, package_id, name, alias
    show_coexistence_message: bool = True      # 是否显示共存Mod提示
    check_language_support: bool = True        # 是否检查语言支持
    enable_action_prechecks: bool = True       # 是否启用操作前检查功能
    language_packs_follow_targets: bool = False # 是否让语言包贴紧其最后一个前置/依赖目标
    
    # --- 社区设置 ---
    community_workshop_db_url: str = "https://github.com/RimSort/Steam-Workshop-Database/blob/main/steamDB.json"
    community_workshop_db_path: str = str(COMMUNITY_WORKSHOP_DB_PATH)
    community_instead_db_url: str = "https://github.com/emipa606/UseThisInstead/blob/main/replacements.json.gz"
    community_instead_db_path: str = str(COMMUNITY_INSTEAD_DB_PATH)
    community_rules_url: str = "https://github.com/RimSort/Community-Rules-Database/blob/main/communityRules.json"
    community_rules_path: str = str(COMMUNITY_RULES_PATH)
    user_rules_path: str = str(USER_RULES_PATH)
    steam_web_api_key: str = ""  # Steamworks Web API 鉴权密钥，仅供需要受限接口的后端请求使用
    
    # --- 开发与调试设置 ---
    browser_mode: bool = False            # 是否默认使用浏览器模式启动
    auto_enter_silent_mode: bool = True   # 游戏运行时是否自动进入静默模式
    silent_mode_default_view: str = "home" # 静默模式默认落点: home / logs
    debug_mode: bool = False  # 开发模式开关
    log_retention_days: int = 7  # 日志保留天数
    log_level: str = "INFO"  # 默认日志等级 DEBUG, INFO, WARNING, ERROR
    enable_auto_update_check: bool = True  # 自动检查更新开关
    ignored_update_version: str = ""       # 跳过的版本号
    last_update_check_time: float = 0      # 上次检查时间（用于限流）
    # 以下三类检查都只负责“发现问题并提醒”，真正更新仍需用户确认后手动触发。
    enable_auto_tool_check: bool = True
    tool_check_interval_days: int = 3
    last_tool_check_time: float = 0
    
    enable_auto_external_data_update_check: bool = True
    external_data_update_check_interval_days: int = 1
    last_external_data_update_check_time: float = 0
    
    enable_auto_steamcmd_mod_update_check: bool = True
    steamcmd_mod_update_check_interval_days: int = 1
    last_steamcmd_mod_update_check_time: float = 0
    
    last_run_time: float = 0               # 上次运行时间（用于判断Mod是否存在变动）
    run_count: int = 0                     # 运行次数（用于判断是否需要重新扫描）
    
    # --- 界面设置 ---
    language: str = "zh-CN"     # 默认语言
    window_width: int = 1400
    window_height: int = 900
    completed_guides: Dict[str, str] = field(default_factory=dict) # 存储已完成的引导, e.g. {"main_v1.0": "done"}
    ui: UIConfig = field(default_factory=UIConfig)
    
    # --- 功能设置 ---
    network: NetworkConfig = field(default_factory=NetworkConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    texture_opt: TextureOptConfig = field(default_factory=TextureOptConfig)
    

class SettingsManager:
    _instance = None
    
    def __new__(cls):
        """单例模式：确保全局只有一个 SettingsManager 实例"""
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._ensure_config_dir()
        self._save_lock = threading.Lock()
        self._legacy_prefer_steam_launch = None
        # self.config: AppConfig = self._load() # 加载配置
        
        # 1. 先初始化一个空的配置对象，防止加载过程中访问 self.config 崩溃
        self.config = AppConfig()
        # 2. 执行加载（此时 _recursive_update 访问 self.config 就安全了）
        self._load_to_config()
        
        self._initialized = True

    def _ensure_config_dir(self):
        """ 确保配置目录存在 """
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True)
        # 确保日志目录存在
        log_dir = DATA_DIR / "logs"
        if not log_dir.exists():
            log_dir.mkdir(parents=True)
        if not TOOL_MODS_DIR.exists():
            TOOL_MODS_DIR.mkdir(parents=True)
            
    def _recursive_update(self, target_obj, source_dict: Dict[str, Any]):
        """
        递归更新 dataclass 对象。
        :param target_obj: 初始化的 dataclass 对象 (包含默认值)
        :param source_dict: 从 JSON 加载的字典
        """
        # 获取目标对象的所有字段定义
        target_fields = {f.name: f for f in fields(target_obj)}
        
        for key, value in source_dict.items():
            # 1. 忽略未知字段 (配置文件里有，但代码里没有定义的)
            if key not in target_fields: continue
            # 获取当前对象上的属性值
            current_attr = getattr(target_obj, key)
            # 2. 判断是否需要递归
            # 如果当前属性是 dataclass 实例，且来源值是字典，则递归更新
            if is_dataclass(current_attr):
                if isinstance(value, dict):
                    self._recursive_update(current_attr, value)
                continue
            # 3. 普通赋值
            else:
                # 这里可以加一些简单的类型保护，比如防止把 str 赋给 int，但 Python 鸭子类型通常允许直接赋值，除非为了极高的健壮性
                setattr(target_obj, key, value)
                
    def _load_raw_config(self, path: Path) -> Dict[str, Any]:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Config root is not an object")
        return data

    def _extract_compatible_config_values(self, raw_dict: Dict[str, Any], target_obj) -> Dict[str, Any]:
        """
        从原始配置中提取“当前版本仍然可识别”的字段。
        设计原因：
        1. 更新后字段结构可能变化，不能因为少数字段异常就整份判死刑。
        2. 只要还能识别出一部分字段，就优先保留用户数据，其余部分交给默认值补齐。
        """
        compatible: Dict[str, Any] = {}
        target_fields = {f.name: f for f in fields(target_obj)}

        for key, value in raw_dict.items():
            if key not in target_fields:
                continue

            current_attr = getattr(target_obj, key)
            if is_dataclass(current_attr):
                # 嵌套配置块必须仍是对象；若被写坏成字符串/数组，则忽略该块并保留默认值。
                if not isinstance(value, dict):
                    continue
                nested_compatible = self._extract_compatible_config_values(value, current_attr)
                if nested_compatible:
                    compatible[key] = nested_compatible
                continue

            compatible[key] = value

        return compatible

    def _is_config_valid(self) -> bool:
        return all([
            str(self.config.home_path or "").strip(),
            str(self.config.self_mods_path or "").strip(),
            str(self.config.steamcmd_path or "").strip(),
            str(self.config.current_profile_id or "").strip(),
        ])

    def _merge_config_dicts(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        递归合并两个配置片段。
        base 一般来自备份，override 一般来自当前配置，因此 override 优先级更高。
        """
        merged = dict(base)
        for key, value in override.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_config_dicts(merged[key], value)
                continue
            merged[key] = value
        return merged

    def _parse_config_fragment(self, data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[bool]]:
        """
        从原始 JSON 对象中提取当前版本仍可识别的配置片段。
        这里故意采用“宽进严出”策略：
        1. 只要还能识别出一部分字段，就把它们留下；
        2. 识别不到的字段直接忽略，不因为局部损坏把整份配置判死刑。
        """
        compatible = self._extract_compatible_config_values(data, AppConfig())
        legacy_prefer_steam_launch = None
        if 'prefer_steam_launch' in data:
            legacy_prefer_steam_launch = bool(data.get('prefer_steam_launch'))

        if compatible or legacy_prefer_steam_launch is not None:
            return compatible, legacy_prefer_steam_launch
        return None, None

    def _read_config_fragment(self, path: Path, source_name: str) -> Tuple[Optional[Dict[str, Any]], Optional[bool]]:
        """
        尝试宽松读取一个配置源。
        返回值：
        1. 兼容字段片段，用于后续恢复；
        2. 旧版 prefer_steam_launch 兼容值（若存在）。
        """
        if not path.exists(): return None, None

        try:
            data = self._load_raw_config(path)
        except Exception as e:
            print(f"Config read error [{source_name}]: {e}")
            return None, None

        compatible, legacy_prefer_steam_launch = self._parse_config_fragment(data)
        if compatible or legacy_prefer_steam_launch is not None:
            return compatible, legacy_prefer_steam_launch

        print(f"Config parse warning [{source_name}]: no compatible fields found")
        return None, None

    def _apply_config_fragment(self, data: Dict[str, Any], legacy_prefer_steam_launch: Optional[bool] = None):
        """
        将“已筛选过的兼容字段”应用到默认配置骨架上。
        实现原理：
        - 先构建完整默认值；
        - 再把仍可识别的用户字段覆盖进去；
        - 最后统一做归一化与衍生路径同步。
        """
        self.config = AppConfig()
        if legacy_prefer_steam_launch is not None:
            self._legacy_prefer_steam_launch = legacy_prefer_steam_launch
        self._recursive_update(self.config, data)
        self._normalize_config()
        self._sync_derived_paths()
        if not self._is_config_valid():
            raise ValueError("Config validation failed after normalization")

    def _load_to_config(self):
        """
        将磁盘配置加载到现有的 self.config 中
        """
        current_fragment, current_legacy_prefer = self._read_config_fragment(CONFIG_PATH, "current")
        backup_fragment, backup_legacy_prefer = self._read_config_fragment(CONFIG_UPDATE_BACKUP_PATH, "update-backup")

        if current_fragment is None and current_legacy_prefer is None and \
           backup_fragment is None and backup_legacy_prefer is None:
            self._normalize_config()
            self._sync_derived_paths()
            return

        try:
            effective_fragment = current_fragment or {}
            effective_legacy_prefer = current_legacy_prefer
            recovered_from_backup = False

            if backup_fragment is not None or backup_legacy_prefer is not None:
                # 只要更新备份还在，就把它当作“缺失字段补丁源”参与合并：
                # 1. 当前配置完全损坏/丢失时，可直接由备份兜底；
                # 2. 当前配置只能解析出一部分字段时，可从备份补齐剩余可识别字段；
                # 3. 当前配置中已经成功读取出的值始终优先，避免旧备份反向覆盖用户最新设置。
                merged_fragment = self._merge_config_dicts(backup_fragment or {}, effective_fragment)
                recovered_from_backup = merged_fragment != effective_fragment
                effective_fragment = merged_fragment
                if effective_legacy_prefer is None:
                    effective_legacy_prefer = backup_legacy_prefer
                    recovered_from_backup = recovered_from_backup or backup_legacy_prefer is not None

            self._apply_config_fragment(effective_fragment, effective_legacy_prefer)

            # 只有备份确实补进了缺失字段时才回写，避免“备份一直存在时每次启动都重写配置”。
            if recovered_from_backup:
                self.save()
        except Exception as e:
            print(f"Config load error: {e}")
            self.config = AppConfig()
            self._normalize_config()
            self._sync_derived_paths()

    def _normalize_config(self):
        self.config.home_path = str(HOME_DIR)
        self.config.current_profile_id = str(self.config.current_profile_id or "").strip() or "default"
        self.config.steam_path = str(self.config.steam_path or "").strip()
        self.config.workshop_mods_path = str(self.config.workshop_mods_path or "").strip()
        self.config.steamcmd_path = str(self.config.steamcmd_path or "").strip() or str(TOOLS_DIR / "steamcmd")
        self.config.self_mods_path = str(self.config.self_mods_path or "").strip() or str(MODS_DIR)
        self.config.ripgrep_path = str(self.config.ripgrep_path or "").strip() or str(TOOLS_DIR / "ripgrep")
        self.config.language = normalize_language_code(self.config.language, default="zh-CN") or "zh-CN"
        valid_modes = {"default", "remember", "custom"}
        if str(self.config.load_order_import_dir_mode or "").strip().lower() not in valid_modes:
            self.config.load_order_import_dir_mode = "default"
        else:
            self.config.load_order_import_dir_mode = str(self.config.load_order_import_dir_mode).strip().lower()
        if str(self.config.load_order_export_dir_mode or "").strip().lower() not in valid_modes:
            self.config.load_order_export_dir_mode = "default"
        else:
            self.config.load_order_export_dir_mode = str(self.config.load_order_export_dir_mode).strip().lower()
        ai_cfg = self.config.ai
        if isinstance(ai_cfg, AIConfig):
            try:
                ai_cfg.max_output_tokens = max(0, int(ai_cfg.max_output_tokens or 0))
            except (TypeError, ValueError):
                ai_cfg.max_output_tokens = 0
            try:
                ai_cfg.max_input_tokens = max(0, int(ai_cfg.max_input_tokens or 0))
            except (TypeError, ValueError):
                ai_cfg.max_input_tokens = 0
            try:
                ai_cfg.context_window_tokens = max(0, int(ai_cfg.context_window_tokens or 0))
            except (TypeError, ValueError):
                ai_cfg.context_window_tokens = 0
    
    def _sync_derived_paths(self):
        """
        统一管理所有依赖路径的计算逻辑。
        """
        # 根据 steamcmd_path 计算 steamcmd_mods_path
        if self.config.steamcmd_path:
            base_path = Path(self.config.steamcmd_path).resolve()
            new_path = str(base_path / "steamapps" / "workshop" / "content" / "294100")
            self.config.steamcmd_mods_path = new_path
            
    def get_default_external_paths(self):
        """获取“外部依赖”页相关路径的默认值。"""
        return {
            # 目录型外部工具统一在这里给出默认位置。
            # SteamCMD 的工坊内容目录仍由 `_sync_derived_paths()` 负责衍生，不在这里直接暴露。
            "steamcmd_path": str(TOOLS_DIR / "steamcmd"),
            "ripgrep_path": str(TOOLS_DIR / "ripgrep"),
            "texture_opt": {
                "texture_tools_path": str(TOOLS_DIR / "texture_tools"),
            },
            "community_workshop_db_path": str(COMMUNITY_WORKSHOP_DB_PATH),
            "community_instead_db_path": str(COMMUNITY_INSTEAD_DB_PATH),
            "community_rules_path": str(COMMUNITY_RULES_PATH),
            "user_rules_path": str(USER_RULES_PATH),
        }
        
    
    def get(self, key: str) -> Any:
        """
        获取配置项。
        支持: settings.get('language')
        """
        if hasattr(self.config, key):
            return getattr(self.config, key)
        return None

    def set(self, key: str, value: Any):
        """
        设置配置项并自动处理路径同步逻辑
        """
        if not hasattr(self.config, key):
            print(f"Warning: Unknown key {key}")
            return
        before_state = asdict(self.config)
        current_attr = getattr(self.config, key)
        if is_dataclass(current_attr) and isinstance(value, dict):
            self._recursive_update(current_attr, value)
        else:
            setattr(self.config, key, value)
        self._normalize_config()
        self._sync_derived_paths()
        after_state = asdict(self.config)
        if after_state == before_state: return
        old_self_mods_path = before_state.get('self_mods_path', '')
        old_steamcmd_path = before_state.get('steamcmd_path', '')
        new_self_mods_path = after_state.get('self_mods_path', '')
        new_steamcmd_path = after_state.get('steamcmd_path', '')
        # --- 逻辑触发区 ---
        # 1. 重新计算衍生路径
        # 2. 如果 self_mods_path 变了，触发同步
        if old_self_mods_path != new_self_mods_path:
            from backend.managers.mgr_files import FileManager
            FileManager.sync_steamcmd_root_link(
                old_mods_path=old_self_mods_path,
                move_old_data=self.config.move_old_self_mods
            )
        # 3. 如果 steamcmd_path 变了，也触发同步
        if old_steamcmd_path != new_steamcmd_path:
            from backend.managers.mgr_files import FileManager
            FileManager.sync_steamcmd_root_link()
        self.save()

    def save(self):
        """保存当前配置到磁盘"""
        temp_path = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
        try:
            with self._save_lock:
                self._normalize_config()
                self._sync_derived_paths()
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(asdict(self.config), f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, CONFIG_PATH)
            # print("Settings saved.")
        except Exception as e:
            print(f"Error saving settings: {e}")
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

    # 强烈建议新增这个方法供 api.save_all_settings 使用
    def update_from_dict(self, data_dict: Dict[str, Any]):
        """
        全量更新，同样需要处理逻辑触发
        """
        before_state = asdict(self.config)
        self._recursive_update(self.config, data_dict)
        self._normalize_config()
        self._sync_derived_paths()
        after_state = asdict(self.config)
        if after_state == before_state: return
        old_self_mods_path = before_state.get('self_mods_path', '')
        old_steamcmd_path = before_state.get('steamcmd_path', '')
        new_self_mods_path = after_state.get('self_mods_path', '')
        new_steamcmd_path = after_state.get('steamcmd_path', '')
        # 检查并同步
        if old_self_mods_path != new_self_mods_path or \
           old_steamcmd_path != new_steamcmd_path:
            from backend.managers.mgr_files import FileManager
            FileManager.sync_steamcmd_root_link(
                old_mods_path=old_self_mods_path,
                move_old_data=self.config.move_old_self_mods
            )
        self.save()

    def update_paths(self, paths_dict: Dict[str, str]):
        """批量更新路径"""
        changed = False
        for k, v in paths_dict.items():
            if hasattr(self.config, k):
                setattr(self.config, k, v)
                changed = True
        if changed:
            self.save()

# 全局单例实例
settings = SettingsManager()


def backup_config_for_update() -> bool:
    if not CONFIG_PATH.exists(): return False
    try:
        config_backup_dir = BACKUP_DIR / "config"
        config_backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CONFIG_PATH, CONFIG_UPDATE_BACKUP_PATH)
        # 除了“更新中途可直接回滚”的固定备份，再保留一份时间戳快照，避免后续排查时只剩最后一次状态。
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(CONFIG_PATH, config_backup_dir / f"config-update-{timestamp}.json")
        return True
    except Exception as e:
        print(f"Backup config for update error: {e}")
        return False
