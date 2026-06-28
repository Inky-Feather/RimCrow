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


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


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


def detect_load_order_format(file_path: str | Path) -> str:
    """
    根据文件名、扩展名和内容探测导入格式。

    这里故意把“识别格式”独立出来，是为了避免 manager 里出现一长串
    `if suffix == ... elif root.tag == ...` 的条件分支。
    """

    path = Path(file_path)
    suffix = path.suffix.lower()
    file_name = path.name.lower()

    if file_name == "modsconfig.xml":
        return FORMAT_MODSCONFIG
    if suffix == ".rws":
        return FORMAT_SAVEGAME

    if suffix == ".json":
        data = json.loads(_read_text(path) or "null")
        if isinstance(data, dict):
            if any(key in data for key in ("mods", "active_mods", "activeMods", "mod_list", "modList")):
                return FORMAT_RIMSORT_JSON
            if any(key in data for key in ("package_ids", "modlist", "workshop_ids", "mod_names")):
                return FORMAT_RMM_JSON
        return FORMAT_RMM_JSON

    if suffix == ".xml":
        root = ET.fromstring(_read_text(path))
        tag_name = root.tag.lower()

        if tag_name == "savegame" or root.find(".//meta/modIds") is not None:
            return FORMAT_SAVEGAME
        if tag_name == "modlist" or root.find(".//modSteamWorkshopIds") is not None:
            return FORMAT_MODLIST
        if tag_name == "modsconfigdata" or root.find(".//activeMods") is not None:
            # 有些 RimPy 导出的 XML 也可能带 activeMods。
            # 这里仍然优先认成 ModsConfig，因为它更接近游戏原生格式。
            return FORMAT_MODSCONFIG
        return FORMAT_RIMPY_XML

    if suffix == ".rml":
        text = _read_text(path)
        try:
            root = ET.fromstring(text)
            tag_name = root.tag.lower()
            if tag_name == "savedmodlist" or root.find(".//meta/modIds") is not None:
                return FORMAT_RML
        except ET.ParseError:
            pass

        # 极端情况下，如果 .rml 并不是 XML，而只是一个文本列表，就回退到纯文本判断。
        lines = _non_comment_lines(text)
        if lines and all(_looks_like_workshop_value(line) for line in lines[:10]):
            return FORMAT_WORKSHOP_IDS
        return FORMAT_PLAIN_TEXT

    if suffix in {".txt", ".list"}:
        lines = _non_comment_lines(_read_text(path))
        if lines and all(_looks_like_workshop_value(line) for line in lines[:10]):
            return FORMAT_WORKSHOP_IDS
        return FORMAT_PLAIN_TEXT

    # 未知扩展名时，退化成纯文本解析。这样即使用户随手拖了一个无扩展名文件，
    # 也仍有机会从内容里提取 package id / workshop id。
    return FORMAT_PLAIN_TEXT
