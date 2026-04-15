from dataclasses import asdict, dataclass, field
from typing import Any

from backend.utils.tools import normalize_package_id, normalize_workshop_id
from .models import ParsedLoadOrderData
from backend.utils.versioning import score_version_support


@dataclass(slots=True)
class ImportCheckInstalledCandidate:
    """
    当前环境里可见的候选安装项。

    这里保留最少但足够做判断和展示的字段，避免把整条 Mod 记录原样塞给前端。
    """

    package_id: str
    workshop_id: str
    name: str
    path: str
    store: str


@dataclass(slots=True)
class ImportCheckItem:
    """
    单条导入项的匹配结果。

    status 约定：
    - exact_match: 包名和工坊 ID 都能与当前环境精确匹配
    - package_match: 包名能匹配，但导入项没有有效工坊 ID，无法进一步判定版本差异
    - replacement: 导入项和当前安装项不是同一 WID，但对应了已安装模组的替代版本
    - other_version: 包名一致，但导入项与当前安装项是不同版本/不同工坊条目
    - missing: 当前环境没有这个包名，但可以定位到目标 WID，可执行订阅/下载
    - unknown: 当前环境没有这个包名，同时也无法补出可操作的 WID
    """

    row_key: str
    origin_kind: str
    package_id: str
    name: str
    status: str
    import_workshop_id: str = ""
    import_workshop_id_valid: bool = False
    resolved_workshop_id: str = ""
    resolved_from: str = "none"
    target_workshop_id: str = ""
    target_workshop_url: str = ""
    warning: str = ""
    reason_text: str = ""
    installed_via_replacement: bool = False
    replacement: dict[str, Any] | None = None
    installed_candidates: list[ImportCheckInstalledCandidate] = field(default_factory=list)


@dataclass(slots=True)
class ImportCheckReport:
    summary: dict[str, int]
    items: list[ImportCheckItem] = field(default_factory=list)


def _build_workshop_url(workshop_id: str) -> str:
    if not workshop_id:
        return ""
    return f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"


def _fallback_package_label(package_id: str) -> str:
    normalized = normalize_package_id(package_id)
    return f"<{normalized}>" if normalized else "<未知包名>"


def _replacement_rule_matches(rule: dict[str, Any] | None, game_version: str) -> bool:
    if not rule:
        return False
    versions = rule.get("new_versions") or []
    return score_version_support(game_version, versions) > 0


def _build_installed_candidate(mod: dict[str, Any]) -> ImportCheckInstalledCandidate:
    return ImportCheckInstalledCandidate(
        package_id=normalize_package_id(mod.get("package_id")),
        workshop_id=normalize_workshop_id(mod.get("workshop_id")),
        name=str(
            mod.get("alias_name")
            or mod.get("display_name")
            or mod.get("name")
            or mod.get("package_id")
            or "未知模组"
        ).strip(),
        path=str(mod.get("path") or ""),
        store=str(mod.get("store") or "unknown"),
    )


def _build_summary(items: list[ImportCheckItem]) -> dict[str, int]:
    summary = {
        "exact_match": 0,
        "package_match": 0,
        "replacement": 0,
        "other_version": 0,
        "missing": 0,
        "unknown": 0,
    }
    for item in items:
        if item.status in summary:
            summary[item.status] += 1
    return summary


def _build_reason_text(
    status: str,
    import_workshop_id: str,
    resolved_workshop_id: str,
    resolved_from: str,
    warning: str,
    installed_via_replacement: bool = False,
) -> str:
    lines: list[str] = []
    if status == "exact_match":
        lines.append("已和当前环境中的安装项精确匹配。")
    elif status == "package_match":
        lines.append("当前环境存在同包名模组，但导入项没有有效 Workshop ID，无法继续区分具体版本。")
    elif status == "replacement":
        lines.append("该导入项对应了已安装模组的替代版本。")
        if installed_via_replacement:
            lines.append("当前环境已经安装了替代版本。")
    elif status == "other_version":
        lines.append("当前环境存在同包名模组，但对应的是另一个 Workshop 版本。")
    elif status == "missing":
        lines.append("当前环境未发现该导入项对应的可用安装项。")
    elif status == "unknown":
        lines.append("无法从导入项、本地缓存或外置数据库补全有效的 Workshop 信息。")

    if import_workshop_id:
        lines.append(f"导入项 Workshop ID：{import_workshop_id}")
    if resolved_workshop_id and resolved_workshop_id != import_workshop_id:
        lines.append(f"补全/替代后的目标 Workshop ID：{resolved_workshop_id}")
    if resolved_from and resolved_from != "none":
        lines.append(f"信息来源：{resolved_from}")
    if warning:
        lines.append(f"备注：{warning}")
    return "\n".join(lines)


