from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.database.models import MOD_ASSET_STATE_MISSING, MOD_ASSET_STATE_PRESENT, GameProfile, ModAsset, SystemInfo, db
from backend.settings import settings
from backend.utils.logger import logger
from backend.utils.tools import generate_path_hash, normalize_path_for_storage, normalize_path_list_for_storage


PATH_NORMALIZATION_VERSION = "1"
PATH_NORMALIZATION_INFO_KEY = "path_normalization_version"


@dataclass
class PathNormalizationResult:
    checked: bool = False
    config_updated: bool = False
    profile_updates: int = 0
    asset_updates: int = 0
    asset_merges: int = 0
    messages: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return any([self.profile_updates, self.asset_updates, self.asset_merges])


def _path_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_optional_path(value: Any) -> str:
    return normalize_path_for_storage(value) if _path_text(value) else ""


def _normalize_asset_paths(asset: ModAsset) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in ["path", "icon_path", "preview_path"]:
        current = _path_text(getattr(asset, key, ""))
        normalized = _normalize_optional_path(current)
        if normalized != current:
            payload[key] = normalized

    gallery_paths = normalize_path_list_for_storage(getattr(asset, "gallery_paths", []))
    if gallery_paths != list(getattr(asset, "gallery_paths", []) or []):
        payload["gallery_paths"] = gallery_paths

    shadow_paths = normalize_path_list_for_storage(getattr(asset, "shadow_paths", []))
    if shadow_paths != list(getattr(asset, "shadow_paths", []) or []):
        payload["shadow_paths"] = shadow_paths

    if "path" in payload:
        payload["path_hash"] = generate_path_hash(payload["path"])
    return payload


def _clone_asset_payload(asset: ModAsset, updates: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {field.name: getattr(asset, field.name) for field in ModAsset._meta.sorted_fields}  # type: ignore[attr-defined]
    if updates:
        payload.update(updates)
    return payload


def _non_empty_score(payload: dict[str, Any]) -> int:
    score = 0
    for value in payload.values():
        if value is None or value == "":
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        score += 1
    return score


def _asset_score(payload: dict[str, Any]) -> tuple[int, int, int]:
    state = str(payload.get("state") or MOD_ASSET_STATE_PRESENT).strip().lower()
    present_score = 1 if state != MOD_ASSET_STATE_MISSING else 0
    latest_time = max(
        int(payload.get(key) or 0)
        for key in ["last_seen_at", "last_scanned_at", "file_modify_time", "mod_update_time", "last_active_time"]
    )
    return present_score, _non_empty_score(payload), latest_time


def _merge_path_lists(left: Any, right: Any) -> list[str]:
    return normalize_path_list_for_storage([*(left or []), *(right or [])])


def _merge_asset_payloads(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    primary, secondary = (left, right) if _asset_score(left) >= _asset_score(right) else (right, left)
    merged = dict(primary)

    for key, value in secondary.items():
        current = merged.get(key)
        if current in (None, "", [], {}):
            merged[key] = value

    merged["gallery_paths"] = _merge_path_lists(left.get("gallery_paths"), right.get("gallery_paths"))
    merged["shadow_paths"] = _merge_path_lists(left.get("shadow_paths"), right.get("shadow_paths"))
    for key in ["last_seen_at", "last_scanned_at", "file_create_time", "file_modify_time", "mod_update_time", "last_active_time", "last_moved_time"]:
        merged[key] = max(int(left.get(key) or 0), int(right.get(key) or 0))
    merged["file_size"] = max(int(left.get("file_size") or 0), int(right.get("file_size") or 0))
    return merged


def _apply_asset_path_updates(asset: ModAsset, updates: dict[str, Any]) -> bool:
    old_hash = str(asset.path_hash or "")
    new_hash = str(updates.get("path_hash") or old_hash)
    if not old_hash:
        return False

    incoming_payload = _clone_asset_payload(asset, updates)
    if new_hash == old_hash:
        ModAsset.update(**{key: value for key, value in updates.items() if key != "path_hash"}).where(ModAsset.path_hash == old_hash).execute()
        return True

    existing = ModAsset.get_or_none(ModAsset.path_hash == new_hash)
    if existing:
        existing_payload = _clone_asset_payload(existing)
        merged_payload = _merge_asset_payloads(existing_payload, incoming_payload)
        merged_payload["path_hash"] = new_hash
        ModAsset.update(**{key: value for key, value in merged_payload.items() if key != "path_hash"}).where(ModAsset.path_hash == new_hash).execute()
        ModAsset.delete().where(ModAsset.path_hash == old_hash).execute()
        return True

    ModAsset.insert(**incoming_payload).execute()
    ModAsset.delete().where(ModAsset.path_hash == old_hash).execute()
    return True


def _normalize_profiles() -> int:
    updated = 0
    for profile in GameProfile.select():
        payload: dict[str, str] = {}
        for key in ["game_install_path", "user_data_path"]:
            current = _path_text(getattr(profile, key, ""))
            normalized = _normalize_optional_path(current)
            if normalized != current:
                payload[key] = normalized
        if not payload:
            continue
        GameProfile.update(**payload).where(GameProfile.id == profile.id).execute()
        updated += 1
    return updated


def _normalize_mod_assets() -> tuple[int, int]:
    updated = 0
    merged = 0
    for asset in list(ModAsset.select()):
        updates = _normalize_asset_paths(asset)
        if not updates:
            continue
        old_hash = str(asset.path_hash or "")
        new_hash = str(updates.get("path_hash") or old_hash)
        had_duplicate = bool(new_hash != old_hash and ModAsset.get_or_none(ModAsset.path_hash == new_hash))
        if _apply_asset_path_updates(asset, updates):
            updated += 1
            if had_duplicate:
                merged += 1
    return updated, merged


def run_path_normalization_migration(force: bool = False) -> PathNormalizationResult:
    """
    启动期路径规范化迁移。

    通过 SystemInfo 版本标记保证同一版只自动执行一次；函数本身保持幂等，方便测试和手动修复复用。
    """
    result = PathNormalizationResult(checked=True)
    marker = SystemInfo.get_or_none(SystemInfo.key == PATH_NORMALIZATION_INFO_KEY)
    if not force and marker and str(marker.value or "") == PATH_NORMALIZATION_VERSION:
        return result

    try:
        with db.atomic():
            # 配置对象在加载阶段已经完成内存归一化；这里持久化一次，修正旧 config.json。
            settings.save()
            result.config_updated = True
            result.profile_updates = _normalize_profiles()
            result.asset_updates, result.asset_merges = _normalize_mod_assets()
            SystemInfo.insert(
                key=PATH_NORMALIZATION_INFO_KEY,
                value=PATH_NORMALIZATION_VERSION,
            ).on_conflict_replace().execute()
    except Exception as exc:
        logger.warning(f"路径规范化迁移失败: {exc}", exc_info=True)
        result.messages.append("路径规范化迁移失败，部分旧路径可能需要重新保存或重新扫描。")
        return result

    if result.changed:
        result.messages.append(
            f"已完成路径规范化：环境 {result.profile_updates} 项，模组记录 {result.asset_updates} 项，合并重复 {result.asset_merges} 项。"
        )
    return result
