
from email.policy import default
import os
import json
import uuid
import shutil
from pathlib import Path
from typing import Any, Dict
from datetime import datetime
from dataclasses import asdict, dataclass, field
from playhouse.shortcuts import model_to_dict
from backend.database.models import GameProfile, db
from backend.managers.mgr_files import PathChecker
from backend.managers.mgr_game_install import GameInstallInspector
from backend.managers.mgr_game import GameManager
from backend.profile import UserDataRoot
from backend.utils.profile_runtime import (
    normalize_profile_runtime_flags,
    resolve_profile_runtime_capabilities,
)
from backend.settings import BACKUP_DIR, settings, DATA_DIR
from backend.utils.logger import logger 
from backend.utils.tools import delete_fs_path, normalize_path_for_storage


# @dataclass
@dataclass(frozen=True) # 使用 frozen=True 让其不可变，防止运行时被意外篡改
class ProfileContext:
    profile_id: str
    game_version: str
    game_install_path: str
    user_data_path: str
    prefer_steam_launch: bool
    use_workshop_mods: bool
    use_self_mods: bool
    inactive_mods_order: list = field(default_factory=list)
    temp_mods_order: list = field(default_factory=list)
    is_steam: bool = False
    is_steam_managed: bool = False
    runtime_capabilities: dict = field(default_factory=dict)
    
    is_healthy: bool = True
    health_report: dict = field(default_factory=dict) 
    
    # 动态计算出来的绝对路径（初始化时即确定，拒绝中途修改）
    @property
    def local_mods_path(self):
        install_path = str(self.game_install_path or "").strip()
        return str(Path(install_path) / "Mods") if install_path else ""
    @property
    def game_dlc_path(self):
        install_path = str(self.game_install_path or "").strip()
        return str(Path(install_path) / "Data") if install_path else ""
    @property
    def _user_data_root(self):
        user_data_path = str(self.user_data_path or "").strip()
        if not user_data_path:
            return None
        return UserDataRoot.from_raw(
            user_data_path,
            default_roots=GameManager.get_default_user_data_paths(),
        )
    @property
    def game_config_path(self):
        root = self._user_data_root
        return root.config_dir if root else ""
    @property
    def game_saves_path(self):
        root = self._user_data_root
        return root.saves_dir if root else ""
    @property
    def mods_config_file(self):
        root = self._user_data_root
        return root.mods_config_file if root else ""
    @property
    def backup_dir(self): 
        result = str(BACKUP_DIR / "profile" / self.profile_id) # 强隔离：备份跟环境走！
        if self.profile_id == "default": result = str(BACKUP_DIR)
        return result

    def ensure_directories(self):
        """生命周期钩子：激活此环境时，强制校验并创建必需的目录"""
        try:
            os.makedirs(self.game_config_path, exist_ok=True)
            os.makedirs(self.game_saves_path, exist_ok=True)
            os.makedirs(self.backup_dir, exist_ok=True)
            os.makedirs(os.path.join(self.backup_dir, "today"), exist_ok=True)
            os.makedirs(os.path.join(self.backup_dir, "earlier"), exist_ok=True)
            os.makedirs(os.path.join(self.backup_dir, "other"), exist_ok=True)
        except Exception as e:
            logger.error(f"无法初始化环境目录 {self.profile_id}: {e}")
    
    def validate_health(self):
        """生命周期钩子：装载上下文时的绝对防御"""
        report = {
            "game_install_path": PathChecker.check_install_path(self.game_install_path),
            "user_data_path": PathChecker.check_user_data_path(self.user_data_path)
        }
        # 强制绕过 frozen 限制
        object.__setattr__(self, 'health_report', report)
        # 只要有一项核心检查没过，健康度就为 False
        value = all(res["pass"] for res in report.values())
        object.__setattr__(self, 'is_healthy', value)
        # self.is_healthy = all(res["pass"] for res in self.health_report.values())
        
        if self.is_healthy: self.ensure_directories() # 健康的话，才去创建配置和备份目录
    
    def to_dict(self):
        data = asdict(self) # 拿到基础字段
        # 手动注入动态属性
        data.update({
            "local_mods_path": self.local_mods_path,
            "game_dlc_path": self.game_dlc_path,
            "game_config_path": self.game_config_path,
            "game_saves_path": self.game_saves_path,
            "mods_config_file": self.mods_config_file,
            "backup_dir": self.backup_dir,
        })
        return data


