from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from typing import cast

from packaging.version import Version

from backend.database.models_ext import ext_db
from backend.database.repair import _remove_file_with_retry
from backend.database.models import GameProfile, GroupData, GroupMod, ModAsset, UserModData, db
from backend.settings import COMMUNITY_INSTEAD_DB_PATH, COMMUNITY_WORKSHOP_DB_PATH, DATA_DIR, settings
from backend.utils.logger import logger
from backend.utils.tools import normalize_package_id


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

    last = Version(last_version)

    if last < Version("0.17.10"):
        result.pending_actions.append("recommend_scan")
        result.messages.append("检测到核心解析引擎升级，建议执行全量扫描以获得更好的兼容性。")
        settings.set('community_workshop_db_path', str(COMMUNITY_WORKSHOP_DB_PATH))
        settings.set('community_instead_db_path', str(COMMUNITY_INSTEAD_DB_PATH))

    if last < Version("0.19.8"):
        _migrate_legacy_default_profile_user_data_path()

    if last < Version("0.19.21"):
        _migrate_legacy_launch_preference_to_default_profile()

    if last < Version("0.20.4"):
        _migrate_legacy_workshop_cache_schema(result)

    if last < Version("0.21.0"):
        _migrate_legacy_group_memberships(result)

    result.pending_actions.append("show_update_news")
    return result


def normalize_duplicate_group_names_on_load() -> list[tuple[str, str, str]]:
    """
    启动时修正数据库里已经存在的重名分组。

    规则：
    1. 仅把“去掉首尾空白后同名”的后续重复项改名；
    2. 第一项保留原名不动；
    3. 追加 `-1/-2/...` 后缀时，避开当前库里其它已存在名称。
    """
    groups = list(
        GroupData.select()
        .order_by(GroupData.sort_index, GroupData.group_id)
    )
    if not groups:
        return []

    normalized_counts = Counter(str(group.name or "").strip() for group in groups)
    duplicate_keys = {
        key
        for key, count in normalized_counts.items()
        if key and count > 1
    }
    if not duplicate_keys:
        return []

    remaining_original_names = Counter(str(group.name or "") for group in groups)
    seen_duplicate_keys: set[str] = set()
    finalized_names: set[str] = set()
    renamed_groups: list[tuple[str, str, str]] = []

    with db.atomic():
        for group in groups:
            original_name = str(group.name or "")
            normalized_name = original_name.strip()
            remaining_original_names[original_name] -= 1
            if remaining_original_names[original_name] <= 0:
                remaining_original_names.pop(original_name, None)

            if normalized_name not in duplicate_keys or normalized_name not in seen_duplicate_keys:
                seen_duplicate_keys.add(normalized_name)
                finalized_names.add(original_name)
                continue

            base_name = normalized_name or original_name.strip() or "新分组"
            suffix = 1
            candidate_name = f"{base_name}-{suffix}"
            while candidate_name in finalized_names or candidate_name in remaining_original_names:
                suffix += 1
                candidate_name = f"{base_name}-{suffix}"

            GroupData.update(name=candidate_name).where(GroupData.group_id == group.group_id).execute()
            finalized_names.add(candidate_name)
            renamed_groups.append((group.group_id, original_name, candidate_name))

    return renamed_groups


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


def _migrate_legacy_group_memberships(result: AppUpgradeResult):
    """
    修复 0.21.0 之前历史版本留下的分组成员脏数据。

    历史问题：
    - 部分 GroupMod.mod_id 被错误写成 ModAsset.path_hash
    - 部分关系缺失对应的 UserModData 父记录
    这里作为一次性版本迁移执行，避免把低频历史修复常驻在 DAO 运行路径中。
    """
    raw_rows = list(
        GroupMod.select(GroupMod.group_id, GroupMod.mod_id, GroupMod.sort_index)
        .order_by(GroupMod.group_id, GroupMod.sort_index, GroupMod.mod_id)
        .dicts()
    )
    if not raw_rows: return

    raw_mod_ids = [str(row.get("mod_id") or "").strip() for row in raw_rows if str(row.get("mod_id") or "").strip()]
    normalized_candidates = {
        normalize_package_id(mod_id)
        for mod_id in raw_mod_ids
        if normalize_package_id(mod_id)
    }
    mod_assets = list(
        ModAsset.select(ModAsset.package_id, ModAsset.path_hash)
        .where(
            cast(str, ModAsset.package_id).in_(list(normalized_candidates)) # type: ignore
            | cast(str, ModAsset.path_hash).in_(raw_mod_ids) # type: ignore
        )
        .dicts()
    )
    if not mod_assets: return

    known_package_ids = {
        normalize_package_id(asset.get("package_id"))
        for asset in mod_assets
        if normalize_package_id(asset.get("package_id"))
    }
    package_ids_by_path_hash = {
        str(asset.get("path_hash") or "").strip(): normalize_package_id(asset.get("package_id"))
        for asset in mod_assets
        if str(asset.get("path_hash") or "").strip() and normalize_package_id(asset.get("package_id"))
    }

    rebuilt_rows_by_group: dict[str, list[str]] = {}
    seen_by_group: dict[str, set[str]] = {}
    fixed_count = 0
    deduped_count = 0
    removed_empty_count = 0

    for row in raw_rows:
        group_id = str(row.get("group_id") or "").strip()
        raw_mod_id = str(row.get("mod_id") or "").strip()
        if group_id not in rebuilt_rows_by_group:
            rebuilt_rows_by_group[group_id] = []
            seen_by_group[group_id] = set()

        if not raw_mod_id:
            removed_empty_count += 1
            continue

        normalized_id = normalize_package_id(raw_mod_id)
        resolved_id = normalized_id
        if normalized_id not in known_package_ids:
            mapped_id = normalize_package_id(package_ids_by_path_hash.get(raw_mod_id))
            if mapped_id: resolved_id = mapped_id

        if not resolved_id:
            removed_empty_count += 1
            continue

        if raw_mod_id != resolved_id: fixed_count += 1

        if resolved_id in seen_by_group[group_id]:
            deduped_count += 1
            continue

        seen_by_group[group_id].add(resolved_id)
        rebuilt_rows_by_group[group_id].append(resolved_id)

    if fixed_count == 0 and deduped_count == 0 and removed_empty_count == 0: return

    with db.atomic():
        final_ids = [mod_id for mod_ids in rebuilt_rows_by_group.values() for mod_id in mod_ids]
        if final_ids:
            existing_user_ids = {
                row["mod_id"]
                for row in UserModData.select(UserModData.mod_id)
                .where(cast(str, UserModData.mod_id).in_(final_ids)) # type: ignore
                .dicts()
            }
            missing_user_ids = [mod_id for mod_id in final_ids if mod_id not in existing_user_ids]
            if missing_user_ids:
                UserModData.insert_many([{"mod_id": mod_id} for mod_id in sorted(set(missing_user_ids))]).on_conflict_ignore().execute()

        GroupMod.delete().execute()
        data_source = []
        for group_id, mod_ids in rebuilt_rows_by_group.items():
            data_source.extend(
                {
                    "group_id": group_id,
                    "mod_id": mod_id,
                    "sort_index": index,
                }
                for index, mod_id in enumerate(mod_ids)
            )
        if data_source: GroupMod.insert_many(data_source).execute()

    result.messages.append(f"已完成旧版分组数据修复：纠正 {fixed_count} 项，去重 {deduped_count} 项。")
