# backend/managers/mgr_steam_api.py
import re
import time
from pathlib import Path
from typing import Any

import requests

# --- 模块测试准备 ---
if __name__ == "__main__":
    import sys
    # Path(__file__).resolve() 获取当前文件的绝对路径
    # .parents[2] 表示向上跳 3 级 (文件->scanner->backend->项目根目录)
    project_root = Path(__file__).resolve().parents[2]
    # 调试打印，确保路径正确
    print(f"Project Root: {project_root}")
    # sys.path 需要字符串类型，所以要用 str() 转换一下
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from backend.database.workshop_selection import normalize_cached_workshop_id
from backend.database.dao_ext import ExtDAO
from backend.database.models_ext import WorkshopOnlineCache, ext_db, init_ext_db
from backend.managers.mgr_network import build_retry_session, merge_headers, network_mgr
from backend.settings import settings
from backend.utils.constants import to_steam_webapi_language_code
from backend.utils.logger import logger


class SteamWebAPI:
    """统一封装 Steam Workshop 详情查询、合集解析和在线搜索。"""

    BASE_URL = "https://api.steampowered.com"
    PUBLISHED_FILE_DETAILS_URL = f"{BASE_URL}/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    COLLECTION_DETAILS_URL = f"{BASE_URL}/ISteamRemoteStorage/GetCollectionDetails/v1/"
    QUERY_FILES_URL = f"{BASE_URL}/IPublishedFileService/QueryFiles/v1/"
    WORKSHOP_ITEM_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
    RIMWORLD_APP_ID = 294100
    CACHE_TTL_MS = 1 * 24 * 60 * 60 * 1000

    @classmethod
    def _normalize_workshop_ids(cls, workshop_ids: list) -> list[str]:
        """规范化并保序去重请求 ID，避免重复请求同一条 Steam 详情。"""
        normalized_ids: list[str] = []
        seen_ids: set[str] = set()
        for workshop_id in workshop_ids:
            normalized_id = normalize_cached_workshop_id(workshop_id)
            if not normalized_id or normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            normalized_ids.append(normalized_id)
        return normalized_ids

    @classmethod
    def _build_request_kwargs(cls, *, headers: dict[str, str] | None = None, timeout: tuple[int, int] = (10, 20)) -> dict[str, Any]:
        """
        统一整理 Steam 请求参数。

        这里显式传入代理，而不是完全依赖 requests 的环境变量探测，
        这样在运行时修改代理配置后，后续请求可以立即使用新配置。
        """
        request_kwargs: dict[str, Any] = {
            "headers": merge_headers(headers),
            "timeout": timeout,
        }
        proxy_url = network_mgr.get_proxy_url()
        if proxy_url:
            request_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
        return request_kwargs

    @classmethod
    def _request_json(
        cls,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: tuple[int, int] = (10, 20),
    ) -> dict[str, Any]:
        """通过统一的重试、代理和报错转换逻辑请求 Steam JSON 接口。"""
        with build_retry_session(allowed_methods=("GET", "HEAD", "POST")) as session:
            response = session.request(method, url, params=params, data=data, **cls._build_request_kwargs(headers=headers, timeout=timeout))
            cls._raise_for_steam_status(response, url)
            payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Steam 接口返回了无法识别的 JSON 结构: {url}")
        return payload

    @classmethod
    def _request_text( cls, method: str, url: str, *, params: dict[str, Any] | None = None, data: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: tuple[int, int] = (10, 20)) -> str:
        """供网页抓取回退方案复用的统一文本请求。"""
        with build_retry_session(allowed_methods=("GET", "HEAD", "POST")) as session:
            response = session.request(method, url, params=params, data=data, **cls._build_request_kwargs(headers=headers, timeout=timeout))
            cls._raise_for_steam_status(response, url)
            return response.text

    @classmethod
    def _raise_for_steam_status(cls, response: requests.Response, request_label: str) -> None:
        """把 Steam HTTP 错误转换成更贴近调用场景的异常文本。"""
        if response.status_code < 400: return
        if response.status_code == 403:
            raise RuntimeError("Steam Web API Key 无效、权限不足，或当前网络/IP 未被 Steam 接受")
        if response.status_code == 429:
            raise RuntimeError("Steam Web API 请求过于频繁，请稍后重试")
        raise RuntimeError(f"Steam 接口请求失败({response.status_code}): {request_label}")

    @classmethod
    def _safe_int(cls, value: Any, default: int = 0) -> int:
        """Steam 的字段可能混有空串或 None，这里统一做整型兜底。"""
        try: return int(value)
        except (TypeError, ValueError): return default

    @classmethod
    def _safe_float(cls, value: Any, default: float = 0.0) -> float:
        """评分等字段统一按浮点数解析，避免前端拿到字符串。"""
        try: return float(value)
        except (TypeError, ValueError): return default

    @classmethod
    def _clean_online_text(cls, value: Any) -> str:
        """
        清理在线搜索摘要中的异常空白与图片链接残片。

        这里处理的是列表摘要，目标是给搜索结果和详情摘要区稳定展示的纯文本，
        而不是保留 Steam 页面原始富文本。
        """
        text = str(value or "").strip()
        if not text: return ""
        text = re.sub(r"https:\s+//", "https://", text)
        text = re.sub(r"http:\s+//", "http://", text)
        text = re.sub(r"(https?://\S+\.(?:png|jpg|jpeg|gif|webp))", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def _extract_game_versions_from_tags(cls, tags: list[str]) -> list[str]:
        """从 Steam 标签中提取版本号，供缺失 manifest 时作为展示回退。"""
        versions: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            normalized = str(tag or "").strip()
            if not re.fullmatch(r"\d+(?:\.\d+)+", normalized):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            versions.append(normalized)
        return versions

    @classmethod
    def _get_steam_web_api_key(cls) -> str:
        """从配置中读取用户填写的 Steam Web API Key。"""
        return str(getattr(settings.config, "steam_web_api_key", "") or "").strip()

    @classmethod
    def _resolve_steam_language(cls, language: str | None = None) -> str:
        """把应用内语言配置映射成 Steam Web API 可识别的语言码。"""
        return to_steam_webapi_language_code(language or settings.config.language, default="en")

    @classmethod
    def _resolve_online_search_sort(cls, sort: str, *, has_query: bool) -> tuple[str, int]:
        """
        将前端友好的排序名映射成 Steam 的 query_type。

        文本搜索为空时改走“最近更新”，避免空关键字仍然执行文本相关度排序。
        """
        normalized_sort = str(sort or "").strip().lower()
        if not normalized_sort or normalized_sort == "default":
            normalized_sort = "relevance" if has_query else "latest"

        query_type_map = {
            "relevance": 12,
            "latest": 21,
            "updated": 21,
            "subscriptions": 9,
            "popular": 9,
            "votes": 11,
            "trend": 3,
        }
        if normalized_sort == "relevance" and not has_query:
            return "latest", query_type_map["latest"]
        return normalized_sort, query_type_map.get(normalized_sort, 12 if has_query else 21)

    @classmethod
    def _normalize_online_page_size(cls, page_size: int) -> int:
        """限制单次在线搜索返回量，避免 UI 一次拉取过多数据。"""
        return max(1, min(cls._safe_int(page_size, default=25), 100))

    @classmethod
    def _build_workshop_url(cls, workshop_id: str) -> str:
        """统一生成 Steam 社区详情页地址，避免不同调用方重复拼接。"""
        return cls.WORKSHOP_ITEM_URL.format(workshop_id=workshop_id)

    @classmethod
    def _extract_preview_url(cls, item: dict[str, Any]) -> str:
        """优先使用主预览图，没有时再退回 previews 里的首张图片。"""
        preview_url = str(item.get("preview_url") or "").strip()
        if preview_url: return preview_url
        previews = item.get("previews") or []
        for preview in previews:
            if cls._safe_int(preview.get("preview_type")) != 0:
                continue
            preview_url = str(preview.get("url") or "").strip()
            if preview_url: return preview_url
        return ""

    @classmethod
    def _normalize_query_file_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        """把 QueryFiles 返回的原始字段整理成前端更稳定的结构。"""
        workshop_id = str(item.get("publishedfileid") or "").strip()
        title = cls._clean_online_text(item.get("title"))
        previews = item.get("previews") or []
        screenshots = [
            str(preview.get("url") or "").strip()
            for preview in previews
            if cls._safe_int(preview.get("preview_type")) == 0 and str(preview.get("url") or "").strip()
        ]
        children = [
            {
                "workshop_id": str(child.get("publishedfileid") or "").strip(),
                "file_type": cls._safe_int(child.get("filetype")),
                "sort_order": cls._safe_int(child.get("sortorder")),
            }
            for child in (item.get("children") or [])
            if str(child.get("publishedfileid") or "").strip()
        ]
        tags = [
            str(tag.get("tag") or "").strip()
            for tag in (item.get("tags") or [])
            if str(tag.get("tag") or "").strip()
        ]
        short_description = cls._clean_online_text(item.get("short_description") or item.get("file_description"))
        time_created = cls._safe_int(item.get("time_created")) * 1000
        time_updated = cls._safe_int(item.get("time_updated")) * 1000
        return {
            "workshop_id": workshop_id,
            "name": title,
            "title": title,
            "preview_url": cls._extract_preview_url(item),
            "short_description": short_description,
            "author_steam_id": str(item.get("creator") or "").strip(),
            "time_created": time_created,
            "time_updated": time_updated,
            "subscriptions": cls._safe_int(item.get("subscriptions")),
            "favorited": cls._safe_int(item.get("favorited")),
            "lifetime_subscriptions": cls._safe_int(item.get("lifetime_subscriptions")),
            "lifetime_favorited": cls._safe_int(item.get("lifetime_favorited")),
            "views": cls._safe_int(item.get("views")),
            "score": cls._safe_float(item.get("score")),
            "file_type": cls._safe_int(item.get("file_type")),
            "consumer_app_id": cls._safe_int(item.get("consumer_app_id")),
            "creator_app_id": cls._safe_int(item.get("creator_app_id")),
            "children": children,
            "tags": tags,
            "screenshots": screenshots,
            "url": cls._build_workshop_url(workshop_id),
            "source": "steam_online",
        }

    @classmethod
    def _build_online_summary_upsert_row(cls, item: dict[str, Any], sync_time: int) -> dict[str, Any]:
        """把在线搜索结果整理成摘要缓存结构。"""
        return {
            "workshop_id": str(item.get("workshop_id") or "").strip(),
            "title": item.get("title") or item.get("name") or "",
            "short_description": item.get("short_description") or "",
            "author_steam_id": item.get("author_steam_id") or "",
            "preview_url": item.get("preview_url") or None,
            "tags": list(item.get("tags") or []),
            "children": list(item.get("children") or []),
            "screenshots": item.get("screenshots") or [],
            "time_created": cls._safe_int(item.get("time_created")),
            "time_updated": cls._safe_int(item.get("time_updated")),
            "subscriptions": cls._safe_int(item.get("subscriptions")),
            "favorited": cls._safe_int(item.get("favorited")),
            "lifetime_subscriptions": cls._safe_int(item.get("lifetime_subscriptions")),
            "lifetime_favorited": cls._safe_int(item.get("lifetime_favorited")),
            "views": cls._safe_int(item.get("views")),
            "summary_last_sync_time": sync_time,
            "last_sync_time": sync_time,
        }

    @classmethod
    def _load_cached_online_details(cls, workshop_ids: list[str], cache_ttl_ms: int) -> tuple[dict[str, dict], list[str]]:
        """
        从在线缓存表读取仍在有效期内的数据。

        返回值拆成两部分：
        - results: 可直接返回给调用方的缓存命中结果；
        - ids_to_fetch: 需要继续请求 Steam API 的缺失或过期 ID。
        """
        current_time = int(time.time() * 1000)
        results: dict[str, dict] = {}
        cached_items = WorkshopOnlineCache.select().where(WorkshopOnlineCache.workshop_id.in_(workshop_ids))  # type: ignore
        for item in cached_items:
            if current_time - int(item.detail_last_sync_time or item.last_sync_time or 0) < cache_ttl_ms:
                results[item.workshop_id] = {
                    "title": item.title or "",
                    "description": item.description or "",
                    "preview_url": item.preview_url,
                    "screenshots": item.screenshots or [],
                    "time_updated": int(item.time_updated or 0),
                }
        ids_to_fetch = [wid for wid in workshop_ids if wid not in results]
        return results, ids_to_fetch

    @classmethod
    def _request_published_file_details(cls, workshop_ids: list[str]) -> dict[str, dict[str, object]]:
        """批量调用 Steam PublishedFileDetails 接口，并整理成统一缓存结构。"""
        fetched_details: dict[str, dict[str, object]] = {}
        for i in range(0, len(workshop_ids), 100):
            batch_ids = workshop_ids[i : i + 100]
            data = {
                "itemcount": len(batch_ids),
                "includepreviews": 1,
            }
            for idx, wid in enumerate(batch_ids):
                data[f"publishedfileids[{idx}]"] = str(wid)  # type: ignore

            try:
                payload = cls._request_json("POST", cls.PUBLISHED_FILE_DETAILS_URL, data=data)
                res_data = payload.get("response", {}).get("publishedfiledetails", [])
                for item in res_data:
                    wid = str(item.get("publishedfileid"))
                    previews = item.get("previews", [])
                    screenshots = [preview.get("url") for preview in previews if preview.get("preview_type") == 0]
                    fetched_details[wid] = {
                        "title": item.get("title") or "",
                        "description": item.get("description", ""),
                        "preview_url": item.get("preview_url"),
                        "screenshots": screenshots,
                        "time_updated": int(item.get("time_updated", 0)) * 1000,
                    }
            except Exception as e:
                logger.error(f"Steam API 请求失败: {e}", exc_info=True)
        return fetched_details

    @classmethod
    def probe_item_availability(cls, workshop_ids: list) -> dict[str, dict[str, Any]]:
        """
        探查工坊项目是否仍能从 Steam 获取有效详情。

        这个结果只服务运行时 UI 提示，不写入缓存和数据库，避免把网络波动误固化成业务事实。
        """
        normalized_ids = cls._normalize_workshop_ids(workshop_ids)
        result = {
            wid: {"workshop_id": wid, "status": "unknown", "result": None, "online_info": None}
            for wid in normalized_ids
        }
        for i in range(0, len(normalized_ids), 100):
            batch_ids = normalized_ids[i : i + 100]
            data = {"itemcount": len(batch_ids), "includepreviews": 1}
            for idx, wid in enumerate(batch_ids):
                data[f"publishedfileids[{idx}]"] = str(wid)  # type: ignore

            try:
                payload = cls._request_json("POST", cls.PUBLISHED_FILE_DETAILS_URL, data=data, timeout=(5, 12))
                for item in payload.get("response", {}).get("publishedfiledetails", []):
                    wid = str(item.get("publishedfileid") or "").strip()
                    if wid not in result:
                        continue
                    result_code = cls._safe_int(item.get("result"))
                    title = str(item.get("title") or "").strip()
                    preview_url = str(item.get("preview_url") or "").strip()
                    time_updated = cls._safe_int(item.get("time_updated")) * 1000
                    has_usable_detail = bool(title or preview_url or time_updated)
                    result[wid] = {
                        "workshop_id": wid,
                        "status": "available" if result_code == 1 and has_usable_detail else "unavailable",
                        "result": result_code,
                        "online_info": {
                            "title": title,
                            "preview_url": preview_url or None,
                            "time_updated": time_updated,
                        } if has_usable_detail else None,
                    }
            except Exception as e:
                logger.warning("Steam 工坊项目可用性探查失败：%s", e)
        return result

    @classmethod
    def _save_online_details(cls, details_map: dict[str, dict[str, object]], sync_time: int) -> None:
        """将统一结构的在线详情批量落入缓存表。"""
        cache_batch = [
            {
                "workshop_id": workshop_id,
                **detail,
                "detail_last_sync_time": sync_time,
                "last_sync_time": sync_time,
            }
            for workshop_id, detail in details_map.items()
        ]
        cls._upsert_online_cache_batch(cache_batch)

    @classmethod
    def _upsert_online_cache_batch(cls, cache_batch: list[dict[str, object]]):
        """批量写入在线缓存，并只覆盖在线字段。"""
        if not cache_batch: return
        with ext_db.atomic():
            WorkshopOnlineCache.insert_many(cache_batch).on_conflict(
                conflict_target=[WorkshopOnlineCache.workshop_id],
                preserve=[
                    WorkshopOnlineCache.title,
                    WorkshopOnlineCache.short_description,
                    WorkshopOnlineCache.description,
                    WorkshopOnlineCache.author_steam_id,
                    WorkshopOnlineCache.preview_url,
                    WorkshopOnlineCache.tags,
                    WorkshopOnlineCache.children,
                    WorkshopOnlineCache.screenshots,
                    WorkshopOnlineCache.time_created,
                    WorkshopOnlineCache.time_updated,
                    WorkshopOnlineCache.subscriptions,
                    WorkshopOnlineCache.favorited,
                    WorkshopOnlineCache.lifetime_subscriptions,
                    WorkshopOnlineCache.lifetime_favorited,
                    WorkshopOnlineCache.views,
                    WorkshopOnlineCache.summary_last_sync_time,
                    WorkshopOnlineCache.detail_last_sync_time,
                    WorkshopOnlineCache.last_sync_time,
                ],
            ).execute()

    @classmethod
    def _save_online_search_summaries(cls, items: list[dict[str, Any]], sync_time: int) -> None:
        """把在线搜索摘要写入缓存，供后续列表/详情头部复用。"""
        cache_batch = [
            cls._build_online_summary_upsert_row(item, sync_time)
            for item in items
            if str(item.get("workshop_id") or "").strip()
        ]
        cls._upsert_online_cache_batch(cache_batch)

    @classmethod
    def _collect_related_workshop_ids(cls, detail: dict[str, Any]) -> list[str]:
        """
        从详情扩展结果中提取需要预热的关联 workshop_id。

        这里只收集同作者作品和生态关联项，
        这样详情页首次展开时，关联卡片也更容易直接拿到封面和标题。
        """
        related_ids: list[str] = []
        seen_ids: set[str] = set()
        for key in ("same_author_mods", "dependents_mods"):
            for item in list(detail.get(key) or []):
                workshop_id = str(item.get("workshop_id") or "").strip()
                if not workshop_id or workshop_id in seen_ids:
                    continue
                seen_ids.add(workshop_id)
                related_ids.append(workshop_id)
        return related_ids

    @classmethod
    def fetch_item_details(
        cls,
        workshop_ids: list,
        force_refresh=False,
        only_cache=False,
        cache_ttl_hours=None,
        trace_label: str = "",
    ):
        """
        获取 Mod 或合集详情，自带本地在线缓存拦截。

        在线缓存单独落在 `WorkshopOnlineCache` 中：
        - 文件导入阶段只更新 `WorkshopManifest`；
        - TTL 刷新阶段只更新 `WorkshopOnlineCache` 中的在线字段。
        """
        trace_prefix = f"[{trace_label}] " if str(trace_label or "").strip() else ""

        if not workshop_ids:
            logger.debug(f"{trace_prefix}Steam 详情请求：输入为空，跳过")
            return {}, []

        normalized_ids = cls._normalize_workshop_ids(workshop_ids)
        if not normalized_ids:
            logger.debug(f"{trace_prefix}Steam 详情请求：规范化后为空，跳过")
            return {}, []

        results: dict[str, dict] = {}
        cache_ttl_ms = cache_ttl_hours * 60 * 60 * 1000 if cache_ttl_hours else cls.CACHE_TTL_MS

        if not force_refresh:
            results, ids_to_fetch = cls._load_cached_online_details(normalized_ids, cache_ttl_ms)
            logger.debug(
                f"{trace_prefix}Steam 详情请求：总数 {len(normalized_ids)}，"
                f"仅缓存 {only_cache}，强制刷新 {force_refresh}，"
                f"缓存命中 {len(results)}，待在线获取 {len(ids_to_fetch)}"
            )
        else:
            ids_to_fetch = normalized_ids
            logger.debug(
                f"{trace_prefix}Steam 详情请求：总数 {len(normalized_ids)}，"
                f"仅缓存 {only_cache}，强制刷新 {force_refresh}，"
                f"跳过缓存，待在线获取 {len(ids_to_fetch)}"
            )

        if only_cache: return results, ids_to_fetch

        if ids_to_fetch:
            current_time = int(time.time() * 1000)
            fetched_details = cls._request_published_file_details(ids_to_fetch)
            results.update(fetched_details)
            cls._save_online_details(fetched_details, current_time)
            logger.debug(f"{trace_prefix}Steam 详情请求：在线拉取完成 {len(fetched_details)} 条，已写入缓存")

        return results, ids_to_fetch

    @classmethod
    def search_workshop_online(
        cls,
        query: str,
        cursor: str = "*",
        page_size: int = 25,
        sort: str = "relevance",
        language: str | None = None,
    ) -> dict[str, Any]:
        """
        调用 QueryFiles 在线搜索 Steam Workshop。

        返回结构尽量贴近现有离线搜索结果，后续前端只需要切换数据源，
        无需为在线搜索单独维护一套完全不同的列表字段。
        """
        api_key = cls._get_steam_web_api_key()
        if not api_key:
            raise ValueError("未配置 Steam Web API Key，无法执行在线工坊搜索")

        search_text = str(query or "").strip()
        normalized_sort, query_type = cls._resolve_online_search_sort(sort, has_query=bool(search_text))
        normalized_cursor = str(cursor or "").strip() or "*"
        normalized_page_size = cls._normalize_online_page_size(page_size)
        steam_language = cls._resolve_steam_language(language)

        params: dict[str, Any] = {
            "key": api_key,
            "format": "json",
            "query_type": query_type,
            "page": 1,
            "cursor": normalized_cursor,
            "numperpage": normalized_page_size,
            "creator_appid": cls.RIMWORLD_APP_ID,
            "appid": cls.RIMWORLD_APP_ID,
            "requiredtags": "",
            "excludedtags": "",
            "required_flags": "",
            "omitted_flags": "",
            "search_text": search_text,
            "filetype": 0,
            "days": 7,
            "include_recent_votes_only": 0,
            "cache_max_age_seconds": 300,
            "language": steam_language,
            "totalonly": 0,
            "ids_only": 0,
            "return_vote_data": 0,
            "return_tags": 1,
            "return_previews": 1,
            "return_children": 1,
            "return_short_description": 1,
            "return_metadata": 0,
        }
        payload = cls._request_json("GET", cls.QUERY_FILES_URL, params=params)
        response = payload.get("response", {})
        if not isinstance(response, dict):
            raise RuntimeError("Steam 在线搜索返回了无法识别的响应结构")

        raw_items = response.get("publishedfiledetails") or []
        items = [cls._normalize_query_file_item(item) for item in raw_items if isinstance(item, dict)]
        cls._save_online_search_summaries(items, int(time.time() * 1000))
        next_cursor = str(response.get("next_cursor") or "").strip()
        total = cls._safe_int(response.get("total"))
        return {
            "items": items,
            "total": total,
            "cursor": normalized_cursor,
            "next_cursor": next_cursor,
            "has_more": bool(next_cursor and next_cursor != normalized_cursor and len(items) >= normalized_page_size),
            "page_size": normalized_page_size,
            "query": search_text,
            "sort": normalized_sort,
            "query_type": query_type,
            "language": steam_language,
            "source": "steam_online",
        }

    @classmethod
    def get_or_fetch_details(cls, workshop_id: str):
        """获取单个模组详情，包含图文、同作者推荐、反向依赖、替代方案。"""
        meta = ExtDAO.get_merged_meta_by_workshop_id(workshop_id)
        current_time = int(time.time() * 1000)
        if not meta or not meta.get("description") or (current_time - int(meta.get("detail_last_sync_time") or meta.get("last_sync_time") or 0) > cls.CACHE_TTL_MS):
            cls.fetch_item_details([workshop_id], force_refresh=True)
            meta = ExtDAO.get_merged_meta_by_workshop_id(workshop_id)
        if not meta: return None

        screenshots = list(meta.get("screenshots") or [])
        if not screenshots:
            screenshots = cls._fetch_screenshots_via_scraper(workshop_id)
            if screenshots:
                WorkshopOnlineCache.update(
                    screenshots=screenshots,
                ).where(WorkshopOnlineCache.workshop_id == workshop_id).execute()
                meta["screenshots"] = screenshots

        detail = ExtDAO.get_workshop_detail_extended(workshop_id)
        if not detail or not detail.get("meta", {}): return None

        related_ids = cls._collect_related_workshop_ids(detail)
        if related_ids:
            # 详情页会立刻展示这些关联卡片，先把它们的在线详情补进缓存，
            # 可以减少卡片缺封面、缺标题时的空白感。
            cls.fetch_item_details(related_ids, force_refresh=False)
            refreshed_detail = ExtDAO.get_workshop_detail_extended(workshop_id)
            if refreshed_detail and refreshed_detail.get("meta", {}):
                detail = refreshed_detail

        response = detail.get("meta", {})
        if not response.get("game_versions"):
            response["game_versions"] = cls._extract_game_versions_from_tags(list(response.get("tags") or []))
        if not response.get("description"):
            response["description"] = response.get("short_description") or ""
        response.update(
            {
                "replacement_mod": detail.get("replacement_mod"),
                "same_author_mods": detail.get("same_author_mods", []),
                "dependents_mods": detail.get("dependents_mods", []),
            }
        )
        return response

    @classmethod
    def fetch_collection_children(cls, collection_id: str) -> list:
        """解析合集，返回包含的全部正常 Mod ID 列表。"""
        data = {"collectioncount": "1", "publishedfileids[0]": str(collection_id)}
        try:
            payload = cls._request_json("POST", cls.COLLECTION_DETAILS_URL, data=data)
            children = payload.get("response", {}).get("collectiondetails", [{}])[0].get("children", [])
            return [str(c.get("publishedfileid")) for c in children if c.get("filetype") == 0]
        except Exception as e:
            logger.error(f"解析合集失败: {e}")
            return []

    @classmethod
    def _fetch_screenshots_via_scraper(cls, workshop_id: str) -> list:
        """
        网页抓取补充方案：正则提取 rgScreenshotURLs。

        抓取到的截图只写入在线缓存层，因为截图属于展示增强数据。
        """
        url = cls._build_workshop_url(workshop_id)
        screenshots = []

        try:
            headers = {
                "Accept-Language": f"{cls._resolve_steam_language()};q=0.9,en;q=0.8",
            }
            logger.debug(f"Triggering Scraper Fallback for Mod: {workshop_id}")
            html_content = cls._request_text("GET", url, headers=headers)
            # 核心：正则匹配变量内容
            # 匹配 rgScreenshotURLs = { ... }; 
            pattern = re.compile(r"rgScreenshotURLs\s*=\s*\{(.*?)\};", re.DOTALL)
            match = pattern.search(html_content)
            if match:
                js_object_content = match.group(1)
                # 进一步提取所有引号中的 URL
                # 匹配格式如 'id': 'https://...'
                url_pattern = re.compile(r"'(https://images\.steamusercontent\.com/ugc/.*?)'")
                urls = url_pattern.findall(js_object_content)
                # 去重并清洗（过滤掉空白和重复）
                for u in urls:
                    if u and u not in screenshots:
                        screenshots.append(u)
            logger.info(f"Scraper found {len(screenshots)} screenshots for {workshop_id}")
        except Exception as e:
            logger.error(f"Scraper Fallback failed for {workshop_id}: {e}")

        return screenshots
    
if __name__ == "__main__":
    init_ext_db()
    # 测试用例：解析合集
    collection_id = "3670074636"
    # children = SteamWebAPI.fetch_collection_children(collection_id)
    # print(f"合集 {collection_id} 包含 {len(children)} 个 Mod")
    #  # 测试用例：解析 Mod 详情
    mod_id = '3723552881'
    # details = SteamWebAPI.fetch_item_details([mod_id], True)
    # print(f"Mod {mod_id} 详情: {details}")
    
    # screenshots = SteamWebAPI._fetch_screenshots_via_scraper(mod_id)
    # print(f"Mod 截图: {screenshots}")
    
    # search_res = SteamWebAPI.search_workshop_online("rim tuber")
    # print(f"搜索结果: {search_res}")
    
    