class ProfileManager:
    # 定义属于环境数据的字段白名单
    PROFILE_KEYS = {
        'name',
        'description',
        'game_install_path', 
        'user_data_path', 
        'prefer_steam_launch',
        'use_workshop_mods', 
        'use_self_mods', 
        'run_commands',
        'inactive_mods_order',
        'temp_mods_order',
        'last_played_time'
    }
    
    def __init__(self):
        # 仅供内部探测逻辑使用，避免被 pywebview 误当成可暴露对象递归扫描。
        self._install_inspector = GameInstallInspector()
        self._ensure_default_profile()
        self.current_profile = GameProfile.get_or_none(GameProfile.id == settings.config.current_profile_id)
        self.update_version()

    def _get_install_inspector(self) -> GameInstallInspector:
        inspector = getattr(self, '_install_inspector', None)
        if inspector is None:
            # 单测里常用 `__new__` 绕过 `__init__`，这里做一次兜底，
            # 保证创建/更新/构造上下文时都能拿到同一套安装探针逻辑。
            inspector = GameInstallInspector()
            self._install_inspector = inspector
        return inspector

    def _ensure_default_profile(self):
        """确保至少有一个默认 Profile (通常是当前设置的 Steam 版)"""
        default_profile = GameProfile.get_or_none(GameProfile.id == "default")
        if default_profile:
            return
        # 默认数据路径
        with db.atomic():
            GameProfile.create(
                id='default',
                name='Default',
                description='Default Profile',
                game_install_path='',
                user_data_path='',
                game_version='',
                is_steam=True,
                prefer_steam_launch=True,
                use_workshop_mods=False,
                use_self_mods=False,    # 默认不加载 Self Mod
                run_commands=[]
            )
        # 这里只负责补建保底记录，不在这里递归走切换链路。
        # 真正的激活由调用方按当前流程继续处理，避免 default 缺失时再次回到 activate_profile
        # 造成启动阶段的补建链路绕回自身。
        if str(getattr(settings.config, "current_profile_id", "") or "").strip() == "":
            settings.set("current_profile_id", "default")

    def _ensure_user_data_structure(self, user_data_path: str) -> str:
        """
        统一收敛 user_data_path 的目录策略。
        允许目标目录不存在，只要其父目录可落盘，就在保存时自动补齐 Config / Saves 结构。
        """
        normalized_path = self._normalize_user_data_path(user_data_path)
        parent_dir = os.path.dirname(normalized_path)
        if parent_dir and not os.path.exists(parent_dir):
            raise ValueError(f"Parent path not found: {parent_dir}")
        root = UserDataRoot.from_raw(normalized_path, default_roots=GameManager.get_default_user_data_paths())
        os.makedirs(root.root_path, exist_ok=True)
        os.makedirs(root.config_dir, exist_ok=True)
        os.makedirs(root.saves_dir, exist_ok=True)
        return root.root_path

    def _normalize_user_data_path(self, user_data_path: str) -> str:
        """
        所有持久化入口统一使用“用户数据根目录”语义。

        这里只对默认路径类误填做自动纠偏；其它疑似子路径直接失败，
        避免把用户的自定义路径猜错。
        """
        normalized_input = str(user_data_path or "").strip()
        # 环境路径可为空；空值代表“尚未初始化”，由前端提示用户补全，
        # 这里不能把它当成结构错误，否则 default 保底环境会在启动阶段崩溃。
        if not normalized_input:
            return ""
        return UserDataRoot.from_raw(
            normalized_input,
            default_roots=GameManager.get_default_user_data_paths(),
        ).root_path

    def _profile_snapshot_path(self, profile_id: str) -> Path:
        return DATA_DIR / "profiles" / str(profile_id or "").strip() / "profile.json"

    def _snapshot_profile_data(self, profile: GameProfile | Any):
        data = model_to_dict(profile)
        data['created_time'] = data.get('created_time')
        data['last_played_time'] = data.get('last_played_time')
        return data

    def _write_profile_snapshot(self, profile: GameProfile | Any):
        snapshot_path = self._profile_snapshot_path(getattr(profile, "id", ""))
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(self._snapshot_profile_data(profile), f, indent=2, ensure_ascii=False)
        return str(snapshot_path)

    def create_profile(self, data: Dict[str, Any], copy_current_data: bool = False):
        """
        创建新版本环境
        :param copy_current_data: 是否从当前环境复制 Config 和 Saves 到新环境作为初始状态
        """
        game_install_path = normalize_path_for_storage(data.get('game_install_path'))
        # 验证游戏安装路径是否存在
        if not GameManager.detect_executable(game_install_path):
            raise ValueError(f"Game executable not found: {game_install_path}")
        profile_id = uuid.uuid4().hex
        # 规划数据隔离目录 (例如存放在 data/profiles/<id>)
        # 注意：这里使用绝对路径
        data_dir = self._ensure_user_data_structure(
            data.get('user_data_path') or str(DATA_DIR / "profiles" / profile_id)
        )
        install_facts = self._get_install_inspector().inspect(game_install_path)
        runtime_flags = normalize_profile_runtime_flags(
            install_facts.is_steam,
            data.get('prefer_steam_launch') if 'prefer_steam_launch' in data else None,
            data.get('use_workshop_mods') if 'use_workshop_mods' in data else None,
            default_prefer_steam_launch=install_facts.is_steam,
            default_use_workshop_mods=False,
        )
        
        # 如果需要继承数据
        if copy_current_data:
            current_user_data_path = getattr(self.current_profile, 'user_data_path', '') if self.current_profile else ''
            current_config_dir = os.path.join(current_user_data_path, "Config") if current_user_data_path else ''
            if current_config_dir and os.path.exists(current_config_dir):
                self._clone_user_data(current_config_dir, data_dir)
        
        with db.atomic():
            profile = GameProfile.create(
                id=profile_id,
                name=data.get('name', 'Profile'),
                description=data.get('description', ''),
                user_data_path=data_dir,
                game_install_path=game_install_path,
                game_version=install_facts.game_version or GameManager.get_game_version(game_install_path),
                prefer_steam_launch=runtime_flags['prefer_steam_launch'],
                use_workshop_mods=runtime_flags['use_workshop_mods'],
                use_self_mods=data.get('use_self_mods', False), # 默认不加载 Self Mod
                is_steam=runtime_flags['is_steam'],
                run_commands=data.get('run_commands', [])
            )
        # 同步到磁盘
        self._sync_profile_to_disk(profile)
        return profile
    
    def update_profile(self, profile_id: str, data: Dict[str, Any]):
        """更新环境配置"""
        # 验证 Profile ID 是否存在
        if not profile_id:  raise ValueError("Profile ID is required")
        # 验证 Profile 是否在数据库中
        if profile_id not in [p.id for p in GameProfile.select()]: 
            raise ValueError(f"Profile not found: {profile_id}")
        profile = self.get_profile(profile_id)
        # 过滤掉非环境字段
        clean_data = {k: v for k, v in data.items() if k in self.PROFILE_KEYS}
        if not clean_data: return False
        # 验证字段有效性
        # valid_field_names = set(GameProfile._meta.fields.keys()) # type: ignore
        # clean_data = {k: v for k, v in data.items() if k in valid_field_names}
        # if 'id' in clean_data: del clean_data['id']
        if 'user_data_path' in clean_data:
            clean_data['user_data_path'] = self._ensure_user_data_structure(clean_data['user_data_path'])
        if 'game_install_path' in clean_data:
            clean_data['game_install_path'] = normalize_path_for_storage(clean_data['game_install_path'])
            if not os.path.exists(clean_data['game_install_path']):
                raise ValueError(f"Path not found: {clean_data['game_install_path']}")
            install_facts = self._get_install_inspector().inspect(clean_data['game_install_path'], force=True)
            clean_data['game_version'] = install_facts.game_version or GameManager.get_game_version(clean_data['game_install_path'])
            clean_data['is_steam'] = install_facts.is_steam

        target_is_steam = bool(clean_data.get('is_steam', getattr(profile, 'is_steam', False)))
        prefer_input = (
            clean_data.get('prefer_steam_launch')
            if 'prefer_steam_launch' in clean_data
            else (None if 'game_install_path' in clean_data else getattr(profile, 'prefer_steam_launch', False))
        )
        workshop_input = (
            clean_data.get('use_workshop_mods')
            if 'use_workshop_mods' in clean_data
            else getattr(profile, 'use_workshop_mods', False)
        )
        runtime_flags = normalize_profile_runtime_flags(
            target_is_steam,
            prefer_input,
            workshop_input,
            default_prefer_steam_launch=target_is_steam,
            default_use_workshop_mods=False,
        )
        # 更新阶段同样强制走统一归一化：
        # 1. 安装路径变化时，重新以探测结果决定默认 Steam 启动值；
        # 2. 用户手动开启 Steam 启动时，Workshop 链接部署开关立即归零；
        # 3. 非 Steam 正版副本不保留 `prefer_steam_launch=True` 的脏状态。
        clean_data['prefer_steam_launch'] = runtime_flags['prefer_steam_launch']
        clean_data['use_workshop_mods'] = runtime_flags['use_workshop_mods']
        clean_data['is_steam'] = runtime_flags['is_steam']
                
        query = GameProfile.update(**clean_data).where(GameProfile.id == profile_id)
        query.execute()
        # 获取更新后的对象并同步到磁盘
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if profile: self._sync_profile_to_disk(profile)
        return True

    def update_version(self):
        """检查环境游戏版本是否与当前游戏版本匹配"""
        if not self.current_profile: return False
        new_version = GameManager.get_game_version(self.current_profile.game_install_path)
        if self.current_profile.game_version == new_version: return False
        self.current_profile.game_version = new_version
        self.current_profile.save()
        return True

    def delete_profile(self, profile_id, force: bool = False):
        """删除环境 (及隔离区数据)。默认移入回收站，force=True 时彻底删除。"""
        if profile_id == 'default':
            raise Exception("无法删除默认环境")
            
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile: return False
        # 1. 删除隔离文件
        default_profile = self.get_profile('default')
        if profile.user_data_path and os.path.exists(profile.user_data_path) and (Path(profile.user_data_path) != Path(default_profile.user_data_path)):
            try:
                delete_fs_path(profile.user_data_path, force=force)
            except Exception as e:
                logger.warning(f"清理配置数据失败：{e}")
        # 2. 删库
        profile.delete_instance()
        # 3. 如果删的是当前激活的，回退到 default
        if settings.config.current_profile_id == profile_id:
            self.activate_profile('default')
            
        return True
    
    def get_profile(self, profile_id: str) -> GameProfile:
        """获取指定 Profile 对象"""
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")
        return profile

    def get_current_profile(self) -> GameProfile:
        """获取当前激活的 Profile 对象"""
        pid = settings.config.current_profile_id
        profile = GameProfile.get_or_none(GameProfile.id == pid)
        if not profile:
            # 兜底：获取第一个
            profile = GameProfile.select().first()
            if profile and settings.config.current_profile_id != profile.id:
                settings.set('current_profile_id', profile.id)
        return profile

    def build_profile_context(self, profile_id: str) -> ProfileContext:
        """
        为指定环境构造只读 Context。
        这个过程不会修改当前激活环境，也不会写回 settings。
        """
        if not profile_id:
            profile_id = 'default'
        profile = self.get_profile(profile_id)
        install_facts = self._get_install_inspector().quick_inspect(profile.game_install_path)
        runtime_flags = normalize_profile_runtime_flags(
            bool(getattr(profile, 'is_steam', False)),
            getattr(profile, 'prefer_steam_launch', None),
            getattr(profile, 'use_workshop_mods', None),
            default_prefer_steam_launch=bool(getattr(profile, 'is_steam', False)),
            default_use_workshop_mods=False,
        )
        context = ProfileContext(
            profile_id=profile.id,
            game_version=profile.game_version,
            game_install_path=profile.game_install_path,
            user_data_path=self._normalize_user_data_path(profile.user_data_path),
            prefer_steam_launch=runtime_flags['prefer_steam_launch'],
            use_workshop_mods=runtime_flags['use_workshop_mods'],
            use_self_mods=profile.use_self_mods,
            inactive_mods_order=list(profile.inactive_mods_order or []),
            temp_mods_order=list(getattr(profile, 'temp_mods_order', []) or []),
            is_steam=runtime_flags['is_steam'],
            is_steam_managed=install_facts.is_steam_managed,
        )
        # 这里把“持久化事实 + 动态事实”一起封进上下文：
        # - `is_steam` 来自已缓存/迁移后的真实探测结果；
        # - `is_steam_managed` 每次按路径动态计算，承接旧语义。
        object.__setattr__(context, 'runtime_capabilities', resolve_profile_runtime_capabilities(context))
        context.validate_health()
        return context
    
    def get_all_profiles(self):
        """获取所有 Profile 对象"""
        res = list(GameProfile.select().dicts())
        # 遍历环境对象检测路径是否存在
        for profile in res:
            install_facts = self._get_install_inspector().quick_inspect(profile.get('game_install_path', ''))
            runtime_flags = normalize_profile_runtime_flags(
                bool(profile.get('is_steam')),
                profile.get('prefer_steam_launch'),
                profile.get('use_workshop_mods'),
                default_prefer_steam_launch=bool(profile.get('is_steam')),
                default_use_workshop_mods=False,
            )
            profile['prefer_steam_launch'] = runtime_flags['prefer_steam_launch']
            profile['use_workshop_mods'] = runtime_flags['use_workshop_mods']
            profile['is_steam_managed'] = install_facts.is_steam_managed
            profile_context_stub = type("ProfileStub", (), {
                "is_steam": runtime_flags['is_steam'],
                "is_steam_managed": install_facts.is_steam_managed,
                "prefer_steam_launch": runtime_flags['prefer_steam_launch'],
                "use_workshop_mods": runtime_flags['use_workshop_mods'],
            })()
            profile['runtime_capabilities'] = resolve_profile_runtime_capabilities(profile_context_stub)
            # 验证游戏安装路径是否有效
            check_install = PathChecker.check_install_path(profile.get('game_install_path',''))
            # 验证用户数据路径是否有效
            check_data = PathChecker.check_user_data_path(profile.get('user_data_path',''))
            if not check_install['pass'] or not check_data['pass']: 
                msg = (check_install['msg'] if not check_install['pass'] else "") + (check_data['msg'] if not check_data['pass'] else '') + " 环境路径可能被删除，请重新配置或删除环境。"
                profile['msg'] = msg.strip()
                profile['check'] = False
                
            else:
                profile['check'] = True
                profile['msg'] = None
                
        return res
    
    def activate_profile(self, profile_id) -> ProfileContext:
        """
        切换当前环境
        这会影响：
        1. Settings 中的 game_config_path 指向
        2. ModScanner 对 Core/DLC 的判定路径
        3. LoadOrderManager 读取的 XML 文件位置
        """
        if not profile_id: profile_id = 'default'
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile and profile_id == 'default':
            # default 是系统保底环境；如果记录被误删，这里直接补建，
            # 避免启动、回退、外部接管等任何依赖 default 的流程整体崩溃。
            self._ensure_default_profile()
            profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile: raise ValueError("环境不存在")   # 检测环境数据是否存在
        # 验证游戏安装路径是否有效
        check_install = PathChecker.check_install_path(profile.game_install_path)
        # 验证用户数据路径是否有效
        check_data = PathChecker.check_user_data_path(profile.user_data_path)
        install_path = str(profile.game_install_path or "").strip()
        user_data_path = str(profile.user_data_path or "").strip()
        # 空路径表示环境尚未初始化，允许前端接管并引导用户补全；
        # 只有“用户已经填了值，但值本身无效”时，才阻止切换到该环境。
        has_invalid_install = bool(install_path) and not check_install['pass']
        has_invalid_user_data = bool(user_data_path) and not check_data['pass']
        if (has_invalid_install or has_invalid_user_data) and profile_id != 'default':
            msg = f"""{check_install['msg'] if not check_install['pass'] else ""}\n{check_data['msg'] if not check_data['pass'] else ''}"""
            raise ValueError(msg.strip())
        
        self.current_profile = profile
        self.update_version()
        if settings.config.current_profile_id != profile.id:
            settings.set('current_profile_id', profile.id)

        # 2. 实例化并校验沙盒上下文
        return self.build_profile_context(profile.id)
        
    
    def get_launch_args(self, profile_id: str = '', include_executable: bool = True):
        """
        获取启动参数
        :param profile_id: 环境ID，默认当前环境
        :param include_executable: 是否包含游戏可执行文件路径
        :return: 启动参数列表
        """
        if not profile_id:
            profile_id = self.current_profile.id
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile: return []
        args = []
        if include_executable:
            args.append(GameManager.detect_executable(profile.game_install_path) or '')
        # 只要环境显式绑定了用户数据根目录，就始终把 savedatafolder 注入启动参数。
        default_user_data_path = GameManager.auto_detect_paths().get('user_data_path','')
        profile_root = self._normalize_user_data_path(profile.user_data_path) if profile.user_data_path else ""
        is_default_root = False
        if default_user_data_path and profile_root:
            is_default_root = UserDataRoot.from_raw(
                default_user_data_path,
                default_roots=GameManager.get_default_user_data_paths(),
            ).equivalent_to(profile_root)
        if profile_root and not is_default_root:
            args.append(f"-savedatafolder={os.path.abspath(profile_root)}")
        # 合并自定义参数
        run_commands = getattr(profile, "run_commands", None) or []
        if run_commands: args.extend(run_commands)

        return args

    def _clone_user_data(self, src_config_dir, target_root):
        """复制存档和配置到新隔离区"""
        # src_config_dir 通常是 .../LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config
        # 需要复制 Config 和 Saves
        src_root = os.path.dirname(src_config_dir) # 回退一级
        try:
            # 复制 Config
            shutil.copytree(os.path.join(src_root, "Config"), os.path.join(target_root, "Config"), dirs_exist_ok=True)
            # `copy_current_data` 语义应完整复制当前环境的 Config 与 Saves。
            saves_dir = os.path.join(src_root, "Saves")
            if os.path.exists(saves_dir):
                shutil.copytree(saves_dir, os.path.join(target_root, "Saves"), dirs_exist_ok=True)
        except Exception as e:
            logger.error(f"克隆数据失败：{e}")
            
    def _sync_profile_to_disk(self, profile: GameProfile):
        """
        将 Profile 配置写入隔离区的 profile.json
        相当于物理“存档”
        """
        try:
            # 统一把快照写到应用数据目录，避免污染真实用户数据根目录。
            self._write_profile_snapshot(profile)
        except Exception as e:
            logger.error(f"同步配置到磁盘失败：{e}")
            
    def scan_orphaned_profiles(self):
        """
        扫描 profiles 目录，寻找数据库中不存在但磁盘上存在的配置
        返回: List[Dict] (可以直接用于展示给用户确认导入)
        """
        profiles_root = DATA_DIR / "profiles"
        if not profiles_root.exists(): return []

        orphans = []
        
        # 获取数据库中已有的所有 ID
        existing_ids = set(p.id for p in GameProfile.select(GameProfile.id))

        # 遍历目录
        for entry in os.scandir(profiles_root):
            if entry.is_dir():
                json_path = os.path.join(entry.path, "profile.json")
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 检查 ID 是否冲突
                        # 情况 1: 文件夹名就是 ID，且数据库里没有 -> 孤儿
                        # 情况 2: data['id'] 数据库里没有 -> 孤儿
                        pid = data.get('id', entry.name)
                        
                        if pid not in existing_ids:
                            # 额外检查：路径有效性校验 (可选)
                            # 如果游戏本体都被删了，可能标个 invalid
                            is_valid = GameManager.detect_executable(data.get('game_install_path', '')) is not None
                            data['_is_valid'] = is_valid
                            data['_folder_path'] = entry.path # 记录物理位置
                            orphans.append(data)
                            
                    except Exception as e:
                        logger.error(f"读取配置失败：{entry.name}，错误：{e}")
        
        return orphans

    def import_profile_from_disk(self, profile_data):
        """
        将扫描到的 json 数据重新写入数据库
        """
        try:
            # 数据清洗，防止脏数据
            # 转换时间字符串回 datetime 对象
            if 'created_time' in profile_data and isinstance(profile_data['created_time'], str):
                try:
                    profile_data['created_time'] = datetime.fromisoformat(profile_data['created_time'])
                except: del profile_data['created_time']
            
            # 移除临时字段
            profile_data.pop('_is_valid', None)
            profile_data.pop('_folder_path', None)

            # 确保 ID 存在
            if 'id' not in profile_data: return False, "Profile data missing ID"

            valid_field_names = set(GameProfile._meta.fields.keys()) # type: ignore[attr-defined]
            clean_data = {key: value for key, value in profile_data.items() if key in valid_field_names}
            if 'user_data_path' in clean_data:
                clean_data['user_data_path'] = self._normalize_user_data_path(clean_data['user_data_path'])

            install_path = str(clean_data.get('game_install_path') or '').strip()
            install_facts = None
            if install_path:
                normalized_install_path = normalize_path_for_storage(install_path)
                clean_data['game_install_path'] = normalized_install_path
                install_facts = self._get_install_inspector().inspect(normalized_install_path, force=True)
            detected_is_steam = bool(install_facts.is_steam) if install_facts else False
            runtime_flags = normalize_profile_runtime_flags(
                detected_is_steam,
                clean_data.get('prefer_steam_launch', True),
                clean_data.get('use_workshop_mods', False),
                default_prefer_steam_launch=True,
                default_use_workshop_mods=False,
            )
            clean_data['prefer_steam_launch'] = runtime_flags['prefer_steam_launch']
            clean_data['use_workshop_mods'] = runtime_flags['use_workshop_mods']
            clean_data['is_steam'] = runtime_flags['is_steam']
            if install_facts and install_facts.game_version:
                clean_data['game_version'] = install_facts.game_version
             
            with db.atomic():
                # 使用 upsert 防止并发冲突
                GameProfile.insert(**clean_data).on_conflict_replace().execute()
             
            return True, "导入成功"
        except Exception as e: return False, str(e)
            

