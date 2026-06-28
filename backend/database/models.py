import json
from peewee import Model, Field, SqliteDatabase, CharField, TextField, DateTimeField, ForeignKeyField, BooleanField, IntegerField, CompositeKey
from backend._version import __db_version__

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
    author = UTF8JSONField(default=list)            # 作者，可能为多人
    version = CharField(null=True)                  # Mod版本
    description = TextField(null=True)              # Mod描述
    
    # 路径与来源
    path = CharField()                              # 本地储存路径，绝对路径
    url = CharField(null=True)                      # 网络地址，如 github 仓库地址、steam 创意工坊地址
    source = CharField(default='local')             # 来源，如 steam, local, git, dlc, other
    icon_path = CharField(null=True)                # 图标路径
    preview_path = CharField(null=True)             # 预览图片路径
    gallery_paths = UTF8JSONField(default=list)     # 画廊图片路径列表，包括本地或网络路径 ['img1.jpg', 'img2.jpg']
    
    # 深度扫描信息 (使用 JSON 存列表，方便扩展)
    supported_versions = UTF8JSONField(default=list)      # 支持游戏版本 ['1.4', '1.5']
    supported_languages = UTF8JSONField(default=list)     # 支持的语言 ['zh-cn', 'en']
    file_stats = UTF8JSONField(default=dict)              # 文件统计 {'xml_count': 50, 'dll_count': 50, 'img_count': 50, 'audio_count': 50}
    mod_type = CharField(default='XML')                   # Mod类型，如 'Assembly', 'XML', 'LanguagePack'
    dependencies_mods = UTF8JSONField(null=True)          # 依赖Mod ['ludeon.rimworld','ludeon.rimworld2']
    load_after_mods = UTF8JSONField(default=list)         # 前置Mod ['ludeon.rimworld','ludeon.rimworld2']
    load_before_mods = UTF8JSONField(default=list)        # 后置Mod ['ludeon.rimworld','ludeon.rimworld2']
    incompatible_mods = UTF8JSONField(default=list)       # 不兼容Mod ['ludeon.rimworld','ludeon.rimworld2']
    save_breaking = IntegerField(default=0)               # 是否破坏存档 (ModSync)，-1: 破坏, 0：未知, 1: 不破坏 
    
    # 时间戳 (用于增量扫描)
    mod_update_time = DateTimeField(null=True)      # mod更新时间（通常为steam workshop），用于记录提示
    file_create_time = DateTimeField(null=True)     # 文件创建时间，用于记录提示
    file_modify_time = DateTimeField(null=True)     # 文件修改时间，用于增量扫描更新
    last_active_time = DateTimeField(null=True)     # 上次启用时间，用于排查错误时找到最近启用的Mod
    last_moved_time = DateTimeField(null=True)      # 上次调整顺序的时间，用于排查错误时找到最近的修改点
    
    # 存储重复但被禁用(About.xml.disabled)的同名Mod路径
    # 格式: ["D:/Mods/Harmony_Old", "E:/Steam/Harmony"]
    shadow_paths = UTF8JSONField(default=list)

class UserModData(BaseModel):
    """
    存储用户对 Mod 的自定义数据 (与 Mod 表 1对1，避免重新扫描时丢失)
    """
    mod_id = ForeignKeyField(Mod, backref='user_data', on_delete='CASCADE', primary_key=True) # 外键关联 Mod 表
    alias_name = CharField(null=True)           # 别名
    notes = TextField(null=True)                # 用户备注
    tags = UTF8JSONField(default=list)          # 用户打的标签 ['排队必备', '前置']
    sign_color = CharField(null=True)           # 标记颜色，用于在UI中分类突显
    user_mod_type = CharField(null=True)        # Mod类型，如 'Assembly', 'XML', 'LanguagePack'
    lock_previous_mod = TextField(null=True)    # 联锁的前一个Mod包名，用于固定两个Mod的顺序
    lock_next_mod = TextField(null=True)        # 联锁的后一个Mod包名，用于固定两个Mod的顺序
    ignored_issues = UTF8JSONField(default=list)      # 存储忽略的问题 Key 列表 ["id:type:target", ...]
    
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

class SystemInfo(BaseModel):
    key = CharField(primary_key=True)
    value = CharField()

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
    # 检查数据库版本
    CURRENT_DB_VERSION = __db_version__ 
    try:
        ver_record = SystemInfo.get_or_none(SystemInfo.key == 'db_version')
        if not ver_record:
            # 新库，写入版本
            SystemInfo.create(key='db_version', value=CURRENT_DB_VERSION)
        elif ver_record.value != CURRENT_DB_VERSION:
            # 版本不匹配！需要迁移或重置
            print(f"数据库版本过期: {ver_record.value} -> {CURRENT_DB_VERSION}")
            pass 
    except Exception as e:
        print(f"DB Version check failed: {e}")
    
    
def clear_db():
    """
    清空数据库
    为了防止数据残留或锁死，采用：关闭外键 -> Drop -> Vacuum -> Create 的流程。
    """
    try:
        # 1. 确保连接是打开的
        if db.is_closed():
            db.connect()
        
        # 2. 临时关闭外键约束 (防止删除顺序导致的报错)
        db.execute_sql('PRAGMA foreign_keys = OFF;')
        
        # 3. 显式开启事务
        with db.atomic():
            # 删除所有表 (cascade=True 会处理外键依赖，但 SQLite 对 cascade 支持有限，
            # 所以我们手动按依赖顺序删，或者直接 drop_tables)
            # 注意顺序：先删依赖别人的(GroupMod, UserModData)，再删被依赖的(Mod, GroupData)
            db.drop_tables([GroupMod, UserModData, Mod, GroupData])
        
        # 4. 【关键】执行 VACUUM
        # 这会物理清除数据库文件中的所有数据页，重置所有自增 ID，
        # 并强制同步 WAL 文件。这相当于把 .db 文件变成了一个全新的空文件。
        # 注意：VACUUM 不能在事务块 (atomic) 内部执行。
        db.execute_sql('VACUUM;')
        
        # 5. 重新创建表
        with db.atomic():
            db.create_tables([Mod, UserModData, GroupData, GroupMod])
            
        # 6. 恢复外键约束
        db.execute_sql('PRAGMA foreign_keys = ON;')
        
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise Exception(f"清空数据库时出错: {e}")