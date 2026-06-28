from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.database.models_ext import ext_db
from backend.database.repair import _remove_file_with_retry
from backend.database.models import GameProfile
from backend.settings import COMMUNITY_INSTEAD_DB_PATH, COMMUNITY_WORKSHOP_DB_PATH, DATA_DIR, settings
from backend.utils.logger import logger


@dataclass
class AppUpgradeResult:
    """
    应用版本升级期间的附加结果。
    这些内容最终会被 API 层写入 upgrade_context，供前端展示或后续流程复用。
    """
    pending_actions: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def run_app_upgrade_migrations(last_version: str, current_version: str) -> AppUpgradeResult:
    """
    执行应用层升级迁移。
    设计原则：
    1. 仅处理“应用版本升级”语义下的补丁，不与数据库 schema 迁移混在一起。
    2. 每项迁移都应具备幂等性，重复执行不会破坏现有数据。
    3. 旧版兼容补丁集中管理，避免散落在 API/ProfileManager 各处。
    """
    result = AppUpgradeResult()

    from distutils.version import LooseVersion

    if LooseVersion(last_version) < LooseVersion("0.17.10"):
        result.pending_actions.append("recommend_scan")
        result.messages.append("检测到核心解析引擎升级，建议执行全量扫描以获得更好的兼容性。")
        settings.set('community_workshop_db_path', str(COMMUNITY_WORKSHOP_DB_PATH))
        settings.set('community_instead_db_path', str(COMMUNITY_INSTEAD_DB_PATH))

    if LooseVersion(last_version) < LooseVersion("0.19.8"):
        _migrate_legacy_default_profile_user_data_path()

    if LooseVersion(last_version) < LooseVersion("0.19.21"):
        _migrate_legacy_launch_preference_to_default_profile()

    if LooseVersion(last_version) < LooseVersion("0.20.4"):
        _migrate_legacy_workshop_cache_schema(result)

    result.pending_actions.append("show_update_news")
    return result


def _migrate_legacy_default_profile_user_data_path():
    """
    修正旧版默认环境误存的用户数据目录。
    历史问题：
    - 旧版有机会把 default.user_data_path 存成 `.../RimWorld by Ludeon Studios/Config`
    - 新版语义要求该字段始终指向用户数据根目录 `.../RimWorld by Ludeon Studios`
    这里只针对默认环境做幂等修正，避免影响用户自行创建的其它隔离环境。
    """
    default_profile = GameProfile.get_or_none(GameProfile.id == 'default')
    if not default_profile: return

    raw_path = str(default_profile.user_data_path or '').strip()
    if not raw_path: return

    path_obj = Path(raw_path)
    if path_obj.name.lower() != 'config': return

    parent_path = path_obj.parent
    if not parent_path: return

    # 仅在路径末段确实是 RimWorld 用户数据根目录时才执行修正，避免误伤其它名为 Config 的目录。
    if parent_path.name.lower() != 'rimworld by ludeon studios': return

    default_profile.user_data_path = str(parent_path)
    default_profile.save()


def _migrate_legacy_launch_preference_to_default_profile():
    """
    将 0.19.21 之前版本的默认环境 prefer_steam_launch 统一修正为 True。
    这里不再额外写入数据库标记，原因是：
    1. 该迁移只会在应用版本从 < 0.19.21 升级时进入；
    2. 升级完成后 app_version 会被持久化，新版本重复启动不会再次走到这里；
    3. 因此版本门槛本身已经足够表达“一次性迁移”语义，避免再维护冗余状态。
    """
    default_profile = GameProfile.get_or_none(GameProfile.id == 'default')
    if default_profile:
        target_value = True
        if bool(getattr(default_profile, 'prefer_steam_launch', True)) != target_value:
            default_profile.prefer_steam_launch = target_value
            default_profile.save()

    # 迁移完成后立刻清空临时缓存，避免本次进程后续逻辑再把它当成有效配置源。
    settings._legacy_prefer_steam_launch = None


def _migrate_legacy_workshop_cache_schema(result: AppUpgradeResult):
    """
    清理旧版 workshop_cache.db。

    0.20.4 起外置工坊缓存的表模型已从旧 `WorkshopMeta` 拆分为新结构，
    这里直接删除旧缓存库，让新版启动后的默认重建流程按新结构重新生成。
    """
    db_path = DATA_DIR / "workshop_cache.db"
    try:
        if not ext_db.is_closed():
            ext_db.close()
    except Exception as exc:
        logger.warning(f"关闭旧版外置缓存数据库连接失败，将继续尝试清理文件: {exc}", exc_info=True)

    sidecar_paths = [
        db_path,
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
        db_path.with_name(db_path.name + "-journal"),
    ]

    removed_any = False
    for path in sidecar_paths:
        if not path.exists():
            continue
        _remove_file_with_retry(str(path), retries=5, delay=0.1)
        removed_any = True

    if removed_any:
        result.messages.append("检测到工坊缓存结构升级，已清理旧版 workshop_cache 缓存库，启动后将按新结构自动重建。")
