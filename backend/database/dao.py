from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import reduce
import json
import operator
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, cast
import uuid

from peewee import JOIN, chunked, fn

from backend.database.models import (
    GroupData,
    GroupMod,
    MOD_ASSET_STATE_DELETED,
    MOD_ASSET_STATE_MISSING,
    MOD_ASSET_STATE_PRESENT,
    ModAsset,
    ModInterlock,
    SubscribedCollection,
    UserModData,
    db,
)
from backend.utils.profile_runtime import resolve_profile_runtime_capabilities
from backend.managers.mgr_profile import ProfileContext
from backend.scanner.analyzer import ModAnalyzer
from backend.settings import TOOL_MODS_DIR, settings
from backend.utils.constants import normalize_language_code, normalize_language_codes
from backend.utils.event_bus import EventBus
from backend.utils.logger import logger
from backend.utils.tools import (
    current_ms,
    is_hex_color,
    normalize_hex_color,
    normalize_dir_root_for_compare,
    normalize_package_id,
    normalize_package_ids, 
    delete_fs_path,
)


_MOD_ASSET_UPSERT_EXCLUDED_FIELDS = {"path_hash"}


def _present_asset_condition():
    """
    数据库层统一的“物理资产仍有效”条件。

    缺失记录现在会保留最后路径，所以不能再只靠 path 是否为空判断有效性。
    """
    return (
        ((ModAsset.state == MOD_ASSET_STATE_PRESENT) | ModAsset.state.is_null())  # type: ignore
        & ModAsset.path.is_null(False)  # type: ignore
        & (ModAsset.path != "")
    )


def _asset_marked_unavailable(asset: dict[str, Any]) -> bool:
    state = str(asset.get("state") or MOD_ASSET_STATE_PRESENT).strip().lower()
    return state in {MOD_ASSET_STATE_MISSING, MOD_ASSET_STATE_DELETED} or not str(asset.get("path") or "").strip()


