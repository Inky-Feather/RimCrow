import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from backend.utils.tools import normalize_package_id, normalize_workshop_id
from .package_tokens import parse_package_token
from .detector import detect_load_order_format
from .models import (
    FORMAT_MODLIST,
    FORMAT_MODSCONFIG,
    FORMAT_PLAIN_TEXT,
    FORMAT_RML,
    FORMAT_RIMPY_XML,
    FORMAT_RIMSORT_JSON,
    FORMAT_RIMCROW_JSON,
    FORMAT_SAVEGAME,
    FORMAT_WORKSHOP_IDS,
    ParsedLoadOrderData,
)


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _append_mod_entry(
    package_ids: list[str],
    package_tokens: list[str],
    mod_names: list[str],
    workshop_ids: list[str],
    source_urls: list[str],
    package_id: str,
    name: str = "",
    workshop_id: str = "",
    source_url: str = "",
) -> None:
    """
    维护三组并行数组。

    这里特意不用 dict/list of dict 作为输出主结构，是为了兼容当前 manager
    已经在使用的“package_ids + mod_names + workshop_ids”拼装逻辑。
    """

    token_info = parse_package_token(package_id)
    normalized_package_id = token_info.canonical_package_id
    if not normalized_package_id: return
    if normalized_package_id in package_ids: return

    package_ids.append(normalized_package_id)
    package_tokens.append(token_info.normalized_token or normalized_package_id)
    mod_names.append(str(name or "").strip())
    workshop_ids.append(normalize_workshop_id(workshop_id, zero_is_empty=False))
    source_urls.append(str(source_url or "").strip())


