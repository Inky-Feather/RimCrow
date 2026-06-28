import json
from typing import Optional, cast

from peewee import (
    BigIntegerField,
    BooleanField,
    CharField,
    CompositeKey,
    Field,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

from backend.utils.tools import current_ms

db = SqliteDatabase(None)

MOD_ASSET_STATE_PRESENT = "present"
MOD_ASSET_STATE_MISSING = "missing"


class BaseModel(Model):
    class Meta:
        database = db


class UTF8JSONField(Field):
    """
    不转义中文的 JSONField。
    目的：让数据库中的 JSON 文本保持可读，避免日志和调试时全是 unicode 转义。
    """
    field_type = 'TEXT'

    def python_value(self, value):
        if value is None:
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value

    def db_value(self, value):
        if value is None: return None
        return json.dumps(value, ensure_ascii=False)


class GameProfile(BaseModel):
    """游戏环境配置方案"""
    id = cast(str, CharField(primary_key=True))
    name = cast(str, CharField())
    description = cast(str, TextField(null=True))
    game_version = cast(str, CharField(null=True))
    game_install_path = cast(str, CharField())
    user_data_path = cast(str, CharField())
    run_commands = cast(list[str], UTF8JSONField(default=list))
    prefer_steam_launch = cast(bool, BooleanField(default=False))
    use_workshop_mods = cast(bool, BooleanField(default=False))
    use_self_mods = cast(bool, BooleanField(default=False))
    is_steam = cast(bool, BooleanField(default=False))
    inactive_mods_order = cast(list[str], UTF8JSONField(default=list))
    temp_mods_order = cast(list[str], UTF8JSONField(default=list))
    last_played_time = cast(int, BigIntegerField(default=0))
    created_time = cast(int, BigIntegerField(default=current_ms))


class ModAsset(BaseModel):
    """存储从磁盘扫描到的 Mod 固有信息"""
    path_hash = cast(str, CharField(primary_key=True))
    package_id = cast(str, CharField(index=True, collation='NOCASE'))
    package_id_raw = cast(str, CharField(null=True))
    workshop_id = cast(str, CharField(null=True))
    name = cast(str, CharField())
    author = cast(list[str], UTF8JSONField(default=list))
    version = cast(str, CharField(null=True))
    description = cast(str, TextField(null=True))
    descriptions_by_version = cast(dict, UTF8JSONField(default=dict))

    path = cast(str, CharField())
    url = cast(str, CharField(null=True))
    source = cast(str, CharField(default='local'))
    store = cast(str, CharField(default='local'))
    # 库存状态只描述物理资产是否仍可用；About.xml.disabled 仍由 disabled 字段表达。
    state = cast(str, CharField(default=MOD_ASSET_STATE_PRESENT, index=True))
    icon_path = cast(str, CharField(null=True))
    preview_path = cast(str, CharField(null=True))
    gallery_paths = cast(list[str], UTF8JSONField(default=list))

    supported_versions = cast(list[str], UTF8JSONField(default=list))
    supported_languages = cast(list[str], UTF8JSONField(default=list))
    file_stats = cast(dict, UTF8JSONField(default=dict))
    mod_type = cast(str, CharField(default='XML'))
    dependencies_mods = cast(list[dict], UTF8JSONField(default=list))
    load_after_mods = cast(list[dict], UTF8JSONField(default=list))
    load_before_mods = cast(list[dict], UTF8JSONField(default=list))
    incompatible_mods = cast(list[dict], UTF8JSONField(default=list))
    save_breaking = cast(Optional[bool], BooleanField(default=None, null=True))

    mod_update_time = cast(int, BigIntegerField(default=0))
    file_create_time = cast(int, BigIntegerField(default=0))
    file_modify_time = cast(int, BigIntegerField(default=0))
    last_active_time = cast(int, BigIntegerField(default=0))
    last_moved_time = cast(int, BigIntegerField(default=0))
    last_seen_at = cast(int, BigIntegerField(default=0))
    last_scanned_at = cast(int, BigIntegerField(default=0))
    file_size = cast(int, BigIntegerField(default=0))

    shadow_paths = cast(list[str], UTF8JSONField(default=list))
    disabled = cast(bool, BooleanField(default=False))


class ModInterlock(BaseModel):
    """存储固定的 Mod 联锁序列"""
    id = cast(str, CharField(primary_key=True))
    chain = cast(list[str], UTF8JSONField(default=list))


class UserModData(BaseModel):
    """存储用户对 Mod 的自定义数据"""
    mod_id = cast(str, CharField(primary_key=True, collation='NOCASE'))
    alias_name = cast(Optional[str], CharField(null=True))
    notes = cast(Optional[str], TextField(null=True))
    tags = cast(list[str], UTF8JSONField(default=list))
    sign_color = cast(Optional[str], CharField(null=True))
    user_mod_type = cast(Optional[str], CharField(null=True))
    interlock_id = cast(Optional[str], ForeignKeyField(ModInterlock, null=True, backref='mods', on_delete='SET NULL'))
    ignored_issues = cast(list[str], UTF8JSONField(default=list))


class GroupData(BaseModel):
    """用户自定义的分组"""
    group_id = cast(str, TextField(primary_key=True))
    name = cast(str, CharField(default='New Group'))
    color = cast(str, CharField(default='#ffffff'))
    sort_index = cast(int, IntegerField(default=0))
    is_expanded = cast(bool, BooleanField(default=True))


class GroupMod(BaseModel):
    """分组与 Mod 的多对多关系表"""
    group_id = cast(str, ForeignKeyField(GroupData, backref='mods', on_delete='CASCADE'))
    mod_id = cast(str, ForeignKeyField(UserModData, backref='groups', on_delete='CASCADE', collation='NOCASE'))
    sort_index = cast(int, IntegerField(default=0))

    class Meta:
        primary_key = CompositeKey('group_id', 'mod_id')


class GithubModRecord(BaseModel):
    """Git 仓库模组订阅记录"""
    repo_url = CharField(primary_key=True)
    provider = CharField(default="github")
    host = CharField(default="github.com")
    owner = CharField()
    repo_name = CharField()
    install_type = CharField(default="source")
    target_branch = CharField(default="main")
    installed_version = CharField(null=True)
    local_folder = CharField(null=True)
    online_info_cache = cast(dict, UTF8JSONField(default=dict))
    last_sync_time = cast(int, BigIntegerField(default=0))


class GithubTimeline(BaseModel):
    """主动记录的 GitHub 操作时间线"""
    repo_url = CharField(index=True)
    time = BigIntegerField(default=current_ms)
    action = CharField()
    message = TextField()


class SubscribedCollection(BaseModel):
    """用户收藏/订阅的合集"""
    id = cast(str, CharField(primary_key=True))
    title = cast(str, CharField(null=True))
    description = cast(str, TextField(null=True))
    preview_url = cast(str, CharField(null=True))
    total = cast(int, IntegerField(default=0))
    time_updated = cast(int, BigIntegerField(default=0))
    created_time = cast(int, BigIntegerField(default=current_ms))
    last_sync_time = cast(int, BigIntegerField(default=0))
    children = cast(list, UTF8JSONField(default=list))


class SystemInfo(BaseModel):
    key = cast(str, CharField(primary_key=True))
    value = cast(str, CharField())


all_models = [
    SystemInfo,
    GroupMod,
    GroupData,
    ModInterlock,
    UserModData,
    ModAsset,
    GameProfile,
    GithubTimeline,
    GithubModRecord,
    SubscribedCollection,
]
