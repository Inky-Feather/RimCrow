# backend/database/models_ext.py
import json
import os
from pathlib import Path

from peewee import BigIntegerField, CharField, Field, FloatField, IntegerField, Model, SqliteDatabase, TextField

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
    screenshots = UTF8JSONField(default=list)
    tags = UTF8JSONField(default=list)
    kv_tags = UTF8JSONField(default=list)
    children = UTF8JSONField(default=list)
    revision_change_number = BigIntegerField(default=0)
    file_size = BigIntegerField(default=0)
    # 工坊统计信息。统一保存用户可感知的计数和投票数据：
    # {
    #   "subscriptions": 订阅数,
    #   "favorited": 收藏数,
    #   "votes_up": 赞成票,
    #   "votes_down": 反对票,
    #   "vote_score": Steam 评分/投票分数,
    #   "num_reports": 举报数,
    #   "num_comments_public": 公开评论数
    # }
    stats = UTF8JSONField(default=dict)
    # 工坊项目类型。使用业务侧可读值：
    # "mod" = 普通模组，"collection" = 合集，"other" = 其它 Steam UGC 类型。
    item_type = CharField(default="mod")
    consumer_app_id = IntegerField(default=0)
    # 工坊状态信息。集中保存权限、可见性、封禁等不会参与常规排序的状态字段：
    # {
    #   "visibility": Steam 可见性枚举,
    #   "can_subscribe": 当前项目是否允许订阅,
    #   "flags": Steam 状态位,
    #   "banned": 是否被封禁,
    #   "ban_reason": 封禁原因,
    #   "ban_text_check_result": 文本检查结果,
    #   "banner": Steam 返回的横幅状态
    # }
    status = UTF8JSONField(default=dict)
    maybe_inappropriate_sex = IntegerField(default=0)
    maybe_inappropriate_violence = IntegerField(default=0)
    # 翻译缓存。以项目语言码为键，保存用户生成的展示译文。
    # 译文只按原文哈希判断是否过期，不跟随 Steam 在线缓存 TTL 刷新：
    # {
    #   "zh-CN": {
    #     "title": "译名",
    #     "description": "译文说明",
    #     "source_hash": "sha256...",
    #     "provider": "ai.default",
    #     "updated_at": 1760000000000
    #   }
    # }
    translations = UTF8JSONField(default=dict)
    playtime_stats = UTF8JSONField(null=True)
    time_created = BigIntegerField(default=0)
    time_updated = BigIntegerField(default=0)
    summary_last_sync_time = BigIntegerField(default=0)
    detail_last_sync_time = BigIntegerField(default=0)
    last_sync_time = BigIntegerField(default=0)


class WorkshopAuthorCache(ExtBaseModel):
    """
    Steam 作者资料缓存层。

    设计原因：
    - 增强搜索只稳定返回 creator SteamID，作者名称需要通过 GetPlayerSummaries 批量补齐；
    - 作者资料可被搜索结果、详情页和后续作者页复用，不应重复写进每个工坊条目。
    """

    steam_id = CharField(primary_key=True)
    personaname = CharField(null=True)
    profile_url = CharField(null=True)
    avatar = CharField(null=True)
    country_code = CharField(null=True)
    time_created = BigIntegerField(default=0)
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
    WorkshopAuthorCache,
    ModReplacement,
    ExtDatasetState,
]
def init_ext_db():
    """初始化外部数据库连接与表结构。"""
    db_path = os.path.join(DATA_DIR, "workshop_cache.db")
    try:
        _connect_ext_db(db_path)
        ext_db.create_tables(EXT_MODELS, safe=True)
        # 外置工坊库是可重建缓存。字段有删改时直接删库重建，
        # 避免旧列残留导致后续解析、排序和前端契约继续被旧结构污染。
        if not validate_ext_schema(ext_db, EXT_MODELS):
            reset_ext_db_files(db_path)
            _connect_ext_db(db_path)
            ext_db.create_tables(EXT_MODELS, safe=True)
        return True
    except Exception as e:
        logger.error(f"初始化外置数据库失败: {e}", exc_info=True)
        return False


def _connect_ext_db(db_path: str):
    """按统一参数连接外置工坊数据库。"""
    if not ext_db.is_closed():
        ext_db.close()
    ext_db.init(
        db_path,
        pragmas={
            "journal_mode": "wal",
            "cache_size": -1024 * 64,
            "synchronous": "normal",
        },
    )
    ext_db.connect(reuse_if_open=True)


def validate_ext_schema(db, models) -> bool:
    """
    严格检查外置库表结构是否与当前模型一致。

    外置库只保存可重建的工坊快照和在线缓存，因此发现旧列残留、
    缺列或表缺失时不做补丁迁移，而是交给初始化流程删库重建。
    """
    for model in models:
        table_name = model._meta.table_name
        try:
            db_columns = {column.name for column in db.get_columns(table_name)}
        except Exception as exc:
            logger.info(f"外置工坊库表 {table_name} 不可读取，将重建缓存库: {exc}")
            return False
        model_columns = {field.column_name for field in model._meta.fields.values()}
        if db_columns != model_columns:
            logger.info(
                "外置工坊库表结构不一致，将重建缓存库: %s missing=%s extra=%s",
                table_name,
                sorted(model_columns - db_columns),
                sorted(db_columns - model_columns),
            )
            return False
    return True


def reset_ext_db_files(db_path: str):
    """删除外置工坊数据库及 SQLite 旁路文件，随后由导入流程重建内容。"""
    try:
        if not ext_db.is_closed():
            ext_db.close()
    except Exception as exc:
        logger.warning(f"关闭外置工坊数据库连接失败，将继续尝试重建: {exc}", exc_info=True)

    path = Path(db_path)
    for target in [
        path,
        path.with_name(path.name + "-wal"),
        path.with_name(path.name + "-shm"),
        path.with_name(path.name + "-journal"),
    ]:
        if not target.exists():
            continue
        try:
            target.unlink()
            logger.info(f"已删除外置工坊缓存文件: {target}")
        except Exception as exc:
            logger.error(f"删除外置工坊缓存文件失败: {target}, {exc}", exc_info=True)
            raise