def _normalize_path_hashes(path_hashes: Sequence[str] | str) -> list[str]:
    """统一处理单个或批量 path_hash 输入。"""
    if isinstance(path_hashes, str):
        value = path_hashes.strip()
        return [value] if value else []

    normalized: list[str] = []
    seen: set[str] = set()
    for path_hash in path_hashes:
        value = str(path_hash or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _sanitize_model_payload(payload: dict[str, Any], valid_field_names: set[str]) -> dict[str, Any]:
    """过滤掉模型上不存在的字段，避免批量写入时混入 UI 临时字段。"""
    return {key: value for key, value in payload.items() if key in valid_field_names}


def _coerce_json_list(value: Any) -> list[Any]:
    """兼容旧库里被二次 JSON 编码的列表字段。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return [text]
        if isinstance(parsed, list):
            return parsed
        if parsed in (None, ""):
            return []
        return [parsed]
    return [value]


def normalize_user_mod_data_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """统一用户自定义数据的可变字段格式，避免旧格式继续扩散。"""
    normalized = dict(payload or {})
    normalized["mod_id"] = normalize_package_id(normalized.get("mod_id"))
    for field_name in ("tags", "ignored_issues"):
        if field_name in normalized:
            normalized[field_name] = [str(item).strip() for item in _coerce_json_list(normalized.get(field_name)) if str(item).strip()]
    if "interlock_id" in normalized:
        interlock_id = normalized.get("interlock_id")
        if hasattr(interlock_id, "id"):
            interlock_id = interlock_id.id
        normalized["interlock_id"] = str(interlock_id or "").strip() or None
    return normalized


def normalize_interlock_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """统一联锁组结构，导入导出和迁移共用同一套格式。"""
    normalized = dict(payload or {})
    normalized["id"] = str(normalized.get("id") or "").strip()
    normalized["chain"] = normalize_package_ids(_coerce_json_list(normalized.get("chain")))
    return normalized


def _normalize_language_fields(asset: dict[str, Any]) -> dict[str, Any]:
    """统一数据库读出时的语言字段格式，兼容历史旧数据。"""
    asset["supported_languages"] = normalize_language_codes(asset.get("supported_languages", []))
    if "language" in asset and asset.get("language") is not None:
        asset["language"] = normalize_language_code(asset.get("language"))
    return asset


def _normalize_file_stats(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, count in value.items():
        try:
            normalized[str(key)] = int(count or 0)
        except (TypeError, ValueError):
            normalized[str(key)] = 0
    return normalized


def _build_coexist_sync_info(local_asset: dict[str, Any], workshop_asset: dict[str, Any]) -> dict[str, Any]:
    """判断本地共存副本是否落后于工坊版本，时间方向明确时优先用时间。"""
    local_modify_time = int(local_asset.get("file_modify_time") or 0)
    workshop_modify_time = int(workshop_asset.get("file_modify_time") or 0)
    local_size = int(local_asset.get("file_size") or 0)
    workshop_size = int(workshop_asset.get("file_size") or 0)
    local_stats = _normalize_file_stats(local_asset.get("file_stats"))
    workshop_stats = _normalize_file_stats(workshop_asset.get("file_stats"))

    known_differences = []
    has_comparable_time = local_modify_time > 0 and workshop_modify_time > 0
    workshop_is_newer = has_comparable_time and workshop_modify_time > local_modify_time
    workshop_is_not_older = (not has_comparable_time) or workshop_modify_time >= local_modify_time

    if workshop_is_newer:
        known_differences.append("modify_time")
    if workshop_is_not_older:
        if local_size > 0 and workshop_size > 0 and local_size != workshop_size:
            known_differences.append("size")
        if local_stats and workshop_stats and local_stats != workshop_stats:
            known_differences.append("file_stats")

    return {
        "coexist_sync_state": "outdated" if known_differences else "synced",
        "coexist_sync_diff": {
            "signals": known_differences,
            "local_modify_time": local_modify_time,
            "workshop_modify_time": workshop_modify_time,
            "local_size": local_size,
            "workshop_size": workshop_size,
            "local_file_stats": local_stats,
            "workshop_file_stats": workshop_stats,
        },
    }


def _should_include_workshop_in_runtime_detection(context: ProfileContext | None) -> bool:
    return bool(resolve_profile_runtime_capabilities(context).get("workshop_detection_enabled", False))


def _should_include_workshop_in_runtime_deploy(context: ProfileContext | None) -> bool:
    return bool(resolve_profile_runtime_capabilities(context).get("workshop_deploy_enabled", False))


def _ensure_user_data_rows(mod_ids: Iterable[str]) -> None:
    """
    确保 UserModData 中存在这些 mod_id 的占位记录。

    GroupMod 和 interlock 都通过 UserModData 作为“用户层主键”做外键关联，
    因此只要后续逻辑要写入这些关系，就必须先把父记录准备好。
    """
    stubs = [{"mod_id": mod_id} for mod_id in normalize_package_ids(list(mod_ids))]
    if not stubs: return
    UserModData.insert_many(stubs).on_conflict_ignore().execute()


def _mod_dir_exists(path: str) -> bool:
    """
    判断一个模组目录是否仍然像“一个有效 Mod”。

    这里不用简单的 os.path.exists(path)，而是检查 About.xml / About.xml.disabled，
    因为项目里“存在目录但已失去 Mod 结构”的情况也应视为失效。
    """
    if not path: return False
    mod_path = Path(path)
    return ((mod_path / "About" / "About.xml").is_file() or (mod_path / "About" / "About.xml.disabled").is_file())


@dataclass(frozen=True)
class _ProfilePathScope:
    """
    将 Profile 相关的物理路径和启用开关收束成一个只读对象。

    `ModDAO.get_profile_mods()` 和三域分类都依赖同一套路径判断规则。
    以前这些规则分散在方法内部，后续一旦有人修改优先级或路径标准化逻辑，
    很容易只改到一半，导致“列表可见性”和“工作区分类”不一致。
    """

    local_root: str = ""
    dlc_root: str = ""
    workshop_root: str = ""
    self_root: str = ""
    tool_root: str = ""
    use_workshop_mods: bool = False
    use_self_mods: bool = False
    use_tool_mods: bool = False

    @staticmethod
    def _normalize_root(path: str | None) -> str:
        if not path: return ""
        return normalize_dir_root_for_compare(path)

    @classmethod
    def from_context(cls, context: ProfileContext | None) -> "_ProfilePathScope":
        if not context: return cls()
        return cls(
            local_root=cls._normalize_root(context.local_mods_path),
            dlc_root=cls._normalize_root(context.game_dlc_path),
            workshop_root=cls._normalize_root(settings.config.workshop_mods_path),
            self_root=cls._normalize_root(settings.config.self_mods_path),
            tool_root=cls._normalize_root(str(TOOL_MODS_DIR)),
            use_workshop_mods=bool(context.use_workshop_mods),
            use_self_mods=bool(context.use_self_mods),
            use_tool_mods=bool(settings.config.enable_tool_mods),
        )

    def build_visibility_conditions(self, include_workshop: bool = True, force_include_workshop: bool = False) -> list[Any]:
        """
        生成当前 Profile 下“哪些路径应被视为可见资产”的查询条件。

        注意这里只负责“路径进入候选池”，后续真正的“谁最终可见”还要走遮蔽仲裁。
        """
        conditions: list[Any] = []
        if self.local_root:
            conditions.append(ModAsset.path.startswith(self.local_root))
        if self.dlc_root:
            conditions.append(ModAsset.path.startswith(self.dlc_root))
        if self.workshop_root and include_workshop and (self.use_workshop_mods or force_include_workshop):
            conditions.append(ModAsset.path.startswith(self.workshop_root))
        if self.use_self_mods and self.self_root:
            conditions.append(ModAsset.path.startswith(self.self_root))
        if self.use_tool_mods and self.tool_root:
            conditions.append(ModAsset.path.startswith(self.tool_root))
        return conditions

    def _normalize_asset_path(self, path: str | None) -> str:
        return self._normalize_root(path)

    def priority_for_path(self, path: str | None) -> int:
        """
        返回路径在可见性仲裁中的优先级。

        数字越小代表优先级越高：
        DLC > Local > Self > Workshop > Tool > Unknown
        """
        normalized_path = self._normalize_asset_path(path)
        if self.dlc_root and normalized_path.startswith(self.dlc_root):
            return 0
        if self.local_root and normalized_path.startswith(self.local_root):
            return 1
        if self.self_root and normalized_path.startswith(self.self_root):
            return 2
        if self.workshop_root and normalized_path.startswith(self.workshop_root):
            return 3
        if self.tool_root and normalized_path.startswith(self.tool_root):
            return 4
        return 9

    def domain_for_path(self, path: str | None) -> str:
        """
        将一个物理路径归类到运行时域。

        这里比 `classify_asset()` 更底层，专门服务于冲突检测 / 部署分析。
        它只看路径归属，不关心数据库里的 `store` 字段，避免历史脏数据把运行时判定带偏。
        """
        normalized_path = self._normalize_asset_path(path)
        if self.dlc_root and normalized_path.startswith(self.dlc_root):
            return "dlc"
        if self.local_root and normalized_path.startswith(self.local_root):
            return "local"
        if self.self_root and normalized_path.startswith(self.self_root):
            return "self"
        if self.workshop_root and normalized_path.startswith(self.workshop_root):
            return "workshop"
        if self.tool_root and normalized_path.startswith(self.tool_root):
            return "tool"
        return "unknown"

    def includes_runtime_path(self, path: str | None, include_workshop: bool | None = None) -> bool:
        """
        判断一个路径是否属于“当前 Profile 运行时会参与仲裁的域”。

        库存扫描会把所有域都写入数据库，但当前环境冲突/部署只应该看启用域。
        """
        domain = self.domain_for_path(path)
        if domain in {"dlc", "local"}:
            return True
        if domain == "self":
            return self.use_self_mods
        if domain == "workshop":
            if include_workshop is None:
                return self.use_workshop_mods
            return bool(include_workshop and self.workshop_root)
        if domain == "tool":
            return self.use_tool_mods
        return False

    def classify_asset(self, asset: dict[str, Any]) -> str:
        """
        将资产归入工作区三域视图。

        本地/DLC 必须按当前 Profile 路径归属判断，不能只信任 `store=local`。
        否则其它环境扫描过的本地模组会混入当前工作区。
        """
        store = str(asset.get("store") or "").strip().lower()
        path = str(asset.get("path") or "")
        normalized_path = self._normalize_asset_path(path)

        if ((self.local_root and normalized_path.startswith(self.local_root))
            or (self.dlc_root and normalized_path.startswith(self.dlc_root))):
            return "local"
        if store == "workshop":
            return "workshop"
        if store == "self":
            return "self"
        return "unknown"


def _load_group_names_by_mod_id() -> dict[str, list[str]]:
    """
    预加载 package_id -> [group_name] 映射。

    这一步属于“展示增强信息”，与 Mod 主查询无关，但前端很多视图都依赖它。
    为了避免在每个 Mod 上做 N 次查询，这里统一一次取全后内存分发。
    """
    group_map: dict[str, list[str]] = {}
    try:
        query = (
            GroupMod.select(GroupMod.mod_id, GroupData.name)
            .join(GroupData, on=(GroupMod.group_id == GroupData.group_id))
            .dicts()
        )
        for row in query:
            mod_id = normalize_package_id(row.get("mod_id"))
            if not mod_id:
                continue
            group_map.setdefault(mod_id, []).append(row["name"])
    except Exception as exc:
        logger.error(f"加载分组映射失败：{exc}")
    return group_map


def _build_group_structures(allowed_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """
    统一组装分组数据结构。

    `get_all_groups_structured()` 和 `get_groups_structured_by_mod_ids()` 的唯一区别，
    只是是否需要按当前可见 Mod 集合过滤成员，因此用一个内部函数收口。
    """
    if getattr(db, "deferred", False):
        # 单测会用假的 DAO / Models 预注入来隔离排序逻辑。
        # 一旦其它测试先导入了真实 DAO，这里就可能在“数据库尚未初始化”时被调用。
        # 对这类预初始化场景，分组信息本来就只是可选增强数据，直接回退为空更安全，
        # 也能避免排序、预览等纯内存逻辑被数据库初始化顺序绑死。
        return []

    groups = list(
        GroupData.select()
        .order_by(GroupData.sort_index, GroupData.group_id)
        .dicts()
    )
    group_mods = list(
        GroupMod.select()
        .order_by(GroupMod.group_id, GroupMod.sort_index, GroupMod.mod_id)
        .dicts()
    )

    group_map = {group["group_id"]: [] for group in groups}
    seen_mod_ids_by_group = {group["group_id"]: set() for group in groups}
    for group_mod in group_mods:
        group_id = group_mod["group_id"]
        mod_id = normalize_package_id(group_mod.get("mod_id"))
        if allowed_ids is not None and mod_id not in allowed_ids:
            continue
        if group_id in group_map and mod_id and mod_id not in seen_mod_ids_by_group[group_id]:
            seen_mod_ids_by_group[group_id].add(mod_id)
            group_map[group_id].append(mod_id)

    for group in groups:
        group["mod_ids"] = group_map.get(group["group_id"], [])
    return groups


def _normalize_and_validate_group_name(
    name: Any,
    error_prefix: str,
    exclude_group_id: str | None = None,
) -> str:
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValueError(f"{error_prefix}：分组名称不能为空。")
    for group in GroupData.select(GroupData.group_id, GroupData.name):
        if exclude_group_id and group.group_id == exclude_group_id:
            continue
        if str(group.name or "").strip() == normalized_name:
            raise ValueError(f"{error_prefix}：分组名称已存在。")
    return normalized_name


def _require_existing_group(group_id: str, error_prefix: str) -> str:
    normalized_group_id = str(group_id or "").strip()
    if not normalized_group_id or not GroupData.get_or_none(GroupData.group_id == normalized_group_id):
        raise ValueError(f"{error_prefix}：目标分组不存在。")
    return normalized_group_id


def _normalize_group_mod_ids(
    mod_ids: Iterable[Any] | None,
    *,
    reject_duplicates: bool = False,
    duplicate_error_prefix: str = "分组处理失败",
) -> list[str]:
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for raw_mod_id in mod_ids or []:
        mod_id = normalize_package_id(raw_mod_id)
        if not mod_id:
            continue
        if mod_id in seen_ids:
            if reject_duplicates:
                raise ValueError(f"{duplicate_error_prefix}：提交的成员列表存在重复项。")
            continue
        seen_ids.add(mod_id)
        normalized_ids.append(mod_id)
    return normalized_ids


def _assert_mod_assets_exist(mod_ids: Iterable[str], error_prefix: str) -> None:
    normalized_ids = _normalize_group_mod_ids(mod_ids)
    if not normalized_ids:
        return
    valid_ids = {
        normalize_package_id(asset.package_id)
        for asset in ModAsset.select(ModAsset.package_id).where(
            cast(Any, ModAsset.package_id).in_(normalized_ids)
        )
    }
    invalid_ids = [mod_id for mod_id in normalized_ids if mod_id not in valid_ids]
    if invalid_ids:
        raise ValueError(f"{error_prefix}：提交的成员列表包含无效成员。")


class ModDAO:
    """
    模组数据库主入口。

    这个类现在只保留“读取可见模组 / 批量写入资产与用户数据 / 用户侧轻量编辑”。
    任何会触碰磁盘、扫描目录、删除物理文件、修复联锁的行为，都会交给
    `ModMaintenanceDAO` 或 `ModInterlockDAO` 处理。
    """

    @staticmethod
    def get_profile_mods(context: ProfileContext | None):
        """
        根据当前 Profile 获取“最终可见”的模组列表。

        这里不是简单的数据库查询，而是三步业务编排：
        1. 先按 Profile 路径把候选资产筛出来
        2. 再按 DLC > Local > Self > Workshop > Tool 的优先级做遮蔽仲裁
        3. 最后补充 groups 等前端展示字段

        这个返回值是项目里“当前环境实际可见模组”的事实来源，
        AI、排序、导入检查、主界面都依赖它。
        """
        if not context: return []

        scope = _ProfilePathScope.from_context(context)
        include_workshop = _should_include_workshop_in_runtime_detection(context)
        conditions = scope.build_visibility_conditions(
            include_workshop=include_workshop,
            force_include_workshop=include_workshop,
        )
        if not conditions: return []

        combined_condition = reduce(operator.or_, conditions)
        active_condition = (
            ((ModAsset.disabled == False) | (ModAsset.disabled.is_null()))  # type: ignore
            & _present_asset_condition()
        )
        query = (
            ModAsset.select(ModAsset, UserModData)
            .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
            .where(combined_condition & active_condition)
            .dicts()
        )

        group_map = _load_group_names_by_mod_id()
        grouped_assets: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for asset in query:
            _normalize_language_fields(asset)
            package_id = normalize_package_id(asset.get("package_id"))
            if not package_id:
                continue
            asset["groups"] = group_map.get(package_id, [])
            grouped_assets[package_id].append(asset)

        visible_mods: list[dict[str, Any]] = []
        for package_id in sorted(grouped_assets.keys()):
            group = sorted(
                grouped_assets[package_id],
                key=lambda asset: (
                    scope.priority_for_path(asset.get("path")),
                    os.path.dirname(str(asset.get("path") or "")).lower(),
                    str(asset.get("path") or "").lower(),
                ),
            )
            if not group:
                continue

            winner = dict(group[0])
            if len(group) > 1:
                winner["_has_shadow_version"] = True

            by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for asset in group:
                by_parent[os.path.dirname(str(asset.get("path") or "")).lower()].append(asset)
            has_hard_conflict = any(len(items) > 1 for items in by_parent.values())
            if has_hard_conflict:
                winner["has_package_conflict"] = True

            if not has_hard_conflict and scope.domain_for_path(winner.get("path")) in {"local", "self"}:
                workshop_variants = [
                    dict(asset)
                    for asset in group[1:]
                    if scope.domain_for_path(asset.get("path")) == "workshop"
                ]
                if workshop_variants:
                    workshop_variant = workshop_variants[0]
                    workshop_variant["groups"] = group_map.get(package_id, [])
                    winner["is_coexistence"] = True
                    winner.update(_build_coexist_sync_info(winner, workshop_variant))
                    winner["coexist_workshop_variant"] = workshop_variant

            visible_mods.append(winner)

        return visible_mods

    @staticmethod
    def get_localizable_assets(context: ProfileContext | None, path_hashes: Sequence[str] | str, store: str):
        """
        获取当前 Profile 路径范围内允许同步为本地共存的资产。

        API 层传入的是 path_hash，但数据库里可能残留其它环境的同类资产；
        这里再按当前 Profile 的运行时路径做一次约束，避免跨环境误同步。
        """
        scope = _ProfilePathScope.from_context(context)
        hashes = _normalize_path_hashes(path_hashes)
        normalized_store = str(store or "").strip().lower()
        if not context or not hashes or not normalized_store:
            return []

        query = (
            ModAsset.select(ModAsset, UserModData.alias_name)
            .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
            .where(
                (ModAsset.path_hash << hashes)  # type: ignore
                & (ModAsset.store == normalized_store)
                & _present_asset_condition()
            )
            .dicts()
        )
        return [
            asset for asset in query
            if scope.includes_runtime_path(asset.get("path"), include_workshop=True)
        ]

    @staticmethod
    def get_profile_disabled_mods(context: ProfileContext | None):
        """
        获取当前环境路径范围内的物理禁用 Mod。

        禁用列表是资产视角，不参与加载顺序仲裁；但它仍必须限定在当前环境相关路径内，
        避免把其它环境扫描过的禁用项混进来。
        """
        if not context: return []

        scope = _ProfilePathScope.from_context(context)
        conditions: list[Any] = []
        if scope.local_root:
            conditions.append(ModAsset.path.startswith(scope.local_root))
        if scope.dlc_root:
            conditions.append(ModAsset.path.startswith(scope.dlc_root))
        if scope.workshop_root:
            conditions.append(ModAsset.path.startswith(scope.workshop_root))
        if scope.self_root:
            conditions.append(ModAsset.path.startswith(scope.self_root))
        if scope.use_tool_mods and scope.tool_root:
            conditions.append(ModAsset.path.startswith(scope.tool_root))
        if not conditions: return []

        combined_condition = reduce(operator.or_, conditions)
        disabled_condition = (
            (ModAsset.disabled == True)  # type: ignore
            & _present_asset_condition()
        )
        query = (
            ModAsset.select(ModAsset, UserModData)
            .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
            .where(combined_condition & disabled_condition)
            .order_by(ModAsset.file_modify_time.desc(), ModAsset.name, ModAsset.package_id)
            .dicts()
        )

        group_map = _load_group_names_by_mod_id()
        disabled_mods: list[dict[str, Any]] = []
        for asset in query:
            _normalize_language_fields(asset)
            package_id = normalize_package_id(asset.get("package_id"))
            if not package_id:
                continue
            asset["groups"] = group_map.get(package_id, [])
            asset["runtime_domain"] = scope.domain_for_path(asset.get("path"))
            disabled_mods.append(asset)
        return disabled_mods

    @staticmethod
    def get_visible_profile_mod(context: ProfileContext | None, package_id: str):
        """
        获取当前 Profile 中一个包名对应的最终可见模组。

        这里仍然复用 `get_profile_mods()` 的结果，而不是重新拼一套单项 SQL，
        原因是“可见性”本质上依赖完整的遮蔽仲裁。单条 SQL 可以更快，
        但更容易和主列表的规则发生漂移。
        """
        normalized_package_id = normalize_package_id(package_id)
        if not context or not normalized_package_id: return None

        for mod in ModDAO.get_profile_mods(context):
            if normalize_package_id(mod.get("package_id")) == normalized_package_id: return mod
        return None

    @staticmethod
    def get_triple_domain_assets(context: ProfileContext | None):
        """
        获取工作区三域资产视图，但不做 Profile 遮蔽。

        这个接口服务于“工作区全景矩阵”之类的 UI，它关心的是：
        - 资产存在于哪个物理域
        - 当前数据库里有哪些条目
        而不是“最终列表里谁可见”。
        """
        scope = _ProfilePathScope.from_context(context)
        all_assets = (
            ModAsset.select(ModAsset, UserModData)
            .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
            .dicts()
        )

        result = {"workshop": [], "self": [], "local": [], "unknown": []}
        for asset in all_assets:
            _normalize_language_fields(asset)
            result[scope.classify_asset(asset)].append(asset)
        return result

    @staticmethod
    def get_profile_conflict_analysis(
        context: ProfileContext | None = None,
        assets: Sequence[dict[str, Any]] | None = None,
        include_workshop: bool | None = None,
        include_workshop_in_detection: bool | None = None,
        include_workshop_in_deploy: bool | None = None,
    ):
        """
        生成当前 Profile 的运行态分析结果。

        这里的职责是统一回答三件事：
        1. 当前启用域内哪些重复属于“同目录硬冲突”
        2. 当前启用域内哪些重复只是“跨目录共存/遮蔽”
        3. 当前 Profile 最终应该部署哪些链接

        这样扫描、部署和后续可能的“切换 Profile 后即时重算”都能共用同一套规则。
        """
        empty_result = {"hard_conflicts": [], "coexistences": [], "deploy_paths": []}
        if not context: return empty_result

        scope = _ProfilePathScope.from_context(context)
        detect_workshop = (
            include_workshop_in_detection
            if include_workshop_in_detection is not None
            else (
                include_workshop
                if include_workshop is not None
                else _should_include_workshop_in_runtime_detection(context)
            )
        )
        deploy_workshop = (
            include_workshop_in_deploy
            if include_workshop_in_deploy is not None
            else (
                include_workshop
                if include_workshop is not None
                else _should_include_workshop_in_runtime_deploy(context)
            )
        )
        active_assets: list[dict[str, Any]] = []

        if assets is None:
            conditions = scope.build_visibility_conditions(
                include_workshop=detect_workshop,
                force_include_workshop=detect_workshop,
            )
            if not conditions: return empty_result
            combined_condition = reduce(operator.or_, conditions)
            active_condition = (
                ((ModAsset.disabled == False) | (ModAsset.disabled.is_null()))  # type: ignore
                & _present_asset_condition()
            )
            query = (
                ModAsset.select()
                .where(combined_condition & active_condition)
                .dicts()
            )
            active_assets = [dict(asset) for asset in query]
        else:
            for asset in assets:
                asset_dict = dict(asset)
                if asset_dict.get("disabled"):
                    continue
                if _asset_marked_unavailable(asset_dict):
                    continue
                if not scope.includes_runtime_path(asset_dict.get("path"), include_workshop=detect_workshop):
                    continue
                active_assets.append(asset_dict)

        grouped_assets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for asset in active_assets:
            path = str(asset.get("path") or "").strip()
            if not path or not scope.includes_runtime_path(path, include_workshop=detect_workshop):
                continue
            package_id = normalize_package_id(asset.get("package_id"))
            if not package_id:
                continue
            _normalize_language_fields(asset)
            grouped_assets[package_id].append(asset)

        hard_conflicts: list[dict[str, Any]] = []
        coexistences: list[dict[str, Any]] = []
        deploy_buckets: dict[str, list[str]] = {"self": [], "workshop": [], "tool": []}

        for package_id in sorted(grouped_assets.keys()):
            group = sorted(
                grouped_assets[package_id],
                key=lambda asset: (
                    scope.priority_for_path(asset.get("path")),
                    os.path.dirname(str(asset.get("path") or "")).lower(),
                    str(asset.get("path") or "").lower(),
                ),
            )
            by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for asset in group:
                by_parent[os.path.dirname(str(asset.get("path") or "")).lower()].append(asset)

            hard_conflict_paths: set[str] = set()
            for same_dir_items in by_parent.values():
                if len(same_dir_items) > 1:
                    for conflict_item in same_dir_items:
                        hard_conflict_paths.add(str(conflict_item.get("path") or ""))
                    hard_conflicts.append({
                        "package_id": package_id,
                        "items": same_dir_items,
                        "type": "same_directory",
                    })

            safe_candidates = [
                asset for asset in group
                if str(asset.get("path") or "") not in hard_conflict_paths
            ]

            if not hard_conflict_paths and len(group) > 1:
                coexistences.append({
                    "package_id": package_id,
                    "items": group,
                    "type": "different_directory",
                })

            if not safe_candidates:
                continue

            winner = safe_candidates[0]
            winner_domain = scope.domain_for_path(winner.get("path"))
            if winner_domain == "workshop" and not deploy_workshop:
                continue
            if winner_domain in deploy_buckets:
                deploy_buckets[winner_domain].append(str(winner["path"]))

        # 按部署优先级合并后做一次去重，避免异常数据导致重复链接请求。
        deploy_paths = list(dict.fromkeys(
            deploy_buckets["self"] + deploy_buckets["workshop"] + deploy_buckets["tool"]
        ))

        return {
            "hard_conflicts": hard_conflicts,
            "coexistences": coexistences,
            "deploy_paths": deploy_paths,
        }

    @staticmethod
    def get_all_mods_with_user_data(ignore_missing: bool = False):
        """
        获取所有 Mod 与其用户数据。

        这个方法当前在仓库里没有直接调用，第一轮保留仅为了兼容外部可能存在的调用。
        `ignore_missing=True` 时会排除 path 为空或缺失的记录。
        """
        query = (
            ModAsset.select(ModAsset, UserModData)
            .join(UserModData, on=(ModAsset.package_id == UserModData.mod_id), join_type=JOIN.LEFT_OUTER)
        )
        if ignore_missing:
            query = query.where(_present_asset_condition())
        return [_normalize_language_fields(asset) for asset in query.dicts()]

    @staticmethod
    def get_all_user_data():
        """获取全部用户自定义数据。"""
        return list(UserModData.select().dicts())

    @staticmethod
    def get_mod_snapshots():
        """
        返回扫描器需要的轻量快照。

        扫描器并不需要整个 ModAsset，只需要和增量扫描判定相关的字段。
        因此这里直接返回 path_hash -> snapshot 的字典，减少上层二次转换。
        """
        query = (
            ModAsset.select(
                ModAsset.path_hash,
                ModAsset.file_create_time,
                ModAsset.file_modify_time,
                ModAsset.file_size,
                ModAsset.package_id,
                ModAsset.workshop_id,
                ModAsset.path,
                ModAsset.disabled,
                ModAsset.name,
                ModAsset.version,
                ModAsset.store,
                ModAsset.state,
                ModAsset.supported_versions,
            )
            .dicts()
        )

        snapshots: dict[str, dict[str, Any]] = {}
        for row in query:
            snapshots[row["path_hash"]] = {
                "ctime": row["file_create_time"] or 0,
                "mtime": row["file_modify_time"] or 0,
                "size": row["file_size"] or 0,
                "package_id": normalize_package_id(row.get("package_id")),
                "workshop_id": row.get("workshop_id"),
                "path": row.get("path"),
                "disabled": row.get("disabled"),
                "name": row.get("name", ""),
                "version": row.get("version", ""),
                "store": row.get("store", "local"),
                "state": row.get("state") or MOD_ASSET_STATE_PRESENT,
                "supported_versions": row.get("supported_versions", []),
            }
        return snapshots

    @staticmethod
    def batch_upsert_mods(mods_data_list: List[Dict[str, Any]]):
        """
        批量插入或更新扫描得到的 ModAsset。

        扫描结果是“资产快照”，天然适合做 upsert。这里会先过滤掉模型上不存在的键，
        再按 path_hash 冲突进行保留式更新，避免 UI 临时字段污染数据库写入。
        """
        if not mods_data_list: return

        valid_field_names = set(ModAsset._meta.fields.keys())  # type: ignore
        preserve_fields = [
            field
            for field in ModAsset._meta.sorted_fields  # type: ignore
            if field.name not in _MOD_ASSET_UPSERT_EXCLUDED_FIELDS
        ]

        with db.atomic():
            for batch in chunked(mods_data_list, 100):
                clean_batch = [_sanitize_model_payload(mod_data, valid_field_names) for mod_data in batch]
                if not clean_batch:
                    continue
                ModAsset.insert_many(clean_batch).on_conflict(
                    conflict_target=[ModAsset.path_hash],
                    preserve=preserve_fields,
                ).execute()

    @staticmethod
    def batch_update_mods(mods_data_list: List[Dict[str, Any]]):
        """
        批量更新已存在的 ModAsset 字段。

        这里按“字段集合”分批，是为了避免不同 payload 的字段不一致时，
        把某些实例上未提供的字段也一起写回数据库。
        """
        if not mods_data_list: return

        field_map = ModAsset._meta.fields  # type: ignore
        batches_by_signature: dict[tuple[str, ...], list[dict[str, Any]]] = {}

        for payload in mods_data_list:
            path_hash = str(payload.get("path_hash") or "").strip()
            if not path_hash: continue
            signature = tuple( sorted( key for key in payload.keys() if key != "path_hash" and key in field_map ) )
            if not signature: continue
            batches_by_signature.setdefault(signature, []).append({"path_hash": path_hash, **payload})

        with db.atomic():
            for signature, batch in batches_by_signature.items():
                update_fields = [field_map[field_name] for field_name in signature]
                model_instances = [ModAsset(**payload) for payload in batch]
                ModAsset.bulk_update(model_instances, fields=update_fields, batch_size=100)

    @staticmethod
    def batch_update_shadow_paths(shadow_paths_map: Dict[str, List[str]]):
        """
        批量回写 shadow_paths。

        扫描器会重新计算每个“最终保留条目”背后有哪些被禁用副本，
        这里仅负责把结果落库，不参与任何业务推断。
        """
        if not shadow_paths_map: return

        model_instances = [
            ModAsset(path_hash=path_hash, shadow_paths=paths)
            for path_hash, paths in shadow_paths_map.items()
        ]

        with db.atomic():
            for batch in chunked(model_instances, 100):
                ModAsset.bulk_update(list(batch), fields=[ModAsset.shadow_paths], batch_size=100)

    @staticmethod
    def update_user_data(package_id: str, data_dict: Dict[str, Any]):
        """
        更新单个 Mod 的用户数据。

        单条更新最终也收口到 `batch_upsert_user_data()`，这样字段过滤、
        默认值处理和冲突策略都只有一套实现。
        """
        normalized_package_id = normalize_package_id(package_id)
        if not normalized_package_id or not data_dict: return True

        payload = {"mod_id": normalized_package_id, **data_dict}
        ModDAO.batch_upsert_user_data([payload])
        return True

    @staticmethod
    def batch_upsert_user_data(user_data_list: List[Dict[str, Any]]):
        """
        批量插入或更新 UserModData。

        设计目标是“按输入字段做部分更新”：
        - 传了哪些字段，就更新哪些字段
        - 没传的字段，不在这次写入里被覆盖
        """
        if not user_data_list: return

        valid_field_names = set(UserModData._meta.fields.keys())  # type: ignore
        input_keys = set().union(*(data.keys() for data in user_data_list))
        update_fields = [
            field
            for field in UserModData._meta.sorted_fields  # type: ignore
            if field.name in input_keys and field.name != "mod_id"
        ]

        with db.atomic():
            for batch in chunked(user_data_list, 100):
                clean_batch = []
                for user_data in batch:
                    clean_data = _sanitize_model_payload(user_data, valid_field_names)
                    clean_data = normalize_user_mod_data_payload(clean_data)
                    if clean_data["mod_id"]:
                        clean_batch.append(clean_data)
                if not clean_batch:
                    continue

                UserModData.insert_many(clean_batch).on_conflict(
                    conflict_target=[UserModData.mod_id],
                    preserve=update_fields,
                ).execute()

    @staticmethod
    def set_user_mods_type(mod_ids: List[str], new_type: str):
        """批量设置用户自定义 Mod 类型。"""
        normalized_ids = normalize_package_ids(mod_ids)
        if not normalized_ids: return
        ModDAO.batch_upsert_user_data([{"mod_id": mod_id, "user_mod_type": new_type} for mod_id in normalized_ids])

    @staticmethod
    def set_mods_color(mod_ids: List[str], color_hex: str):
        """批量设置 UI 标记颜色。"""
        normalized_ids = normalize_package_ids(mod_ids)
        if not normalized_ids: return
        if color_hex and not is_hex_color(color_hex):
            raise ValueError("Invalid color format. Use #RRGGBB.")
        ModDAO.batch_upsert_user_data([{"mod_id": mod_id, "sign_color": color_hex} for mod_id in normalized_ids])

    @staticmethod
    def add_tags_to_mods(mod_ids: List[str], new_tags: List[str]):
        """
        批量追加标签并自动去重。

        这里刻意使用 `dict.fromkeys()`，而不是 set，
        这样既能去重，也能保留用户更容易理解的标签顺序。
        """
        normalized_ids = normalize_package_ids(mod_ids)
        cleaned_tags = [str(tag).strip() for tag in new_tags if str(tag).strip()]
        if not normalized_ids or not cleaned_tags: return

        with db.atomic():
            existing_records = UserModData.select().where(cast(Any, UserModData.mod_id).in_(normalized_ids))
            existing_map = {normalize_package_id(record.mod_id): record for record in existing_records}
            batch_data = []

            for mod_id in normalized_ids:
                record = existing_map.get(mod_id)
                current_tags = list(record.tags) if record and record.tags else []
                updated_tags = list(dict.fromkeys(current_tags + cleaned_tags))
                batch_data.append({"mod_id": mod_id, "tags": updated_tags})

            if batch_data:
                ModDAO.batch_upsert_user_data(batch_data)

    @staticmethod
    def remove_tags_from_mods(mod_ids: List[str], remove_tags: List[str]):
        """从指定 Mod 中批量移除标签。"""
        normalized_ids = normalize_package_ids(mod_ids)
        remove_set = {str(tag).strip() for tag in remove_tags if str(tag).strip()}
        if not normalized_ids or not remove_set: return

        with db.atomic():
            existing_records = UserModData.select().where(cast(Any, UserModData.mod_id).in_(normalized_ids))
            existing_map = {normalize_package_id(record.mod_id): record for record in existing_records}
            batch_data = []

            for mod_id in normalized_ids:
                record = existing_map.get(mod_id)
                if not record or not record.tags:
                    continue
                current_tags = list(record.tags)
                new_tags = [tag for tag in current_tags if tag not in remove_set]
                if len(new_tags) != len(current_tags):
                    batch_data.append({"mod_id": mod_id, "tags": new_tags})

            if batch_data:
                ModDAO.batch_upsert_user_data(batch_data)


class ModInterlockDAO:
    """
    Mod 联锁相关逻辑。

    联锁不是简单的 CRUD，它体现的是“多个 Mod 必须维持固定顺序”的业务规则，
    因此单独拆出来，避免继续混在 `ModDAO` 的普通读写里。
    """

    @staticmethod
    def link_mods(mod_ids: List[str]):
        """创建新的联锁序列，并把涉及的 Mod 从旧联锁中安全摘出。"""
        normalized_ids = normalize_package_ids(mod_ids)
        if len(normalized_ids) < 2: return {"status": "error", "msg": "联锁至少需要 2 个模组"}

        with db.atomic():
            existing_mods = UserModData.select(UserModData.mod_id, UserModData.interlock_id).where(UserModData.mod_id << normalized_ids)  # type: ignore
            old_interlock_ids = {mod.interlock_id for mod in existing_mods if getattr(mod, "interlock_id", None)}

            if old_interlock_ids:
                old_interlocks = ModInterlock.select().where(ModInterlock.id << list(old_interlock_ids))  # type: ignore
                for interlock in old_interlocks:
                    new_chain = [mod_id for mod_id in interlock.chain if mod_id not in normalized_ids]
                    if len(new_chain) < 2:
                        interlock.delete_instance()
                    else:
                        interlock.chain = new_chain
                        interlock.save()

            new_id = uuid.uuid4().hex
            ModInterlock.create(id=new_id, chain=normalized_ids)
            _ensure_user_data_rows(normalized_ids)
            UserModData.update(interlock_id=new_id).where(UserModData.mod_id << normalized_ids).execute()  # type: ignore

        return {"interlock_id": new_id, "chain": normalized_ids}

    @staticmethod
    def unlink_mods(mod_ids: List[str]):
        """把指定 Mod 从其所属联锁中剥离。"""
        normalized_ids = normalize_package_ids(mod_ids)
        if not normalized_ids: return True

        with db.atomic():
            target_mods = UserModData.select(UserModData.mod_id, UserModData.interlock_id).where(UserModData.mod_id << normalized_ids)  # type: ignore
            affected_interlock_ids = {mod.interlock_id for mod in target_mods if getattr(mod, "interlock_id", None)}

            if affected_interlock_ids:
                interlocks = ModInterlock.select().where(ModInterlock.id << list(affected_interlock_ids))  # type: ignore
                for interlock in interlocks:
                    new_chain = [mod_id for mod_id in interlock.chain if mod_id not in normalized_ids]
                    if len(new_chain) < 2:
                        interlock.delete_instance()
                    else:
                        interlock.chain = new_chain
                        interlock.save()

            UserModData.update(interlock_id=None).where(UserModData.mod_id << normalized_ids).execute()  # type: ignore

        return True

    @staticmethod
    def heal_interlock(interlock_id: str):
        """
        修复一个已经断裂的联锁。

        这里的“修复”不是尝试补回缺失 Mod，而是保守地剔除已经失效的成员，
        让剩余仍然存在的 Mod 继续保持顺序。
        """
        interlock = ModInterlock.get_or_none(ModInterlock.id == interlock_id)
        if not interlock: return None

        with db.atomic():
            existing_assets = ModAsset.select(ModAsset.package_id).where(
                (ModAsset.package_id << interlock.chain)
                & _present_asset_condition()
            )
            valid_ids = {normalize_package_id(asset.package_id) for asset in existing_assets}
            healed_chain = [mod_id for mod_id in interlock.chain if normalize_package_id(mod_id) in valid_ids]

            if len(healed_chain) < 2:
                interlock.delete_instance()
                return []

            interlock.chain = healed_chain
            interlock.save()
            return healed_chain

    @staticmethod
    def get_interlock_missing_mods(interlock_id: str, context: ProfileContext = None):  # type: ignore
        """
        分析联锁中哪些成员在当前环境下不可用，以及为什么不可用。

        reason 分类：
        - missing: 数据库里没有有效路径，或物理结构已失效
        - disabled: 物理目录存在，但 About 被禁用
        - shadowed: 物理存在，但当前 Profile 中不可见
        """
        interlock = ModInterlock.get_or_none(ModInterlock.id == interlock_id)
        if not interlock: return []

        all_assets = (
            ModAsset.select(ModAsset.package_id, ModAsset.path, ModAsset.disabled, ModAsset.workshop_id, ModAsset.state)
            .where(ModAsset.package_id << interlock.chain)
            .dicts()
        )
        asset_map = {normalize_package_id(asset.get("package_id")): asset for asset in all_assets}

        visible_ids: set[str] = set()
        if context:
            visible_ids = {normalize_package_id(mod.get("package_id")) for mod in ModDAO.get_profile_mods(context)}

        missing_details = []
        for mod_id in interlock.chain:
            normalized_id = normalize_package_id(mod_id)
            if normalized_id in visible_ids:
                continue

            asset = asset_map.get(normalized_id)
            detail = {
                "package_id": normalized_id,
                "workshop_id": asset.get("workshop_id") if asset else None,
                "reason": "missing",
            }

            if asset:
                if _asset_marked_unavailable(asset) or not _mod_dir_exists(asset["path"]):
                    detail["reason"] = "missing"
                elif asset.get("disabled"):
                    detail["reason"] = "disabled"
                elif context and normalized_id not in visible_ids:
                    detail["reason"] = "shadowed"

            missing_details.append(detail)

        return missing_details


class ModMaintenanceDAO:
    """
    会触碰磁盘或执行全库维护任务的操作。

    这类逻辑以前放在 `ModDAO` 里最容易让人误判：
    看名字像是普通 DAO，实际却会改文件、移动回收站、扫描目录。
    单独拆出来后，调用方一眼就能看出这是“带副作用的维护操作”。
    """

    @staticmethod
    def set_mod_disabled_status(path: str, disable: bool = True):
        """通过改名 About.xml / About.xml.disabled 切换物理禁用状态。"""
        try:
            about_state = ModAnalyzer.resolve_mod_about_state(path, cleanup_dual_files=True)
        except Exception as exc:
            return False, f"清理 About 文件残留失败: {exc}"

        if not about_state.resolved_path:
            return False, "未找到 About.xml 或 About.xml.disabled，无法切换禁用状态"

        if about_state.is_disabled == disable:
            ModAsset.update(disabled=disable).where(ModAsset.path == path).execute()
            return True, "状态已同步"

        source_path = about_state.resolved_path
        target_path = about_state.disabled_xml if disable else about_state.about_xml
        try:
            if os.path.exists(target_path):
                os.remove(target_path)
            os.replace(source_path, target_path)
        except Exception as exc:
            return False, f"文件操作失败: {exc}"

        ModAsset.update(disabled=disable).where(ModAsset.path == path).execute()
        return True, "成功"

    @staticmethod
    def delete_mods_physically(path_hashes: List[str] | str, force: bool = False):
        """
        根据 path_hash 删除 Mod。

        这里先删数据库，再尝试删除物理文件，保持“界面不再引用已删除条目”的数据库事实优先。
        如果物理删除失败，只记录错误，不回滚数据库，避免在损坏路径上反复死循环。
        """
        normalized_hashes = _normalize_path_hashes(path_hashes)
        if not normalized_hashes: return {"success_count": 0, "errors": []}

        assets = list(
            ModAsset.select(ModAsset.path, ModAsset.path_hash, ModAsset.name, ModAsset.state)
            .where(ModAsset.path_hash.in_(normalized_hashes))  # type: ignore
            .dicts()
        )
        if not assets: return {"success_count": 0, "errors": ["未找到有效的模组记录"]}

        target_paths: list[str] = []
        valid_hashes = [asset["path_hash"] for asset in assets]
        errors: list[str] = []
        success_count = 0
        task_id = uuid.uuid4().hex
        EventBus.resume()
        EventBus.emit_progress(
            task_id,
            "file-delete",
            status="pending",
            progress=0,
            message=f"准备删除 {len(assets)} 个模组...",
            metrics={"title": "删除模组文件", "current": 0, "total": len(assets)},
        )

        for asset in assets:
            path = str(asset.get("path") or "")
            state = str(asset.get("state") or MOD_ASSET_STATE_PRESENT).strip().lower()
            if state in {MOD_ASSET_STATE_MISSING, MOD_ASSET_STATE_DELETED} or not path or not os.path.exists(path):
                success_count += 1
                continue
            target_paths.append(path)

        try:
            with db.atomic():
                ModAsset.delete().where(ModAsset.path_hash << valid_hashes).execute()  # type: ignore
        except Exception as exc:
            logger.error(f"数据库删除失败：{exc}")
            EventBus.emit_progress(task_id, "file-delete", status="failed", progress=0, message="数据库记录清理失败", metrics={"title": "删除模组文件"})
            return {"success_count": 0, "errors": [f"数据库记录清理失败: {exc}"]}

        total_paths = max(len(target_paths), 1)
        for index, path in enumerate(target_paths, start=1):
            EventBus.emit_progress(
                task_id,
                "file-delete",
                status="running",
                progress=min(95, int((index - 1) / total_paths * 90) + 5),
                message=f"正在删除: {os.path.basename(path)}",
                metrics={"title": "删除模组文件", "current": index, "total": len(target_paths)},
            )
            try:
                delete_fs_path(path, force=force)
                success_count += 1
            except Exception as exc:
                delete_mode = "彻底删除" if force else "移入回收站"
                errors.append(f"物理文件{delete_mode}失败 ({os.path.basename(path)}): {exc}")

        final_status = "failed" if success_count <= 0 and errors else "success"
        EventBus.emit_progress(
            task_id,
            "file-delete",
            status=final_status,
            progress=100,
            message=f"删除完成：成功 {success_count} 个，失败 {len(errors)} 个",
            metrics={"title": "删除模组文件", "current": len(target_paths), "total": len(target_paths), "success_count": success_count, "error_count": len(errors)},
        )
        return {"success_count": success_count, "errors": errors}

    @staticmethod
    def delete_mod_records(path_hashes: List[str] | str):
        """只删除库存数据库记录，不触碰物理文件；用于取消订阅后清理本地库存显示。"""
        normalized_hashes = _normalize_path_hashes(path_hashes)
        if not normalized_hashes: return {"success_count": 0, "errors": []}

        existing_hashes = [
            row["path_hash"]
            for row in ModAsset.select(ModAsset.path_hash)
                .where(ModAsset.path_hash.in_(normalized_hashes))  # type: ignore
                .dicts()
        ]
        if not existing_hashes: return {"success_count": 0, "errors": ["未找到有效的模组记录"]}

        try:
            with db.atomic():
                deleted_count = ModAsset.delete().where(ModAsset.path_hash << existing_hashes).execute()  # type: ignore
        except Exception as exc:
            logger.error(f"数据库记录删除失败：{exc}")
            return {"success_count": 0, "errors": [f"数据库记录清理失败: {exc}"]}

        return {"success_count": int(deleted_count or 0), "errors": []}

    @staticmethod
    def add_shadow_path(keep_path_hash: str, shadow_path: str):
        """为最终保留的 Mod 记录被遮蔽副本路径。"""
        mod = ModAsset.get_or_none(ModAsset.path_hash == keep_path_hash)
        if not mod: return False

        current_paths = list(mod.shadow_paths or [])
        if shadow_path in current_paths: return True

        current_paths.append(shadow_path)
        mod.shadow_paths = current_paths
        mod.save()
        return True

    @staticmethod
    def clean_invalid_shadow_paths():
        """
        清理所有已经失效的 shadow_paths。

        这里不强行检查 About.xml.disabled，只要目录还在就保留，
        因为 shadow 只是一个“曾被遮蔽副本”的展示辅助信息，不应过度严格。
        """
        cleaned_count = 0
        mods_with_shadows = ModAsset.select().where(cast(Any, ModAsset.shadow_paths).is_null(False))

        with db.atomic():
            for mod in mods_with_shadows:
                current_paths = mod.shadow_paths
                if not current_paths or not isinstance(current_paths, list):
                    continue

                valid_paths = [path for path in current_paths if path and os.path.exists(path)]
                if len(valid_paths) == len(current_paths):
                    continue

                cleaned_count += len(current_paths) - len(valid_paths)
                mod.shadow_paths = valid_paths
                mod.save()
                logger.debug("清理失效禁用副本路径: package_id=%s removed=%s", mod.package_id, len(current_paths) - len(valid_paths))

        return cleaned_count

    @staticmethod
    def find_missing_mods(delete: bool = False, subscribed_workshop_ids: Iterable[str] | None = None):
        """
        查找数据库中已经失效的 Mod。

        - missing_mods: Steam 本地记录仍显示订阅，但没有有效本地模组结构
        - deleted_mods: 数据库记录的本地资产已经删除或失效
        """
        missing_mods: list[str] = []
        deleted_mods: list[str] = []
        restored_mods: list[str] = []
        missing_update_mods: list[str] = []
        deleted_update_mods: list[str] = []
        subscribed_ids = {
            str(workshop_id or "").strip()
            for workshop_id in (subscribed_workshop_ids or [])
            if str(workshop_id or "").strip()
        }

        query = ModAsset.select(ModAsset.path_hash, ModAsset.path, ModAsset.state, ModAsset.store, ModAsset.workshop_id).dicts()
        for asset in query:
            path = str(asset.get("path") or "").strip()
            state = str(asset.get("state") or MOD_ASSET_STATE_PRESENT).strip().lower()
            path_hash = asset["path_hash"]
            has_valid_mod = _mod_dir_exists(path)
            if has_valid_mod:
                if state in {MOD_ASSET_STATE_MISSING, MOD_ASSET_STATE_DELETED}:
                    restored_mods.append(path_hash)
                continue

            workshop_id = str(asset.get("workshop_id") or "").strip()
            store = str(asset.get("store") or "").strip().lower()
            if store == "workshop" and workshop_id and workshop_id in subscribed_ids:
                missing_mods.append(path_hash)
                if state != MOD_ASSET_STATE_MISSING:
                    missing_update_mods.append(path_hash)
            else:
                deleted_mods.append(path_hash)
                if state != MOD_ASSET_STATE_DELETED:
                    deleted_update_mods.append(path_hash)

        total_invalid_mods = missing_mods + deleted_mods
        if not total_invalid_mods and not restored_mods:
            return {"missing_mods": missing_mods, "deleted_mods": deleted_mods, "restored_mods": restored_mods}

        with db.atomic():
            if delete:
                ModAsset.delete().where(cast(Any, ModAsset.path_hash).in_(total_invalid_mods)).execute()
            else:
                now = current_ms()
                if missing_update_mods:
                    ModAsset.update(
                        state=MOD_ASSET_STATE_MISSING,
                        last_scanned_at=now,
                        file_modify_time=now,
                    ).where(cast(Any, ModAsset.path_hash).in_(missing_update_mods)).execute()
                if deleted_update_mods:
                    ModAsset.update(
                        state=MOD_ASSET_STATE_DELETED,
                        last_scanned_at=now,
                        file_modify_time=now,
                    ).where(cast(Any, ModAsset.path_hash).in_(deleted_update_mods)).execute()
                if restored_mods:
                    ModAsset.update(
                        state=MOD_ASSET_STATE_PRESENT,
                        last_scanned_at=now,
                    ).where(cast(Any, ModAsset.path_hash).in_(restored_mods)).execute()

        return {"missing_mods": missing_mods, "deleted_mods": deleted_mods, "restored_mods": restored_mods}

    @staticmethod
    def clean_orphaned_data():
        """
        清理没有任何 ModAsset 对应的用户数据与分组关系。

        这一步是数据库维护任务，不影响正常界面读取，
        但长期不做会留下越来越多的脏数据。
        """
        with db.atomic():
            deleted_user_data = UserModData.delete().where(cast(Any, UserModData.mod_id).not_in(ModAsset.package_id)).execute()
            deleted_group_mod = GroupMod.delete().where(cast(Any, GroupMod.mod_id).not_in(ModAsset.package_id)).execute()
        return {
            "deleted_user_configs": deleted_user_data,
            "deleted_group_relations": deleted_group_mod,
        }


class GroupDAO:
    """管理分组结构、成员关系与排序。"""

    @staticmethod
    def get_all_groups_structured():
        """返回完整分组结构，保留所有成员。"""
        return _build_group_structures()

    @staticmethod
    def get_groups_structured_by_mod_ids(allowed_ids: List[str]):
        """返回只包含当前可见 Mod 的分组结构。"""
        return _build_group_structures(set(normalize_package_ids(allowed_ids)))

    @staticmethod
    def create_group(name: str, color: str = "#ffffff"):
        """创建新分组，默认追加到当前列表末尾。"""
        normalized_name = _normalize_and_validate_group_name(name, "创建分组失败")
        new_id = uuid.uuid4().hex
        max_idx = GroupData.select(fn.MAX(GroupData.sort_index)).scalar()
        return GroupData.create(
            group_id=new_id,
            name=normalized_name,
            color=normalize_hex_color(color),
            sort_index=0 if max_idx is None else int(max_idx) + 1,
            is_expanded=True,
        )

    @staticmethod
    def delete_group(group_id: str):
        """删除分组。GroupMod 会由级联约束一起删除。"""
        normalized_group_id = _require_existing_group(group_id, "删除分组失败")
        return GroupData.delete().where(GroupData.group_id == normalized_group_id).execute()

    @staticmethod
    def update_group_info(group_id: str, **kwargs):
        """更新分组名称、颜色或折叠状态。"""
        normalized_group_id = _require_existing_group(group_id, "更新分组失败")
        allowed_fields = {"name", "color", "is_expanded"}
        clean_updates = {
            key: value
            for key, value in kwargs.items()
            if key in allowed_fields
        }
        if not clean_updates:
            raise ValueError("更新分组失败：未提供有效字段。")
        if "name" in clean_updates:
            clean_updates["name"] = _normalize_and_validate_group_name(
                clean_updates["name"],
                "更新分组失败",
                exclude_group_id=normalized_group_id,
            )
        if "color" in clean_updates:
            clean_updates["color"] = normalize_hex_color(clean_updates["color"])
        if "is_expanded" in clean_updates:
            clean_updates["is_expanded"] = bool(clean_updates["is_expanded"])
        return GroupData.update(**clean_updates).where(GroupData.group_id == normalized_group_id).execute()

    @staticmethod
    def add_mods_to_group(group_id: str, mod_ids: List[str]):
        """向分组批量添加 Mod。只会追加当前尚未在组内且资产有效的成员。"""
        normalized_group_id = _require_existing_group(group_id, "分组添加失败")
        normalized_ids = _normalize_group_mod_ids(mod_ids)
        if not normalized_ids:
            return 0

        with db.atomic():
            existing_ids = set(_normalize_group_mod_ids(
                row.get("mod_id")
                for row in GroupMod.select(GroupMod.mod_id)
                .where(GroupMod.group_id == normalized_group_id)
                .order_by(GroupMod.sort_index, GroupMod.mod_id)
                .dicts()
            ))
            new_ids = [mod_id for mod_id in normalized_ids if mod_id not in existing_ids]
            if not new_ids:
                return 0

            _assert_mod_assets_exist(new_ids, "分组添加失败")
            _ensure_user_data_rows(new_ids)
            max_idx = GroupMod.select(fn.MAX(GroupMod.sort_index)).where(GroupMod.group_id == normalized_group_id).scalar()
            data_source = [
                {
                    "group_id": normalized_group_id,
                    "mod_id": mod_id,
                    "sort_index": (0 if max_idx is None else int(max_idx) + 1) + index,
                }
                for index, mod_id in enumerate(new_ids)
            ]
            for batch in chunked(data_source, 500):
                GroupMod.insert_many(batch).execute()
            return len(new_ids)

    @staticmethod
    def remove_mods_from_group(group_id: str, mod_ids: List[str]):
        """从分组移除一批 Mod。"""
        normalized_group_id = _require_existing_group(group_id, "分组移除失败")
        normalized_ids = _normalize_group_mod_ids(mod_ids)
        if not normalized_ids:
            return 0
        return GroupMod.delete().where(
            (GroupMod.group_id == normalized_group_id)
            & (cast(Any, GroupMod.mod_id).in_(normalized_ids))
        ).execute()

    @staticmethod
    def update_all_expansion_state(is_expanded: bool):
        """一次性展开或折叠全部分组。"""
        GroupData.update(is_expanded=is_expanded).execute()

    @staticmethod
    def reorder_groups(group_id_list: List[str]):
        """按前端传回的新顺序重排分组本身。"""
        normalized_ids = [str(group_id or "").strip() for group_id in group_id_list if str(group_id or "").strip()]
        existing_ids = [row.group_id for row in GroupData.select(GroupData.group_id).order_by(GroupData.sort_index, GroupData.group_id)]
        if not existing_ids:
            return
        if len(normalized_ids) != len(existing_ids):
            raise ValueError("分组排序失败：提交的分组数量与当前数据不一致。")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("分组排序失败：提交的分组列表存在重复项。")
        if set(normalized_ids) != set(existing_ids):
            raise ValueError("分组排序失败：提交的分组集合与当前数据不一致。")

        with db.atomic():
            for index, group_id in enumerate(normalized_ids):
                GroupData.update(sort_index=index).where(GroupData.group_id == group_id).execute()

    @staticmethod
    def reorder_mods_in_group(group_id: str, mod_id_list: List[str]):
        """
        重排分组内成员顺序。

        前端当前拿到的是“当前上下文下可见成员”的子集，而且拖入分组时
        还会把“新加入成员”一并放进这个顺序列表里。
        因此这里不能再要求提交列表必须完全属于当前组内成员，否则会把
        “拖拽新增成员”误判成非法数据。

        正确做法是：
        1. 校验提交列表不能有重复
        2. 允许列表中带有“当前尚未在组内，但在 ModAsset 中有效”的新增成员
        3. 以提交顺序作为最终结果的前缀
        4. 将当前组里“这次没出现在提交列表中的成员”按原顺序去重后统一续到末尾
        """
        normalized_group_id = _require_existing_group(group_id, "分组内排序失败")
        normalized_ids = _normalize_group_mod_ids(
            mod_id_list,
            reject_duplicates=True,
            duplicate_error_prefix="分组内排序失败",
        )
        if not normalized_ids:
            raise ValueError("分组内排序失败：提交的成员列表为空。")

        with db.atomic():
            existing_rows = list(
                GroupMod.select(GroupMod.mod_id, GroupMod.sort_index)
                .where(GroupMod.group_id == normalized_group_id)
                .order_by(GroupMod.sort_index, GroupMod.mod_id)
                .dicts()
            )
            existing_ids = _normalize_group_mod_ids(row.get("mod_id") for row in existing_rows)
            existing_id_set = set(existing_ids)

            new_member_ids = [mod_id for mod_id in normalized_ids if mod_id not in existing_id_set]
            _assert_mod_assets_exist(new_member_ids, "分组内排序失败")

            merged_ids = list(normalized_ids)
            appended_ids = set(normalized_ids)
            for mod_id in existing_ids:
                if mod_id in appended_ids:
                    continue
                appended_ids.add(mod_id)
                merged_ids.append(mod_id)

            _ensure_user_data_rows(merged_ids)
            GroupMod.delete().where(GroupMod.group_id == normalized_group_id).execute()
            data_source = [
                {"group_id": normalized_group_id, "mod_id": mod_id, "sort_index": index}
                for index, mod_id in enumerate(merged_ids)
            ]
            for batch in chunked(data_source, 500):
                GroupMod.insert_many(batch).execute()


class CollectionDAO:
    """管理本地缓存的 Workshop 合集快照。"""

    @staticmethod
    def get_all():
        """获取所有缓存合集，按创建时间倒序。"""
        return list(SubscribedCollection.select().order_by(SubscribedCollection.created_time.desc()).dicts())  # type: ignore

    @staticmethod
    def get_collection_by_id(coll_id: str):
        """获取单个合集缓存。"""
        return SubscribedCollection.get_or_none(SubscribedCollection.id == str(coll_id))

    @staticmethod
    def upsert_collection(coll_id: str, meta: dict, children: list, total: int):
        """
        持久化合集快照。

        created_time 保留首次创建时间，last_sync_time 则反映最近一次成功同步。
        这样前端既能知道“这条记录是什么时候收藏的”，也能知道“缓存新鲜度”。
        """
        existing = SubscribedCollection.get_or_none(SubscribedCollection.id == str(coll_id))
        return SubscribedCollection.insert(
            id=str(coll_id),
            title=meta.get("title"),
            description=meta.get("description"),
            preview_url=meta.get("preview_url"),
            children=children,
            total=total,
            time_updated=meta.get("time_updated", 0),
            created_time=existing.created_time if existing else current_ms(),
            last_sync_time=current_ms(),
        ).on_conflict_replace().execute()

    @staticmethod
    def delete(coll_id: str):
        """删除合集缓存。"""
        return SubscribedCollection.delete().where(SubscribedCollection.id == str(coll_id)).execute()
