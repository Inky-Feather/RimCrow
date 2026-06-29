from __future__ import annotations

import hashlib
import io
import json
import re
import time
import zipfile
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.settings import settings
from backend.managers.mgr_network import build_retry_session, merge_headers
from backend.utils.logger import logger


MULTIPLAYER_PACKAGE_ID = "rwmt.multiplayer"
MP_COMPAT_PACKAGE_ID = "rwmt.multiplayercompatibility"
MP_COMPAT_DEFAULT_SOURCE_URL = "https://github.com/rwmt/Multiplayer-Compatibility/archive/refs/heads/master.zip"
MP_COMPAT_FOR_RE = re.compile(r'MpCompatFor\s*\(\s*@?"((?:[^"\\]|\\.)*)"\s*\)')

STATUS_LABELS = {
    0: "未知",
    1: "不兼容",
    2: "勉强可用",
    3: "基本可用",
    4: "完全可用",
}

STATUS_DESCRIPTIONS = {
    0: "官方兼容表暂无明确结论。",
    1: "官方兼容表标记为无法正常联机使用。",
    2: "官方兼容表标记为可运行，但较多或重要功能不可用。",
    3: "官方兼容表标记为可运行，但少量功能可能不可用。",
    4: "官方兼容表标记为功能可正常使用。",
}


