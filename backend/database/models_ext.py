# backend/database/models_ext.py
import json
import os

from peewee import BigIntegerField, CharField, Field, IntegerField, Model, SqliteDatabase, TextField
from playhouse.migrate import SqliteMigrator, migrate

from backend.settings import DATA_DIR
from backend.utils.logger import logger

# 建立独立的外部数据缓存库。
# 表按职责拆分为三类：
# 1. 文件快照表：保存离线文件导入的稳定元数据与依赖关系；
# 2. 在线缓存表：保存 Steam Web API 补充的展示字段与同步时间；
# 3. 导入状态表：保存文件变更判定所需的元数据。
ext_db = SqliteDatabase(None)

# 定义一个不转义中文的 JSONField
class UTF8JSONField(Field):
    field_type = "TEXT"

    def python_value(self, value):
        # 从 SQLite 读出 TEXT 后，自动反序列化为 Python 对象，
        # 这样上层始终按 list / dict 使用，不需要重复 json.loads。
        if value is None:
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value

    def db_value(self, value):
        # 写入时统一转成 JSON 文本，并保留中文原文，
        # 便于日志排查和人工查看数据库内容。
        if value is None: return None
        # ensure_ascii=False 允许 JSON 序列化非 ASCII 字符（如中文、日文、特殊符号等）
        return json.dumps(value, ensure_ascii=False)


class ExtBaseModel(Model):
    class Meta:
        database = ext_db


class WorkshopManifest(ExtBaseModel):
    """
    外置文件快照层。

    设计原因：
    - 这张表只保存来自 `steamDB.json` 的“静态身份与依赖关系”；
    - 文件一旦变化，可以整表重建，不需要顾虑 Steam 在线缓存是否被覆盖；
    - 规则系统、包名反查、依赖补全都应只依赖这层数据。
    """

    workshop_id = CharField(primary_key=True)
    package_id = CharField(index=True, collation="NOCASE", null=True)
    name = CharField(null=True)
    author = CharField(null=True)
    game_versions = UTF8JSONField(default=list)
    dependencies_mods = UTF8JSONField(default=dict)


class WorkshopOnlineCache(ExtBaseModel):
    """
    Steam Web API 在线缓存层。

    设计原因：
    - 这张表只保存标题、长描述、封面、截图、云端更新时间等在线补充信息；
    - 它是 TTL 缓存，不应该随着文件快照重建而被一起删除；
    - 这样文件导入阶段可以直接重建 `WorkshopManifest`，不会误删在线缓存内容。
    """

    workshop_id = CharField(primary_key=True)
    title = CharField(null=True)
    short_description = TextField(null=True)
    description = TextField(null=True)
    author_steam_id = CharField(null=True)
    preview_url = CharField(null=True)
    tags = UTF8JSONField(default=list)
    children = UTF8JSONField(default=list)
    screenshots = UTF8JSONField(default=list)
    time_created = BigIntegerField(default=0)
    time_updated = BigIntegerField(default=0)
    subscriptions = IntegerField(default=0)
    favorited = IntegerField(default=0)
    lifetime_subscriptions = IntegerField(default=0)
    lifetime_favorited = IntegerField(default=0)
    views = IntegerField(default=0)
    summary_last_sync_time = BigIntegerField(default=0)
    detail_last_sync_time = BigIntegerField(default=0)
    last_sync_time = BigIntegerField(default=0)


class ModReplacement(ExtBaseModel):
    """映射 replacements.json / replacements.json.gz。"""

    old_workshop_id = CharField(index=True, null=True)
    old_package_id = CharField(index=True, collation="NOCASE", null=True)
    old_name = CharField(null=True)
    old_author = CharField(null=True)
    new_workshop_id = CharField(null=True)
    new_package_id = CharField(null=True)
    new_name = CharField(null=True)
    old_versions = UTF8JSONField(default=list)
    new_versions = UTF8JSONField(default=list)


class ExtDatasetState(ExtBaseModel):
    """
    外置数据集导入状态表。

    设计目标：
    - 启动时只用文件元数据快速判断“是否值得重建”；
    - 记录上次导入结果，避免每次启动都重新解析几十 MB 的文件；
    - 后续如需升级导入结构，可通过 `import_schema_version` 强制触发一次重建。
    """

    dataset_name = CharField(primary_key=True)
    source_path = CharField(null=True)
    file_size = BigIntegerField(default=0)
    file_mtime = BigIntegerField(default=0)
    source_version = CharField(null=True)
    import_schema_version = IntegerField(default=1)
    row_count = IntegerField(default=0)
    last_import_time = BigIntegerField(default=0)


EXT_MODELS = [
    WorkshopManifest,
    WorkshopOnlineCache,
    ModReplacement,
    ExtDatasetState,
]
def init_ext_db():
    """初始化外部数据库连接与表结构。"""
    db_path = os.path.join(DATA_DIR, "workshop_cache.db")
    try:
        ext_db.init(
            db_path,
            pragmas={
                "journal_mode": "wal",
                "cache_size": -1024 * 64,
                "synchronous": "normal",
            },
        )
        ext_db.connect(reuse_if_open=True)
        ext_db.create_tables(EXT_MODELS, safe=True)
        # 启动阶段只自动补齐缺失列，保证新增字段可被现有库结构识别。
        # 删列、改类型等破坏性结构变更不在这里执行。
        auto_upgrade_schema(ext_db, EXT_MODELS)
        return True
    except Exception as e:
        logger.error(f"初始化外置数据库失败: {e}", exc_info=True)
        return False


def auto_upgrade_schema(db, models):
    """
    自动检测并添加模型中新增的字段。

    这里仅处理“缺列补列”，不处理删列、改类型等高风险结构变更，
    这样可以避免启动阶段误做破坏性迁移。
    """
    migrator = SqliteMigrator(db)
    for model in models:
        table_name = model._meta.table_name
        # 1. 获取数据库中现有的列名
        try:
            columns = [f.name for f in db.get_columns(table_name)]
        except Exception:
            continue
        # 2. 遍历模型定义的字段
        fields = model._meta.fields
        operations = []
        for _, field_obj in fields.items():
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
                logger.error(f"表 {table_name} 结构同步失败: {e}", exc_info=True)
