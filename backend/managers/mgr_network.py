# backend/managers/mgr_network.py
import os
import socket
import copy
import ipaddress
import json
import math
import re
import time
import threading
import queue
from dataclasses import asdict
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit
from urllib.request import getproxies

try:
    from pip_system_certs.wrapt_requests import inject_truststore
    inject_truststore()
except ImportError:
    pass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from backend.settings import BASE_RESOURCE_DIR, CACHE_DIR, settings
from backend.utils.error_contract import InvalidResponseError, _classify_http_status, classify_exception
from backend.utils.json_io import write_json_atomic
from backend.utils.logger import logger
from backend.utils.system_hosts import SystemHostsService

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 RimCrow"
PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy")
GITHUB_HOSTS_CACHE_PATH = CACHE_DIR / "github_hosts.json"
_HOSTS_OVERRIDE: ContextVar[dict[str, str] | None] = ContextVar("network_hosts_override", default=None)
NETWORK_CHECK_TARGETS = (
    ("github", "GitHub 项目浏览", "https://github.com/Inky-Feather/RimCrow"),
    ("github_api", "GitHub API", "https://api.github.com/repos/Inky-Feather/RimCrow"),
    ("github_archive", "GitHub 源码下载", "https://codeload.github.com/Inky-Feather/RimCrow/zip/refs/heads/main"),
    ("github_raw", "GitHub 文件内容", "https://raw.githubusercontent.com/Inky-Feather/RimCrow/main/README.md"),
    ("gitee", "Gitee 项目浏览", "https://gitee.com/InkyXFeather/RimCrow"),
    ("gitlab", "GitLab 项目浏览", "https://gitlab.com/explore/projects"),
    ("gitgud", "GitGud 项目浏览", "https://gitgud.io/explore/projects"),
    ("sourceforge", "SourceForge 下载入口", "https://sourceforge.net/projects/rimcrow/files/latest/download?format=json"),
    ("steam_workshop", "Steam 创意工坊", "https://steamcommunity.com/app/294100/workshop/"),
    ("steam_api", "Steam Web API", "https://api.steampowered.com/ISteamWebAPIUtil/GetServerInfo/v1/"),
    ("steamcmd_install", "SteamCMD 安装包", "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"),
    ("steamcmd_update", "SteamCMD 更新清单", "https://client-update.steamstatic.com/steam_cmd_win32"),
    # 下载节点仅作连通性参考，不代表 SteamCMD 的全部可用节点。
    ("steamcmd_cdn_clngaa", "SteamCMD 下载节点（clngaa）", "http://dl.steam.clngaa.com/"),
    ("steamcmd_cdn_eccdnx", "SteamCMD 下载节点（eccdnx）", "http://st.dl.eccdnx.com/"),
    # ("steamcmd_cdn_pphimalayanrt", "SteamCMD 下载节点（pphimalayanrt）", "http://xz.pphimalayanrt.com/"),
    # UGC 图片路径末尾的斜杠不能省略，否则部分图片入口会返回 404。
    ("steam_images", "Steam 工坊图片", "https://images.steamusercontent.com/ugc/781856287315666264/268334829540C1D4FFEEF9924CAB105C60AC4A13/"),
    ("steam_images_legacy", "Steam 工坊图片（旧版）", "https://steamuserimages-a.akamaihd.net/ugc/781856287315666264/268334829540C1D4FFEEF9924CAB105C60AC4A13/"),
)


def _map_network_tasks(fetch, items: list, stop: threading.Event) -> list:
    """限量并发并保持输入顺序；退出后不再等待阻塞中的网络 I/O。"""
    tasks = queue.Queue()
    completed = queue.Queue()
    for index, item in enumerate(items):
        tasks.put((index, item))

    def run():
        while not stop.is_set():
            try:
                index, item = tasks.get_nowait()
            except queue.Empty:
                return
            try:
                completed.put((index, fetch(item), None))
            except Exception as exc:
                completed.put((index, None, exc))

    # requests 无法强制终止线程；daemon 不参与解释器的线程池退出等待。
    for _ in range(min(4, len(items))):
        threading.Thread(target=run, name="network-source", daemon=True).start()
    results = [None] * len(items)
    remaining = len(items)
    while remaining and not stop.is_set():
        try:
            index, result, error = completed.get(timeout=0.1)
        except queue.Empty:
            continue
        if error is not None:
            raise error
        results[index] = result
        remaining -= 1
    return results


