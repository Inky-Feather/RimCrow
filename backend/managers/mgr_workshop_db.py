# backend/managers/mgr_workshop_db.py
import gzip
import json
from pathlib import Path
from typing import Any

from peewee import chunked

from backend.database.models import SystemInfo
from backend.database.models_ext import (
    ExtDatasetState,
    ModReplacement,
    WorkshopManifest,
    ext_db,
    init_ext_db,
)
from backend.settings import settings
from backend.utils.logger import logger
from backend.utils.tools import current_ms


class WorkshopDBManager:
    # 这里显式记录导入器版本。
    # 当“文件 -> 表字段”的映射规则发生变化时，递增版本号即可强制重建，
    # 避免继续复用旧的导入结果。
    WORKSHOP_DB_IMPORT_SCHEMA_VERSION = 2
    INSTEAD_DB_IMPORT_SCHEMA_VERSION = 2

    def __init__(self):
        # 启动时只建立外置缓存库连接，不在构造阶段执行大文件导入。
        # 这样首屏阶段只做“轻初始化”，把真正的重活放到后台预热里。
        init_ext_db()
        self._cache_loaded = False

    def load_all_cache(self):
        """后台预热所有外置缓存。"""
        self.rebuild_workshop_cache()
        self.rebuild_instead_cache()
        self._cache_loaded = True

    @property
    def cache_loaded(self) -> bool:
        """暴露当前缓存是否完成预热，方便启动链路做一次性守护。"""
        return bool(self._cache_loaded)

    def _resolve_existing_dataset_path(self, path: Path, *, allow_gz_fallback: bool = False) -> Path:
        """统一处理 `.gz` 回退，避免多处各写一套路径判断。"""
        if path.exists(): return path
        if allow_gz_fallback and path.with_suffix(path.suffix + ".gz").exists():
            return path.with_suffix(path.suffix + ".gz")
        return path

    def _get_dataset_state(self, dataset_name: str) -> ExtDatasetState | None:
        return ExtDatasetState.get_or_none(ExtDatasetState.dataset_name == dataset_name)

    def _get_dataset_file_stats(self, path: Path) -> tuple[int, int]:
        """统一读取文件大小和毫秒级修改时间，避免多处重复 stat。"""
        if not path.exists(): return 0, 0
        stat = path.stat()
        return int(stat.st_size), int(stat.st_mtime * 1000)

    def _should_rebuild_dataset(self, state: ExtDatasetState | None, path: Path, *, import_schema_version: int, expected_min_rows: int = 1) -> bool:
        """
        使用轻量文件元数据快速判断是否需要重建。

        判定原则：
        1. 状态不存在 -> 重建
        2. 文件大小/修改时间变化 -> 重建
        3. 导入器版本变化 -> 重建
        4. 上次导入结果为空 -> 重建

        这里不额外计算 hash，而是使用 `path + size + mtime + schema_version`：
        - 启动阶段应优先降低 I/O 和解析成本；
        - 元数据未变化时可以在解析 JSON 之前直接复用旧结果。
        """
        if not state: return True
        state_data: Any = state

        file_size, file_mtime = self._get_dataset_file_stats(path)

        if str(state_data.source_path or "") != str(path):
            return True
        if int(state_data.file_size or 0) != file_size:
            return True
        if int(state_data.file_mtime or 0) != file_mtime:
            return True
        if int(state_data.import_schema_version or 0) != int(import_schema_version):
            return True
        if int(state_data.row_count or 0) < int(expected_min_rows):
            return True
        return False

    def _save_dataset_state(self, dataset_name: str, path: Path, *, source_version: str, import_schema_version: int, row_count: int) -> None:
        # 状态表只保存快速判定所需的元数据，避免下一次启动再次解析整份大文件。
        file_size, file_mtime = self._get_dataset_file_stats(path)
        ExtDatasetState.insert(
            dataset_name=dataset_name,
            source_path=str(path),
            file_size=file_size,
            file_mtime=file_mtime,
            source_version=str(source_version or ""),
            import_schema_version=int(import_schema_version),
            row_count=int(row_count),
            last_import_time=current_ms(),
        ).on_conflict_replace().execute()

    def _read_dataset_payload(self, path: Path) -> dict[str, Any]:
        """按文件后缀读取 JSON / GZip JSON，统一导入入口。"""
        if str(path).endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8-sig") as handle:
                return json.load(handle)
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)

    def _replace_ext_table_rows(self, model: Any, rows: list[dict[str, Any]], *, batch_size: int = 500) -> None:
        """
        用整表替换方式刷新纯文件来源表。

        这种表完全由外部文件生成，清空后重建可以同步删除上游已移除的历史记录。
        """
        with ext_db.atomic():
            model.delete().execute()
            for chunk in chunked(rows, batch_size):
                model.insert_many(chunk).execute()

    def rebuild_workshop_cache(self):
        """
        将 `steamDB.json` 的文件快照写入 `WorkshopManifest`。

        实现原则：
        1. 只写文件来源字段，不触碰在线缓存表；
        2. 文件未变化时直接跳过；
        3. 文件变化时整表替换，确保上游删除的条目也能正确同步消失。
        """
        path = self._resolve_existing_dataset_path(Path(settings.config.community_workshop_db_path))
        if not path.exists(): return False
        try:
            state = self._get_dataset_state("workshop_db")
            if not self._should_rebuild_dataset(
                state,
                path,
                import_schema_version=self.WORKSHOP_DB_IMPORT_SCHEMA_VERSION,
            ):
                logger.info("SteamDB 文件元数据未变化，跳过本轮 manifest 重建")
                return True

            data = self._read_dataset_payload(path)

            version = str(data.get("version", "0"))
            raw_db = data.get("database", {}) or {}

            batch = []
            for wid, info in raw_db.items():
                if wid == "294100": continue # 跳过游戏本体
                # 提取依赖项，压缩结构：{"2891845502": "Alpha Genes"}
                deps = {}
                for dep_id, dep_info in (info.get("dependencies", {}) or {}).items():
                    deps[dep_id] = dep_info[0] if isinstance(dep_info, list) and dep_info else "Unknown"
                batch.append(
                    {
                        "workshop_id": wid,
                        "package_id": str(info.get("packageId", "") or "").lower() or None,
                        "name": info.get("name", ""),
                        "author": info.get("authors", ""),
                        "game_versions": info.get("gameVersions", []),
                        "dependencies_mods": deps,
                    }
                )

            self._replace_ext_table_rows(WorkshopManifest, batch)

            self._save_dataset_state(
                "workshop_db",
                path,
                source_version=version,
                import_schema_version=self.WORKSHOP_DB_IMPORT_SCHEMA_VERSION,
                row_count=len(batch),
            )
            # 记录版本号到主数据库
            SystemInfo.insert(key="steamdb_version", value=version).on_conflict_replace().execute()
            logger.info(f"SteamDB manifest 重建完成！总记录数: {len(batch)}")
            return True
        except Exception as e:
            logger.error(f"SteamDB manifest 重建失败: {e}", exc_info=True)
            return False

    def rebuild_instead_cache(self):
        """
        将 `replacements.json(.gz)` 写入替代规则表。

        这张表也是纯文件来源，因此同样使用快速判定 + 整表替换。
        """
        path = self._resolve_existing_dataset_path(
            Path(settings.config.community_instead_db_path),
            allow_gz_fallback=True,
        )
        if not path.exists(): return False
        try:
            state = self._get_dataset_state("instead_db")
            if not self._should_rebuild_dataset(
                state,
                path,
                import_schema_version=self.INSTEAD_DB_IMPORT_SCHEMA_VERSION,
            ):
                logger.info("UseThisInstead 文件元数据未变化，跳过本轮替代规则重建")
                return True

            content = self._read_dataset_payload(path)

            version = str(content.get("version", "0"))
            rules = content.get("rules", []) or []

            batch = []
            for r in rules:
                batch.append(
                    {
                        "old_workshop_id": r.get("oldWorkshopId"),
                        "old_package_id": str(r.get("oldPackageId", "")).lower(),
                        "old_name": r.get("oldName", ""),
                        "old_author": r.get("oldAuthor", ""),
                        "new_workshop_id": r.get("newWorkshopId"),
                        "new_package_id": str(r.get("newPackageId", "")).lower(),
                        "new_name": r.get("newName", ""),
                        "old_versions": r.get("oldVersions", []),
                        "new_versions": r.get("newVersions", []),
                    }
                )

            self._replace_ext_table_rows(ModReplacement, batch)

            self._save_dataset_state(
                "instead_db",
                path,
                source_version=version,
                import_schema_version=self.INSTEAD_DB_IMPORT_SCHEMA_VERSION,
                row_count=len(batch),
            )
            SystemInfo.insert(key="instead_version", value=version).on_conflict_replace().execute()
            logger.info(f"替代规则库重建完成！总记录数: {len(batch)}")
            return True
        except Exception as e:
            logger.error(f"替代规则库重建失败: {e}", exc_info=True)
            return False

    # =============== 快速查询接口 ===============

    def check_replacement(self, package_id: str, game_version: str):
        """替代方案极速检测。"""
        rule = ModReplacement.get_or_none(ModReplacement.old_package_id == package_id.lower())
        if rule and game_version in rule.new_versions:
            return {
                "type": "instead",
                "new_id": rule.new_workshop_id,
                "new_name": rule.new_name,
                "message": f"发现接力版本：推荐使用 {rule.new_name} 替代当前模组。",
            }
        return None

    def get_workshopdb_version(self):
        """获取当前文件快照库版本。"""
        record = SystemInfo.get_or_none(SystemInfo.key == "steamdb_version")
        return record.value if record else ""

    def get_insteaddb_version(self):
        """获取当前替代规则库版本。"""
        record = SystemInfo.get_or_none(SystemInfo.key == "instead_version")
        return record.value if record else ""

    def get_replacements(self):
        """获取替代方案规则。"""
        return ModReplacement.select().dicts()

    def get_missing_dependencies(self, workshop_id: str, local_installed_package_ids: set):
        """
        根据 manifest 快照层查找缺失依赖。

        这里不走在线缓存层：
        - 依赖关系来自文件快照，不属于在线补充数据；
        - 规则判断应尽量稳定，不受 Steam API TTL 和可用性波动影响。
        """
        meta = WorkshopManifest.get_or_none(WorkshopManifest.workshop_id == str(workshop_id))
        if not meta or not meta.dependencies_mods: return []

        missing = []
        for dep_wid, dep_name in meta.dependencies_mods.items():
            dep_meta = WorkshopManifest.get_or_none(WorkshopManifest.workshop_id == dep_wid)
            if dep_meta and dep_meta.package_id not in local_installed_package_ids:
                missing.append({"workshop_id": dep_wid, "name": dep_name})

        return missing
