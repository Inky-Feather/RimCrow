from __future__ import annotations

from typing import Any

from backend.settings import settings


def normalize_profile_runtime_flags(
    is_steam: bool,
    prefer_steam_launch: bool | None = None,
    use_workshop_mods: bool | None = None,
    *,
    default_prefer_steam_launch: bool | None = None,
    default_use_workshop_mods: bool = False,
) -> dict[str, bool]:
    """
    统一收口环境运行开关。

    规则：
    1. `prefer_steam_launch` 保留用户选择，`is_steam` 只作为识别结果；
    2. `prefer_steam_launch=True` 时，`use_workshop_mods` 必须归零；
    3. 只做冲突归零，不做互相自动补开。

    这里故意不把 `use_workshop_mods` 绑死到 `is_steam=False`：
    有些玩家会关闭 Steam 启动，但仍希望通过链接部署方式使用 Workshop。
    因此两者关系是“互斥”，不是“对立字段”。
    """
    target_is_steam = bool(is_steam)
    if prefer_steam_launch is None:
        prefer_value = bool(
            target_is_steam
            if default_prefer_steam_launch is None
            else default_prefer_steam_launch
        )
    else:
        prefer_value = bool(prefer_steam_launch)

    workshop_value = (
        default_use_workshop_mods
        if use_workshop_mods is None
        else bool(use_workshop_mods)
    )

    if prefer_value:
        workshop_value = False

    return {
        "is_steam": target_is_steam,
        "prefer_steam_launch": prefer_value,
        "use_workshop_mods": workshop_value,
    }


def resolve_profile_runtime_capabilities(
    context: Any | None,
    *,
    workshop_mods_path: str | None = None,
    steam_path: str | None = None,
) -> dict[str, Any]:
    """
    生成当前环境的运行能力快照。

    这里只回答“现在这套环境在当前配置下能做什么”，
    不负责写库，也不直接驱动副作用。

    这样 DAO / API / 扫描器都只消费同一份事实层，
    避免再次把 `prefer_steam_launch` / `use_workshop_mods` 的组合判断
    分散复制到多个文件里。
    """
    if not context:
        return {
            "is_steam": False,
            "is_steam_managed": False,
            "prefer_steam_launch": False,
            "use_workshop_mods": False,
            "has_workshop_mods_path": False,
            "has_steam_path": False,
            "steam_launch_enabled": False,
            "workshop_detection_enabled": False,
            "workshop_deploy_enabled": False,
            "workshop_feature_visible": False,
        }

    normalized = normalize_profile_runtime_flags(
        bool(getattr(context, "is_steam", False)),
        getattr(context, "prefer_steam_launch", None),
        getattr(context, "use_workshop_mods", None),
        default_prefer_steam_launch=bool(getattr(context, "is_steam", False)),
    )
    workshop_root = str(
        workshop_mods_path
        if workshop_mods_path is not None
        else getattr(settings.config, "workshop_mods_path", "")
    ).strip()
    steam_root = str(
        steam_path
        if steam_path is not None
        else getattr(settings.config, "steam_path", "")
    ).strip()
    has_workshop_root = bool(workshop_root)

    return {
        "is_steam": normalized["is_steam"],
        "is_steam_managed": bool(getattr(context, "is_steam_managed", False)),
        "prefer_steam_launch": normalized["prefer_steam_launch"],
        "use_workshop_mods": normalized["use_workshop_mods"],
        "has_workshop_mods_path": has_workshop_root,
        "has_steam_path": bool(steam_root),
        "steam_launch_enabled": bool(normalized["prefer_steam_launch"]),
        "workshop_detection_enabled": bool(
            has_workshop_root
            and (
                normalized["prefer_steam_launch"]
                or normalized["use_workshop_mods"]
            )
        ),
        "workshop_deploy_enabled": bool(
            has_workshop_root
            and normalized["use_workshop_mods"]
            and (not normalized["prefer_steam_launch"])
        ),
        "workshop_feature_visible": has_workshop_root,
    }
