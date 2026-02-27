# backend/database/models_ext.py
import os
import json
from peewee import Model, CharField, SqliteDatabase, TextField, Field
from backend.settings import DATA_DIR
from backend.utils.logger import logger

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
    author = CharField(null=True)
    game_versions = UTF8JSONField(default=list)
    dependencies_mod = UTF8JSONField(default=dict) # 格式: {"2891845502": "Alpha Genes"}

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
        ext_db.create_tables([WorkshopMeta, ModReplacement], safe=True)
        return True
    except Exception as e:
        logger.error(f"初始化外置数据库失败: {e}")
        return False