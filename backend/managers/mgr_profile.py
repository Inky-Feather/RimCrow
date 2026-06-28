from datetime import datetime
import json
import os
from typing import Any, Dict
import uuid
import shutil
import subprocess
from playhouse.shortcuts import model_to_dict
from backend.database.dao import ModDAO
from backend.database.models import GameProfile, db
from backend.managers.mgr_game import GameManager
from backend.settings import settings, CONFIG_DIR
from backend.utils.logger import logger 


class ProfileManager:
    def __init__(self):
        self.current_profile = GameProfile.get_or_none(GameProfile.id == settings.config.current_profile_id)
        self.update_version()
        self._ensure_default_profile()

    def _ensure_default_profile(self):
        """确保至少有一个默认 Profile (通常是当前设置的 Steam 版)"""
        if GameProfile.select().count() == 0:
            # 默认数据路径
            with db.atomic():
                GameProfile.create(
                    id='default',
                    name='Default',
                    description='Default Profile',
                    user_data_path=settings.config.user_data_path,
                    game_install_path=settings.config.game_install_path,
                    game_version=GameManager.get_game_version(settings.config.game_install_path),
                    use_workshop_mods="steamlibrary" in settings.config.game_install_path.lower() # 默认非Steam版不加载工坊
                )
            self.activate_profile('default')  # 切换到默认环境
        else:
            self._update_paths(self.current_profile)    # 更新默认profile的路径

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
        data_dir = data.get('user_data_path') or str(CONFIG_DIR / "profiles" / profile_id)
        
        # 检测路径是否存在，然后初始化目录结构
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        game_config_path = os.path.join(data_dir, "Config")
        if not os.path.exists(game_config_path):
            os.makedirs(game_config_path)
        game_saves_path = os.path.join(data_dir, "Saves")
        if not os.path.exists(game_saves_path):
            os.makedirs(game_saves_path)
            
        # 如果需要继承数据
        if copy_current_data:
            self._clone_user_data(settings.config.game_config_path, data_dir)
        
        with db.atomic():
            profile = GameProfile.create(
                id=profile_id,
                name=data.get('name', 'Profile'),
                description=data.get('description', ''),
                user_data_path=data_dir,
                game_install_path=data.get('game_install_path', settings.config.game_install_path),
                game_version=GameManager.get_game_version(data.get('game_install_path', settings.config.game_install_path)),
                use_workshop_mods=data.get('use_workshop_mods', False)
            )
        # 同步到磁盘
        self._sync_profile_to_disk(profile)
        return profile
    
    def update_profile(self, profile_id: str, data: Dict[str, Any]):
        """更新环境配置"""
        if profile_id not in [p.id for p in GameProfile.select()]: 
            raise ValueError(f"Profile not found: {profile_id}")
        if 'id' in data: del data['id']
        data['game_version'] = GameManager.get_game_version(data.get('game_install_path', settings.config.game_install_path))
        query = GameProfile.update(**data).where(GameProfile.id == profile_id)
        query.execute()
        # 获取更新后的对象并同步到磁盘
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if profile:
            self._sync_profile_to_disk(profile)
        return True

    def update_version(self):
        """检查环境游戏版本是否与当前游戏版本匹配"""
        if not self.current_profile: return False
        self.current_profile.game_version = GameManager.get_game_version(self.current_profile.game_install_path)
        self.current_profile.save()

    def delete_profile(self, profile_id):
        """删除环境 (及隔离区数据)"""
        if profile_id == 'default':
            raise Exception("无法删除默认环境")
            
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile: return False
        # 1. 删除隔离文件
        if profile.user_data_path and os.path.exists(profile.user_data_path):
            try:
                shutil.rmtree(profile.user_data_path)
            except Exception as e:
                logger.warning(f"Failed to clean up profile data: {e}")

        # 2. 删库
        profile.delete_instance()
        # 3. 如果删的是当前激活的，回退到 default
        if settings.config.current_profile_id == profile_id:
            self.activate_profile('default')
            
        return True

    def get_current_profile(self) -> GameProfile:
        """获取当前激活的 Profile 对象"""
        pid = settings.config.current_profile_id
        profile = GameProfile.get_or_none(GameProfile.id == pid)
        if not profile:
            # 兜底：获取第一个
            profile = GameProfile.select().first()
            if profile:
                settings.set('current_profile_id', profile.id)
        return profile
    
    def get_all_profiles(self):
        """获取所有 Profile 对象"""
        return list(GameProfile.select().dicts())
    
    def activate_profile(self, profile_id):
        """
        切换当前环境
        这会影响：
        1. Settings 中的 game_config_path 指向
        2. ModScanner 对 Core/DLC 的判定路径
        3. LoadOrderManager 读取的 XML 文件位置
        """
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile: return False
        self.current_profile = profile
        self.update_version()
        self._update_paths(profile)
        return True
        
    def _update_paths(self, profile):
        # 动态更新全局设置中的路径，指向隔离区
        settings.config.current_profile_id = profile.id
        
        # 指向隔离环境的 Config 目录
        settings.config.game_version = profile.game_version
        # 更新游戏安装目录（用于扫描 mod
        settings.config.game_install_path = profile.game_install_path
        settings.config.local_mods_path = os.path.join(profile.game_install_path, "Mods")
        settings.config.game_dlc_path = os.path.join(profile.game_install_path, "Data")
        # RimWorld 的结构是: <Root>/Config, <Root>/Saves
        settings.config.user_data_path = profile.user_data_path
        # 检测路径是否存在
        if os.path.exists(profile.user_data_path):
            settings.config.game_config_path = os.path.join(profile.user_data_path, "Config")
            if not os.path.exists(settings.config.game_config_path):
                os.makedirs(settings.config.game_config_path)
            settings.config.game_saves_path = os.path.join(profile.user_data_path, "Saves")
            if not os.path.exists(settings.config.game_saves_path):
                os.makedirs(settings.config.game_saves_path)
        
        # 控制是否扫描工坊
        settings.config.use_workshop_mods = profile.use_workshop_mods if profile.id != 'default' else True
        
        # 强制持久化到 config.json
        settings.save()
        

    def get_launch_args(self, profile_id: str = ''):
        """
        获取启动参数
        :param profile_id: 环境ID，默认当前环境
        :return: 启动参数列表
        """
        if not profile_id:
            profile_id = self.current_profile.id
        if profile_id == 'default': return []
        profile = GameProfile.get_or_none(GameProfile.id == profile_id)
        if not profile: return []
        args = [GameManager.detect_executable(str(profile.game_install_path))]
        # 核心：注入数据隔离参数
        if profile.user_data_path:
            args.append(f"-savedatafolder={str(profile.user_data_path)}")
            
        return args
    def get_launch_args_only(self):
        """
        获取当前 Profile 的命令行参数（不含 EXE 路径）
        """
        profile = self.get_current_profile()
        args = []
        
        # 隔离存档与配置目录 (核心)
        if profile and profile.id != 'default':
            # 必须使用绝对路径，并处理可能的空格（Popen 会自动处理列表项的空格）
            data_path = os.path.abspath(str(profile.user_data_path))
            args.append(f"-savedatafolder={data_path}")
            
        # 可以在此处添加其他参数，如 -nomousegrab 等
        return args

    def _clone_user_data(self, src_config_dir, target_root):
        """复制存档和配置到新隔离区"""
        # src_config_dir 通常是 .../LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config
        # 我们需要复制 Config 和 Saves
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
        if not profile.user_data_path or not os.path.exists(str(profile.user_data_path)):
            return

        json_path = os.path.join(str(profile.user_data_path), "profile.json")
        
        try:
            # 2. 序列化模型
            # Peewee 的 model_to_dict 会把 datetime 对象转好，但为了保险我们手动处理一下非 JSON 类型
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
        profiles_root = CONFIG_DIR / "profiles"
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
            

