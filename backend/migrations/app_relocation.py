from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.utils.tools import generate_path_hash


@dataclass
class AppRelocationResult:
    moved: bool = False
    old_home: str = ""
    new_home: str = ""
    config_updates: dict[str, str] = field(default_factory=dict)
    profile_updates: int = 0
    asset_updates: int = 0
    messages: list[str] = field(default_factory=list)


def _path_text(value: Any) -> str:
    return str(value or "").strip()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _relocate_path_value(value: Any, old_home: str, new_home: str) -> str:
    raw = _path_text(value)
    if not raw:
        return raw
    try:
        path = Path(raw)
        root = Path(old_home)
        candidate = path if path.is_absolute() else root / path
        if not _is_relative_to(candidate, root):
            return raw
        return str(Path(new_home) / candidate.resolve().relative_to(root.resolve()))
    except Exception:
        return raw


def _relocate_path_list(values: Any, old_home: str, new_home: str) -> list[str]:
    if not isinstance(values, list):
        return []
    return [_relocate_path_value(item, old_home, new_home) for item in values]


def apply_config_relocation(config: Any, old_home: str, new_home: str) -> AppRelocationResult:
    """
    更新旧软件目录下的内部配置路径。

    只迁移位于旧 HOME 内部的路径；Steam、游戏安装目录、工坊目录等外部路径保持原样。
    """
    result = AppRelocationResult(old_home=_path_text(old_home), new_home=_path_text(new_home))
    if not result.old_home or not result.new_home:
        return result
    try:
        if Path(result.old_home).resolve() == Path(result.new_home).resolve():
            return result
    except Exception:
        if result.old_home == result.new_home:
            return result

    scalar_keys = [
        "self_mods_path",
        "steamcmd_path",
        "ripgrep_path",
        "community_workshop_db_path",
        "community_instead_db_path",
        "community_rules_path",
        "multiplayer_compatibility_path",
        "mp_compat_package_ids_path",
        "user_rules_path",
        "load_order_import_custom_path",
        "load_order_import_last_path",
        "load_order_export_custom_path",
        "load_order_export_last_path",
    ]

    for key in scalar_keys:
        if not hasattr(config, key):
            continue
        current = _path_text(getattr(config, key))
        relocated = _relocate_path_value(current, result.old_home, result.new_home)
        if relocated != current:
            setattr(config, key, relocated)
            result.config_updates[key] = relocated

    texture_opt = getattr(config, "texture_opt", None)
    if texture_opt is not None and hasattr(texture_opt, "texture_tools_path"):
        current = _path_text(getattr(texture_opt, "texture_tools_path"))
        relocated = _relocate_path_value(current, result.old_home, result.new_home)
        if relocated != current:
            setattr(texture_opt, "texture_tools_path", relocated)
            result.config_updates["texture_opt.texture_tools_path"] = relocated

    config.home_path = result.new_home
    result.moved = True
    if result.config_updates:
        result.messages.append("检测到管理器目录已移动，已自动更新内部工具、规则库和管理器模组路径。")
    else:
        result.messages.append("检测到管理器目录已移动，正在同步内部数据库路径。")
    return result


def _relocate_mod_asset_record(asset: Any, old_home: str, new_home: str) -> dict[str, Any] | None:
    changed = False
    payload: dict[str, Any] = {}

    for key in ["path", "icon_path", "preview_path"]:
        current = _path_text(getattr(asset, key, ""))
        relocated = _relocate_path_value(current, old_home, new_home)
        if relocated != current:
            payload[key] = relocated
            changed = True

    gallery_paths = _relocate_path_list(getattr(asset, "gallery_paths", []), old_home, new_home)
    if gallery_paths != list(getattr(asset, "gallery_paths", []) or []):
        payload["gallery_paths"] = gallery_paths
        changed = True

    shadow_paths = _relocate_path_list(getattr(asset, "shadow_paths", []), old_home, new_home)
    if shadow_paths != list(getattr(asset, "shadow_paths", []) or []):
        payload["shadow_paths"] = shadow_paths
        changed = True

    if not changed:
        return None

    new_path = payload.get("path") or _path_text(getattr(asset, "path", ""))
    new_hash = generate_path_hash(new_path)
    payload["path_hash"] = new_hash
    return payload


def _clone_asset_payload(asset: Any, model: Any, updates: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in model._meta.sorted_fields:
        payload[field.name] = getattr(asset, field.name)
    payload.update(updates)
    return payload


def apply_database_relocation(old_home: str, new_home: str) -> AppRelocationResult:
    """迁移数据库中仍指向旧软件目录的内部路径。"""
    from backend.database.models import GameProfile, ModAsset, db

    result = AppRelocationResult(old_home=_path_text(old_home), new_home=_path_text(new_home))
    if not result.old_home or not result.new_home:
        return result
    try:
        if Path(result.old_home).resolve() == Path(result.new_home).resolve():
            return result
    except Exception:
        if result.old_home == result.new_home:
            return result

    with db.atomic():
        for profile in GameProfile.select():
            current = _path_text(profile.user_data_path)
            relocated = _relocate_path_value(current, result.old_home, result.new_home)
            if relocated == current:
                continue
            profile.user_data_path = relocated
            profile.save()
            result.profile_updates += 1

        for asset in list(ModAsset.select()):
            updates = _relocate_mod_asset_record(asset, result.old_home, result.new_home)
            if not updates:
                continue
            old_hash = asset.path_hash
            new_hash = updates["path_hash"]
            payload = _clone_asset_payload(asset, ModAsset, updates)
            if new_hash != old_hash:
                existing = ModAsset.get_or_none(ModAsset.path_hash == new_hash)
                if existing:
                    ModAsset.delete().where(ModAsset.path_hash == old_hash).execute()
                else:
                    ModAsset.insert(**payload).execute()
                    ModAsset.delete().where(ModAsset.path_hash == old_hash).execute()
            else:
                ModAsset.update(**{k: v for k, v in updates.items() if k != "path_hash"}).where(ModAsset.path_hash == old_hash).execute()
            result.asset_updates += 1

    result.moved = bool(result.profile_updates or result.asset_updates)
    if result.moved:
        result.messages.append(
            f"已同步内部数据库路径：环境 {result.profile_updates} 项，模组记录 {result.asset_updates} 项。"
        )
    return result


def write_relocation_marker(result: AppRelocationResult, data_dir: str | Path) -> None:
    """写入最近一次目录迁移记录，便于排查路径问题。"""
    if not result.old_home or not result.new_home:
        return
    try:
        marker = Path(data_dir) / "app_relocation.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "old_home": result.old_home,
                    "new_home": result.new_home,
                    "config_updates": result.config_updates,
                    "profile_updates": result.profile_updates,
                    "asset_updates": result.asset_updates,
                    "messages": result.messages,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
