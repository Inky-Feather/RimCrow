
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
from backend.managers.mgr_game import GameManager
from backend.settings import BACKUP_DIR, settings, DATA_DIR
from backend.utils.logger import logger 
from backend.utils.tools import delete_fs_path


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
    
    is_healthy: bool = True
    health_report: dict = field(default_factory=dict) 
    
    # 动态计算出来的绝对路径（初始化时即确定，拒绝中途修改）
    @property
    def local_mods_path(self): return str(Path(self.game_install_path) / "Mods")
    @property
    def game_dlc_path(self): return str(Path(self.game_install_path) / "Data")
    @property
    def game_config_path(self): return str(Path(self.user_data_path) / "Config")
    @property
    def game_saves_path(self): return str(Path(self.user_data_path) / "Saves")
    @property
    def mods_config_file(self): return str(Path(self.game_config_path) / "ModsConfig.xml")
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
        'last_played_time'
    }
    
    def __init__(self):
        self._ensure_default_profile()
        self.current_profile = GameProfile.get_or_none(GameProfile.id == settings.config.current_profile_id)
        self.update_version()

    def _ensure_default_profile(self):
        """确保至少有一个默认 Profile (通常是当前设置的 Steam 版)"""
        if GameProfile.select().count() == 0:
            # 默认数据路径
            with db.atomic():
                GameProfile.create(
                    id='default',
                    name='Default',
                    description='Default Profile',
                    game_install_path='',
                    user_data_path='',
                    game_version='',
                    is_steam=False,
                    prefer_steam_launch=True,
                    use_workshop_mods=True, # 默认非Steam版不加载工坊
                    use_self_mods=False,    # 默认不加载 Self Mod
                    run_commands=[]
                )
            self.activate_profile('default')  # 切换到默认环境

    def create_profile(self, data: Dict[str, Any], copy_current_data: bool = False):
        """
        创建新版本环境
        :param copy_current_data: 是否从当前环境复制 Config 和 Saves 到新环境作为初始状态
        """
        # 验证游戏安装路径是否存在
        if not GameManager.detect_executable(data.get('game_install_path')):
            raise ValueError(f"Game executable not found: {data.get('game_install_path')}")
        profile_id = uuid.uuid4().hex
        # 规划数据隔离目录 (例如存放在 data/profiles/<id>)
        # 注意：这里使用绝对路径
        data_dir = data.get('user_data_path') or str(DATA_DIR / "profiles" / profile_id)
        # 检测路径是否存在，然后初始化目录结构
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        game_config_path = os.path.join(data_dir, "Config")
        if not os.path.exists(game_config_path):
            os.makedirs(game_config_path)
        game_saves_path = os.path.join(data_dir, "Saves")
        if not os.path.exists(game_saves_path):
            os.makedirs(game_saves_path)
        
        isSteam = os.path.normpath(data.get('game_install_path','')).lower().rfind(os.path.join('steamapps', 'common')) != -1
        
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
                game_install_path=data.get('game_install_path'),
                game_version=GameManager.get_game_version(data.get('game_install_path')),
                prefer_steam_launch=bool(data.get('prefer_steam_launch', isSteam)),
                use_workshop_mods=data.get('use_workshop_mods', False),
                use_self_mods=data.get('use_self_mods', False), # 默认不加载 Self Mod
                is_steam=isSteam,
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
        # 过滤掉非环境字段
        clean_data = {k: v for k, v in data.items() if k in self.PROFILE_KEYS}
        if not clean_data: return False
        # 验证字段有效性
        # valid_field_names = set(GameProfile._meta.fields.keys()) # type: ignore
        # clean_data = {k: v for k, v in data.items() if k in valid_field_names}
        # if 'id' in clean_data: del clean_data['id']
        if('game_install_path' in clean_data):
            clean_data['game_version'] = GameManager.get_game_version(clean_data.get('game_install_path'))
            clean_data['is_steam'] = os.path.normpath(clean_data.get('game_install_path','')).lower().rfind(os.path.join('steamapps', 'common')) != -1
        if('use_workshop_mods' in clean_data):
            clean_data['use_workshop_mods'] = True if profile_id =='default' else clean_data.get('use_workshop_mods', False)
        
        path_fields = ['user_data_path', 'game_install_path']
        # 验证路径有效性
        for field in path_fields:
            if field in clean_data:
                if not os.path.exists(clean_data[field]):
                    raise ValueError(f"Path not found: {clean_data[field]}")
                clean_data[field] = os.path.normpath(clean_data[field])
                
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
        if self.current_profile.game_version == new_version:
            return False
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
                logger.warning(f"Failed to clean up profile data: {e}")
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
        context = ProfileContext(
            profile_id=profile.id,
            game_version=profile.game_version,
            game_install_path=profile.game_install_path,
            user_data_path=profile.user_data_path,
            prefer_steam_launch=bool(getattr(profile, 'prefer_steam_launch', True)),
            use_workshop_mods=profile.use_workshop_mods,
            use_self_mods=profile.use_self_mods,
            inactive_mods_order=list(profile.inactive_mods_order or []),
        )
        context.validate_health()
        return context
    
    def get_all_profiles(self):
        """获取所有 Profile 对象"""
        res = list(GameProfile.select().dicts())
        # 遍历环境对象检测路径是否存在
        for profile in res:
            # 验证游戏安装路径是否有效
            check_install = PathChecker.check_install_path(profile.get('game_install_path',''))
            # 验证用户数据路径是否有效
            check_data = PathChecker.check_normal_path(profile.get('user_data_path',''))
            if not check_install['pass'] or not check_data['pass']: 
                self.activate_profile('default')
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
        if not profile: raise ValueError("环境不存在")   # 检测环境数据是否存在
        # 验证游戏安装路径是否有效
        check_install = PathChecker.check_install_path(profile.game_install_path)
        # 验证用户数据路径是否有效
        check_data = PathChecker.check_normal_path(profile.user_data_path)
        if (not check_install['pass'] or not check_data['pass']) and profile_id != 'default': 
            self.activate_profile('default')
            msg = f"""{check_install['msg'] if not check_install['pass'] else ""}\n{check_data['msg'] if not check_data['pass'] else ''}"""
            raise ValueError(msg.strip())
        
        self.current_profile = profile
        self.update_version()
        if settings.config.current_profile_id != profile.id:
            settings.set('current_profile_id', profile.id)

        # 2. 实例化并校验沙盒上下文
        return self.build_profile_context(profile.id)
        
    
    def get_launch_args(self, profile_id: str = ''):
        """
        获取启动参数
        :param profile_id: 环境ID，默认当前环境
        :return: 启动参数列表
        """
        if not profile_id:
            profile_id = self.current_profile.id
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile: return []
        # 获取当前 Profile 的 EXE 路径
        args = [GameManager.detect_executable(profile.game_install_path) or '']
        # 核心：注入数据隔离参数（非默认环境）
        if profile.user_data_path and profile_id != 'default':
            # 必须使用绝对路径，并处理可能的空格（Popen 会自动处理列表项的空格）
            args.append(f"-savedatafolder={os.path.abspath(profile.user_data_path)}")
        # 合并自定义参数
        if profile.run_commands:
            args.extend(profile.run_commands)
            
        return args
    
    def get_launch_args_only(self, profile_id: str = ''):
        """
        获取当前 Profile 的命令行参数（不含 EXE 路径）
        :param profile_id: 环境ID，默认当前环境
        """
        args = self.get_launch_args(profile_id)[1:]
        return args

    def _clone_user_data(self, src_config_dir, target_root):
        """复制存档和配置到新隔离区"""
        # src_config_dir 通常是 .../LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config
        # 需要复制 Config 和 Saves
        src_root = os.path.dirname(src_config_dir) # 回退一级
        try:
            # 复制 Config
            shutil.copytree(os.path.join(src_root, "Config"), os.path.join(target_root, "Config"), dirs_exist_ok=True)
            # 复制 Saves (可选，或者询问用户)
            # shutil.copytree(os.path.join(src_root, "Saves"), os.path.join(target_root, "Saves"), dirs_exist_ok=True)
        except Exception as e:
            logger.error(f"Clone data failed: {e}")
            
    def _sync_profile_to_disk(self, profile: GameProfile):
        """
        将 Profile 配置写入隔离区的 profile.json
        相当于物理“存档”
        """
        # 1. 如果没有自定义隔离路径（例如使用系统默认路径的 Default 环境），则不写入
        # 防止污染用户的 AppData
        if not profile.user_data_path or not os.path.exists(profile.user_data_path):
            return

        json_path = os.path.join(profile.user_data_path, "profile.json")
        
        try:
            # 2. 序列化模型
            # Peewee 的 model_to_dict 会把 datetime 对象转好，但为了保险手动处理一下非 JSON 类型
            data = model_to_dict(profile)
            
            # 处理 datetime 转字符串
            data['created_time'] = data.get('created_time')
            data['last_played_time'] = data.get('last_played_time')

            # 3. 写入文件
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            # logger.info(f"Profile synced to disk: {json_path}")
        except Exception as e:
            logger.error(f"Failed to sync profile to disk: {e}")
            
    def scan_orphaned_profiles(self):
        """
        扫描 profiles 目录，寻找数据库中不存在但磁盘上存在的配置
        返回: List[Dict] (可以直接用于展示给用户确认导入)
        """
        profiles_root = DATA_DIR / "profiles"
        if not profiles_root.exists():
            return []

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
                        logger.error(f"Error reading profile {entry.name}: {e}")
        
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
            if 'id' not in profile_data:
                return False, "Profile data missing ID"

            with db.atomic():
                # 使用 upsert 防止并发冲突
                GameProfile.insert(**profile_data).on_conflict_replace().execute()
            
            return True, "导入成功"
        except Exception as e:
            return False, str(e)
            

