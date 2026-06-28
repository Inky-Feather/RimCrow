import json
import os
import shutil
import sqlite3
import time
from collections import defaultdict, deque

from peewee import BigIntegerField, BooleanField, CharField, DatabaseError, ForeignKeyField, IntegerField, SqliteDatabase, TextField

from backend.database.models import UTF8JSONField, all_models, db
from backend.database.runtime import ensure_minimum_startup_data, init_db, validate_database_file
from backend.utils.logger import logger
from backend.utils.tools import current_ms

# 主动修复流程的临时产物：快照库、修复成功候选库、启动切换标记。
# 这里统一约定文件名后缀，便于启动阶段与手动修复阶段共用同一套清理/切换逻辑。
REPAIR_SNAPSHOT_SUFFIX = ".repair.snapshot.db"
REPAIR_READY_SUFFIX = ".repair.ready.db"
REPAIR_MARKER_SUFFIX = ".repair.ready.json"
REPAIR_FAILED_SOURCE_SUFFIX = ".repair.failed.source.db"


def _get_repair_paths(db_path):
    """统一生成修复链路使用的临时文件路径。"""
    return {
        'snapshot_path': db_path + REPAIR_SNAPSHOT_SUFFIX,
        'repaired_path': db_path + REPAIR_READY_SUFFIX,
        'marker_path': db_path + REPAIR_MARKER_SUFFIX,
        'failed_source_path': db_path + REPAIR_FAILED_SOURCE_SUFFIX,
    }


def _move_file_with_retry(src_path, dst_path, retries=10, delay=0.5):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            shutil.move(src_path, dst_path)
            return True
        except PermissionError as e:
            last_error = e
            logger.warning(f"移动文件失败，正在重试 ({attempt}/{retries}): {src_path} -> {dst_path}; {e}")
            import gc
            gc.collect()
            time.sleep(delay)
    if last_error:
        raise last_error
    return False