class NetworkManager:
    def __init__(self):
        # 保存原始的 getaddrinfo，防止重复 patch 导致死循环
        self._original_getaddrinfo = socket.getaddrinfo
        self._is_socket_patched = False
        self._patched_getaddrinfo = None
        self._dynamic_github_hosts: dict[str, str] = {}
        self._dynamic_github_hosts_source = ""
        self._github_hosts_lock = threading.RLock()
        self._hosts_cache_thread: threading.Thread | None = None
        self._hosts_cache_pending = False
        self._github_hosts_stop = threading.Event()
        self._github_hosts_request_id = 0
        self._github_hosts_thread: threading.Thread | None = None
        self._github_hosts_preview_request_id = 0
        self._github_hosts_preview_thread: threading.Thread | None = None
        self._last_github_hosts_enabled: bool | None = None
        self._github_hosts_state: dict[str, Any] = {
            "status": "idle", "source_url": "", "hosts": {}, "error": "", "updated_at": 0,
        }
        self._github_hosts_preview_state: dict[str, Any] = {
            "status": "idle", "source_url": "", "hosts": {}, "error": "", "source_errors": [], "updated_at": 0,
        }
        
        self._system_hosts = SystemHostsService(BASE_RESOURCE_DIR / "main.py", self._on_system_hosts_result)

        # 首次初始化
        self.apply(startup=True)

    def apply(self, *, startup: bool = False, allow_system_hosts_elevation: bool = False):
        """应用已保存设置；启动按间隔更新，关闭后重新开启时立即后台获取一次。"""
        if self._github_hosts_stop.is_set():
            return
        source_url = "\n".join(self.split_hosts_sources(settings.config.network.hosts_sources))
        if startup and settings.config.network.github_hosts_enabled:
            self._load_github_hosts_cache(source_url)
        save_cache = False
        with self._github_hosts_lock:
            if self._github_hosts_stop.is_set():
                return
            cfg = settings.config.network
            enabled = bool(cfg.github_hosts_enabled)
            was_disabled = self._last_github_hosts_enabled is False and enabled
            source_url = "\n".join(self.split_hosts_sources(cfg.hosts_sources))
            source_changed = self._dynamic_github_hosts_source != source_url
            if self._dynamic_github_hosts_source != source_url:
                self._dynamic_github_hosts = {}
            state = self._github_hosts_state
            if not enabled and state["status"] == "loading":
                # 已发出的请求不能立即中断，但关闭后不得再提交结果。
                self._github_hosts_request_id += 1
                self._github_hosts_state = {**state, "status": "idle"}
            preview = self._github_hosts_preview_state
            if enabled and preview["status"] == "ready" and preview["source_url"] == source_url and (
                source_changed or preview["updated_at"] > state["updated_at"]
            ):
                # 保存表单后接管已完成的预览结果，避免相同来源重复请求。
                self._github_hosts_state = {**preview, "hosts": dict(preview["hosts"])}
                state = self._github_hosts_state
                self._dynamic_github_hosts = dict(state["hosts"])
                self._dynamic_github_hosts_source = source_url
                cfg.github_hosts_updated_at = state["updated_at"]
                self._github_hosts_request_id += 1
                save_cache = True
                self._github_hosts_preview_state = {**preview, "status": "idle", "source_url": "", "hosts": {}}
            if enabled and state["status"] == "ready" and state["source_url"] == source_url:
                is_new = (self._dynamic_github_hosts != state["hosts"] or self._dynamic_github_hosts_source != source_url
                    or cfg.github_hosts_updated_at != state["updated_at"])
                self._dynamic_github_hosts = dict(state["hosts"])
                self._dynamic_github_hosts_source = source_url
                cfg.github_hosts_updated_at = state["updated_at"]
                if is_new:
                    save_cache = True
            self._apply_hosts(allow_elevation=allow_system_hosts_elevation)
            is_due = time.time() - float(cfg.github_hosts_updated_at or 0) >= max(1, int(cfg.github_hosts_refresh_interval_hours or 24)) * 3600
            if startup and not self._dynamic_github_hosts:
                is_due = True  # 无有效缓存视为从未成功获取，不能只凭旧时间戳跳过首次下载。
            should_fetch = startup and enabled and is_due and (
                not self._dynamic_github_hosts or cfg.github_hosts_auto_update
            )
            self._last_github_hosts_enabled = enabled
            has_current_request = (
                state["source_url"] == source_url and state["status"] in {"loading", "ready"}
            )
            if (enabled and (was_disabled or source_changed) and not has_current_request) or should_fetch:
                self.refresh_github_hosts()
        if save_cache:
            self._save_github_hosts_cache()

    def _apply_hosts(self, *, allow_elevation: bool = False) -> None:
        """只发布内存状态并提交系统写入目标；不在网络锁内做文件 I/O。"""
        with self._github_hosts_lock:
            if self._github_hosts_stop.is_set():
                return
            self.patch_socket_for_hosts()
            hosts = self._effective_hosts() if settings.config.network.write_to_system_hosts else {}
            self._system_hosts.submit(hosts, allow_elevation=allow_elevation)

    def retry_system_hosts(self) -> dict[str, Any]:
        """重试已保存的系统映射；不下载来源，不读取表单预览。"""
        self._apply_hosts(allow_elevation=True)
        return self.get_github_hosts_status()

    @staticmethod
    def _system_hosts_message(state: dict[str, Any]) -> str:
        from backend.i18n.messages import tr
        if state.get("status") != "error":
            return ""
        if state.get("removing"):
            return tr("network.hosts.system_remove_failed", "系统 Hosts 中可能仍保留之前的映射，请点击重试完成清理。")
        code = state.get("error_code", "")
        if code == "NETWORK.HOSTS.ELEVATION_CANCELLED":
            return tr("network.hosts.authorization_cancelled", "已取消管理员授权，系统 Hosts 未完成更新。应用内映射不受影响。")
        if code == "NETWORK.HOSTS.AUTHORIZATION_TIMEOUT":
            return tr("network.hosts.authorization_timeout", "等待管理员授权超时，系统 Hosts 未完成更新。需要时可点击重试。")
        if code == "NETWORK.HOSTS.PERMISSION_DENIED":
            if os.name != "nt":
                return tr("network.hosts.permission_denied_unix", "没有权限更新系统 Hosts，请检查系统文件权限后重试。应用内映射不受影响。")
            return tr("network.hosts.permission_denied", "没有权限更新系统 Hosts。可点击重试并允许管理员授权，或检查安全软件的拦截设置。")
        if code == "NETWORK.HOSTS.CONTENT_CHANGED":
            return tr("network.hosts.content_changed", "检测到其他程序修改了系统 Hosts，请停止同时修改后重试。")
        if code == "NETWORK.HOSTS.TIMEOUT":
            return tr("network.hosts.write_timeout", "系统 Hosts 更新超时，结果尚未确认。请点击重试核实并应用已保存的设置。")
        return tr("network.hosts.system_apply_failed", "系统 Hosts 未能更新，应用内映射仍可使用。请检查系统文件权限或安全软件设置后重试。")

    def _on_system_hosts_result(self, state: dict[str, Any]) -> None:
        if self._github_hosts_stop.is_set():
            return  # 退出结果由 close 统一记录，不再派发界面通知。
        log = logger.warning if state["status"] == "error" else logger.debug
        log("[SystemHosts] status=%s version=%s duration_ms=%s removing=%s error_code=%s errno=%s winerror=%s detail=%s",
            state["status"], state["version"], state["duration_ms"], state.get("removing", False), state.get("error_code", ""),
            state.get("errno"), state.get("winerror"), state.get("error", ""))
        if state["status"] == "error":
            from backend.utils.event_bus import EventBus
            # WebView 通知可能等待界面响应，不能占用系统文件串行执行线程。
            threading.Thread(target=EventBus.send_toast,
                args=(self._system_hosts_message(state),),
                kwargs={"type": "warning", "error_code": state.get("error_code", "")}, name="hosts-notification", daemon=True).start()

    @staticmethod
    def _normalize_host(value: Any) -> str:
        return str(value or "").strip().lower().rstrip(".")

    @staticmethod
    def _proxy_url_from_config(cfg: Any) -> str:
        get = cfg.get if isinstance(cfg, dict) else lambda key, default=None: getattr(cfg, key, default)
        if not cfg or not bool(get("enabled", False)):
            return ""
        host = str(get("host", "") or "").strip()
        try:
            port = int(get("port", 0) or 0)
        except (TypeError, ValueError):
            port = 0
        if not host or not 1 <= port <= 65535:
            return ""
        scheme = str(get("type", "http") or "http").strip().lower()
        if scheme not in {"http", "socks5"}:
            scheme = "http"
        username = str(get("username", "") or "").strip()
        password = str(get("password", "") or "").strip()
        auth = ""
        if username:
            from urllib.parse import quote
            auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{scheme}://{auth}{host}:{port}"

    @classmethod
    def _host_matches_bypass(cls, host: str, bypass_list: Any) -> bool:
        normalized = cls._normalize_host(host)
        for raw in bypass_list or []:
            item = cls._normalize_host(raw)
            if not item:
                continue
            if item.startswith("*."):
                item = item[2:]
            if normalized == item or normalized.endswith(f".{item}"):
                return True
        return False

    def snapshot_config(self) -> dict[str, Any]:
        """任务固定代理与有效 Hosts，不修改系统环境或运行配置。"""
        network = asdict(settings.config.network)
        network["effective_hosts"] = dict(self._effective_hosts())
        network["environment_proxies"] = dict(getproxies())
        network["certificate_bundle"] = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
        return network

    def request_route(self, url: str, *, network_override: dict[str, Any] | None = None) -> dict[str, Any]:
        """返回单个 URL 的连接决策；镜像由调用方先生成，这里只决定代理和 Hosts。"""
        parsed = urlsplit(str(url or "").strip())
        host = self._normalize_host(parsed.hostname)
        network = network_override if isinstance(network_override, dict) else None
        proxy_cfg = (network or {}).get("proxy") if network is not None else settings.config.network.proxy
        proxy_url = self._proxy_url_from_config(proxy_cfg)
        app_proxy_enabled = bool(proxy_url)
        bypass_list = (proxy_cfg or {}).get("bypass_list", []) if isinstance(proxy_cfg, dict) else getattr(proxy_cfg, "bypass_list", [])
        # 绕过列表只属于应用代理；关闭应用代理时，requests 仍应按外部环境代理工作。
        bypassed = bool(app_proxy_enabled and self._host_matches_bypass(host, bypass_list))
        if not app_proxy_enabled:
            environment = network.get("environment_proxies") if network is not None else None
            if isinstance(environment, dict):
                bypassed = requests.utils.should_bypass_proxies(str(url), no_proxy=str(environment.get("no") or ""))
                proxy_url = "" if bypassed else requests.utils.select_proxy(str(url), environment) or ""
            else:
                proxy_url = requests.utils.select_proxy(str(url), requests.utils.get_environ_proxies(str(url))) or ""
        active_hosts = self._effective_hosts() if network is None else self._preview_hosts(network)
        hosts_ip = active_hosts.get(host, "")
        return {
            "host": host,
            "route": "direct" if not proxy_url or bypassed else "proxy",
            "proxy_url": "" if bypassed else proxy_url,
            "proxy_enabled": app_proxy_enabled,
            "proxy_bypassed": bypassed,
            "hosts_ip": hosts_ip,
            "hosts_hit": bool(hosts_ip),
        }

    def prepare_session_for_url(self, session: requests.Session, url: str, *, network_override: dict[str, Any] | None = None) -> dict[str, Any]:
        """按 URL 更新 Session 路由；由 RoutedSession 在真正请求前调用。"""
        decision = self.request_route(url, network_override=network_override)
        proxies = getattr(session, "proxies", None)
        if proxies is None:
            proxies = {}
            session.proxies = proxies
        proxies.clear()
        has_environment_snapshot = network_override is not None and "environment_proxies" in network_override
        session.trust_env = not decision["proxy_enabled"] and not has_environment_snapshot
        if has_environment_snapshot and network_override.get("certificate_bundle"):
            session.verify = network_override["certificate_bundle"]
        if decision["proxy_url"] and not decision["proxy_bypassed"]:
            session.proxies.update({"http": decision["proxy_url"], "https": decision["proxy_url"]})
        return decision

    def _preview_hosts(self, network: dict[str, Any]) -> dict[str, str]:
        dynamic = {}
        if network.get("github_hosts_enabled", True):
            dynamic = network.get("effective_hosts") or network.get("dynamic_hosts") or {}
        if not isinstance(dynamic, dict):
            dynamic = {}
        manual = network.get("hosts") or {}
        if not isinstance(manual, dict):
            manual = {}
        result = {}
        for host, ip in dynamic.items():
            normalized = self._normalize_host(host)
            if normalized and str(ip).strip():
                result[normalized] = str(ip).strip()
        for host, ip in manual.items():
            normalized = self._normalize_host(host)
            if normalized and str(ip).strip():
                result[normalized] = str(ip).strip()
        return result

    @contextmanager
    def hosts_override(self, hosts: dict[str, str] | None):
        """仅覆盖当前执行上下文；空映射明确禁用应用映射，不回退到已保存值。"""
        token = _HOSTS_OVERRIDE.set(self._preview_hosts({"effective_hosts": hosts or {}}))
        try:
            yield
        finally:
            _HOSTS_OVERRIDE.reset(token)
    
    def get_proxy_url(self) -> str:
        """获取当前的代理 URL 字符串"""
        return self._proxy_url_from_config(settings.config.network.proxy)

    def get_proxy_env(self) -> dict:
        """获取用于 subprocess 的代理环境变量字典。"""
        proxy_url = self.get_proxy_url()
        if not proxy_url: return {}
        env = {
            "HTTP_PROXY": proxy_url,
            "HTTPS_PROXY": proxy_url,
            "ALL_PROXY": proxy_url, # SteamCMD 有时也看这个
        }
        env.update({key.lower(): value for key, value in list(env.items())})
        # 注入绕过列表
        bypass = [str(item).strip() for item in (settings.config.network.proxy.bypass_list or []) if str(item).strip()]
        env["NO_PROXY"] = env["no_proxy"] = ",".join(bypass)
        return env

    # ====================== Hosts 配置 =======================
    def _build_network_check_targets(self, settings_override: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, str]]:
        """根据当前或表单配置生成检测目标；不发起网络请求。"""
        override = settings_override if isinstance(settings_override, dict) else None
        raw_network_override = override.get("network") if isinstance(override, dict) else None
        # 预览只读取表单快照；补齐脱敏密钥时不能回写调用方对象。
        network_override = dict(raw_network_override) if isinstance(raw_network_override, dict) else None
        proxy_override = network_override.get("proxy") if network_override else None
        if isinstance(proxy_override, dict):
            proxy_override = dict(proxy_override)
            network_override["proxy"] = proxy_override
        else:
            proxy_override = None
        if proxy_override is not None:
            preserved_secrets = set(override.get("_preserve_secret_keys") or []) if override else set()
            for field, secret_key in (("username", "network.proxy.username"), ("password", "network.proxy.password")):
                if secret_key in preserved_secrets and not str(proxy_override.get(field) or "").strip():
                    proxy_override[field] = settings.reveal_secret(secret_key)
        targets = [
            {"id": target_id, "label": label, "url": url}
            for target_id, label, url in NETWORK_CHECK_TARGETS
        ]
        # 复用发布元数据读取，按当前配置补充来源；延迟导入避免下载管理器的循环依赖。
        from backend.managers.mgr_update import _load_project_meta
        from backend.managers.mgr_github import GithubManager

        configured_targets = [
            # 工坊数据库由“外部库”页面单独维护，不自动混入常用站点连通性检测。
            ("community_instead_db", "替代模组数据库", settings.config.community_instead_db_url),
            ("community_rules", "社区排序规则", settings.config.community_rules_url),
            ("multiplayer", "联机兼容数据库", settings.config.multiplayer_compatibility_url),
            ("mp_compat", "联机兼容模组清单", settings.config.mp_compat_package_ids_url),
        ]
        for index, entry in enumerate(GithubManager._split_catalog_config_rows(settings.config.git_provider_catalog_url)):
            _, url = GithubManager._split_catalog_label_value(entry, default_label="")
            configured_targets.append((f"git_catalog_{index}", "Git 模组目录", url))
        network = network_override if network_override is not None else vars(settings.config.network)
        if network.get("github_hosts_enabled"):
            configured_targets.extend(
                (f"hosts_source_{index}", "Hosts 来源", url)
                for index, url in enumerate(self.split_hosts_sources(network.get("hosts_sources")))
            )
        for index, source in enumerate((_load_project_meta().get("update") or {}).get("sources") or []):
            if isinstance(source, dict) and source.get("type") in {"manifest", "update_manifest"}:
                configured_targets.append((f"update_manifest_{index}", "备用更新清单", source.get("url")))
        targets.extend(
            {"id": target_id, "label": label, "url": str(value or "").strip()}
            for target_id, label, value in configured_targets
        )

        # 先校验并按原始地址去重，确保配置来源不会因为后续镜像替换而重新占据同一站点。
        unique_targets = []
        known_origins = set()
        for target in targets:
            try:
                parsed = urlsplit(target["url"])
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                    continue
                origin = (
                    parsed.scheme.lower(),
                    parsed.hostname.lower().rstrip("."),
                    parsed.port or (443 if parsed.scheme.lower() == "https" else 80),
                )
            except ValueError:
                continue
            if origin not in known_origins:
                unique_targets.append(target)
                known_origins.add(origin)
        targets = unique_targets

        selected_mirror = str(
            (override or {}).get("github_mirror_id", getattr(settings.config, "github_mirror_id", "direct")) or "direct"
        ).strip().lower()
        dynamic_enabled = bool((override or {}).get(
            "github_dynamic_mirrors_enabled", getattr(settings.config, "github_dynamic_mirrors_enabled", False)
        ))
        mirrors = (override or {}).get("github_mirrors", getattr(settings.config, "github_mirrors", []))
        from backend.managers.mgr_github import GithubManager
        mirrored_targets = []
        capability_by_target = {
            "github": "web", "github_raw": "raw", "github_archive": "archive", "github_api": "api",
        }
        for target in targets:
            capability = capability_by_target.get(target["id"])
            nodes = GithubManager.get_effective_mirrors(
                selected_mirror,
                capability or "",
                mirrors if isinstance(mirrors, list) else None,
                dynamic_enabled,
            ) if capability else []
            node = nodes[0] if nodes else None
            if not node:
                mirrored_targets.append(target)
                continue
            mirror_url = GithubManager._render_mirror_url(node.get("url_template", ""), target["url"], node.get("url_mode", "full_url"))
            parsed = urlsplit(mirror_url)
            if parsed.scheme.lower() != "https" or not parsed.netloc or mirror_url == target["url"]:
                mirrored_targets.append(target)
                continue
            label = str(node.get("label") or node.get("id") or "镜像节点").strip()
            mirrored_targets.append({
                **target, "url": mirror_url, "source_url": target["url"],
                "mirror_id": selected_mirror, "mirror_label": label,
                "label": f"{target['label']}（{label}）",
            })
        targets = mirrored_targets

        preview_hosts = self._preview_hosts(network) if network_override is not None else self._effective_hosts()
        return targets, network_override, preview_hosts

    def _probe_network_target(self, target: dict[str, Any], network_override: dict[str, Any] | None, preview_hosts: dict[str, str]) -> dict[str, Any]:
        """检测单个目标，供同步兼容接口和前端渐进式检测共用。"""
        started = time.perf_counter()
        response = None
        session = build_retry_session(
            total=1,
            connect=1,
            read=1,
            redirect=3,
            route_manager=self,
            network_override=network_override,
        )
        hostname = self._normalize_host(urlsplit(target["url"]).hostname)
        probe_id = str(target.get("mirror_of") or target.get("id") or "")
        try:
            is_file_probe = probe_id in {"github_archive", "github_raw"}
            with self.hosts_override(preview_hosts):
                route = self.request_route(target["url"], network_override=network_override)
                response = session.get(
                    target["url"],
                    stream=True,
                    allow_redirects=True,
                    timeout=(5, 12),
                    headers={
                        "User-Agent": "RimCrow/NetworkCheck" if probe_id == "sourceforge" else DEFAULT_USER_AGENT,
                        "Accept": "*/*",
                        **({"Range": "bytes=0-0", "Accept-Encoding": "identity"} if is_file_probe else {}),
                    },
                )
            status_code = int(response.status_code)
            final_url = response.url if isinstance(response.url, str) else target["url"]
            _, error_code, _, error_message = _classify_http_status(status_code)
            range_supported = False
            invalid_range = False
            if is_file_probe and status_code == 206:
                headers = response.headers
                content_range = re.fullmatch(r"bytes 0-0/([1-9]\d*)", str(headers.get("Content-Range") or "").strip())
                invalid_range = not content_range or str(headers.get("Content-Encoding") or "identity").lower() != "identity"
                length = headers.get("Content-Length")
                invalid_range = invalid_range or (length is not None and str(length).strip() != "1")
                if not invalid_range:
                    chunks = response.iter_content(chunk_size=2)
                    first = next(chunks, b"")
                    invalid_range = len(first) != 1 or bool(next(chunks, b""))
                range_supported = not invalid_range
                if invalid_range:
                    classified = classify_exception(InvalidResponseError("文件片段未通过范围或长度校验"), module="network", action="access_check")
                    error_code, error_message = classified.error_code, classified.user_message
            return {
                **target,
                "domain": (urlsplit(final_url).hostname or hostname).lower(),
                "final_url": final_url,
                "status": "failed" if invalid_range else ("ok" if 200 <= status_code < 300 else "http_error"),
                **({"range_supported": range_supported} if is_file_probe else {}),
                "reachable": True,
                "http_status": status_code,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error_code": error_code,
                "error": error_message or (f"HTTP {status_code}" if status_code >= 400 else ""),
                "route": route["route"],
                "proxy_bypassed": route["proxy_bypassed"],
                "hosts_hit": route["hosts_hit"],
            }
        except requests.RequestException as exc:
            classified = classify_exception(exc, module="network", action="access_check")
            route = self.request_route(target["url"], network_override=network_override)
            return {
                **target,
                "domain": (urlsplit(target["url"]).hostname or "").lower(),
                "status": "timeout" if classified.error_code == "NETWORK.TIMEOUT" else "failed",
                "reachable": False,
                "http_status": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error_code": classified.error_code,
                "error": classified.user_message or f"无法连接到目标服务：{type(exc).__name__}",
                "route": route["route"],
                "proxy_bypassed": route["proxy_bypassed"],
                "hosts_hit": route["hosts_hit"],
            }
        finally:
            if response is not None:
                response.close()
            session.close()

    def check_network_access(self, settings_override: dict[str, Any] | None = None, *, target_ids: list[str] | None = None, plan_only: bool = False) -> dict[str, Any]:
        """检测常用网络服务；可只返回目标计划或只检测指定目标。"""
        targets, network_override, preview_hosts = self._build_network_check_targets(settings_override)
        if target_ids is not None:
            wanted = {str(item).strip() for item in target_ids if str(item).strip()}
            targets = [target for target in targets if str(target.get("id")) in wanted]
        if plan_only:
            return {
                "targets": [
                    {**target, "domain": (urlsplit(target["url"]).hostname or "").lower(), "status": "loading", "http_status": None, "latency_ms": None}
                    for target in targets
                ]
            }
        if not targets:
            return {"targets": []}

        stop = getattr(self, "_github_hosts_stop", threading.Event())
        results = _map_network_tasks(lambda target: self._probe_network_target(target, network_override, preview_hosts), targets, stop)
        return {"targets": [result for result in results if result is not None]}

    @staticmethod
    def parse_github_hosts(text: str) -> dict[str, str]:
        """读取完整 Hosts 文本或 JSON（[IP, 域名] 列表、域名到 IP 的映射），过滤无效条目。"""
        content = str(text or "").lstrip("\ufeff").strip()
        if content.startswith(("[", "{")):
            try:
                payload = json.loads(content)
            except ValueError:
                return {}
            if isinstance(payload, dict):
                rows = [(ip, host) for host, ip in payload.items()]
            elif isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, list)]
            else:
                return {}
        else:
            rows = [line.split("#", 1)[0].split() for line in content.splitlines()]
        result: dict[str, str] = {}
        for fields in rows:
            if len(fields) < 2:
                continue
            try:
                address = str(ipaddress.ip_address(str(fields[0])))
                if "%" in address:
                    continue
            except (ValueError, TypeError):
                continue
            for host in fields[1:]:
                if not isinstance(host, str):
                    continue
                normalized_host = host.strip().lower().rstrip(".")
                if len(normalized_host) <= 253 and re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", normalized_host):
                    result[normalized_host] = address
        return result

    def _load_github_hosts_cache(self, source_url: str) -> None:
        """重启后复用同一来源的有效缓存，更新时间与映射一起保存。"""
        try:
            payload = json.loads(GITHUB_HOSTS_CACHE_PATH.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("source_url") != source_url:
                return
            hosts = payload.get("hosts")
            if not isinstance(hosts, dict):
                raise ValueError("Hosts 缓存映射格式无效")
            parsed = self.parse_github_hosts("\n".join(f"{ip} {host}" for host, ip in hosts.items()))
            updated_at = float(payload.get("updated_at", 0))
            if not parsed or not math.isfinite(updated_at) or not 0 < updated_at <= time.time():
                raise ValueError("Hosts 缓存内容或更新时间无效")
            self._github_hosts_state = {
                "status": "ready", "source_url": source_url, "hosts": parsed, "error": "", "updated_at": updated_at,
            }
        except FileNotFoundError:
            return
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("动态 Hosts 缓存读取失败，启动时将重新获取: %s", exc)

    @staticmethod
    def split_hosts_sources(value: list[dict[str, Any]] | str | None) -> list[str]:
        """从列表选出启用来源；缓存签名使用逐行文本，按顺序去重。"""
        rows = (row.get("url", "") for row in value if isinstance(row, dict) and row.get("enabled", True) is True) if isinstance(value, list) else str(value or "").splitlines()
        return list(dict.fromkeys(str(url).strip() for url in rows if str(url).strip()))

    def _save_github_hosts_cache(self) -> None:
        """后台持久化正式映射；保存表单不等待缓存磁盘操作。"""
        with self._github_hosts_lock:
            if self._github_hosts_stop.is_set():
                return
            self._hosts_cache_pending = True
            if self._hosts_cache_thread is None:
                self._hosts_cache_thread = threading.Thread(target=self._persist_hosts_cache, name="hosts-cache", daemon=True)
                self._hosts_cache_thread.start()

    def _persist_hosts_cache(self) -> None:
        while True:
            with self._github_hosts_lock:
                if self._github_hosts_stop.is_set() or not self._hosts_cache_pending:
                    self._hosts_cache_thread = None
                    return
                self._hosts_cache_pending = False
                payload = {"source_url": self._dynamic_github_hosts_source, "hosts": dict(self._dynamic_github_hosts),
                           "updated_at": self._github_hosts_state["updated_at"]}
            try:
                write_json_atomic(GITHUB_HOSTS_CACHE_PATH, payload)
            except OSError as exc:
                if not self._github_hosts_stop.is_set():
                    logger.warning("动态 Hosts 已应用，但缓存保存失败: %s", exc)

    def refresh_github_hosts(self, network_override: dict[str, Any] | None = None) -> dict[str, Any]:
        """后台获取已保存来源或表单预览来源，预览任务与运行态完全隔离。"""
        # 后台线程必须使用不可变快照，避免表单对象后续变动影响本次预览。
        if isinstance(network_override, dict):
            network_override = copy.deepcopy(network_override)
            proxy_override = network_override.get("proxy")
            if isinstance(proxy_override, dict):
                preserved_secrets = set(network_override.get("_preserve_secret_keys") or [])
                for field, secret_key in (("username", "network.proxy.username"), ("password", "network.proxy.password")):
                    if secret_key in preserved_secrets and not str(proxy_override.get(field) or "").strip():
                        proxy_override[field] = settings.reveal_secret(secret_key)
        with self._github_hosts_lock:
            cfg = settings.config.network
            is_preview = isinstance(network_override, dict)
            request_id_attr = "_github_hosts_preview_request_id" if is_preview else "_github_hosts_request_id"
            state_attr = "_github_hosts_preview_state" if is_preview else "_github_hosts_state"
            thread_attr = "_github_hosts_preview_thread" if is_preview else "_github_hosts_thread"
            state = getattr(self, state_attr)
            enabled = bool(network_override.get("github_hosts_enabled")) if is_preview else cfg.github_hosts_enabled
            if not enabled or self._github_hosts_stop.is_set():
                if is_preview:
                    setattr(self, request_id_attr, getattr(self, request_id_attr) + 1)
                    setattr(self, state_attr, {**state, "status": "idle", "source_url": "", "hosts": {}, "error": "", "source_errors": []})
                return self.get_github_hosts_status()
            value = network_override.get("hosts_sources") if is_preview else cfg.hosts_sources
            source_url = "\n".join(self.split_hosts_sources(value))
            if not source_url:
                setattr(self, request_id_attr, getattr(self, request_id_attr) + 1)
                setattr(self, state_attr, {**state, "status": "idle", "source_url": "", "hosts": {}, "error": "", "source_errors": []})
                return self.get_github_hosts_status()
            if not is_preview and state["source_url"] == source_url and state["status"] == "loading":
                return self.get_github_hosts_status()
            request_id = getattr(self, request_id_attr) + 1
            setattr(self, request_id_attr, request_id)
            setattr(self, state_attr, {
                "status": "loading", "source_url": source_url,
                "hosts": {}, "error": "", "source_errors": [], "updated_at": 0,
            })
            thread = threading.Thread(
                target=self._fetch_github_hosts, args=(request_id, source_url, is_preview,
                    network_override if is_preview else {**asdict(cfg), "effective_hosts": self.get_effective_hosts()}),
                name="dynamic-hosts-preview" if is_preview else "dynamic-hosts", daemon=True,
            )
            setattr(self, thread_attr, thread)
            thread.start()
            return self.get_github_hosts_status()

    def _fetch_github_hosts(self, request_id: int, source_url: str, is_preview: bool = False, network_override: dict[str, Any] | None = None) -> None:
        request_id_attr = "_github_hosts_preview_request_id" if is_preview else "_github_hosts_request_id"
        state_attr = "_github_hosts_preview_state" if is_preview else "_github_hosts_state"

        def fetch(source: str) -> tuple[dict[str, str], str]:
            response = None
            try:
                if self._github_hosts_stop.is_set() or request_id != getattr(self, request_id_attr):
                    return {}, "cancelled"
                url = urlsplit(source)
                if url.scheme.lower() != "https" or not url.hostname or url.username or url.password:
                    raise ValueError("动态 Hosts 来源必须是有效的 HTTPS 地址")
                # 独立会话使用表单快照，关闭应用代理时仍继承外部环境代理。
                with build_retry_session(
                    total=1,
                    connect=1,
                    read=1,
                    redirect=3,
                    route_manager=self,
                    network_override=network_override,
                ) as session:
                    response = session.get(
                        source,
                        timeout=(15, 60),
                        headers={"Accept": "text/plain, application/json", "User-Agent": DEFAULT_USER_AGENT},
                    )
                    response.raise_for_status()
                    hosts = self.parse_github_hosts(response.text)
                if not hosts:
                    raise ValueError("动态 Hosts 来源没有包含有效映射")
                return hosts, ""
            except Exception as exc:
                if not self._github_hosts_stop.is_set() and request_id == getattr(self, request_id_attr):
                    logger.warning("动态 Hosts 来源获取失败: source=%s, error=%s", source, exc)
                return {}, "timeout" if isinstance(exc, requests.Timeout) else "failed"
            finally:
                if response is not None:
                    response.close()

        try:
            sources = self.split_hosts_sources(source_url)
            parsed: dict[str, str] = {}
            errors = []
            results = _map_network_tasks(fetch, sources, self._github_hosts_stop)
            if self._github_hosts_stop.is_set():
                return
            # 并行获取但按来源顺序合并，同域名优先使用排在前面的有效来源。
            for source, (hosts, error) in zip(sources, results):
                if error:
                    errors.append({"url": source, "error": error})
                for host, address in hosts.items():
                    parsed.setdefault(host, address)
            with self._github_hosts_lock:
                # 来源切换或退出后，旧请求不得覆盖新任务或写入系统文件。
                if request_id != getattr(self, request_id_attr) or self._github_hosts_stop.is_set():
                    return
                state = getattr(self, state_attr)
                cfg = settings.config.network
                saved_source = "\n".join(self.split_hosts_sources(cfg.hosts_sources))
                can_apply = not is_preview and cfg.github_hosts_enabled and saved_source == source_url
                if not is_preview and not can_apply:
                    setattr(self, state_attr, {**state, "status": "idle"})
                    return
                if not parsed:
                    error = "timeout" if errors and all(item["error"] == "timeout" for item in errors) else "failed"
                    setattr(self, state_attr, {**state, "status": "error", "error": error, "source_errors": errors})
                    return
                ready_state = {**state, "status": "ready", "hosts": parsed, "error": "", "source_errors": errors, "updated_at": time.time()}
                setattr(self, state_attr, ready_state)
                if can_apply:
                    self._dynamic_github_hosts = dict(parsed)
                    self._dynamic_github_hosts_source = source_url
                    cfg.github_hosts_updated_at = ready_state["updated_at"]
                    self._apply_hosts()
            if can_apply:
                self._save_github_hosts_cache()
        except Exception as exc:
            error = "timeout" if isinstance(exc, requests.Timeout) else "failed"
            with self._github_hosts_lock:
                if request_id == getattr(self, request_id_attr) and not self._github_hosts_stop.is_set():
                    state = getattr(self, state_attr)
                    setattr(self, state_attr, {**state, "status": "error", "error": error})
                    logger.warning("动态 Hosts 后台获取失败，保留已有映射: %s", exc)

    def get_github_hosts_status(self) -> dict[str, Any]:
        """返回后台任务状态和映射副本，不发起网络请求。"""
        with self._github_hosts_lock:
            state = {**self._github_hosts_state, "hosts": dict(self._github_hosts_state["hosts"])}
            preview = {**self._github_hosts_preview_state, "hosts": dict(self._github_hosts_preview_state["hosts"])}
            state["preview"] = preview
            cfg = settings.config.network
            state["can_refresh"] = bool(cfg.github_hosts_enabled or state["source_url"])
            state["is_applied"] = bool(cfg.github_hosts_enabled and state["status"] == "ready"
                and state["source_url"] == "\n".join(self.split_hosts_sources(cfg.hosts_sources))
                and state["source_url"] == self._dynamic_github_hosts_source)
            state["effective_hosts"] = self.get_effective_hosts()
            manual_hosts = {
                str(host).strip().lower().rstrip(".") for host, address in (cfg.hosts or {}).items()
                if str(host).strip() and str(address).strip()
            }
            state["dynamic_hosts"] = {
                host: address for host, address in self._dynamic_github_hosts.items()
                if cfg.github_hosts_enabled and host not in manual_hosts
            }
            state["cache_path"] = str(GITHUB_HOSTS_CACHE_PATH)
            state["system_hosts"] = self._system_hosts.status()
            message = self._system_hosts_message(state["system_hosts"])
            state["system_hosts"].update(message=str(message), message_key=getattr(message, "message_key", ""))
            return state

    def close(self) -> None:
        """显式关闭应用网络；不用于环境切换或数据库重建。"""
        started_at = time.perf_counter()
        is_first_close = not self._github_hosts_stop.is_set()
        if is_first_close:
            logger.debug("[NetworkShutdown] stage=started")
        self._github_hosts_stop.set()
        with self._github_hosts_lock:
            self._github_hosts_request_id += 1
            self._github_hosts_preview_request_id += 1
            self.restore_socket_for_hosts()
        self._system_hosts.close()
        if is_first_close:
            system_state = self._system_hosts.status()
            log = logger.warning if system_state["status"] in {"error", "applying", "authorizing"} else logger.debug
            log("[NetworkShutdown] stage=finished elapsed_ms=%.2f system_hosts=%s",
                (time.perf_counter() - started_at) * 1000, system_state)

    def _effective_hosts(self) -> dict[str, str]:
        dynamic_hosts = getattr(self, "_dynamic_github_hosts", {}) if getattr(settings.config.network, "github_hosts_enabled", False) else {}
        manual_hosts = {
            str(host).strip().lower().rstrip("."): str(ip).strip()
            for host, ip in (settings.config.network.hosts or {}).items()
            if str(host).strip() and str(ip).strip()
        }
        return {**dynamic_hosts, **manual_hosts}

    def get_effective_hosts(self) -> dict[str, str]:
        """返回当前进程实际使用的 Hosts 映射，供设置页只读展示。"""
        return dict(self._effective_hosts())

    def patch_socket_for_hosts(self):
        """Python 运行时 Socket 劫持（动态读取最新配置，无死循环风险）"""
        if self._is_socket_patched: return  # 已经劫持过了，不需要重新包一层

        def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            # 【关键修改】：每次发请求时，实时去 settings 里面拿最新的 hosts 配置
            override_hosts = _HOSTS_OVERRIDE.get()
            current_hosts_map = override_hosts if override_hosts is not None else self._effective_hosts()
            lookup_host = str(host or "").strip().lower().rstrip(".")
            if current_hosts_map and lookup_host in current_hosts_map:
                target_ip = current_hosts_map[lookup_host]
                return self._original_getaddrinfo(target_ip, port, family, type, proto, flags)
            
            return self._original_getaddrinfo(host, port, family, type, proto, flags)

        socket.getaddrinfo = new_getaddrinfo
        self._patched_getaddrinfo = new_getaddrinfo
        self._is_socket_patched = True

    def restore_socket_for_hosts(self) -> None:
        """仅恢复由本实例安装的 patch，避免覆盖其它库后续的合法替换。"""
        if self._is_socket_patched and socket.getaddrinfo is self._patched_getaddrinfo:
            socket.getaddrinfo = self._original_getaddrinfo
        self._patched_getaddrinfo = None
        self._is_socket_patched = False



class RoutedSession(requests.Session):
    """带 URL 级网络路由的 requests 会话。

    每次请求前重新计算代理、绕过列表和 Hosts 命中，避免同一个会话在切换
    候选地址时沿用上一次请求的代理状态。显式传入的 session 仍可通过
    ``prepare_session_for_url`` 使用临时网络配置。
    """

    def __init__(self, route_manager: Any = None, network_override: dict[str, Any] | None = None):
        super().__init__()
        self._route_manager = route_manager
        self._network_override = network_override
        self._last_route: dict[str, Any] | None = None

    def request(self, method: str, url: str, **kwargs: Any):
        route_manager = globals().get("network_mgr") if self._route_manager is None else self._route_manager
        if route_manager is not None and route_manager is not False:
            self._last_route = route_manager.prepare_session_for_url(self, url, network_override=self._network_override)
            if self._network_override is not None:
                with route_manager.hosts_override(route_manager._preview_hosts(self._network_override)):
                    return super().request(method, url, **kwargs)
        return super().request(method, url, **kwargs)

    def rebuild_proxies(self, prepared_request, proxies):
        """重定向到新域名时重新计算路由，避免沿用初始地址的代理决定。"""
        route_manager = globals().get("network_mgr") if self._route_manager is None else self._route_manager
        if route_manager is not None and route_manager is not False:
            self._last_route = route_manager.prepare_session_for_url(
                self,
                prepared_request.url,
                network_override=self._network_override,
            )
            # 使用新目标的代理并重建认证头，不能携带上一跳的代理或 Proxy-Authorization。
            return super().rebuild_proxies(prepared_request, dict(self.proxies))
        return super().rebuild_proxies(prepared_request, proxies)


def build_retry_session(*, total: int = 3, connect: int = 3, read: int = 3, redirect: int = 5, 
    backoff_factor: float = 1.0, status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504), 
    allowed_methods: tuple[str, ...] = ("GET", "HEAD"), pool_connections: int = 8, pool_maxsize: int = 8,
    route_manager: Any = None, network_override: dict[str, Any] | None = None,
    trust_env: bool | None = None) -> requests.Session:
    
    session = RoutedSession(route_manager, network_override)
    # 未指定时由 NetworkManager 按 URL 决定；直连专用会话可显式关闭环境代理。
    session.trust_env = True if trust_env is None else bool(trust_env)
    retry = Retry(
        total=total,
        connect=connect,
        read=read,
        redirect=redirect,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(allowed_methods),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=pool_connections, pool_maxsize=pool_maxsize)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def remaining_request_timeout(deadline: float | None, cancel_event: threading.Event | None = None) -> tuple[float, float]:
    """外部数据请求扣同一预算；不把连接/读空闲超时冒充硬取消。"""
    # shortcut: Requests 阻塞 I/O 可能超出预算，可取消传输经验证后再升级为硬截止。
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("Task cancelled by user")
    remaining = deadline - time.monotonic() if deadline is not None else 20.0
    if remaining <= 0:
        raise TimeoutError("外部数据检查已超时")
    return min(5.0, remaining), min(10.0, remaining)


def merge_headers(headers: dict[str, str] | None = None, *, user_agent: str = DEFAULT_USER_AGENT) -> dict[str, str]:
    merged = {"User-Agent": user_agent}
    if headers: merged.update(headers)
    return merged


# 实例化单例
network_mgr = NetworkManager()