def _align_parallel_entry_lists(
    package_ids: list[str],
    package_tokens: list[str] | None = None,
    mod_names: list[str] | None = None,
    workshop_ids: list[str] | None = None,
    source_urls: list[str] | None = None,
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """
    过滤非法 package_id 时，同时把并行数组按同一索引收敛。

    旧实现只过滤了 package_ids，导致后续名称 / workshop id 仍停留在原始索引上，
    一旦源文件里夹杂空行或非法包名，后续条目就会整体错位。
    """

    aligned_package_ids: list[str] = []
    aligned_package_tokens: list[str] = []
    aligned_mod_names: list[str] = []
    aligned_workshop_ids: list[str] = []
    aligned_source_urls: list[str] = []

    for index, raw_package_id in enumerate(package_ids or []):
        token_info = parse_package_token((package_tokens or [])[index] if package_tokens and index < len(package_tokens) else raw_package_id)
        normalized_package_id = token_info.canonical_package_id
        if not normalized_package_id:
            continue
        aligned_package_ids.append(normalized_package_id)
        aligned_package_tokens.append(token_info.normalized_token or normalized_package_id)
        aligned_mod_names.append(str((mod_names or [])[index]).strip() if mod_names and index < len(mod_names) else "")
        aligned_workshop_ids.append(
            normalize_workshop_id((workshop_ids or [])[index], zero_is_empty=False)
            if workshop_ids and index < len(workshop_ids) else ""
        )
        aligned_source_urls.append(str((source_urls or [])[index]).strip() if source_urls and index < len(source_urls) else "")

    return aligned_package_ids, aligned_package_tokens, aligned_mod_names, aligned_workshop_ids, aligned_source_urls


def _extract_workshop_id(value: str) -> str:
    line = str(value or "").strip()
    if line.isdigit() and len(line) >= 7: return line
    match = re.search(r"id=(\d+)", line)
    return match.group(1) if match else ""


def _parse_rimsort_clipboard_line(value: str):
    line = str(value or "").strip()
    match = re.match(r"^(?P<name>.+?)\s+\[(?P<package_id>[\w.\-]+)\]\[(?P<url>.+)\]\s*$", line)
    if not match: return None
    package_id = normalize_package_id(match.group("package_id"))
    if not package_id: return None
    name = match.group("name").strip()
    url = match.group("url").strip()
    workshop_id = "" if url.lower() == "no url specified" else _extract_workshop_id(url)
    source_url = ""
    if url.lower() != "no url specified" and not workshop_id:
        source_url = url
    return package_id, name, workshop_id, source_url


def _parse_list_node(root: ET.Element, *xpaths: str) -> list[str]:
    for xpath in xpaths:
        node = root.find(xpath)
        if node is None:
            continue
        return [str(child.text or "").strip() for child in node.findall("li")]
    return []


def _parse_text_node(root: ET.Element, *xpaths: str) -> str:
    for xpath in xpaths:
        node = root.find(xpath)
        if node is None:
            continue
        return str(node.text or "").strip()
    return ""


def _dedupe_parsed_data(parsed: ParsedLoadOrderData) -> ParsedLoadOrderData:
    """
    统一去重入口。

    规则：
    - package_id 以第一次出现为准
    - package 行对应的名称 / workshop_id 也跟随第一次出现
    - “纯 workshop id”条目单独去重，不混入 package 行
    """

    dedup_package_ids: list[str] = []
    dedup_package_tokens: list[str] = []
    dedup_mod_names: list[str] = []
    dedup_workshop_ids: list[str] = []
    dedup_source_urls: list[str] = []
    seen_package_ids: set[str] = set()

    for index, package_id in enumerate(parsed.package_ids):
        normalized_package_id = normalize_package_id(package_id)
        if not normalized_package_id or normalized_package_id in seen_package_ids:
            continue
        seen_package_ids.add(normalized_package_id)
        dedup_package_ids.append(normalized_package_id)
        dedup_package_tokens.append(
            str(parsed.package_tokens[index]).strip().lower()
            if index < len(parsed.package_tokens) and str(parsed.package_tokens[index]).strip()
            else normalized_package_id
        )
        dedup_mod_names.append(str(parsed.mod_names[index]).strip() if index < len(parsed.mod_names) else "")
        dedup_workshop_ids.append(str(parsed.workshop_ids[index]).strip() if index < len(parsed.workshop_ids) else "")
        dedup_source_urls.append(str(parsed.source_urls[index]).strip() if index < len(parsed.source_urls) else "")

    dedup_loose_workshop_ids: list[str] = []
    seen_workshop_ids: set[str] = set()
    for workshop_id in parsed.workshop_ids[len(parsed.package_ids):]:
        normalized_workshop_id = normalize_workshop_id(workshop_id, zero_is_empty=False)
        if not normalized_workshop_id or normalized_workshop_id in seen_workshop_ids:
            continue
        seen_workshop_ids.add(normalized_workshop_id)
        dedup_loose_workshop_ids.append(normalized_workshop_id)

    parsed.package_ids = dedup_package_ids
    parsed.package_tokens = dedup_package_tokens
    parsed.mod_names = dedup_mod_names
    parsed.workshop_ids = dedup_workshop_ids + dedup_loose_workshop_ids
    parsed.source_urls = dedup_source_urls
    return parsed


def _parse_modsconfig_xml(path: Path) -> ParsedLoadOrderData:
    root = ET.fromstring(_read_text(path))
    package_tokens = [str(item or "").strip() for item in _parse_list_node(root, "./activeMods", ".//activeMods")]
    package_ids = [parse_package_token(item).canonical_package_id for item in package_tokens if parse_package_token(item).canonical_package_id]
    package_tokens = [parse_package_token(item).normalized_token for item in package_tokens if parse_package_token(item).canonical_package_id]
    return ParsedLoadOrderData(
        format=FORMAT_MODSCONFIG,
        list_name=path.stem,
        package_ids=package_ids,
        package_tokens=package_tokens,
    )


def _parse_modlist_xml(path: Path) -> ParsedLoadOrderData:
    root = ET.fromstring(_read_text(path))
    raw_package_ids = _parse_list_node(root, "./modIds", ".//modIds")
    raw_mod_names = _parse_list_node(root, "./modNames", ".//modNames")
    raw_workshop_ids = _parse_list_node(root, "./modSteamWorkshopIds", ".//modSteamWorkshopIds")
    package_ids, package_tokens, mod_names, workshop_ids, source_urls = _align_parallel_entry_lists(
        raw_package_ids,
        raw_package_ids,
        raw_mod_names,
        raw_workshop_ids,
        [""] * len(raw_package_ids),
    )
    return ParsedLoadOrderData(
        format=FORMAT_MODLIST,
        list_name=_parse_text_node(root, "./Name", ".//Name") or path.stem,
        package_ids=package_ids,
        package_tokens=package_tokens,
        mod_names=mod_names,
        workshop_ids=workshop_ids,
        source_urls=source_urls,
    )


def _parse_rml_file(path: Path) -> ParsedLoadOrderData:
    """
    解析 RimWorld 原生导出的 `.rml` 列表。

    从示例文件可以看出，它至少包含：
    - meta/modIds
    - meta/modSteamIds
    - meta/modNames
    - modList/ids
    - modList/names

    这里优先把它视为“结构化 XML 列表”，而不是普通文本文件。
    """

    root = ET.fromstring(_read_text(path))

    meta_package_ids = _parse_list_node(root, "./meta/modIds", ".//meta/modIds")
    meta_workshop_ids = _parse_list_node(root, "./meta/modSteamIds", ".//meta/modSteamIds")
    meta_names = _parse_list_node(root, "./meta/modNames", ".//meta/modNames")
    display_package_ids = _parse_list_node(root, "./modList/ids", ".//modList/ids")
    display_names = _parse_list_node(root, "./modList/names", ".//modList/names")

    # `.rml` 同时给了 meta names 和 modList names。
    # 前者更像原始名称，后者更像最终展示名称（可能本地化）。
    # 这里优先使用 modList/names，缺失时再回退到 meta/modNames。
    package_ids_source = display_package_ids or meta_package_ids
    package_ids: list[str] = []
    package_tokens: list[str] = []
    merged_names: list[str] = []
    workshop_ids: list[str] = []
    source_urls: list[str] = []

    for index, raw_package_id in enumerate(package_ids_source):
        token_info = parse_package_token(raw_package_id)
        normalized_package_id = token_info.canonical_package_id
        if not normalized_package_id:
            continue
        display_name = display_names[index] if index < len(display_names) else ""
        meta_name = meta_names[index] if index < len(meta_names) else ""
        package_ids.append(normalized_package_id)
        package_tokens.append(token_info.normalized_token or normalized_package_id)
        merged_names.append(str(display_name or meta_name).strip())
        workshop_ids.append(
            normalize_workshop_id(meta_workshop_ids[index], zero_is_empty=False)
            if index < len(meta_workshop_ids) else ""
        )
        source_urls.append("")

    return ParsedLoadOrderData(
        format=FORMAT_RML,
        list_name=path.stem,
        package_ids=package_ids,
        package_tokens=package_tokens,
        mod_names=merged_names,
        workshop_ids=workshop_ids,
        source_urls=source_urls,
    )


def _parse_savegame_xml(path: Path) -> ParsedLoadOrderData:
    root = ET.fromstring(_read_text(path))
    raw_package_ids = _parse_list_node(root, "./meta/modIds", ".//meta/modIds")
    raw_mod_names = _parse_list_node(root, "./meta/modNames", ".//meta/modNames")
    raw_workshop_ids = _parse_list_node(root, "./meta/modSteamIds", ".//meta/modSteamIds")
    package_ids, package_tokens, mod_names, workshop_ids, source_urls = _align_parallel_entry_lists(
        raw_package_ids,
        raw_package_ids,
        raw_mod_names,
        raw_workshop_ids,
        [""] * len(raw_package_ids),
    )
    return ParsedLoadOrderData(
        format=FORMAT_SAVEGAME,
        list_name=path.stem,
        package_ids=package_ids,
        package_tokens=package_tokens,
        mod_names=mod_names,
        workshop_ids=workshop_ids,
        source_urls=source_urls,
    )


def _parse_rimpy_xml(path: Path) -> ParsedLoadOrderData:
    root = ET.fromstring(_read_text(path))
    package_ids: list[str] = []
    package_tokens: list[str] = []
    mod_names: list[str] = []
    workshop_ids: list[str] = []
    source_urls: list[str] = []
    loose_workshop_ids: list[str] = []

    for mod_elem in root.iter():
        tag_name = mod_elem.tag.lower()
        if tag_name not in {"mod", "li", "item", "entry"}:
            continue

        package_id = ""
        name = ""
        workshop_id = ""

        if mod_elem.text and mod_elem.text.strip():
            text = mod_elem.text.strip()
            if "." in text:
                package_id = text
            elif text.isdigit():
                workshop_id = text

        for child in mod_elem:
            child_tag = child.tag.lower()
            child_text = str(child.text or "").strip()
            if child_tag in {"packageid", "package_id", "id"}:
                package_id = child_text
            elif child_tag in {"name", "displayname", "title"}:
                name = child_text
            elif child_tag in {"workshopid", "workshop_id", "steamid", "publishedfileid"}:
                workshop_id = child_text

        package_id = package_id or str(mod_elem.get("packageId") or mod_elem.get("id") or "").strip()
        name = name or str(mod_elem.get("name") or "").strip()
        workshop_id = workshop_id or str(mod_elem.get("workshopId") or mod_elem.get("steamId") or "").strip()

        if package_id:
            _append_mod_entry(package_ids, package_tokens, mod_names, workshop_ids, source_urls, package_id, name, workshop_id)
        elif workshop_id.isdigit() and workshop_id not in loose_workshop_ids:
            loose_workshop_ids.append(workshop_id)

    active_mods = root.find(".//activeMods")
    if active_mods is not None:
        for li in active_mods.findall("li"):
            token_info = parse_package_token(str(li.text or ""))
            package_id = token_info.canonical_package_id
            if package_id and package_id not in package_ids:
                package_ids.append(package_id)
                package_tokens.append(token_info.normalized_token or package_id)
                mod_names.append("")
                workshop_ids.append("")
                source_urls.append("")

    return ParsedLoadOrderData(
        format=FORMAT_RIMPY_XML,
        list_name=path.stem,
        package_ids=package_ids,
        package_tokens=package_tokens,
        mod_names=mod_names,
        # 前半段是与 package_ids 对齐的工坊 ID，后半段是“只有工坊 ID、没有 package_id”的条目。
        # manager 在构建 mod 条目时只会消费前半段，但 API 仍可以保留完整的工坊 ID 列表。
        workshop_ids=workshop_ids + loose_workshop_ids,
        source_urls=source_urls,
    )


def _parse_rimsort_json(path: Path) -> ParsedLoadOrderData:
    data = json.loads(_read_text(path) or "null")
    mods_data = None
    package_ids: list[str] = []
    package_tokens: list[str] = []
    mod_names: list[str] = []
    workshop_ids: list[str] = []
    source_urls: list[str] = []
    loose_workshop_ids: list[str] = []

    if isinstance(data, dict):
        for key in ("mods", "active_mods", "activeMods", "mod_list", "modList"):
            if key in data:
                mods_data = data[key]
                break
    elif isinstance(data, list):
        mods_data = data

    if not mods_data:
        return ParsedLoadOrderData(
            format=FORMAT_RIMSORT_JSON,
            list_name=path.stem,
            errors=["No mod list found in JSON file"],
        )

    for item in mods_data:
        if isinstance(item, str):
            if item.isdigit() and len(item) >= 7:
                if item not in loose_workshop_ids:
                    loose_workshop_ids.append(item)
            else:
                _append_mod_entry(package_ids, package_tokens, mod_names, workshop_ids, source_urls, item)
            continue

        if not isinstance(item, dict):
            continue

        package_id = str(item.get("packageId") or item.get("package_id") or item.get("id") or "").strip()
        name = str(item.get("name") or item.get("displayName") or "").strip()
        workshop_id = str(item.get("workshopId") or item.get("workshop_id") or item.get("steamId") or "").strip()
        source_url = str(item.get("source_url") or item.get("sourceUrl") or item.get("url") or "").strip()
        if source_url and not workshop_id:
            workshop_id = _extract_workshop_id(source_url)
        if workshop_id:
            source_url = ""

        if package_id:
            _append_mod_entry(package_ids, package_tokens, mod_names, workshop_ids, source_urls, package_id, name, workshop_id, source_url)
        elif workshop_id.isdigit() and workshop_id not in loose_workshop_ids:
            loose_workshop_ids.append(workshop_id)

    return ParsedLoadOrderData(
        format=FORMAT_RIMSORT_JSON,
        list_name=str(data.get("name") or path.stem) if isinstance(data, dict) else path.stem,
        package_ids=package_ids,
        package_tokens=package_tokens,
        mod_names=mod_names,
        workshop_ids=workshop_ids + loose_workshop_ids,
        source_urls=source_urls,
    )


def _parse_rimcrow_json(path: Path) -> ParsedLoadOrderData:
    data = json.loads(_read_text(path) or "null")
    package_ids: list[str] = []
    package_tokens: list[str] = []
    mod_names: list[str] = []
    workshop_ids: list[str] = []
    source_urls: list[str] = []
    loose_workshop_ids: list[str] = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                _append_mod_entry(package_ids, package_tokens, mod_names, workshop_ids, source_urls, item)
            elif isinstance(item, dict):
                workshop_id = str(item.get("workshop_id") or item.get("workshopId") or "").strip()
                source_url = str(item.get("source_url") or item.get("sourceUrl") or item.get("url") or "").strip()
                if source_url and not workshop_id:
                    workshop_id = _extract_workshop_id(source_url)
                if workshop_id:
                    source_url = ""
                _append_mod_entry(
                    package_ids,
                    package_tokens,
                    mod_names,
                    workshop_ids,
                    source_urls,
                    str(item.get("package_id") or ""),
                    str(item.get("name") or ""),
                    workshop_id,
                    source_url,
                )
    elif isinstance(data, dict):
        if "package_ids" in data:
            for package_id in data["package_ids"]:
                _append_mod_entry(package_ids, package_tokens, mod_names, workshop_ids, source_urls, str(package_id))

        if "modlist" in data:
            for item in data["modlist"]:
                if isinstance(item, str):
                    _append_mod_entry(package_ids, package_tokens, mod_names, workshop_ids, source_urls, item)
                elif isinstance(item, dict):
                    workshop_id = str(item.get("workshop_id") or item.get("workshopId") or "").strip()
                    source_url = str(item.get("source_url") or item.get("sourceUrl") or item.get("url") or "").strip()
                    if source_url and not workshop_id:
                        workshop_id = _extract_workshop_id(source_url)
                    if workshop_id:
                        source_url = ""
                    _append_mod_entry(
                        package_ids,
                        package_tokens,
                        mod_names,
                        workshop_ids,
                        source_urls,
                        str(item.get("package_id") or ""),
                        str(item.get("name") or ""),
                        workshop_id,
                        source_url,
                    )

        if "mod_names" in data and isinstance(data["mod_names"], dict):
            for index, package_id in enumerate(package_ids):
                if index >= len(mod_names):
                    mod_names.append("")
                if not mod_names[index]:
                    mod_names[index] = str(data["mod_names"].get(package_id) or "").strip()

        if "workshop_ids" in data:
            for workshop_id in data["workshop_ids"]:
                workshop_id_value = normalize_workshop_id(str(workshop_id), zero_is_empty=False)
                if workshop_id_value and workshop_id_value not in loose_workshop_ids and workshop_id_value not in workshop_ids:
                    loose_workshop_ids.append(workshop_id_value)

    errors: list[str] = []
    if not package_ids and not workshop_ids and not loose_workshop_ids:
        errors.append("No valid mods found in JSON")

    return ParsedLoadOrderData(
        format=FORMAT_RIMCROW_JSON,
        list_name=path.stem,
        package_ids=package_ids,
        package_tokens=package_tokens,
        mod_names=mod_names,
        workshop_ids=workshop_ids + loose_workshop_ids,
        source_urls=source_urls,
        errors=errors,
    )


def _parse_plain_text(path: Path) -> ParsedLoadOrderData:
    text = _read_text(path)
    package_ids: list[str] = []
    package_tokens: list[str] = []
    mod_names: list[str] = []
    workshop_ids: list[str] = []
    source_urls: list[str] = []
    loose_workshop_ids: list[str] = []
    warnings: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        # RimSort 剪贴板导出头部说明；属于格式噪音，不应进入警告。
        if line.startswith("Created with RimSort "):
            continue
        if line.startswith("RimWorld game version this list was created for:"):
            continue
        if line.startswith("Total # of mods:"):
            continue

        rimsort_entry = _parse_rimsort_clipboard_line(line)
        if rimsort_entry is not None:
            package_id, name, workshop_id, source_url = rimsort_entry
            _append_mod_entry(package_ids, package_tokens, mod_names, workshop_ids, source_urls, package_id, name, workshop_id, source_url)
            continue

        if "#" in line:
            line = line.split("#", 1)[0].strip()

        workshop_id = _extract_workshop_id(line)
        if workshop_id:
            if workshop_id not in loose_workshop_ids and workshop_id not in workshop_ids:
                loose_workshop_ids.append(workshop_id)
            continue

        if "." in line or line.startswith("ludeon."):
            _append_mod_entry(package_ids, package_tokens, mod_names, workshop_ids, source_urls, line)
            continue

        warnings.append(f"Skipped unrecognized line: {line[:50]}")

    errors: list[str] = []
    if not package_ids and not loose_workshop_ids:
        errors.append("No valid package IDs or workshop IDs found")

    return ParsedLoadOrderData(
        format=FORMAT_PLAIN_TEXT,
        list_name=path.stem,
        package_ids=package_ids,
        package_tokens=package_tokens,
        mod_names=mod_names,
        workshop_ids=workshop_ids + loose_workshop_ids,
        source_urls=source_urls,
        warnings=warnings,
        errors=errors,
    )


def _parse_workshop_ids(path: Path) -> ParsedLoadOrderData:
    text = _read_text(path)
    workshop_ids: list[str] = []
    warnings: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        workshop_id = _extract_workshop_id(line)
        if workshop_id:
            if workshop_id not in workshop_ids:
                workshop_ids.append(workshop_id)
        else:
            warnings.append(f"Skipped invalid workshop ID: {line[:30]}")

    errors: list[str] = []
    if not workshop_ids:
        errors.append("No valid workshop IDs found")

    return ParsedLoadOrderData(
        format=FORMAT_WORKSHOP_IDS,
        list_name=path.stem,
        workshop_ids=workshop_ids,
        warnings=warnings,
        errors=errors,
    )


def parse_load_order_file(file_path: str | Path) -> ParsedLoadOrderData:
    """
    统一解析入口。

    manager 层只调用这一个函数，不关心底层到底进入了哪个格式分支。
    """

    path = Path(file_path)
    format_name = detect_load_order_format(path)

    if format_name == FORMAT_MODSCONFIG:
        parsed = _parse_modsconfig_xml(path)
    elif format_name == FORMAT_MODLIST:
        parsed = _parse_modlist_xml(path)
    elif format_name == FORMAT_RML:
        parsed = _parse_rml_file(path)
    elif format_name == FORMAT_SAVEGAME:
        parsed = _parse_savegame_xml(path)
    elif format_name == FORMAT_RIMPY_XML:
        parsed = _parse_rimpy_xml(path)
    elif format_name == FORMAT_RIMSORT_JSON:
        parsed = _parse_rimsort_json(path)
    elif format_name == FORMAT_RIMCROW_JSON:
        parsed = _parse_rimcrow_json(path)
    elif format_name == FORMAT_WORKSHOP_IDS:
        parsed = _parse_workshop_ids(path)
    else:
        parsed = _parse_plain_text(path)

    return _dedupe_parsed_data(parsed)