def _remove_file_with_retry(file_path, retries=10, delay=0.3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            if not os.path.exists(file_path): return True
            os.remove(file_path)
            return True
        except PermissionError as e:
            last_error = e
            logger.warning(f"删除文件失败，正在重试 ({attempt}/{retries}): {file_path}; {e}")
            import gc
            gc.collect()
            time.sleep(delay)
    if last_error:
        raise last_error
    return False


def _cleanup_database_sidecars(db_path):
    """清理 SQLite 的 WAL/SHM 附属文件。"""
    for ext in ['-wal', '-shm']:
        _remove_file_with_retry(db_path + ext, retries=5, delay=0.1)


def _cleanup_repair_artifacts(db_path, keep_failed_source=True):
    """清理修复过程中产生的临时文件。"""
    paths = _get_repair_paths(db_path)
    removable = ['snapshot_path', 'repaired_path', 'marker_path']
    if not keep_failed_source:
        removable.append('failed_source_path')

    for key in removable:
        path = paths[key]
        if path.endswith('.json'):
            if os.path.exists(path):
                os.remove(path)
            continue
        _remove_file_with_retry(path, retries=3, delay=0.1)
        _cleanup_database_sidecars(path)


def _create_database_snapshot_from_live_db(snapshot_path):
    """
    基于当前活动连接创建快照。
    原理：使用 sqlite backup API 读取当前连接视图，比直接复制正在使用的主库更稳定。
    """
    _remove_file_with_retry(snapshot_path, retries=3, delay=0.1)
    _cleanup_database_sidecars(snapshot_path)
    db.connect(reuse_if_open=True)
    db.execute_sql('PRAGMA wal_checkpoint(FULL);')
    src_conn = db.connection()
    dst_conn = sqlite3.connect(snapshot_path)
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()


def _create_database_snapshot_from_file(source_path, snapshot_path):
    """
    从数据库文件创建快照。
    原理：优先走 sqlite backup API 以正确吸收 WAL；若源库损坏到无法连接，再退回文件复制。
    """
    _remove_file_with_retry(snapshot_path, retries=3, delay=0.1)
    _cleanup_database_sidecars(snapshot_path)

    src_conn = None
    dst_conn = None
    try:
        src_conn = sqlite3.connect(source_path)
        dst_conn = sqlite3.connect(snapshot_path)
        src_conn.backup(dst_conn)
        return
    except Exception as e:
        logger.warning(f"源库快照 backup 失败，改为直接复制文件: {e}")
    finally:
        if dst_conn:
            dst_conn.close()
        if src_conn:
            src_conn.close()

    shutil.copy2(source_path, snapshot_path)
    for ext in ['-wal', '-shm']:
        sidecar = source_path + ext
        if os.path.exists(sidecar):
            shutil.copy2(sidecar, snapshot_path + ext)


def _bootstrap_empty_database(target_path):
    """在独立数据库文件上创建当前版本的空表结构，不影响全局 Peewee 连接。"""
    _remove_file_with_retry(target_path, retries=3, delay=0.1)
    _cleanup_database_sidecars(target_path)
    temp_db = SqliteDatabase(
        target_path,
        pragmas={
            'journal_mode': 'delete',
            'cache_size': -1024 * 64,
            'synchronous': 'normal',
            'foreign_keys': 'on'
        },
        timeout=30
    )
    with temp_db.bind_ctx(all_models):
        temp_db.connect(reuse_if_open=True)
        try:
            temp_db.create_tables(all_models, safe=True)
            # 修复目标库从创建时就补齐最小启动数据，避免后续再依赖额外分支补洞。
            ensure_minimum_startup_data(temp_db.connection())
        finally:
            if not temp_db.is_closed():
                temp_db.close()


def _sort_models_for_repair():
    """按外键依赖拓扑排序模型。"""
    models = list(all_models)
    model_set = set(models)
    dependencies = {model: set() for model in models}
    children = defaultdict(set)

    for model in models:
        for field in model._meta.fields.values():
            if isinstance(field, ForeignKeyField):
                related_model = getattr(field, 'rel_model', None)
                if related_model in model_set and related_model != model:
                    dependencies[model].add(related_model)
                    children[related_model].add(model)

    indegree = {model: len(dependencies[model]) for model in models}
    queue = deque(sorted(
        [model for model, degree in indegree.items() if degree == 0],
        key=lambda item: item._meta.table_name
    ))
    ordered = []

    while queue:
        model = queue.popleft()
        ordered.append(model)
        for child in sorted(children[model], key=lambda item: item._meta.table_name):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    remaining = [model for model in models if model not in ordered]
    ordered.extend(sorted(remaining, key=lambda item: item._meta.table_name))
    return ordered


def _resolve_field_default_for_repair(field):
    """为修复时缺失的目标字段生成默认值。"""
    if field.default is not None:
        default_value = field.default() if callable(field.default) else field.default
        return field.db_value(default_value)

    if field.null: return None

    if isinstance(field, UTF8JSONField):
        return field.db_value([] if 'list' in field.name.lower() or field.name.endswith('s') else {})
    if isinstance(field, BooleanField):
        return field.db_value(False)
    if isinstance(field, (IntegerField, BigIntegerField)):
        return field.db_value(0)
    if isinstance(field, (CharField, TextField)):
        return field.db_value('')

    return None


def _normalize_repaired_database(target_path):
    """
    对修复完成的候选数据库做收尾归一化。
    原因：修复重点是尽量保住业务数据，但系统元数据和默认 Profile 必须恢复到可启动状态。
    """
    conn = sqlite3.connect(target_path)
    try:
        # 修复完成后显式改写 app_version，避免旧坏库残留版本号被误判成一次应用升级。
        ensure_minimum_startup_data(conn)
    finally:
        conn.close()


def _apply_database_file(db_path, repaired_path, backup_suffix):
    """
    将修复好的候选数据库切换为主数据库。
    原则：先备份当前主库，再替换主库文件，最后清理 WAL/SHM，避免残留旧事务。
    """
    valid, message = validate_database_file(repaired_path, require_tables=True)
    if not valid:
        raise DatabaseError(f"待切换修复库无效: {message}")

    timestamp = int(time.time())
    backup_path = ""

    if os.path.exists(db_path):
        backup_path = f"{db_path}{backup_suffix}.{timestamp}.bak"
        _move_file_with_retry(db_path, backup_path, retries=5, delay=0.2)

    _cleanup_database_sidecars(db_path)
    _move_file_with_retry(repaired_path, db_path, retries=5, delay=0.2)
    _cleanup_database_sidecars(repaired_path)
    return backup_path


def _stage_failed_source_for_manual_repair(db_path):
    """
    把当前损坏主库转存为“手动修复源”。
    目的：启动自动修复失败后，应用仍可继续启动，同时保留原始问题库供后续手动修复使用。
    """
    paths = _get_repair_paths(db_path)
    failed_source_path = paths['failed_source_path']
    _remove_file_with_retry(failed_source_path, retries=3, delay=0.1)
    _cleanup_database_sidecars(failed_source_path)

    if os.path.exists(db_path):
        _move_file_with_retry(db_path, failed_source_path, retries=5, delay=0.2)
    _cleanup_database_sidecars(db_path)
    return failed_source_path


def repair_database_copy(source_path, target_path):
    """对数据库副本执行修复。"""
    logger.info(f"正在修复数据库副本: {source_path} -> {target_path}")
    _bootstrap_empty_database(target_path)
    rescue_database(source_path, target_path)
    _normalize_repaired_database(target_path)
    ok, message = validate_database_file(target_path, require_tables=True)
    if not ok:
        raise DatabaseError(f"修复后的数据库校验失败: {message}")
    logger.info("数据库副本修复完成")


def prepare_manual_database_repair(db_path):
    """
    设置页主动修复入口。
    目标：在不触碰当前主库的前提下准备修复结果；只有全部成功才写入待重启生效标记。
    """
    logger.info(f"用户主动触发数据库修复: {db_path}")
    paths = _get_repair_paths(db_path)
    _cleanup_repair_artifacts(db_path, keep_failed_source=True)

    if os.path.exists(paths['failed_source_path']):
        source_path = paths['failed_source_path']
        _create_database_snapshot_from_file(source_path, paths['snapshot_path'])
    elif os.path.exists(db_path):
        _create_database_snapshot_from_live_db(paths['snapshot_path'])
    else:
        logger.warning("数据库文件不存在，改为初始化空数据库")
        return {"restart_required": False, "initialized": init_db(db_path)}

    logger.info("数据库快照已准备完成，开始修复")

    try:
        repair_database_copy(paths['snapshot_path'], paths['repaired_path'])
    except Exception:
        _cleanup_repair_artifacts(db_path, keep_failed_source=True)
        raise

    with open(paths['marker_path'], 'w', encoding='utf-8') as f:
        json.dump({
            "status": "ready",
            "created_at": current_ms(),
            "source_db_path": db_path,
            "repaired_path": paths['repaired_path'],
        }, f, ensure_ascii=False, indent=2)

    return {"restart_required": True}


def apply_pending_manual_repair(db_path):
    """
    启动阶段应用已准备好的手动修复结果。
    原则：只要待生效结果无效，就清理掉标记和临时库，防止每次启动都重复卡在坏状态。
    """
    paths = _get_repair_paths(db_path)
    marker_path = paths['marker_path']
    if not os.path.exists(marker_path): return {"applied": False}

    try:
        with open(marker_path, 'r', encoding='utf-8') as f:
            marker = json.load(f)
    except Exception as e:
        logger.error(f"读取数据库修复标记失败: {e}", exc_info=True)
        _cleanup_repair_artifacts(db_path, keep_failed_source=True)
        return {"applied": False, "error": str(e)}

    repaired_path = str(marker.get('repaired_path') or paths['repaired_path'])
    try:
        _apply_database_file(db_path, repaired_path, ".before_repair_apply")
        _cleanup_repair_artifacts(db_path, keep_failed_source=False)
        logger.info(f"已在启动阶段切换修复后的数据库: {db_path}")
        return {"applied": True}
    except Exception as e:
        logger.error(f"启动阶段应用修复数据库失败: {e}", exc_info=True)
        _cleanup_repair_artifacts(db_path, keep_failed_source=True)
        return {"applied": False, "error": str(e)}


def prepare_database_for_startup(db_path):
    """
    启动前数据库预处理入口。
    时序：
    1. 先应用上一次手动修复成功后待生效的结果。
    2. 再检测当前主库是否损坏。
    3. 若损坏则尝试一次热修复；失败时保留原库供手动修复，并让应用继续启动。
    """
    result = {
        "created_clean_database": False,
        "actions_taken": [],
        "messages": [],
    }

    staged_result = apply_pending_manual_repair(db_path)
    if staged_result.get("applied"):
        result["actions_taken"].append("staged_database_repair_applied")
        result["messages"].append("上次准备好的数据库修复结果已生效。")
    elif staged_result.get("error"):
        result["messages"].append("检测到未完成的修复结果，但无法使用，已自动跳过。")

    if not os.path.exists(db_path): return result

    valid, message = validate_database_file(db_path, require_tables=False)
    if valid: return result

    logger.warning(f"启动前检测到数据库损坏，准备尝试自动修复: {message}")
    paths = _get_repair_paths(db_path)
    _cleanup_repair_artifacts(db_path, keep_failed_source=False)

    try:
        _create_database_snapshot_from_file(db_path, paths['snapshot_path'])
        logger.info("自动修复快照已准备完成，开始修复数据库")
        repair_database_copy(paths['snapshot_path'], paths['repaired_path'])
        _apply_database_file(db_path, paths['repaired_path'], ".before_auto_repair")
        _cleanup_repair_artifacts(db_path, keep_failed_source=False)
        result["actions_taken"].append("startup_database_auto_repaired")
        result["messages"].append("检测到数据库异常，软件已自动修复并继续启动。")
        return result
    except Exception as e:
        logger.error(f"启动阶段自动修复失败，将保留问题库供手动修复: {e}", exc_info=True)
        try:
            failed_source_path = _stage_failed_source_for_manual_repair(db_path)
            logger.info(f"问题库已保留为手动修复源: {failed_source_path}")
        except Exception as move_error:
            logger.error(f"保留手动修复源失败: {move_error}", exc_info=True)
            result["messages"].append("数据库异常文件处理失败，建议先备份 data 目录。")
        finally:
            _cleanup_repair_artifacts(db_path, keep_failed_source=True)

        result["created_clean_database"] = True
        result["actions_taken"].append("startup_database_auto_repair_failed")
        result["messages"].append("数据库自动修复失败，请尽快手动修复。软件将继续启动，但部分本地数据可能暂时不可用。")
        return result


def rescue_database(source_path, target_path):
    """
    使用原生 sqlite3 尝试逐表、逐行挽救数据。
    设计原则：
    1. 动态跟随当前 Peewee 模型，不把字段列表写死。
    2. 只读取源表和目标模型共有的列，新增字段自动补默认值。
    3. 单行失败不影响整表继续，尽量多捞出还能读取的数据。
    """
    src_conn = sqlite3.connect(source_path)
    dst_conn = sqlite3.connect(target_path)
    src_cursor = src_conn.cursor()
    dst_cursor = dst_conn.cursor()

    dst_cursor.execute('PRAGMA foreign_keys = OFF;')

    for model in _sort_models_for_repair():
        table = model._meta.table_name
        try:
            src_cursor.execute(f"PRAGMA table_info({table});")
            src_columns = [str(info[1]) for info in src_cursor.fetchall()]
            if not src_columns:
                logger.info(f"  - 数据表 [{table}]: 源库不存在，按当前模型默认结构跳过")
                continue

            target_fields = list(model._meta.sorted_fields)
            target_columns = [field.column_name for field in target_fields]
            shared_columns = [column for column in target_columns if column in src_columns]
            if not shared_columns:
                logger.info(f"  - 数据表 [{table}]: 无可直接复用字段，按当前模型默认结构跳过")
                continue

            src_cursor.execute(f"SELECT * FROM {table};")
            insert_sql = (
                f"INSERT OR REPLACE INTO {table} ({', '.join(target_columns)}) "
                f"VALUES ({', '.join(['?'] * len(target_columns))});"
            )
            source_indexes = {column: index for index, column in enumerate(src_columns)}

            while True:
                try:
                    source_row = src_cursor.fetchone()
                    if source_row is None:
                        break

                    values = []
                    for field in target_fields:
                        column_name = field.column_name
                        if column_name in source_indexes:
                            values.append(source_row[source_indexes[column_name]])
                        else:
                            values.append(_resolve_field_default_for_repair(field))

                    dst_cursor.execute(insert_sql, values)
                except Exception as row_error:
                    logger.debug(f"  - 数据表 [{table}] 某行挽救失败，已跳过: {row_error}")
                    continue

            dst_conn.commit()
        except Exception as e:
            logger.warning(f"  - 数据表 [{table}] 损坏严重，无法挽救: {e}")
            continue

    dst_cursor.execute('PRAGMA foreign_keys = ON;')
    src_conn.close()
    dst_conn.close()
