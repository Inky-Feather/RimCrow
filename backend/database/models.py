import json
from peewee import Model, Field, SqliteDatabase, CharField, TextField, DateTimeField, ForeignKeyField, BooleanField, IntegerField, CompositeKey
from playhouse.sqlite_ext import JSONField

db = SqliteDatabase(None)

class BaseModel(Model):
    class Meta:
        database = db

# 2. 定义一个不转义中文的 JSONField
class UTF8JSONField(Field):
    field_type = 'TEXT'  # 在 SQLite 中存为 TEXT
    # 【关键】python_value 负责从数据库读取时的转换
    def python_value(self, value):
        if value is None:
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    # 【关键】db_value 负责写入数据库时的转换
    def db_value(self, value):
        if value is None:
            return None
        # ensure_ascii=False 允许 JSON 序列化非 ASCII 字符（如中文、日文、特殊符号等）
        return json.dumps(value, ensure_ascii=False)


class Mod(BaseModel):
    """
    存储从磁盘扫描到的 Mod 固有信息 (只读/缓存性质)
    """
    # 核心标识
    package_id = CharField(primary_key=True, index=True) # 包名，如 "ludeon.rimworld" (全小写)
    workshop_id = CharField(null=True)              # 创意工坊ID
    name = CharField()                              # 名称
    author = UTF8JSONField(default=list)                  # 作者，可能为多人
    version = CharField(null=True)                  # Mod版本
    description = TextField(null=True)              # Mod描述
    
    # 路径与来源
    path = CharField()                              # 本地储存路径，绝对路径
    url = CharField(null=True)                      # 网络地址，如 github 仓库地址、steam 创意工坊地址
    source = CharField(default='local')             # 来源，如 steam, local, git, dlc, other
    icon_path = CharField(null=True)                # 图标路径
    preview_path = CharField(null=True)             # 预览图片路径
    gallery_paths = UTF8JSONField(default=list)           # 画廊图片路径列表，包括本地或网络路径 ['img1.jpg', 'img2.jpg']
    
    # 深度扫描信息 (使用 JSON 存列表，方便扩展)
    supported_versions = UTF8JSONField(default=list)      # 支持游戏版本 ['1.4', '1.5']
    supported_languages = UTF8JSONField(default=list)     # 支持的语言 ['zh-cn', 'en']
    file_stats = UTF8JSONField(default=dict)              # 文件统计 {'xml_count': 50, 'dll_count': 50, 'img_count': 50, 'audio_count': 50}
    mod_type = CharField(default='XML')             # Mod类型，如 'Assembly', 'XML', 'LanguagePack'
    dependencies_mods = UTF8JSONField(null=True)        # 依赖Mod ['ludeon.rimworld','ludeon.rimworld2']
    load_after_mods = UTF8JSONField(default=list)         # 前置Mod ['ludeon.rimworld','ludeon.rimworld2']
    load_before_mods = UTF8JSONField(default=list)        # 后置Mod ['ludeon.rimworld','ludeon.rimworld2']
    incompatible_mods = UTF8JSONField(default=list)       # 不兼容Mod ['ludeon.rimworld','ludeon.rimworld2']
    save_breaking = IntegerField(default=0)         # 是否破坏存档 (ModSync)，-1: 破坏, 0：未知, 1: 不破坏 
    
    # 时间戳 (用于增量扫描)
    mod_update_time = DateTimeField(null=True)      # mod更新时间（通常为steam workshop），用于记录提示
    file_create_time = DateTimeField(null=True)     # 文件创建时间，用于记录提示
    file_modify_time = DateTimeField(null=True)     # 文件修改时间，用于增量扫描更新
    last_active_time = DateTimeField(null=True)     # 上次启用时间，用于排查错误时找到最近启用的Mod
    last_moved_time = DateTimeField(null=True)      # 上次调整顺序的时间，用于排查错误时找到最近的修改点

class UserModData(BaseModel):
    """
    存储用户对 Mod 的自定义数据 (与 Mod 表 1对1，避免重新扫描时丢失)
    """
    mod_id = ForeignKeyField(Mod, backref='user_data', on_delete='CASCADE') # 外键关联 Mod 表
    alias_name = CharField(null=True)           # 别名
    notes = TextField(null=True)                # 用户备注
    tags = UTF8JSONField(default=list)          # 用户打的标签 ['排队必备', '前置']
    sign_color = CharField(null=True)           # 标记颜色，用于在UI中分类突显
    lock_previous_mod = TextField(null=True)    # 联锁的前一个Mod包名，用于固定两个Mod的顺序
    lock_next_mod = TextField(null=True)        # 联锁的后一个Mod包名，用于固定两个Mod的顺序
    
    # 这里可以添加 'category' 字段，如果一个 Mod 只能属一个主分类
    
class GroupData(BaseModel):
    """
    用户自定义的分组 (如: "硬核生存包", "魔法包")
    """
    group_id = TextField(primary_key=True)   # 分组ID，主键 uuid
    name = CharField(default='New Group')            # 分组名称
    color = CharField(default='#ffffff')   # 分组颜色，用于在UI中分类突显
    sort_index = IntegerField(default=0)     # 分组在UI的显示顺序
    is_expanded = BooleanField(default=True) # UI折叠状态

class GroupMod(BaseModel):
    """
    分组与 Mod 的多对多关系表 (Junction Table)
    """
    group_id = ForeignKeyField(GroupData, backref='mods', on_delete='CASCADE')
    mod_id = ForeignKeyField(Mod, backref='groups', on_delete='CASCADE')
    sort_index = IntegerField(default=0) # Mod 在该分组内的排序

    class Meta:
        # 联合主键，防止同一个 Mod 在同一个组里出现两次
        primary_key = CompositeKey('group_id', 'mod_id')

def init_db(db_path):
    """初始化数据库"""
    db.init(db_path, pragmas={
        'journal_mode': 'wal',  # 提高并发读写性能
        'cache_size': -1024 * 64
    })
    db.connect()    # 连接数据库
    # safe=True 表示表存在则不创建
    db.create_tables([Mod, UserModData, GroupData, GroupMod], safe=True)
    # db.close()  # 关闭数据库连接