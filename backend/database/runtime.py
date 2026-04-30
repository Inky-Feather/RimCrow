import json
import os
import shutil
import sqlite3

from playhouse.migrate import SqliteMigrator, migrate
from peewee import DatabaseError

from backend._version import __db_version__, __version__
from backend.database.models import SystemInfo, all_models, db
from backend.utils.logger import logger
from backend.utils.tools import current_ms


def _is_database_corruption_message(message: str) -> bool:
    """判断异常是否属于数据库损坏。"""
    text = str(message or "").lower()
    keywords = [
        "malformed",
        "corrupt",
        "not a database",
        "integrity check failed",
        "missing from index",
        "wrong # of entries in index",
        "rowid",
    ]
    return any(keyword in text for keyword in keywords)


# SystemInfo 是系统元信息表，重置业务数据时不应依赖 all_models 的注册顺序去“跳过第一个”；
# 这里显式列出可清空/可重建的业务表，避免后续模型顺序调整时把逻辑带偏。
NON_SYSTEM_MODELS = [model for model in all_models if model is not SystemInfo]


def ensure_minimum_startup_data(conn: sqlite3.Connection):
    """
    补齐数据库最小可启动数据。
    目的：
    1. 保证系统版本元数据始终存在且与当前程序一致。
    2. 保证 default 环境始终存在，避免修复后或重置后因缺默认环境而启动异常。
    说明：
    这里用原生 sqlite3 写入，便于同时复用于 Peewee 当前连接和修复库连接。
    """
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO systeminfo(key, value) VALUES (?, ?)", ('db_version', __db_version__))
    cursor.execute("INSERT OR REPLACE INTO systeminfo(key, value) VALUES (?, ?)", ('app_version', __version__))

    default_profile_exists = cursor.execute(
        "SELECT 1 FROM gameprofile WHERE id = ? LIMIT 1",
        ('default',)
    ).fetchone()
    if not default_profile_exists:
        cursor.execute(
            """
            INSERT INTO gameprofile(
                id, name, description, game_version, game_install_path, user_data_path,
                run_commands, prefer_steam_launch, use_workshop_mods, use_self_mods, is_steam,
                inactive_mods_order, last_played_time, created_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                'default',
                'Default',
                'Default Profile',
                '',
                '',
                '',
                json.dumps([], ensure_ascii=False),
                1,
                1,
                0,
                0,
                json.dumps([], ensure_ascii=False),
                0,
                current_ms(),
            )
        )
    conn.commit()


def init_db(db_path):
    """
    初始化数据库。
    这里只负责连接、建表、迁移和基础完整性检查，不再承担修复流程编排。
    """
    db_exists = os.path.exists(db_path)
    try:
        db.init(db_path, pragmas={
            'journal_mode': 'wal',
            'cache_size': -1024 * 64,
            'synchronous': 'normal',
            'foreign_keys': 'on'
        }, timeout=30)
        db.connect(reuse_if_open=True)

        if db_exists:
            try:
                integrity_row = db.execute_sql('PRAGMA integrity_check(1);').fetchone()
                integrity_result = str(integrity_row[0]) if integrity_row else 'unknown'
                if integrity_result.lower() != 'ok':
                    raise DatabaseError(f"Integrity check failed: {integrity_result}")
            except Exception as e:
                raise DatabaseError(f"Integrity check failed: {e}")

        db.execute_sql('PRAGMA foreign_keys = OFF;')
        auto_upgrade_schema(db, all_models)
        db.create_tables(all_models, safe=True)
        db.execute_sql('PRAGMA foreign_keys = ON;')

        current_db_version = __db_version__
        version_record = SystemInfo.get_or_none(SystemInfo.key == 'db_version')
        if version_record:
            old_v = version_record.value
        else:
            cursor = db.execute_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='mod';")
            if cursor.fetchone():
                old_v = "2"
            else:
                old_v = None

        if old_v is None:
            SystemInfo.create(key='db_version', value=current_db_version)
        elif old_v != current_db_version:
            logger.info(f"检测到版本更新: {old_v} -> {current_db_version}. 正在备份并升级...")
            shutil.copy2(db_path, db_path + ".bak")
            db.execute_sql('PRAGMA foreign_keys = OFF;')
            from backend.database.migrator import run_migrations
            run_migrations(old_v)
            db.execute_sql('PRAGMA foreign_keys = ON;')

        return True
    except (DatabaseError, Exception) as e:
        if _is_database_corruption_message(str(e)):
            logger.error(f"检测到数据库损坏，当前初始化终止: {e}", exc_info=True)
        else:
            logger.error(f"数据库连接失败: {e}", exc_info=True)
        return False


def close_db():
    """安全关闭当前数据库连接并清理 WAL/SHM。"""
    if db.is_closed():
        logger.info("数据库已关闭")
        return
    try:
        db.execute_sql('PRAGMA wal_checkpoint(TRUNCATE);')
        db.execute_sql('PRAGMA journal_mode=DELETE;')
    except Exception as e:
        logger.warning(f"关闭数据库前执行 checkpoint/journal_mode 失败，将继续强制断开连接: {e}", exc_info=True)
    finally:
        try:
            if not db.is_closed():
                db.close()
            logger.info("数据库已安全关闭并清理临时文件")
        except Exception as close_error:
            logger.error(f"强制关闭数据库连接失败: {close_error}", exc_info=True)


def clear_db():
    """
    清空数据库。
    为了防止数据残留或锁死，采用：关闭外键 -> Drop -> Vacuum -> Create 的流程。
    """
    try:
        if db.is_closed():
            db.connect()

        db.execute_sql('PRAGMA foreign_keys = OFF;')
        with db.atomic():
            db.drop_tables(NON_SYSTEM_MODELS)

        db.execute_sql('VACUUM;')
        with db.atomic():
            db.create_tables(NON_SYSTEM_MODELS, safe=True)

        # 重置后需要把系统最小启动数据补回去，保证后续初始化和环境装载稳定。
        ensure_minimum_startup_data(db.connection())

        db.execute_sql('PRAGMA foreign_keys = ON;')
        return True
    except Exception as e:
        logger.error(f"清空数据库时出错: {e}", exc_info=True)
        return False


def validate_database_file(db_path, require_tables=True):
    """使用原生 sqlite3 对数据库文件做基础有效性校验。"""
    if not db_path or not os.path.exists(db_path):
        return False, f"数据库文件不存在: {db_path}"

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        row = cursor.execute('PRAGMA integrity_check(1);').fetchone()
        if not row or str(row[0]).lower() != 'ok':
            return False, f"integrity_check 失败: {row[0] if row else '无返回结果'}"

        if require_tables:
            existing_tables = {
                str(item[0]).lower()
                for item in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
            }
            required_tables = {m._meta.table_name.lower() for m in all_models}
            missing_tables = sorted(required_tables - existing_tables)
            if missing_tables:
                return False, f"缺少必要数据表: {', '.join(missing_tables)}"

        return True, "ok"
    except Exception as e:
        return False, str(e)
    finally:
        if conn:
            conn.close()


def auto_upgrade_schema(database, models):
    """自动检测并添加模型中新增的字段。"""
    migrator = SqliteMigrator(database)

    for model in models:
        table_name = model._meta.table_name
        if not database.table_exists(table_name):
            continue
        try:
            columns = [f.name for f in database.get_columns(table_name)]
        except Exception:
            continue

        fields = model._meta.fields
        for field_name, field_obj in fields.items():
            column_name = field_obj.column_name
            if column_name not in columns:
                logger.info(f"检测到新字段: {table_name}.{column_name}, 正在自动添加...")
                try:
                    with database.atomic():
                        migrate(migrator.add_column(table_name, column_name, field_obj))
                    logger.info(f"表 {table_name} 的 {column_name} 字段结构同步成功")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info(f"字段或索引已存在，安全跳过: {e}")
                    else:
                        logger.error(f"表 {table_name} 同步字段 {column_name} 失败: {e}", exc_info=True)
