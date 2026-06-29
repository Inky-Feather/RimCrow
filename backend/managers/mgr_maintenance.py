from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import platform
from typing import Any

from packaging.version import InvalidVersion, Version

from backend.database.models import GithubModRecord
from backend.managers.mgr_github import GithubManager
from backend.managers.mgr_network import build_retry_session, merge_headers
from backend.managers.mgr_steam import SteamManager
from backend.managers.mgr_steam_api import SteamWebAPI
from backend.managers.mgr_texture_opt import TextureOptimizationManager
from backend.managers.mgr_workshop_db import WorkshopDBManager
from backend.text_search.tooling import get_ripgrep_status
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
        {
            "data_type": "multiplayer_compatibility",
            "name": "Multiplayer 兼容表",
            "path_key": "multiplayer_compatibility_path",
            "url_key": "multiplayer_compatibility_url",
        },
        {
            "data_type": "mp_compat_package_ids",
            "name": "Multiplayer Compatibility 适配缓存",
            "path_key": "mp_compat_package_ids_path",
            "url_key": "mp_compat_package_ids_url",
            "optional": True,
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

    def check_tools(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        overrides = overrides or {}
        checked_at = current_ms()
        steamcmd_path = (
            str(overrides.get("steamcmd_path") or "").strip()
            if "steamcmd_path" in overrides
            else str(self.steam_mgr.steamcmd_dir or "").strip()
        )
        steamcmd_dir = Path(steamcmd_path) if steamcmd_path else None
        steamcmd_exe = steamcmd_dir / ("steamcmd.exe" if platform.system() == "Windows" else "steamcmd.sh") if steamcmd_dir else None
        steamcmd_installed = bool(steamcmd_exe and steamcmd_exe.exists())
        steamcmd_initialized = bool(steamcmd_dir and (steamcmd_dir / "public").exists())
        steamcmd_ready = steamcmd_installed and steamcmd_initialized

        items: list[dict[str, Any]] = [
            {
                "tool_id": "steamcmd",
                "name": "SteamCMD",
                "installed": steamcmd_installed,
                "ready": steamcmd_ready,
                "can_install": True,
                "action": "steam_tools_install",
                "maintenance_action": "none" if steamcmd_ready else ("install" if not steamcmd_installed else "initialize"),
                "resolved_path": str(steamcmd_exe or ""),
                "state": "ready" if steamcmd_ready else ("missing" if not steamcmd_installed else "not_initialized"),
                "message": (
                    "SteamCMD 已安装并完成初始化。"
                    if steamcmd_ready
                    else ("未检测到 SteamCMD，可由管理器自动下载。" if not steamcmd_installed else "SteamCMD 已存在，但尚未完成初始化。")
                ),
            }
        ]

        texture_options = asdict(settings.config.texture_opt)
        texture_overrides = overrides.get("texture_opt")
        if isinstance(texture_overrides, dict):
            texture_options.update(texture_overrides)
        if "texture_tools_path" in overrides:
            texture_options["texture_tools_path"] = overrides.get("texture_tools_path")
        todds_status = self.texture_mgr.get_backend_status(texture_options)
        todds_release = self.github_mgr.fetch_release("todds-encoder", "todds", missing_ok=True) or {}
        todds_ready = bool(todds_status.get("available"))
        items.append(
            {
                "tool_id": "todds",
                "name": "todds 贴图工具",
                "installed": todds_ready,
                "ready": todds_ready,
                "can_install": True,
                "action": "texture_tools_install",
                "maintenance_action": "none" if todds_ready else "install",
                "resolved_path": str(todds_status.get("resolved_path") or ""),
                "state": "ready" if todds_ready else "missing",
                "message": str(todds_status.get("message") or ""),
                "latest_version": str(todds_release.get("tag_name") or ""),
            }
        )

        ripgrep_path = (
            str(overrides.get("ripgrep_path") or "")
            if "ripgrep_path" in overrides
            else str(getattr(settings.config, "ripgrep_path", "") or "")
        )
        ripgrep_status = get_ripgrep_status(ripgrep_path)
        ripgrep_release = self.github_mgr.fetch_release("BurntSushi", "ripgrep", missing_ok=True) or {}
        ripgrep_current_version = str(ripgrep_status.current_version or "")
        ripgrep_latest_version = str(ripgrep_release.get("tag_name") or "")
        ripgrep_can_install = platform.system() == "Windows" and Path(ripgrep_path).suffix.lower() != ".exe"
        ripgrep_outdated = bool(ripgrep_status.available) and ripgrep_can_install and self._is_version_outdated(ripgrep_current_version, ripgrep_latest_version)
        items.append(
            {
                "tool_id": "ripgrep",
                "name": "ripgrep 搜索工具",
                "installed": bool(ripgrep_status.available),
                "ready": bool(ripgrep_status.available) and not ripgrep_outdated,
                "can_install": ripgrep_can_install,
                "action": "ripgrep_install",
                "maintenance_action": "upgrade" if ripgrep_outdated else ("none" if ripgrep_status.available else "install"),
                "resolved_path": str(ripgrep_status.resolved_path or ""),
                "state": "outdated" if ripgrep_outdated else ("ready" if ripgrep_status.available else "missing"),
                "message": (
                    f"已安装 {ripgrep_current_version}，检测到新版本 {ripgrep_latest_version}。"
                    if ripgrep_outdated else str(ripgrep_status.message or "")
                ),
                "current_version": ripgrep_current_version,
                "latest_version": ripgrep_latest_version,
            }
        )

        issues = [item for item in items if item.get("state") != "ready"]
        return {
            "checked_at": checked_at,
            "items": items,
            "issues": issues,
            "has_issues": bool(issues),
        }

    def check_external_data(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        checked_at = current_ms()
        check_overrides = overrides or {}
        items = [self._check_external_dataset(spec, check_overrides) for spec in self.EXTERNAL_DATASETS]
        items.append(self._check_provider_catalog(check_overrides))
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

        installed_ids: list[str] = []
        for local_item in manager_local_data.values():
            if not local_item.get("is_installed"):
                continue
            workshop_id = str(local_item.get("workshop_id") or "").strip()
            if not workshop_id or not workshop_id.isdigit():
                continue
            installed_ids.append(workshop_id)

        logger.debug(
            "SteamCMD 更新检查[self]：合并数据 %s 条，已安装 %s 条，实际检查 %s 条",
            len(manager_local_data),
            len(installed_ids),
            len(installed_ids),
        )
        if not installed_ids:
            return {
                "checked_at": checked_at,
                "updates": [],
                "count": 0,
            }

        # 合并表同时包含 ACF 记录和日志历史，只对当前仍安装在本地的项目做在线更新检查。
        online_details, _ = SteamWebAPI.fetch_item_details(
            installed_ids,
            trace_label="maintenance_check_steamcmd_mod_updates:self",
        )
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

    def check_managed_mod_updates(self) -> dict[str, Any]:
        """统一检查由管理器负责部署的模组更新。

        SteamCMD 与 GitHub 订阅最终都需要用户确认后触发下载/部署，因此这里合并成一个维护检查，
        前端只需要处理同一种“管理器模组更新”提示即可。
        """
        checked_at = current_ms()
        steamcmd_result = self.check_steamcmd_mod_updates()
        steamcmd_updates = [
            {**item, "source": "steamcmd", "source_label": "SteamCMD"}
            for item in (steamcmd_result.get("updates") or [])
        ]
        github_updates = self._check_github_mod_updates()
        updates = [*steamcmd_updates, *github_updates]
        return {
            "checked_at": checked_at,
            "updates": updates,
            "count": len(updates),
            "steamcmd_count": len(steamcmd_updates),
            "github_count": len(github_updates),
        }

    def _check_github_mod_updates(self) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        for record in GithubModRecord.select().dicts():
            online_info = record.get("online_info_cache") or {}
            if not isinstance(online_info, dict):
                continue
            install_type = str(record.get("install_type") or "source").strip() or "source"
            installed_version = str(record.get("installed_version") or "").strip()
            latest_version = (
                str(online_info.get("latest_release_tag") or "").strip()
                if install_type == "release"
                else str(online_info.get("latest_source_version") or "").strip()
            )
            if not installed_version or not latest_version or installed_version == latest_version:
                continue
            if install_type == "source":
                local_branch, _, local_marker = installed_version.partition("@")
                latest_branch, _, latest_marker = latest_version.partition("@")
                if local_branch and latest_branch and local_branch != latest_branch:
                    continue
                local_time = latest_time = 0
                try:
                    if local_marker:
                        local_time = int(datetime.fromisoformat(local_marker.replace("Z", "+00:00")).timestamp() * 1000)
                    if latest_marker:
                        latest_time = int(datetime.fromisoformat(latest_marker.replace("Z", "+00:00")).timestamp() * 1000)
                except Exception:
                    local_time = latest_time = 0
                if local_time and latest_time and latest_time <= local_time:
                    continue

            # source 模式下载参数仍然是分支名；latest_source_version 只用于判断和展示版本差异。
            target_version = (
                latest_version
                if install_type == "release"
                else str(online_info.get("latest_source_branch") or record.get("target_branch") or online_info.get("default_branch") or "main").strip()
            )
            repo_name = str(record.get("repo_name") or record.get("repo_url") or "").strip()
            updates.append(
                {
                    "source": "github",
                    "source_label": "Git 仓库",
                    "repo_url": str(record.get("repo_url") or "").strip(),
                    "provider": str(record.get("provider") or "github").strip() or "github",
                    "host": str(record.get("host") or "github.com").strip() or "github.com",
                    "title": repo_name or "Git 仓库模组",
                    "install_type": install_type,
                    "installed_version": installed_version,
                    "latest_version": latest_version,
                    "target_version": target_version,
                    "message": f"本地版本 {installed_version}，远端版本 {latest_version}。",
                }
            )
        return updates

    def _check_external_dataset(self, spec: dict[str, str], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        overrides = overrides or {}
        data_type = str(spec["data_type"])
        name = str(spec["name"])
        path_text = (
            str(overrides.get(spec["path_key"]) or "")
            if spec["path_key"] in overrides
            else str(getattr(settings.config, spec["path_key"], "") or "")
        )
        url = (
            str(overrides.get(spec["url_key"]) or "")
            if spec["url_key"] in overrides
            else str(getattr(settings.config, spec["url_key"], "") or "")
        )
        path = Path(path_text) if path_text else None
        exists = bool(path and path.exists())
        if spec.get("optional") and not url and not exists:
            return {
                "data_type": data_type,
                "name": name,
                "path": path_text,
                "url": url,
                "exists": False,
                "needs_update": False,
                "message": "未配置远端地址，已跳过自动检查。",
                "local_size": 0,
                "local_mtime": 0,
                "local_signature": "",
                "local_signature_short": "",
                "local_version": "",
                "remote_available": False,
                "remote_supported": False,
                "remote_signature": "",
                "remote_signature_short": "",
                "remote_size": 0,
                "remote_updated_at": 0,
                "remote_version": "",
                "remote_etag": "",
                "comparison_mode": "skipped",
                "download_url": "",
            }

        local_size = path.stat().st_size if exists and path else 0
        local_mtime = int(path.stat().st_mtime * 1000) if exists and path else 0
        local_signature = self._compute_git_blob_sha(path) if exists and path else ""
        local_version = self._resolve_local_dataset_version(data_type)
        local_source_info = self._read_local_source_info(path) if data_type == "mp_compat_package_ids" and exists and path else {}

        remote_info = self._probe_remote_file(url)
        remote_signature = str(remote_info.get("signature") or "")
        remote_size = int(remote_info.get("size") or 0)
        remote_updated_at = int(remote_info.get("updated_at") or 0)

        needs_update = False
        comparison_mode = "unavailable"
        if not exists:
            needs_update = True
            comparison_mode = "missing"
        elif data_type == "mp_compat_package_ids":
            local_source_etag = str(local_source_info.get("etag") or "").strip()
            local_source_updated_at = int(local_source_info.get("updated_at") or 0)
            remote_etag = str(remote_info.get("etag") or "").strip()
            if remote_info.get("available") and remote_etag and local_source_etag:
                comparison_mode = "source_etag"
                needs_update = remote_etag != local_source_etag
            elif remote_info.get("available") and remote_updated_at > 0:
                comparison_mode = "source_mtime"
                needs_update = not local_source_updated_at or remote_updated_at > local_source_updated_at + 1000
            elif remote_info.get("available"):
                comparison_mode = "source_available"
        elif remote_info.get("available") and remote_signature:
            comparison_mode = "signature"
            needs_update = local_signature != remote_signature
        elif remote_info.get("available") and remote_size > 0 and local_size != remote_size:
            comparison_mode = "size"
            needs_update = True
        elif remote_info.get("available") and remote_size > 0:
            comparison_mode = "size"
        elif remote_info.get("available") and remote_updated_at > 0:
            comparison_mode = "mtime"
            needs_update = not local_mtime or remote_updated_at > local_mtime + 1000

        message = ""
        if not exists:
            message = "未检测到本地文件。"
        elif remote_info.get("available"):
            message = "检测到远端文件与本地不一致。" if needs_update else "本地文件已是最新。"
        else:
            message = str(remote_info.get("message") or "暂时无法获取远端状态。")

        return {
            "data_type": data_type,
            "name": name,
            "path": path_text,
            "url": url,
            "exists": exists,
            "needs_update": needs_update,
            "message": message,
            "local_size": local_size,
            "local_mtime": local_mtime,
            "local_signature": local_signature,
            "local_signature_short": local_signature[:12],
            "local_version": local_version,
            "remote_available": bool(remote_info.get("available")),
            "remote_supported": bool(remote_info.get("supported")),
            "remote_signature": remote_signature,
            "remote_signature_short": remote_signature[:12],
            "remote_size": remote_size,
            "remote_updated_at": remote_updated_at,
            "remote_version": str(remote_info.get("version") or ""),
            "remote_etag": str(remote_info.get("etag") or ""),
            "comparison_mode": comparison_mode,
            "download_url": str(remote_info.get("download_url") or ""),
        }

    def _check_provider_catalog(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        overrides = overrides or {}
        url = (
            str(overrides.get("git_provider_catalog_url") or "")
            if "git_provider_catalog_url" in overrides
            else str(getattr(settings.config, "git_provider_catalog_url", "") or "")
        )
        remote_info = self.github_mgr.check_provider_catalog_updates(url)
        sources = remote_info.get("sources") if isinstance(remote_info, dict) else []
        sources = sources if isinstance(sources, list) else []
        exists = bool(sources) and all(bool(source.get("exists")) for source in sources)
        remote_available = bool(remote_info.get("remote_available"))
        needs_update = bool(remote_info.get("needs_update")) and remote_available
        failed_sources = [source for source in sources if not source.get("remote_available")]
        source_labels = [str(source.get("label") or source.get("source_id") or "").strip() for source in sources]

        if not exists:
            message = "未检测到 Git 推荐清单缓存。"
            comparison_mode = "missing"
        elif remote_available:
            message = "检测到 Git 推荐清单有更新。" if needs_update else "Git 推荐清单已是最新。"
            comparison_mode = "signature"
        else:
            message = "Git 推荐清单检查未完成。"
            comparison_mode = "unavailable"

        return {
            "data_type": "git_provider_catalog",
            "name": "Git 推荐清单",
            "path": "",
            "url": url,
            "exists": exists,
            "needs_update": needs_update,
            "message": message,
            "local_size": int(remote_info.get("local_count") or 0),
            "local_mtime": 0,
            "local_signature": str(remote_info.get("local_signature") or ""),
            "local_signature_short": str(remote_info.get("local_signature") or "")[:12],
            "local_version": "",
            "remote_available": remote_available,
            "remote_supported": True,
            "remote_signature": str(remote_info.get("remote_signature") or ""),
            "remote_signature_short": str(remote_info.get("remote_signature") or "")[:12],
            "remote_size": int(remote_info.get("remote_count") or 0),
            "remote_updated_at": 0,
            "remote_version": "",
            "remote_etag": "",
            "comparison_mode": comparison_mode,
            "download_url": "",
            "source_labels": [label for label in source_labels if label],
            "failed_sources": failed_sources,
        }

    def _resolve_local_dataset_version(self, data_type: str) -> str:
        try:
            if data_type == "workshop_db":
                return str(self.workshop_db_mgr.get_workshopdb_version() or "")
            if data_type == "instead_db":
                return str(self.workshop_db_mgr.get_insteaddb_version() or "")
            if data_type == "mp_compat_package_ids":
                source = self._read_local_source_info(Path(settings.config.mp_compat_package_ids_path))
                return str(source.get("etag") or source.get("updated_at") or source.get("signature") or "")
            if data_type == "community_rules" and callable(self.rule_mgr_provider):
                rule_mgr = self.rule_mgr_provider()
                if rule_mgr and getattr(rule_mgr, "community_rules_update_time", 0):
                    return str(int(getattr(rule_mgr, "community_rules_update_time", 0)))
        except Exception:
            logger.debug("解析本地数据集版本失败：%s", data_type, exc_info=True)
        return ""

    def _read_local_source_info(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        source = payload.get("source")
        return source if isinstance(source, dict) else {}

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
                    # HTTP ETag 语义由服务端决定，不一定是文件内容哈希；
                    # 不能拿它和本地 Git blob SHA 直接比较，否则会造成误报。
                    "etag": etag,
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
    def _normalize_release_version(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        match = re.search(r"\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?", raw)
        return match.group(0) if match else raw.lstrip("vV")

    @classmethod
    def _is_version_outdated(cls, current: Any, latest: Any) -> bool:
        """保守比较工具版本。

        只有当前版本和远端版本都能解析时才提示升级，避免把非标准 tag 误判成必须更新。
        """
        current_version = cls._normalize_release_version(current)
        latest_version = cls._normalize_release_version(latest)
        if not current_version or not latest_version:
            return False
        try:
            return Version(current_version) < Version(latest_version)
        except InvalidVersion:
            logger.debug("跳过非标准工具版本比较：%s -> %s", current, latest)
            return False

    @staticmethod
    def _parse_http_datetime_to_ms(value: Any) -> int:
        raw = str(value or "").strip()
        if not raw: return 0
        try:
            parsed = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z")
            return int(parsed.replace(tzinfo=timezone.utc).timestamp() * 1000)
        except Exception: return 0