class MultiplayerCompatibilityManager:
    """读取 Multiplayer 兼容表，并为前端生成稳定的展示状态。"""

    def _read_json_file(self, path_text: str) -> Any:
        path = Path(str(path_text or "").strip())
        if not path.exists() or not path.is_file():
            return None
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                return json.load(handle)
        except Exception as exc:
            logger.warning("读取 Multiplayer 兼容数据失败: path=%s error=%s", path, exc, exc_info=True)
            return None

    def format_official_compatibility_file(self, path_text: str | None = None) -> None:
        target = Path(str(path_text or settings.config.multiplayer_compatibility_path or "").strip())
        if not str(target):
            raise ValueError("Multiplayer 兼容表路径未配置")
        with target.open("r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        # 下载源通常是压缩 JSON；保存为稳定缩进，便于人工检查和后续差异比较。
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _load_official_records(self) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        payload = self._read_json_file(settings.config.multiplayer_compatibility_path)
        records = payload.get("mods") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return {}, {}

        by_workshop: dict[str, dict[str, Any]] = {}
        by_name: dict[str, dict[str, Any]] = {}
        for item in records:
            if not isinstance(item, dict):
                continue
            record = {
                "status": self._normalize_status(item.get("status")),
                "name": str(item.get("name") or "").strip(),
                "notes": str(item.get("notes") or "").strip(),
                "workshop_id": str(item.get("workshopId") or item.get("workshop_id") or "").strip(),
            }
            if record["workshop_id"]:
                by_workshop[record["workshop_id"]] = record
            name_key = record["name"].lower()
            if name_key:
                by_name[name_key] = record
        return by_workshop, by_name

    def _load_mp_compat_package_ids(self) -> set[str]:
        payload = self._read_json_file(settings.config.mp_compat_package_ids_path)
        values: list[Any] = []
        if isinstance(payload, list):
            values = payload
        elif isinstance(payload, dict):
            for key in ("package_ids", "packageIds", "packages", "mods"):
                if isinstance(payload.get(key), list):
                    values.extend(payload[key])
            database = payload.get("database")
            if isinstance(database, dict):
                values.extend(database.keys())

        package_ids: set[str] = set()
        for item in values:
            if isinstance(item, str):
                package_id = item
            elif isinstance(item, dict):
                package_id = item.get("package_id") or item.get("packageId") or item.get("id")
            else:
                package_id = ""
            normalized = self._normalize_package_id(package_id)
            if normalized:
                package_ids.add(normalized)
        return package_ids

    def update_mp_compat_package_ids(self, source_url: str | None = None, target_path: str | None = None) -> dict[str, Any]:
        source_url = str(source_url or settings.config.mp_compat_package_ids_url or MP_COMPAT_DEFAULT_SOURCE_URL).strip()
        target = Path(str(target_path or settings.config.mp_compat_package_ids_path or "").strip())
        if not source_url or not str(target):
            raise ValueError("MP Compat 源码地址或缓存路径未配置")

        archive_url = self._normalize_source_archive_url(source_url)
        archive_bytes, headers, final_url = self._download_source_archive(archive_url)
        package_ids = self.extract_mp_compat_package_ids_from_archive(archive_bytes)
        if not package_ids:
            raise ValueError("未能从 MP Compat 源码中解析到适配包名")

        target.parent.mkdir(parents=True, exist_ok=True)
        updated_at = self._parse_http_datetime_to_ms(headers.get("Last-Modified"))
        signature = hashlib.sha256(archive_bytes).hexdigest()
        payload = {
            "package_ids": sorted(package_ids),
            "source": {
                "url": source_url,
                "download_url": final_url or archive_url,
                "signature": signature,
                "updated_at": updated_at,
                "etag": str(headers.get("ETag") or "").strip('"'),
                "generated_at": int(time.time() * 1000),
            },
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.info("MP Compat 适配包名表已生成: count=%s source=%s target=%s", len(package_ids), final_url or archive_url, target)
        return {
            "path": str(target),
            "count": len(package_ids),
            "source_url": source_url,
            "download_url": final_url or archive_url,
            "source_signature": signature,
            "source_updated_at": updated_at,
        }

    @classmethod
    def extract_mp_compat_package_ids_from_archive(cls, archive_bytes: bytes) -> set[str]:
        package_ids: set[str] = set()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            for name in archive.namelist():
                normalized_name = name.replace("\\", "/")
                if not normalized_name.lower().endswith(".cs"):
                    continue
                if "/Source/" not in f"/{normalized_name}" and "/Source_Referenced/" not in f"/{normalized_name}":
                    continue
                try:
                    source = archive.read(name).decode("utf-8-sig")
                except UnicodeDecodeError:
                    source = archive.read(name).decode("utf-8", errors="ignore")
                package_ids.update(cls.extract_mp_compat_package_ids_from_source(source))
        return package_ids

    @classmethod
    def extract_mp_compat_package_ids_from_source(cls, source: str) -> set[str]:
        package_ids: set[str] = set()
        for match in MP_COMPAT_FOR_RE.finditer(source or ""):
            package_id = cls._decode_csharp_string(match.group(1))
            normalized = cls._normalize_package_id(package_id)
            if normalized:
                package_ids.add(normalized)
        return package_ids

    @staticmethod
    def _normalize_source_archive_url(url: str) -> str:
        text = str(url or "").strip()
        if not text:
            return MP_COMPAT_DEFAULT_SOURCE_URL
        parsed = urlparse(text)
        host = (parsed.netloc or "").lower()
        parts = [part for part in parsed.path.split("/") if part]
        if host == "github.com" and len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            if len(parts) >= 4 and parts[2] == "tree":
                ref = "/".join(parts[3:])
                return f"https://github.com/{owner}/{repo}/archive/refs/heads/{ref}.zip"
            if len(parts) == 2:
                return f"https://github.com/{owner}/{repo}/archive/refs/heads/master.zip"
        return text

    @staticmethod
    def _download_source_archive(url: str) -> tuple[bytes, dict[str, Any], str]:
        with build_retry_session() as session:
            with session.get(url, timeout=(15, 120), headers=merge_headers({"Accept-Encoding": "identity"}), allow_redirects=True) as response:
                response.raise_for_status()
                return response.content, dict(response.headers), str(response.url or url)

    @staticmethod
    def _parse_http_datetime_to_ms(value: Any) -> int:
        text = str(value or "").strip()
        if not text:
            return 0
        try:
            return int(parsedate_to_datetime(text).timestamp() * 1000)
        except Exception:
            return 0

    @staticmethod
    def _decode_csharp_string(value: str) -> str:
        try:
            return bytes(str(value or ""), "utf-8").decode("unicode_escape")
        except Exception:
            return str(value or "")

    def enrich_mods(self, mods: list[dict[str, Any]], active_ids: list[str] | None = None) -> dict[str, Any]:
        feature_enabled = bool(getattr(settings.config, "enable_multiplayer_compatibility_check", False))
        inventory_ids = {self._normalize_package_id(mod.get("package_id")) for mod in mods}
        multiplayer_installed = MULTIPLAYER_PACKAGE_ID in inventory_ids
        active_id_set = {self._normalize_package_id(active_id) for active_id in (active_ids or [])}
        multiplayer_active = MULTIPLAYER_PACKAGE_ID in active_id_set
        mp_compat_active = MP_COMPAT_PACKAGE_ID in active_id_set
        enabled = feature_enabled and multiplayer_installed

        official_by_workshop, official_by_name = self._load_official_records() if enabled else ({}, {})
        mp_compat_package_ids = self._load_mp_compat_package_ids() if enabled else set()

        for mod in mods:
            mod["multiplayer_compat"] = self._build_mod_status(
                mod,
                enabled=enabled,
                feature_enabled=feature_enabled,
                multiplayer_installed=multiplayer_installed,
                multiplayer_active=multiplayer_active,
                active_id_set=active_id_set,
                mp_compat_active=mp_compat_active,
                official_by_workshop=official_by_workshop,
                official_by_name=official_by_name,
                mp_compat_package_ids=mp_compat_package_ids,
            )

        return {
            "enabled": enabled,
            "feature_enabled": feature_enabled,
            "multiplayer_installed": multiplayer_installed,
            "multiplayer_active": multiplayer_active,
            "mp_compat_active": mp_compat_active,
        }

    def _build_mod_status(
        self,
        mod: dict[str, Any],
        *,
        enabled: bool,
        feature_enabled: bool,
        multiplayer_installed: bool,
        multiplayer_active: bool,
        active_id_set: set[str],
        mp_compat_active: bool,
        official_by_workshop: dict[str, dict[str, Any]],
        official_by_name: dict[str, dict[str, Any]],
        mp_compat_package_ids: set[str],
    ) -> dict[str, Any]:
        package_id = self._normalize_package_id(mod.get("package_id"))
        workshop_id = str(mod.get("workshop_id") or "").strip()
        name_key = str(mod.get("name") or "").strip().lower()
        official = official_by_workshop.get(workshop_id) if workshop_id else None
        official = official or official_by_name.get(name_key) or {}
        official_status = self._normalize_status(official.get("status"))
        xml_only = self._is_multiplayer_xml_only(mod)

        effective_status = official_status if official_status in {1, 2, 3, 4} else (4 if xml_only else 0)
        status_source = "official" if official_status in {1, 2, 3, 4} else ("xml_only" if xml_only else "unknown")
        has_patch = package_id in mp_compat_package_ids
        is_active_mod = package_id in active_id_set
        patch_effective = has_patch and is_active_mod and mp_compat_active
        search_values = [STATUS_LABELS.get(effective_status, "未知")]
        if has_patch:
            search_values.append("可修正")

        return {
            "enabled": enabled,
            "feature_enabled": feature_enabled,
            "multiplayer_installed": multiplayer_installed,
            "multiplayer_active": multiplayer_active,
            "official_status": official_status,
            "effective_status": effective_status,
            "effective_label": STATUS_LABELS.get(effective_status, "未知"),
            "status_description": STATUS_DESCRIPTIONS.get(effective_status, STATUS_DESCRIPTIONS[0]),
            "status_source": status_source,
            "notes": str(official.get("notes") or "").strip(),
            "xml_only": xml_only,
            "has_mp_compat_patch": has_patch,
            "mp_compat_active": mp_compat_active,
            "mp_compat_effective": patch_effective,
            "search_values": search_values if enabled else [],
            "sort_rank": effective_status if enabled else 0,
        }

    @staticmethod
    def _normalize_status(value: Any) -> int:
        try:
            status = int(value)
        except (TypeError, ValueError):
            return 0
        return status if 0 <= status <= 4 else 0

    @staticmethod
    def _normalize_package_id(value: Any) -> str:
        return str(value or "").strip().lower().removesuffix("_steam").removesuffix("_local")

    @staticmethod
    def _is_multiplayer_xml_only(mod: dict[str, Any]) -> bool:
        # Multiplayer 的 XML-only 实际语义是“没有程序集”；这里直接使用扫描期 DLL 统计。
        file_stats = mod.get("file_stats") if isinstance(mod.get("file_stats"), dict) else {}
        try:
            return int(file_stats.get("code_dll") or 0) <= 0
        except (TypeError, ValueError):
            return False
