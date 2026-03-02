# backend/database/models_ext.py
import os
import json
from playhouse.migrate import SqliteMigrator, migrate
from peewee import BigIntegerField, Model, CharField, SqliteDatabase, TextField, Field
from backend.settings import DATA_DIR
from backend.utils.logger import logger
from backend.utils.tools import current_ms

# 建立独立的外部数据缓存库
ext_db = SqliteDatabase(None)

# 定义一个不转义中文的 JSONField
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

class ExtBaseModel(Model):
    class Meta:
        database = ext_db


class WorkshopMeta(ExtBaseModel):
    """映射 steamDB.json"""
    workshop_id = CharField(primary_key=True)
    package_id = CharField(index=True, collation='NOCASE', null=True)
    name = CharField(null=True)
    title = CharField(null=True)
    author = CharField(null=True)
    game_versions = UTF8JSONField(default=list)
    dependencies_mods = UTF8JSONField(default=dict) # 格式: {"2891845502": "Alpha Genes"}
    description = TextField(null=True)       # BBCode 格式简介
    preview_url = CharField(null=True)       # 高清封面
    screenshots = UTF8JSONField(default=list) # 截图 URL 列表
    time_updated = BigIntegerField(default=0)# 云端最新修改时间
    last_sync_time = BigIntegerField(default=0) # 上次拉取 Steam API 的时间
    
class ModReplacement(ExtBaseModel):
    """映射 replacements.json"""
    old_workshop_id = CharField(index=True, null=True)
    old_package_id = CharField(index=True, collation='NOCASE', null=True)
    new_workshop_id = CharField(null=True)
    new_package_id = CharField(null=True)
    new_name = CharField(null=True)
    old_versions = UTF8JSONField(default=list)
    new_versions = UTF8JSONField(default=list)



def init_ext_db():
    """初始化外部数据库连接"""
    db_path = os.path.join(DATA_DIR, 'workshop_cache.db')
    try:
        ext_db.init(db_path, pragmas={
            'journal_mode': 'wal',
            'cache_size': -1024 * 64,
            'synchronous': 'normal'
        })
        ext_db.connect()
        all_models = [WorkshopMeta, ModReplacement]
        ext_db.create_tables(all_models, safe=True)
        # 【核心】自动同步字段变动 (解决 no such column 报错)
        auto_upgrade_schema(ext_db, all_models)
        return True
    except Exception as e:
        logger.error(f"初始化外置数据库失败: {e}")
        return False
    
def auto_upgrade_schema(db, models):
    """
    自动检测并添加模型中新增的字段
    """
    migrator = SqliteMigrator(db)
    for model in models:
        table_name = model._meta.table_name
        # 1. 获取数据库中现有的列名
        try:
            columns = [f.name for f in db.get_columns(table_name)]
        except:
            # 如果表还不存在，跳过，由 create_tables 处理
            continue
        # 2. 遍历模型定义的字段
        fields = model._meta.fields
        operations = []
        for field_name, field_obj in fields.items():
            column_name = field_obj.column_name
            if column_name not in columns:
                logger.info(f"检测到新字段: {table_name}.{column_name}, 正在自动添加...")
                # 生成添加列的操作
                operations.append(migrator.add_column(table_name, column_name, field_obj))
        # 3. 执行迁移操作
        if operations:
            try:
                migrate(*operations)
                logger.info(f"表 {table_name} 结构同步成功")
            except Exception as e:
                logger.error(f"表 {table_name} 结构同步失败: {e}")
    
    