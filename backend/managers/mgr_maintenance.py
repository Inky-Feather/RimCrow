from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.managers.mgr_github import GithubManager
from backend.managers.mgr_network import build_retry_session, merge_headers
from backend.managers.mgr_steam import SteamManager
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.managers.mgr_texture_opt import TextureOptimizationManager
from backend.managers.mgr_workshop_db import WorkshopDBManager
from backend.settings import settings
from backend.utils.logger import logger
from backend.utils.tools import current_ms


class MaintenanceManager:
    """聚合非软件更新类的维护检查。

    设计目标：
    1. 把“工具环境检查”“外部库文件检查”“SteamCMD 模组更新检查”统一收口。
    2. 这些检查只负责给前端提供状态，不直接修改用户环境。
    3. 前端根据结果弹窗询问，用户确认后再调用既有安装/下载接口。
    """

    EXTERNAL_DATASETS = (
        {
            "data_type": "community_rules",
            "name": "社区规则库",
            "path_key": "community_rules_path",
            "url_key": "community_rules_url",
        },
        {
            "data_type": "workshop_db",
            "name": "社区工坊数据库",
            "path_key": "community_workshop_db_path",
            "url_key": "community_workshop_db_url",
        },
        {
            "data_type": "instead_db",
            "name": "替代 Mod 数据库",
            "path_key": "community_instead_db_path",
            "url_key": "community_instead_db_url",
        },
    )

    def __init__(
        self,
        steam_mgr: SteamManager,
        texture_mgr: TextureOptimizationManager,
        workshop_db_mgr: WorkshopDBManager,
        *,
        rule_mgr_provider=None,
    ):
        self.steam_mgr = steam_mgr
        self.texture_mgr = texture_mgr
        self.workshop_db_mgr = workshop_db_mgr
        self.rule_mgr_provider = rule_mgr_provider
        self.github_mgr = GithubManager()

    def check_tools(self) -> dict[str, Any]:
        checked_at = current_ms()
        steamcmd_dir = Path(self.steam_mgr.steamcmd_dir)
        steamcmd_exe = Path(self.steam_mgr.steamcmd_exe)
        steamcmd_installed = steamcmd_exe.exists()
        steamcmd_initialized = (steamcmd_dir / "public").exists()
        steamcmd_ready = steamcmd_installed and steamcmd_initialized

        items: list[dict[str, Any]] = [
            {
                "tool_id": "steamcmd",
                "name": "SteamCMD",
                "installed": steamcmd_installed,
                "ready": steamcmd_ready,
                "can_install": True,
                "action": "steam_tools_install",
                "resolved_path": str(steamcmd_exe),
                "state": "ready" if steamcmd_ready else ("missing" if not steamcmd_installed else "not_initialized"),
                "message": (
                    "SteamCMD 已安装并完成初始化。"
                    if steamcmd_ready
                    else ("未检测到 SteamCMD，可由管理器自动下载。" if not steamcmd_installed else "SteamCMD 已存在，但尚未完成初始化。")
                ),
            }
        ]

        texture_options = asdict(settings.config.texture_opt)
        todds_status = self.texture_mgr.get_backend_status(texture_options)
        todds_release = self.github_mgr.fetch_release("todds-encoder", "todds", missing_ok=True) or {}
        items.append(
            {
                "tool_id": "todds",
                "name": "todds 贴图工具",
                "installed": bool(todds_status.get("available")),
                "ready": bool(todds_status.get("available")),
                "can_install": True,
                "action": "texture_tools_install",
                "resolved_path": str(todds_status.get("resolved_path") or ""),
                "state": "ready" if todds_status.get("available") else "missing",
                "message": str(todds_status.get("message") or ""),
                "latest_version": str(todds_release.get("tag_name") or ""),
            }
        )

        issues = [item for item in items if not item.get("ready")]
        return {
            "checked_at": checked_at,
            "items": items,
            "issues": issues,
            "has_issues": bool(issues),
        }

    def check_external_data(self) -> dict[str, Any]:
        checked_at = current_ms()
        items = [self._check_external_dataset(spec) for spec in self.EXTERNAL_DATASETS]
        updates = [item for item in items if item.get("needs_update")]
        missing = [item for item in items if not item.get("exists")]
        # 远端检查失败不等于“已是最新”。
        # 这里单独汇总失败项，前端据此提示“检查未完成/部分失败”，避免把失败误判成无更新。
        failed = [
            item for item in items
            if item.get("remote_supported") and not item.get("remote_available")
        ]
        return {
            "checked_at": checked_at,
            "items": items,
            "updates": updates,
            "missing": missing,
            "failed": failed,
            "has_updates": bool(updates),
            "has_errors": bool(failed),
        }

    def check_steamcmd_mod_updates(self) -> dict[str, Any]:
        checked_at = current_ms()
        manager_local_data = self.steam_mgr.steamcmd_merged_data()
        if not manager_local_data:
            return {
                "checked_at": checked_at,
                "updates": [],
                "count": 0,
            }

        online_details, _ = SteamWebAPI.fetch_item_details(list(manager_local_data.keys()))
        updates: list[dict[str, Any]] = []
        for local_item in manager_local_data.values():
            if not local_item.get("is_installed"):
                continue
            wid = str(local_item.get("workshop_id") or "")
            online_info = online_details.get(wid)
            if not online_info:
                continue
            local_time = int(local_item.get("time_downloaded") or local_item.get("installed_version_time") or 0)
            online_time = int(online_info.get("time_updated") or 0)
            # Steam 本地记录通常会滞后片刻，这里保留 1 小时容差，避免反复误报。
            if online_time <= local_time + 3600 * 1000:
                continue
            updates.append(
                {
                    "workshop_id": wid,
                    "title": online_info.get("title") or wid,
                    "source": "self",
                    "local_time": local_time,
                    "online_time": online_time,
                    "preview_url": online_info.get("preview_url") or "",
                }
            )

        return {
            "checked_at": checked_at,
            "updates": updates,
            "count": len(updates),
        }

    def _check_external_dataset(self, spec: dict[str, str]) -> dict[str, Any]:
        data_type = str(spec["data_type"])
        name = str(spec["name"])
        path = Path(str(getattr(settings.config, spec["path_key"], "") or ""))
        url = str(getattr(settings.config, spec["url_key"], "") or "")
        exists = path.exists()

        local_size = path.stat().st_size if exists else 0
        local_mtime = int(path.stat().st_mtime * 1000) if exists else 0
        local_signature = self._compute_git_blob_sha(path) if exists else ""
        local_version = self._resolve_local_dataset_version(data_type)

        remote_info = self._probe_remote_file(url)
        remote_signature = str(remote_info.get("signature") or "")
        remote_size = int(remote_info.get("size") or 0)
        remote_updated_at = int(remote_info.get("updated_at") or 0)

        needs_update = False
        if not exists:
            needs_update = True
        elif remote_info.get("available") and remote_signature:
            needs_update = local_signature != remote_signature
        elif remote_info.get("available") and remote_size > 0 and local_size != remote_size:
            needs_update = True

        message = ""
        if not exists:
            message = "未检测到本地文件。"
        elif remote_info.get("available"):
            message = "检测到远端版本与本地不一致。" if needs_update else "本地文件已是最新。"
        else:
            message = str(remote_info.get("message") or "暂时无法获取远端状态。")

        return {
            "data_type": data_type,
            "name": name,
            "path": str(path),
            "url": url,
            "exists": exists,
            "needs_update": needs_update,
            "message": message,
            "local_size": local_size,
            "local_mtime": local_mtime,
            "local_signature": local_signature,
            "local_version": local_version,
            "remote_available": bool(remote_info.get("available")),
            "remote_supported": bool(remote_info.get("supported")),
            "remote_signature": remote_signature,
            "remote_size": remote_size,
            "remote_updated_at": remote_updated_at,
            "remote_version": str(remote_info.get("version") or ""),
            "download_url": str(remote_info.get("download_url") or ""),
        }

    def _resolve_local_dataset_version(self, data_type: str) -> str:
        try:
            if data_type == "workshop_db":
                return str(self.workshop_db_mgr.get_workshopdb_version() or "")
            if data_type == "instead_db":
                return str(self.workshop_db_mgr.get_insteaddb_version() or "")
            if data_type == "community_rules" and callable(self.rule_mgr_provider):
                rule_mgr = self.rule_mgr_provider()
                if rule_mgr and getattr(rule_mgr, "community_rules_update_time", 0):
                    return str(int(getattr(rule_mgr, "community_rules_update_time", 0)))
        except Exception:
            logger.debug("Resolve local dataset version failed: %s", data_type, exc_info=True)
        return ""

    def _compute_git_blob_sha(self, path: Path) -> str:
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        header = f"blob {len(data)}\0".encode("utf-8")
        return hashlib.sha1(header + data).hexdigest()

    def _probe_remote_file(self, url: str) -> dict[str, Any]:
        normalized_url = str(url or "").strip()
        if not normalized_url:
            return {
                "supported": False,
                "available": False,
                "message": "未配置远端地址。",
            }

        github_target = self.github_mgr.parse_content_url(normalized_url)
        if github_target:
            try:
                payload = self.github_mgr.fetch_file_metadata(
                    github_target["owner"],
                    github_target["repo"],
                    ref=github_target["ref"],
                    remote_path=github_target["remote_path"],
                    missing_ok=True,
                )
                if payload:
                    return {
                        "supported": True,
                        "available": True,
                        **payload,
                    }
                normalized = f"{github_target['owner']}/{github_target['repo']}/{github_target['remote_path']}"
                return {
                    "supported": True,
                    "available": False,
                    "message": f"GitHub 资源不存在: {normalized}",
                }
            except Exception as exc:
                normalized = f"{github_target['owner']}/{github_target['repo']}/{github_target['remote_path']}"
                logger.warning("GitHub 外部文件检查失败: %s", normalized, exc_info=True)
                return {
                    "supported": True,
                    "available": False,
                    "message": f"获取远端状态失败: {exc}",
                }
        return self._probe_generic_file(normalized_url)

    def _probe_generic_file(self, url: str) -> dict[str, Any]:
        try:
            with build_retry_session() as session:
                response = session.head(
                    url,
                    headers=merge_headers(),
                    timeout=(8, 20),
                    allow_redirects=True,
                )
                response.raise_for_status()
                headers = response.headers
                updated_at = self._parse_http_datetime_to_ms(headers.get("Last-Modified"))
                size = int(headers.get("Content-Length") or 0)
                etag = str(headers.get("ETag") or "").strip('"')
                return {
                    "supported": True,
                    "available": True,
                    "signature": etag,
                    "size": size,
                    "download_url": str(response.url or url),
                    "updated_at": updated_at,
                }
        except Exception as exc:
            logger.warning("通用外部文件检查失败: %s", url, exc_info=True)
            return {
                "supported": True,
                "available": False,
                "message": f"获取远端状态失败: {exc}",
            }

    @staticmethod
    def _parse_http_datetime_to_ms(value: Any) -> int:
        raw = str(value or "").strip()
        if not raw:
            return 0
        try:
            parsed = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z")
            return int(parsed.replace(tzinfo=timezone.utc).timestamp() * 1000)
        except Exception:
            return 0
