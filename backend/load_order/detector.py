import json
from pathlib import Path
import xml.etree.ElementTree as ET

from .models import (
    FORMAT_MODLIST,
    FORMAT_MODSCONFIG,
    FORMAT_PLAIN_TEXT,
    FORMAT_RML,
    FORMAT_RIMPY_XML,
    FORMAT_RIMSORT_JSON,
    FORMAT_RMM_JSON,
    FORMAT_SAVEGAME,
    FORMAT_WORKSHOP_IDS,
)


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _read_text(path: Path) -> str:
    raw = _read_bytes(path)
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _parse_xml_root(path: Path):
    try:
        return ET.fromstring(_read_text(path))
    except ET.ParseError:
        return None


def _non_comment_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith("//"):
            continue
        lines.append(line)
    return lines


def _looks_like_workshop_value(value: str) -> bool:
    if value.isdigit() and len(value) >= 7:
        return True
    if "steamcommunity.com" in value and "id=" in value:
        return True
    return False


def _detect_json_export_format(text: str) -> str | None:
    stripped = str(text or "").lstrip()
    if not stripped.startswith(("{", "[")): return None

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        if any(key in data for key in ("mods", "active_mods", "activeMods", "mod_list", "modList")):
            return FORMAT_RIMSORT_JSON
        if any(key in data for key in ("package_ids", "modlist", "workshop_ids", "mod_names")):
            return FORMAT_RMM_JSON
    return FORMAT_RMM_JSON if isinstance(data, list) else None


def detect_load_order_format(file_path: str | Path) -> str:
    """
    根据文件名、扩展名和内容探测导入格式。

    这里故意把“识别格式”独立出来，是为了避免 manager 里出现一长串
    `if suffix == ... elif root.tag == ...` 的条件分支。
    """

    path = Path(file_path)
    suffix = path.suffix.lower()
    file_name = path.name.lower()
    text = _read_text(path)

    if suffix == ".json":
        json_format = _detect_json_export_format(text)
        if json_format: return json_format
        return FORMAT_RMM_JSON

    # RimSort 某些导出会把 JSON 内容写进带 .xml 的路径里，不能只靠后缀判断。
    json_format = _detect_json_export_format(text)
    if json_format: return json_format

    root = _parse_xml_root(path)
    if root is not None:
        tag_name = root.tag.lower()

        if tag_name == "modlist" or root.find(".//modSteamWorkshopIds") is not None:
            return FORMAT_MODLIST
        if tag_name == "modsconfigdata" or root.find("./activeMods") is not None or (
            file_name == "modsconfig.xml" and root.find(".//activeMods") is not None
        ):
            return FORMAT_MODSCONFIG
        if tag_name == "savegame" or suffix == ".rws":
            return FORMAT_SAVEGAME
        if tag_name == "savedmodlist" or root.find("./meta/gameVersion") is not None or suffix == ".rml":
            return FORMAT_RML
        if root.find(".//meta/modIds") is not None:
            return FORMAT_SAVEGAME
        return FORMAT_RIMPY_XML

    if suffix in {".txt", ".list", ".xml", ".rws", ".rml"}:
        lines = _non_comment_lines(text)
        if lines and all(_looks_like_workshop_value(line) for line in lines[:10]):
            return FORMAT_WORKSHOP_IDS
        return FORMAT_PLAIN_TEXT

    # 未知扩展名时，退化成纯文本解析。这样即使用户随手拖了一个无扩展名文件，
    # 也仍有机会从内容里提取 package id / workshop id。
    return FORMAT_PLAIN_TEXT