def build_import_check_report(
    parsed: ParsedLoadOrderData,
    installed_mods: list[dict[str, Any]],
    details_by_package_id: dict[str, dict[str, Any]] | None = None,
    details_by_workshop_id: dict[str, dict[str, Any]] | None = None,
    replacements_by_old_workshop_id: dict[str, dict[str, Any]] | None = None,
    game_version: str = "",
) -> dict[str, Any]:
    """
    生成导入检查报告。

    这一步是“导入文件解析”与“当前环境真实安装情况”之间的桥梁：
    - 解析器负责告诉我们文件里写了什么
    - 这里负责判断这些内容在当前环境里意味着什么
    """

    details_by_package_id = details_by_package_id or {}
    details_by_workshop_id = details_by_workshop_id or {}
    replacements_by_old_workshop_id = replacements_by_old_workshop_id or {}

    installed_by_package_id: dict[str, list[dict[str, Any]]] = {}
    installed_by_workshop_id: dict[str, list[dict[str, Any]]] = {}
    for mod in installed_mods or []:
        package_id = normalize_package_id(mod.get("package_id"))
        if package_id:
            installed_by_package_id.setdefault(package_id, []).append(mod)
        workshop_id = normalize_workshop_id(mod.get("workshop_id"))
        if workshop_id:
            installed_by_workshop_id.setdefault(workshop_id, []).append(mod)

    items: list[ImportCheckItem] = []

    # 1. 先处理带 package_id 的导入项。这类条目能参与“缺失 / 替代 / 其它版本”判定。
    for index, package_id in enumerate(parsed.package_ids):
        normalized_package_id = normalize_package_id(package_id)
        if not normalized_package_id:
            continue

        import_name = str(parsed.mod_names[index]).strip() if index < len(parsed.mod_names) else ""
        raw_import_workshop_id = str(parsed.workshop_ids[index]).strip() if index < len(parsed.workshop_ids) else ""
        import_workshop_id = normalize_workshop_id(raw_import_workshop_id)
        import_workshop_id_valid = bool(import_workshop_id)

        package_matched_candidates_raw = installed_by_package_id.get(normalized_package_id, [])
        installed_candidates_raw = list(package_matched_candidates_raw)
        if not installed_candidates_raw and import_workshop_id_valid:
            # 有些导入文件的 package_id 可能不稳定，但 workshop id 是准的。
            # 只要当前环境存在同 wid 的安装项，就不应该继续当成“缺失”。
            installed_candidates_raw = list(installed_by_workshop_id.get(import_workshop_id, []))
        installed_candidates = [_build_installed_candidate(mod) for mod in installed_candidates_raw]
        installed_workshop_ids = {candidate.workshop_id for candidate in installed_candidates if candidate.workshop_id}

        detail = details_by_package_id.get(normalized_package_id) or {}
        replacement_rule = replacements_by_old_workshop_id.get(import_workshop_id) if import_workshop_id else None

        resolved_workshop_id = ""
        resolved_from = "none"
        replacement_info = None
        installed_via_replacement = False

        if import_workshop_id_valid:
            resolved_workshop_id = import_workshop_id
            resolved_from = "import"
        else:
            detail_workshop_id = normalize_workshop_id(detail.get("workshop_id"))
            if detail_workshop_id:
                resolved_workshop_id = detail_workshop_id
                if detail.get("is_replacement_derived"):
                    resolved_from = "replacement"
                    replacement_info = {
                        "new_workshop_id": detail_workshop_id,
                        "new_name": detail.get("name") or import_name or normalized_package_id,
                    }
                else:
                    resolved_from = "external_db"
            elif installed_candidates:
                installed_workshop_id = normalize_workshop_id(installed_candidates[0].workshop_id)
                if installed_workshop_id:
                    resolved_workshop_id = installed_workshop_id
                    resolved_from = "installed"

        if not installed_candidates_raw and resolved_workshop_id:
            # 核心补强：只要我们后续补全出了有效 workshop id，
            # 就应该再反查一次当前环境里是否已经装有这个具体工坊项目。
            installed_candidates_raw = list(installed_by_workshop_id.get(resolved_workshop_id, []))
            installed_candidates = [_build_installed_candidate(mod) for mod in installed_candidates_raw]
            installed_workshop_ids = {candidate.workshop_id for candidate in installed_candidates if candidate.workshop_id}

        status = "unknown"
        warning = ""

        if installed_candidates:
            # 已安装包名存在时，优先按你要求的规则判断是否缺失。
            if import_workshop_id_valid:
                if import_workshop_id in installed_workshop_ids:
                    status = "exact_match"
                    if normalized_package_id not in {candidate.package_id for candidate in installed_candidates if candidate.package_id}:
                        warning = "已通过 Workshop ID 对应了已安装项，但包名与导入记录不一致"
                elif not installed_workshop_ids:
                    # 当前环境的这个包没有可用 workshop_id，无法证明是“其它版本”。
                    status = "package_match"
                else:
                    replacement_match = False
                    if replacement_rule and _replacement_rule_matches(replacement_rule, game_version):
                        replacement_info = {
                        "new_workshop_id": normalize_workshop_id(replacement_rule.get("new_workshop_id")),
                            "new_name": replacement_rule.get("new_name"),
                        }
                        if replacement_info["new_workshop_id"] in installed_workshop_ids:
                            replacement_match = True
                            resolved_workshop_id = replacement_info["new_workshop_id"]
                            resolved_from = "replacement"
                    elif detail.get("is_replacement_derived") and resolved_workshop_id in installed_workshop_ids:
                        replacement_match = True
                        replacement_info = {
                            "new_workshop_id": resolved_workshop_id,
                            "new_name": detail.get("name") or import_name or normalized_package_id,
                        }

                    if replacement_match:
                        status = "replacement"
                        installed_via_replacement = True
                        warning = "当前环境安装的是替代版本"
                    else:
                        status = "other_version"
                        warning = "当前环境存在同包名但不同工坊版本"
            else:
                if resolved_from == "replacement" and resolved_workshop_id and resolved_workshop_id in installed_workshop_ids:
                    status = "replacement"
                    installed_via_replacement = True
                    warning = "当前环境安装的是替代版本"
                else:
                    status = "package_match"
        else:
            # 当前环境里完全没有这个包名时，才进入 missing / unknown 分支。
            if resolved_workshop_id and resolved_workshop_id in installed_by_workshop_id:
                installed_candidates = [_build_installed_candidate(mod) for mod in installed_by_workshop_id[resolved_workshop_id]]
                if resolved_from == "replacement":
                    status = "replacement"
                    installed_via_replacement = True
                    warning = "当前环境安装的是替代版本"
                else:
                    status = "exact_match"
                    warning = "已通过补全后的 Workshop ID 对应到了安装项"
            elif resolved_workshop_id:
                status = "missing"
            else:
                status = "unknown"
                warning = "无法查找到对应 Workshop ID，无法进行订阅或下载"

        # 对“纯包名导入”优先保留技术标识的可读性，用尖括号提示这是包名而不是展示名。
        display_name = (
            import_name
            or _fallback_package_label(normalized_package_id)
            or str(detail.get("name") or "").strip()
            or (installed_candidates[0].name if installed_candidates else "")
            or (resolved_workshop_id and f"Workshop {resolved_workshop_id}")
            or "未知导入项"
        )

        target_workshop_id = resolved_workshop_id
        items.append(
            ImportCheckItem(
                row_key=normalized_package_id,
                origin_kind="package",
                package_id=normalized_package_id,
                name=display_name,
                status=status,
                import_workshop_id=import_workshop_id,
                import_workshop_id_valid=import_workshop_id_valid,
                resolved_workshop_id=resolved_workshop_id,
                resolved_from=resolved_from,
                target_workshop_id=target_workshop_id,
                target_workshop_url=_build_workshop_url(target_workshop_id),
                warning=warning,
                reason_text=_build_reason_text(
                    status,
                    import_workshop_id,
                    resolved_workshop_id,
                    resolved_from,
                    warning,
                    installed_via_replacement,
                ),
                installed_via_replacement=installed_via_replacement,
                replacement=replacement_info,
                installed_candidates=installed_candidates,
            )
        )

    # 2. 再处理“只有 workshop_id、没有 package_id”的导入项。
    loose_workshop_ids = parsed.workshop_ids[len(parsed.package_ids):]
    for workshop_id in loose_workshop_ids:
        normalized_workshop_id = normalize_workshop_id(workshop_id)
        if not normalized_workshop_id:
            continue

        installed_candidates_raw = installed_by_workshop_id.get(normalized_workshop_id, [])
        installed_candidates = [_build_installed_candidate(mod) for mod in installed_candidates_raw]
        detail = details_by_workshop_id.get(normalized_workshop_id) or {}
        replacement_rule = replacements_by_old_workshop_id.get(normalized_workshop_id)
        resolved_workshop_id = normalized_workshop_id
        resolved_from = "import"
        replacement_info = None

        installed_via_replacement = False
        if installed_candidates:
            status = "exact_match"
            warning = ""
        else:
            status = "missing"
            warning = "仅提供了 Workshop ID，当前环境未发现对应安装项"
            if replacement_rule and _replacement_rule_matches(replacement_rule, game_version):
                new_workshop_id = normalize_workshop_id(replacement_rule.get("new_workshop_id"))
                if new_workshop_id and new_workshop_id in installed_by_workshop_id:
                    replacement_candidates = [_build_installed_candidate(mod) for mod in installed_by_workshop_id[new_workshop_id]]
                    installed_candidates = replacement_candidates
                    status = "replacement"
                    installed_via_replacement = True
                    resolved_workshop_id = new_workshop_id
                    resolved_from = "replacement"
                    replacement_info = {
                        "new_workshop_id": new_workshop_id,
                        "new_name": replacement_rule.get("new_name"),
                    }
                    warning = "当前环境安装的是替代版本"
                elif new_workshop_id:
                    resolved_workshop_id = new_workshop_id
                    resolved_from = "replacement"
                    replacement_info = {
                        "new_workshop_id": new_workshop_id,
                        "new_name": replacement_rule.get("new_name"),
                    }
                    status = "replacement"
                    warning = "该工坊项目已有替代版本"

        package_id = normalize_package_id(detail.get("package_id"))
        display_name = (
            (_fallback_package_label(package_id) if package_id else "")
            or str(detail.get("name") or "").strip()
            or (installed_candidates[0].name if installed_candidates else "")
            or f"<未知包名>({normalized_workshop_id})"
        )

        items.append(
            ImportCheckItem(
                row_key=f"wid:{normalized_workshop_id}",
                origin_kind="workshop_only",
                package_id=package_id,
                name=display_name,
                status=status,
                import_workshop_id=normalized_workshop_id,
                import_workshop_id_valid=True,
                resolved_workshop_id=resolved_workshop_id,
                resolved_from=resolved_from,
                target_workshop_id=resolved_workshop_id,
                target_workshop_url=_build_workshop_url(resolved_workshop_id),
                warning=warning,
                reason_text=_build_reason_text(
                    status,
                    normalized_workshop_id,
                    resolved_workshop_id,
                    resolved_from,
                    warning,
                    installed_via_replacement,
                ),
                installed_via_replacement=installed_via_replacement,
                replacement=replacement_info,
                installed_candidates=installed_candidates,
            )
        )

    report = ImportCheckReport(summary=_build_summary(items), items=items)
    return asdict(report)
