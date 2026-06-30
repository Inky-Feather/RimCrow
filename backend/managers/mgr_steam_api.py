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
from backend.database.models_ext import WorkshopAuthorCache, WorkshopOnlineCache, ext_db, init_ext_db
from backend.managers.mgr_network import build_retry_session, merge_headers, network_mgr
from backend.settings import settings
from backend.utils.constants import (
    RIMWORLD_DLC_APPID_PACKAGE_MAP, RIMWORLD_STEAM_APP_ID,
    SteamPublishedFileMatchingFileType, SteamPublishedFileQueryType, SteamUserUGCList, SteamUserUGCListSortOrder,
    SteamWorkshopFileType, normalize_steam_matching_file_type, normalize_steam_query_type,
    normalize_steam_search_text_target, normalize_steam_user_ugc_list, normalize_steam_user_ugc_sort,
    normalize_steam_workshop_file_type,
    to_steam_elanguage, to_steam_webapi_language_code,
)
from backend.utils.logger import logger
from backend.utils.tools import normalize_package_id, normalize_workshop_id


class SteamWebAPI:
    """统一封装 Steam Workshop 详情查询、合集解析和在线搜索。"""

    BASE_URL = "https://api.steampowered.com"
    PUBLISHED_FILE_DETAILS_URL = f"{BASE_URL}/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    COLLECTION_DETAILS_URL = f"{BASE_URL}/ISteamRemoteStorage/GetCollectionDetails/v1/"
    PUBLISHED_FILE_SERVICE_URL = f"{BASE_URL}/IPublishedFileService"
    QUERY_FILES_URL = f"{PUBLISHED_FILE_SERVICE_URL}/QueryFiles/v1/"
    STEAM_USER_SUMMARIES_URL = f"{BASE_URL}/ISteamUser/GetPlayerSummaries/v2/"
    WORKSHOP_ITEM_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
    RIMWORLD_APP_ID = RIMWORLD_STEAM_APP_ID
    CACHE_TTL_MS = 1 * 24 * 60 * 60 * 1000
    AUTHOR_CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000

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
    def _published_file_service_url(cls, method_name: str) -> str:
        method = str(method_name or "").strip().strip("/")
        if not method:
            raise ValueError("Steam 接口方法不能为空")
        return f"{cls.PUBLISHED_FILE_SERVICE_URL}/{method}/v1/"

    @classmethod
    def _request_published_file_service(
        cls,
        method_name: str,
        *,
        http_method: str = "GET",
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        timeout: tuple[int, int] = (10, 20),
    ) -> dict[str, Any]:
        """统一调用 IPublishedFileService，保留接口名便于日志排查。"""
        method = str(http_method or "GET").upper()
        url = cls._published_file_service_url(method_name)
        return cls._request_json(method, url, params=params if method == "GET" else None, data=data if method != "GET" else None, timeout=timeout)

    @classmethod
    def _require_response_dict(cls, payload: dict[str, Any], api_name: str) -> dict[str, Any]:
        response = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(response, dict):
            raise RuntimeError(f"{api_name} 返回缺少 response")
        return response

    @classmethod
    def _require_response_list(cls, payload: dict[str, Any], field: str, api_name: str) -> list[Any]:
        response = cls._require_response_dict(payload, api_name)
        if not isinstance(response.get(field), list):
            raise RuntimeError(f"{api_name} 返回缺少 response.{field}")
        return response[field]

    @classmethod
    def _require_steam_web_api_key(cls) -> str:
        api_key = cls._get_steam_web_api_key()
        if not api_key:
            raise ValueError("未配置 Steam Web API Key")
        return api_key

    @classmethod
    def _add_indexed_params(cls, target: dict[str, Any], name: str, values: Any) -> None:
        values = values if isinstance(values, (list, tuple, set)) else ([values] if values not in (None, "") else [])
        for index, value in enumerate(values):
            if value in (None, ""):
                continue
            target[f"{name}[{index}]"] = value

    @classmethod
    def _add_indexed_dict_params(cls, target: dict[str, Any], name: str, values: Any) -> None:
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, (list, tuple)):
            return
        for index, item in enumerate(values):
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                if value in (None, ""):
                    continue
                target[f"{name}[{index}][{key}]"] = value

    @classmethod
    def _add_date_range_params(cls, target: dict[str, Any], name: str, value: Any) -> None:
        if isinstance(value, dict):
            start_value = value.get("start") or value.get("from") or value.get("min")
            end_value = value.get("end") or value.get("to") or value.get("max")
            values = [start_value, end_value]
        elif isinstance(value, (list, tuple)):
            values = list(value[:2])
        else:
            values = []
        for index, item in enumerate(values):
            if item not in (None, ""):
                target[f"{name}[{index}]"] = cls._safe_int(item)

    @classmethod
    def _add_taggroups_params(cls, target: dict[str, Any], taggroups: Any) -> None:
        if isinstance(taggroups, dict):
            taggroups = [taggroups]
        if not isinstance(taggroups, (list, tuple)):
            return
        for group_index, group in enumerate(taggroups):
            if isinstance(group, dict):
                tags = cls._normalize_online_search_terms(group.get("tags"))
                match_all = 1 if bool(group.get("match_all_tags", group.get("matchAllTags", True))) else 0
            else:
                tags = cls._normalize_online_search_terms(group)
                match_all = 1
            if not tags:
                continue
            target[f"taggroups[{group_index}][match_all_tags]"] = match_all
            for tag_index, tag in enumerate(tags):
                target[f"taggroups[{group_index}][tags][{tag_index}]"] = tag

    @classmethod
    def _normalize_service_bool(cls, value: Any) -> int:
        return 1 if bool(value) else 0

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
    def _safe_bool(cls, value: Any) -> bool:
        """Steam 的布尔字段可能返回 bool、0/1 或字符串，这里统一收束。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        normalized = str(value or "").strip().lower()
        return normalized in {"1", "true", "yes", "y"}

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
    def _clean_online_url(cls, value: Any) -> str:
        """清理 Steam URL 中偶发的异常空格。"""
        text = str(value or "").strip()
        if not text:
            return ""
        return re.sub(r"^(https?):\s+//", r"\1://", text, flags=re.IGNORECASE)

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
            "auto": SteamPublishedFileQueryType.RANKED_BY_TEXT_SEARCH if has_query else SteamPublishedFileQueryType.RANKED_BY_TREND,
            "relevance": SteamPublishedFileQueryType.RANKED_BY_TEXT_SEARCH,
            "latest": SteamPublishedFileQueryType.RANKED_BY_LAST_UPDATED_DATE,
            "updated": SteamPublishedFileQueryType.RANKED_BY_LAST_UPDATED_DATE,
            "created": SteamPublishedFileQueryType.RANKED_BY_PUBLICATION_DATE,
            "published": SteamPublishedFileQueryType.RANKED_BY_PUBLICATION_DATE,
            "subscriptions": SteamPublishedFileQueryType.RANKED_BY_TOTAL_UNIQUE_SUBSCRIPTIONS,
            "popular": SteamPublishedFileQueryType.RANKED_BY_TREND,
            "vote": SteamPublishedFileQueryType.RANKED_BY_VOTE,
            "rating": SteamPublishedFileQueryType.RANKED_BY_VOTE,
            "votes": SteamPublishedFileQueryType.RANKED_BY_VOTES_UP,
            "votes_up": SteamPublishedFileQueryType.RANKED_BY_VOTES_UP,
            "trend": SteamPublishedFileQueryType.RANKED_BY_TREND,
        }
        if normalized_sort == "relevance" and not has_query:
            return "latest", int(query_type_map["latest"])
        fallback = SteamPublishedFileQueryType.RANKED_BY_TEXT_SEARCH if has_query else SteamPublishedFileQueryType.RANKED_BY_LAST_UPDATED_DATE
        return normalized_sort, int(query_type_map.get(normalized_sort, fallback))

    @classmethod
    def _resolve_steam_query_language(cls, language: Any = None) -> int:
        """QueryFiles 的 language 是 Steam ELanguage 整数，而不是网页语言码。"""
        if language is None or str(language).strip() == "":
            language = settings.config.language
        return to_steam_elanguage(language, default=settings.config.language or "en")

    @classmethod
    def _normalize_online_search_terms(cls, values: Any) -> list[str]:
        if isinstance(values, str):
            raw_values = re.split(r"[,，;\n\r]+", values)
        elif isinstance(values, (list, tuple, set)):
            raw_values = values
        else:
            raw_values = []
        terms: list[str] = []
        seen: set[str] = set()
        for value in raw_values:
            term = str(value or "").strip()
            key = term.lower()
            if not term or key in seen:
                continue
            seen.add(key)
            terms.append(term)
        return terms

    @classmethod
    def _normalize_online_search_filters(cls, filters: dict[str, Any] | None) -> dict[str, Any]:
        filters = filters or {}
        if not isinstance(filters, dict):
            filters = {}
        return_flags = {
            "return_vote_data": filters.get("return_vote_data", filters.get("returnVoteData", False)),
            "return_metadata": filters.get("return_metadata", filters.get("returnMetadata", False)),
            "return_kv_tags": filters.get("return_kv_tags", filters.get("returnKvTags", False)),
            "return_for_sale_data": filters.get("return_for_sale_data", filters.get("returnForSaleData", False)),
            "return_playtime_stats": filters.get("return_playtime_stats", filters.get("returnPlaytimeStats", False)),
            "return_details": filters.get("return_details", filters.get("returnDetails", False)),
            "strip_description_bbcode": filters.get("strip_description_bbcode", filters.get("stripDescriptionBbcode", False)),
        }
        return {
            "required_tags": cls._normalize_online_search_terms(filters.get("required_tags") or filters.get("requiredTags")),
            "excluded_tags": cls._normalize_online_search_terms(filters.get("excluded_tags") or filters.get("excludedTags")),
            "match_all_tags": 1 if bool(filters.get("match_all_tags", filters.get("matchAllTags", True))) else 0,
            "required_flags": str(filters.get("required_flags") or filters.get("requiredFlags") or "").strip(),
            "omitted_flags": str(filters.get("omitted_flags") or filters.get("omittedFlags") or "").strip(),
            "language": cls._resolve_steam_query_language(filters.get("language")),
            "filetype": int(normalize_steam_matching_file_type(filters.get("filetype"), SteamPublishedFileMatchingFileType.ITEMS)),
            "days": max(0, min(cls._safe_int(filters.get("days"), default=7), 365)),
            "include_recent_votes_only": 1 if bool(filters.get("include_recent_votes_only", filters.get("includeRecentVotesOnly", False))) else 0,
            "child_publishedfileid": str(filters.get("child_publishedfileid") or filters.get("childPublishedFileId") or "").strip(),
            "query_type": filters.get("query_type", filters.get("queryType")),
            "required_kv_tags": filters.get("required_kv_tags", filters.get("requiredKvTags")),
            "taggroups": filters.get("taggroups"),
            "date_range_created": filters.get("date_range_created", filters.get("dateRangeCreated")),
            "date_range_updated": filters.get("date_range_updated", filters.get("dateRangeUpdated")),
            "excluded_content_descriptors": filters.get("excluded_content_descriptors", filters.get("excludedContentDescriptors")),
            "appids_required_for_use": filters.get("appids_required_for_use", filters.get("appidsRequiredForUse")),
            "excluded_appids_required_for_use": filters.get("excluded_appids_required_for_use", filters.get("excludedAppidsRequiredForUse")),
            "required_dlc_appids": cls._normalize_online_search_terms(filters.get("required_dlc_appids") or filters.get("requiredDlcAppids")),
            "special_filter": filters.get("special_filter", filters.get("specialFilter")),
            "search_text_target": int(normalize_steam_search_text_target(filters.get("search_text_target", filters.get("searchTextTarget")))),
            "desired_revision": filters.get("desired_revision", filters.get("desiredRevision")),
            **{key: cls._normalize_service_bool(value) for key, value in return_flags.items()},
        }

    @classmethod
    def _resolve_online_query_type(cls, filters: dict[str, Any], fallback_query_type: int) -> int:
        query_type = filters.get("query_type")
        if query_type in (None, ""):
            return fallback_query_type
        return int(normalize_steam_query_type(query_type, SteamPublishedFileQueryType(fallback_query_type)))

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
        preview_url = cls._clean_online_url(item.get("preview_url"))
        if preview_url: return preview_url
        previews = item.get("previews") or []
        for preview in previews:
            if cls._safe_int(preview.get("preview_type")) != 0:
                continue
            preview_url = cls._clean_online_url(preview.get("url"))
            if preview_url: return preview_url
        return ""

    @classmethod
    def _extract_preview_items(cls, item: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        previews = item.get("previews") or []
        screenshots: list[str] = []
        normalized_previews: list[dict[str, Any]] = []
        for preview in previews:
            if not isinstance(preview, dict):
                continue
            preview_url = cls._clean_online_url(preview.get("url"))
            preview_type = cls._safe_int(preview.get("preview_type"))
            if preview_type == 0 and preview_url:
                screenshots.append(preview_url)
            normalized_previews.append(
                {
                    "preview_id": str(preview.get("previewid") or "").strip(),
                    "sort_order": cls._safe_int(preview.get("sortorder")),
                    "url": preview_url,
                    "preview_type": preview_type,
                    "external_id": str(preview.get("external_id") or "").strip(),
                }
            )
        return screenshots, normalized_previews

    @classmethod
    def _extract_child_items(cls, item: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "workshop_id": str(child.get("publishedfileid") or child.get("workshop_id") or "").strip(),
                "item_type": cls._resolve_workshop_item_type(child.get("item_type", child.get("file_type") or child.get("filetype"))),
                "sort_order": cls._safe_int(child.get("sortorder") or child.get("sort_order")),
            }
            for child in (item.get("children") or [])
            if isinstance(child, dict) and str(child.get("publishedfileid") or child.get("workshop_id") or "").strip()
        ]

    @classmethod
    def _extract_tag_items(cls, item: dict[str, Any]) -> list[str]:
        return [
            str(tag.get("tag") or tag.get("display_name") or "").strip()
            for tag in (item.get("tags") or [])
            if isinstance(tag, dict) and str(tag.get("tag") or tag.get("display_name") or "").strip()
        ]

    @classmethod
    def _extract_kv_tag_items(cls, item: dict[str, Any]) -> list[dict[str, str]]:
        """整理 Steam Key/Value 标签，保留未来模组生态可能用到的轻量结构。"""
        normalized_tags: list[dict[str, str]] = []
        for tag in (item.get("kvtags") or item.get("kv_tags") or []):
            if not isinstance(tag, dict):
                continue
            key = str(tag.get("key") or tag.get("name") or "").strip()
            value = str(tag.get("value") or "").strip()
            if key:
                normalized_tags.append({"key": key, "value": value})
        return normalized_tags

    @classmethod
    def _extract_appids_required_for_use(cls, item: dict[str, Any]) -> list[int]:
        raw_values = item.get("appids_required_for_use") or item.get("appidsrequiredforuse") or []
        if isinstance(raw_values, (str, int)):
            raw_values = [raw_values]
        if not isinstance(raw_values, (list, tuple, set)):
            return []
        result: list[int] = []
        seen: set[int] = set()
        for value in raw_values:
            appid = cls._safe_int(value)
            if appid and appid not in seen:
                seen.add(appid)
                result.append(appid)
        return result

    @classmethod
    def _extract_status_fields(cls, item: dict[str, Any]) -> dict[str, Any]:
        """把 Steam 的零散状态字段收束成一个缓存字段，避免表结构继续膨胀。"""
        status: dict[str, Any] = {}
        if "visibility" in item:
            status["visibility"] = cls._safe_int(item.get("visibility"), default=-1)
        if "can_subscribe" in item:
            status["can_subscribe"] = cls._safe_bool(item.get("can_subscribe"))
        if "flags" in item:
            status["flags"] = cls._safe_int(item.get("flags"))
        if "banned" in item:
            status["banned"] = cls._safe_bool(item.get("banned"))
        if item.get("ban_reason") not in (None, ""):
            status["ban_reason"] = str(item.get("ban_reason") or "")
        if "ban_text_check_result" in item:
            status["ban_text_check_result"] = cls._safe_int(item.get("ban_text_check_result"))
        if item.get("banner") not in (None, ""):
            status["banner"] = str(item.get("banner") or "")
        return status

    @classmethod
    def _resolve_workshop_item_type(cls, raw_type: Any) -> str:
        """把 Steam filetype 映射成业务侧直白类型，避免前端理解 Steam 枚举。"""
        if isinstance(raw_type, str):
            normalized = raw_type.strip().lower()
            if normalized in {"mod", "collection", "other"}:
                return normalized
        file_type = normalize_steam_workshop_file_type(raw_type, SteamWorkshopFileType.COMMUNITY)
        if file_type == SteamWorkshopFileType.COMMUNITY:
            return "mod"
        if file_type == SteamWorkshopFileType.COLLECTION:
            return "collection"
        return "other"

    @classmethod
    def _extract_stats_fields(cls, item: dict[str, Any], vote_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """统一整理订阅、收藏、投票和评论统计，避免顶层字段分散。"""
        vote_data = vote_data if isinstance(vote_data, dict) else {}
        return {
            "subscriptions": cls._safe_int(item.get("subscriptions")),
            "favorited": cls._safe_int(item.get("favorited")),
            "votes_up": cls._safe_int(vote_data.get("votes_up") if "votes_up" in vote_data else item.get("votes_up")),
            "votes_down": cls._safe_int(vote_data.get("votes_down") if "votes_down" in vote_data else item.get("votes_down")),
            "vote_score": cls._safe_float(vote_data.get("score") if "score" in vote_data else item.get("score")),
            "num_reports": cls._safe_int(item.get("num_reports")),
            "num_comments_public": cls._safe_int(item.get("num_comments_public")),
        }

    @classmethod
    def _normalize_published_file_item(cls, item: dict[str, Any], *, source: str = "service") -> dict[str, Any]:
        """统一解析 QueryFiles、GetUserFiles、GetDetails 与旧版详情条目。"""
        workshop_id = str(item.get("publishedfileid") or "").strip()
        title = cls._clean_online_text(item.get("title"))
        screenshots, previews = cls._extract_preview_items(item)
        children = cls._extract_child_items(item)
        tags = cls._extract_tag_items(item)
        short_description = cls._clean_online_text(item.get("short_description"))
        description = str(item.get("file_description") if item.get("file_description") not in (None, "") else item.get("description", "") or "")
        vote_data = item.get("vote_data") if isinstance(item.get("vote_data"), dict) else {}
        if not vote_data:
            vote_data = {
                "score": cls._safe_float(item.get("score")),
                "votes_up": cls._safe_int(item.get("votes_up")),
                "votes_down": cls._safe_int(item.get("votes_down")),
            }
        time_created = cls._safe_int(item.get("time_created")) * 1000
        time_updated = cls._safe_int(item.get("time_updated")) * 1000
        return {
            "workshop_id": workshop_id,
            "name": title,
            "title": title,
            "preview_url": cls._extract_preview_url(item),
            "short_description": short_description,
            "description": description,
            "author_steam_id": str(item.get("creator") or "").strip(),
            "time_created": time_created,
            "time_updated": time_updated,
            "stats": cls._extract_stats_fields(item, vote_data),
            "item_type": cls._resolve_workshop_item_type(item.get("file_type") or item.get("filetype")),
            "consumer_app_id": cls._safe_int(item.get("consumer_app_id") or item.get("consumer_appid")),
            "consumer_shortcutid": cls._safe_int(item.get("consumer_shortcutid")),
            "file_size": cls._safe_int(item.get("file_size")),
            "status": cls._extract_status_fields(item),
            "maybe_inappropriate_sex": cls._safe_bool(item.get("maybe_inappropriate_sex")),
            "maybe_inappropriate_violence": cls._safe_bool(item.get("maybe_inappropriate_violence")),
            "revision_change_number": cls._safe_int(item.get("revision_change_number")),
            "children": children,
            "tags": tags,
            "screenshots": screenshots,
            "previews": previews,
            "kv_tags": cls._extract_kv_tag_items(item),
            "playtime_stats": item.get("playtime_stats") or None,
            "translations": {},
            "url": cls._build_workshop_url(workshop_id),
            "source": "steam_legacy" if source == "legacy" else "steam_online",
        }

    @classmethod
    def _normalize_query_file_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        """兼容旧调用名，统一走新版条目解析。"""
        return cls._normalize_published_file_item(item, source="service")

    @classmethod
    def _build_online_summary_upsert_row(cls, item: dict[str, Any], sync_time: int) -> dict[str, Any]:
        """
        把 QueryFiles / GetUserFiles 的列表结果写成缓存行。

        这些接口和 GetDetails 的条目结构基本一致，因此字段截取统一走
        `_cacheable_detail_fields`，避免搜索结果新增字段时只写入详情缓存。
        """
        return {
            "workshop_id": str(item.get("workshop_id") or "").strip(),
            **cls._cacheable_detail_fields(item),
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
                    "workshop_id": item.workshop_id,
                    "title": item.title or "",
                    "name": item.title or "",
                    "short_description": item.short_description or "",
                    "description": item.description or "",
                    "author_steam_id": item.author_steam_id or "",
                    "preview_url": item.preview_url,
                    "screenshots": item.screenshots or [],
                    "tags": item.tags or [],
                    "children": item.children or [],
                    "kv_tags": item.kv_tags or [],
                    "stats": item.stats or {},
                    "item_type": item.item_type or "mod",
                    "time_created": int(item.time_created or 0),
                    "time_updated": int(item.time_updated or 0),
                    "file_size": int(item.file_size or 0),
                    "status": item.status or {},
                    "maybe_inappropriate_sex": bool(item.maybe_inappropriate_sex),
                    "maybe_inappropriate_violence": bool(item.maybe_inappropriate_violence),
                    "translations": item.translations or {},
                    "playtime_stats": item.playtime_stats,
                }
        ids_to_fetch = [wid for wid in workshop_ids if wid not in results]
        return results, ids_to_fetch

    @classmethod
    def _request_published_file_details(cls, workshop_ids: list[str]) -> dict[str, dict[str, object]]:
        """批量调用旧版 PublishedFileDetails 接口，并整理成基础缓存结构。"""
        fetched_details: dict[str, dict[str, object]] = {}
        for i in range(0, len(workshop_ids), 100):
            batch_ids = workshop_ids[i : i + 100]
            data = {"itemcount": len(batch_ids)}
            for idx, wid in enumerate(batch_ids):
                data[f"publishedfileids[{idx}]"] = str(wid)  # type: ignore

            try:
                payload = cls._request_json("POST", cls.PUBLISHED_FILE_DETAILS_URL, data=data)
                res_data = cls._require_response_list(payload, "publishedfiledetails", "Steam PublishedFileDetails")
                for item in res_data:
                    if not isinstance(item, dict):
                        continue
                    normalized_item = cls._normalize_published_file_item(item, source="legacy")
                    wid = str(normalized_item.get("workshop_id") or "").strip()
                    if wid:
                        fetched_details[wid] = normalized_item
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
            data = {"itemcount": len(batch_ids)}
            for idx, wid in enumerate(batch_ids):
                data[f"publishedfileids[{idx}]"] = str(wid)  # type: ignore

            try:
                payload = cls._request_json("POST", cls.PUBLISHED_FILE_DETAILS_URL, data=data, timeout=(5, 12))
                for item in cls._require_response_list(payload, "publishedfiledetails", "Steam PublishedFileDetails"):
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
                **cls._cacheable_detail_fields(detail),
                "detail_last_sync_time": sync_time,
                "last_sync_time": sync_time,
            }
            for workshop_id, detail in details_map.items()
        ]
        cls._upsert_online_cache_batch(cache_batch)

    @classmethod
    def _upsert_online_cache_batch(cls, cache_batch: list[dict[str, object]]):
        """
        批量写入在线缓存，并只覆盖本次实际传入的表字段。

        Steam 返回结构里会混有 `name`、`source`、`url` 等运行时字段，入库前必须按
        Peewee 模型字段白名单过滤；同时摘要缓存和详情缓存的同步时间不同，不能让
        摘要写入时用默认值覆盖 `detail_last_sync_time`。
        """
        if not cache_batch: return
        model_fields = WorkshopOnlineCache._meta.fields # type: ignore
        grouped_rows: dict[tuple[str, ...], list[dict[str, object]]] = {}
        for row in cache_batch:
            sanitized = {
                key: value
                for key, value in row.items()
                if key in model_fields and value is not None
            }
            if not sanitized.get("workshop_id"):
                continue
            grouped_rows.setdefault(tuple(sorted(sanitized.keys())), []).append(sanitized)
        if not grouped_rows: return

        with ext_db.atomic():
            for field_names, rows in grouped_rows.items():
                preserve_fields = [
                    model_fields[field_name]
                    for field_name in field_names
                    if field_name != "workshop_id"
                ]
                insert_query = WorkshopOnlineCache.insert_many(rows)
                if preserve_fields:
                    insert_query = insert_query.on_conflict(
                        conflict_target=[WorkshopOnlineCache.workshop_id],
                        preserve=preserve_fields,
                    )
                else:
                    insert_query = insert_query.on_conflict_ignore()
                insert_query.execute()

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
    def _normalize_author_profile(cls, player: dict[str, Any], sync_time: int = 0) -> dict[str, Any]:
        """把 GetPlayerSummaries 返回的玩家资料整理成作者缓存结构。"""
        steam_id = str(player.get("steamid") or player.get("steam_id") or "").strip()
        if not steam_id:
            return {}
        return {
            "steam_id": steam_id,
            "personaname": str(player.get("personaname") or player.get("name") or "").strip(),
            "profile_url": cls._clean_online_url(player.get("profileurl") or player.get("profile_url")),
            "avatar": cls._clean_online_url(player.get("avatar")),
            "country_code": str(player.get("loccountrycode") or player.get("country_code") or "").strip(),
            "time_created": cls._safe_int(player.get("timecreated") or player.get("time_created")),
            "last_sync_time": sync_time,
        }

    @classmethod
    def _public_author_profile(cls, profile: dict[str, Any]) -> dict[str, Any]:
        """返回前端需要的作者展示字段，避免暴露完整原始响应。"""
        if not profile:
            return {}
        return {
            "steam_id": str(profile.get("steam_id") or "").strip(),
            "name": str(profile.get("personaname") or profile.get("name") or "").strip(),
            "profile_url": str(profile.get("profile_url") or "").strip(),
            "avatar": str(profile.get("avatar") or "").strip(),
            "country_code": str(profile.get("country_code") or "").strip(),
            "time_created": cls._safe_int(profile.get("time_created")),
        }

    @classmethod
    def _load_cached_author_profiles(cls, steam_ids: list[str], cache_ttl_ms: int | None = None) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """读取作者资料缓存，并返回缺失或过期的 SteamID。"""
        cache_ttl_ms = cache_ttl_ms or cls.AUTHOR_CACHE_TTL_MS
        current_time = int(time.time() * 1000)
        normalized_ids = []
        seen_ids: set[str] = set()
        for steam_id in steam_ids:
            normalized_id = str(steam_id or "").strip()
            if not normalized_id or normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            normalized_ids.append(normalized_id)
        if not normalized_ids:
            return {}, []
        try:
            rows = (
                WorkshopAuthorCache.select()
                .where(WorkshopAuthorCache.steam_id.in_(normalized_ids))
                .dicts()
            )
            cached = {
                str(row["steam_id"]): row
                for row in rows
                if current_time - int(row.get("last_sync_time") or 0) < cache_ttl_ms
            }
        except Exception:
            cached = {}
        return cached, [steam_id for steam_id in normalized_ids if steam_id not in cached]

    @classmethod
    def _save_author_profiles(cls, profiles: dict[str, dict[str, Any]], sync_time: int) -> None:
        """批量写入作者资料缓存。"""
        rows = []
        for steam_id, profile in profiles.items():
            normalized = cls._normalize_author_profile(profile, sync_time)
            if normalized.get("steam_id"):
                rows.append(normalized)
        if not rows:
            return
        model_fields = WorkshopAuthorCache._meta.fields # type: ignore
        sanitized_rows = [
            {key: value for key, value in row.items() if key in model_fields and value is not None}
            for row in rows
        ]
        with ext_db.atomic():
            WorkshopAuthorCache.insert_many(sanitized_rows).on_conflict(
                conflict_target=[WorkshopAuthorCache.steam_id],
                preserve=[
                    WorkshopAuthorCache.personaname,
                    WorkshopAuthorCache.profile_url,
                    WorkshopAuthorCache.avatar,
                    WorkshopAuthorCache.country_code,
                    WorkshopAuthorCache.time_created,
                    WorkshopAuthorCache.last_sync_time,
                ],
            ).execute()

    @classmethod
    def fetch_player_summaries(cls, steam_ids: list[str], force_refresh: bool = False) -> dict[str, dict[str, Any]]:
        """批量获取 Steam 用户资料，用于把 creator SteamID 补成作者名称。"""
        cached, ids_to_fetch = ({}, cls._normalize_online_search_terms(steam_ids)) if force_refresh else cls._load_cached_author_profiles(steam_ids)
        result: dict[str, dict[str, Any]] = dict(cached)
        if not ids_to_fetch:
            return {steam_id: cls._public_author_profile(profile) for steam_id, profile in result.items()}
        api_key = cls._require_steam_web_api_key()
        fetched: dict[str, dict[str, Any]] = {}
        sync_time = int(time.time() * 1000)
        for i in range(0, len(ids_to_fetch), 100):
            batch_ids = ids_to_fetch[i : i + 100]
            payload = cls._request_json(
                "GET",
                cls.STEAM_USER_SUMMARIES_URL,
                params={"key": api_key, "format": "json", "steamids": ",".join(batch_ids)},
            )
            players = cls._require_response_list(payload, "players", "Steam PlayerSummaries")
            for player in players:
                if not isinstance(player, dict):
                    continue
                normalized = cls._normalize_author_profile(player, sync_time)
                steam_id = str(normalized.get("steam_id") or "").strip()
                if steam_id:
                    fetched[steam_id] = normalized
        if fetched:
            cls._save_author_profiles(fetched, sync_time)
            result.update(fetched)
        return {steam_id: cls._public_author_profile(profile) for steam_id, profile in result.items()}

    @classmethod
    def _attach_author_profiles(cls, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """给统一工坊条目补齐作者资料；失败时保留原始 creator ID。"""
        author_ids = [
            str(item.get("author_steam_id") or "").strip()
            for item in items
            if str(item.get("author_steam_id") or "").strip()
        ]
        if not author_ids:
            return items
        try:
            author_map = cls.fetch_player_summaries(author_ids)
        except Exception as exc:
            logger.debug("Steam 作者资料补全失败：%s", exc, exc_info=True)
            return items
        for item in items:
            author_id = str(item.get("author_steam_id") or "").strip()
            profile = author_map.get(author_id) or {}
            if not profile:
                continue
            item["author_profile"] = profile
            if not item.get("author"):
                item["author"] = profile.get("name") or ""
        return items

    @classmethod
    def _collect_related_workshop_ids(cls, detail: dict[str, Any]) -> list[str]:
        """
        从详情扩展结果中提取需要预热的关联 workshop_id。

        这里覆盖依赖项目、生态关联和同作者作品三类，
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
        for workshop_id in (detail.get("meta", {}).get("dependencies_mods") or {}).keys():
            workshop_id = str(workshop_id or "").strip()
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

        这是普通模式允许使用的公开详情通道：走旧版 GetPublishedFileDetails，
        不读取 Steam Web API Key。需要 Key 的增强详情统一走 IPublishedFileService.GetDetails。

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
    def get_workshop_details(cls, workshop_ids: list, trace_label: str = "") -> dict[str, dict[str, Any]]:
        normalized_ids: list[str] = []
        seen_ids: set[str] = set()
        for raw_id in workshop_ids or []:
            workshop_id = normalize_workshop_id(raw_id, digits_only=True, min_length=6, max_length=20)
            if not workshop_id or workshop_id in seen_ids:
                continue
            seen_ids.add(workshop_id)
            normalized_ids.append(workshop_id)
        if not normalized_ids:
            return {}

        cached_details = {}
        online_details = {}
        try:
            cached_details = ExtDAO.get_workshop_details_by_workshop_ids(normalized_ids) or {}
        except Exception as exc:
            logger.debug("查询本地创意工坊详情失败：%s", exc, exc_info=True)
        try:
            online_details, _ = cls.fetch_item_details(normalized_ids, trace_label=trace_label)
        except Exception as exc:
            logger.debug("查询在线创意工坊详情失败：%s", exc, exc_info=True)

        result: dict[str, dict[str, Any]] = {}
        for workshop_id in normalized_ids:
            cached = cached_details.get(workshop_id) or {}
            online = online_details.get(workshop_id) or {}
            cached_package_id = normalize_package_id(cached.get("package_id"))
            title = str(online.get("title") or cached.get("name") or "").strip()
            preview_url = online.get("preview_url") or cached.get("preview_url") or ""
            time_updated = int(online.get("time_updated") or cached.get("time_updated") or 0)
            has_online_detail = bool(str(online.get("title") or "").strip() or online.get("preview_url") or online.get("time_updated"))
            has_cached_detail = bool(str(cached.get("name") or "").strip() or cached.get("preview_url") or cached_package_id)
            result[workshop_id] = {
                "workshop_id": workshop_id,
                "package_id": cached_package_id,
                "title": title,
                "name": str(cached.get("name") or "").strip(),
                "author": cached.get("author") or [],
                "preview_url": preview_url,
                "url": cached.get("url") or cls.WORKSHOP_ITEM_URL.format(workshop_id=workshop_id),
                "time_updated": time_updated,
                "detail_source": "online" if has_online_detail else ("database" if has_cached_detail else "unavailable"),
                "available": bool(has_online_detail or has_cached_detail),
            }
        return result

    @classmethod
    def search_workshop_enhanced(
        cls,
        query: str,
        cursor: str = "*",
        page_size: int = 25,
        sort: str = "relevance",
        language: Any = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        调用 QueryFiles 在线搜索 Steam Workshop。

        增强搜索专用：QueryFiles 属于 IPublishedFileService，必须有 API Key；
        普通模式不得绕到这里，否则会破坏“无 Key 可用”的基础体验。

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
        normalized_filters = cls._normalize_online_search_filters(filters)
        if language is not None and normalized_filters["language"] == cls._resolve_steam_query_language(None):
            normalized_filters["language"] = cls._resolve_steam_query_language(language)
        query_type = cls._resolve_online_query_type(normalized_filters, query_type)

        params: dict[str, Any] = {
            "key": api_key,
            "format": "json",
            "query_type": query_type,
            "page": 1,
            "cursor": normalized_cursor,
            "numperpage": normalized_page_size,
            "creator_appid": cls.RIMWORLD_APP_ID,
            "appid": cls.RIMWORLD_APP_ID,
            "match_all_tags": normalized_filters["match_all_tags"],
            "required_flags": normalized_filters["required_flags"],
            "omitted_flags": normalized_filters["omitted_flags"],
            "search_text": search_text,
            "filetype": normalized_filters["filetype"],
            "include_recent_votes_only": normalized_filters["include_recent_votes_only"],
            "cache_max_age_seconds": 300,
            "language": normalized_filters["language"],
            "ids_only": 0,
            "return_vote_data": normalized_filters["return_vote_data"],
            "return_tags": 1,
            "return_previews": 1,
            "return_children": 1,
            "return_short_description": 0,
            "return_metadata": normalized_filters["return_metadata"],
            "return_kv_tags": normalized_filters["return_kv_tags"],
            "return_for_sale_data": normalized_filters["return_for_sale_data"],
            "return_playtime_stats": normalized_filters["return_playtime_stats"],
            "return_details": normalized_filters["return_details"],
            "strip_description_bbcode": normalized_filters["strip_description_bbcode"],
        }
        if normalized_filters["child_publishedfileid"]:
            params["child_publishedfileid"] = normalized_filters["child_publishedfileid"]
        if normalized_filters["days"] > 0:
            params["days"] = normalized_filters["days"]
        for key in ("special_filter", "search_text_target", "desired_revision"):
            if normalized_filters.get(key) not in (None, ""):
                params[key] = normalized_filters[key]
        # Steam Service 接口的数组不能用逗号或空括号序列化，否则标签过滤会被忽略或误判为单个标签。
        cls._add_indexed_params(params, "requiredtags", normalized_filters["required_tags"])
        cls._add_indexed_params(params, "excludedtags", normalized_filters["excluded_tags"])
        cls._add_indexed_dict_params(params, "required_kv_tags", normalized_filters.get("required_kv_tags"))
        cls._add_taggroups_params(params, normalized_filters.get("taggroups"))
        cls._add_date_range_params(params, "date_range_created", normalized_filters.get("date_range_created"))
        cls._add_date_range_params(params, "date_range_updated", normalized_filters.get("date_range_updated"))
        cls._add_indexed_params(params, "excluded_content_descriptors", normalized_filters.get("excluded_content_descriptors"))
        required_appids = [
            *list(normalized_filters.get("appids_required_for_use") or []),
            *list(normalized_filters.get("required_dlc_appids") or []),
        ]
        cls._add_indexed_params(params, "appids_required_for_use", required_appids)
        cls._add_indexed_params(params, "excluded_appids_required_for_use", normalized_filters.get("excluded_appids_required_for_use"))
        payload = cls._request_json("GET", cls.QUERY_FILES_URL, params=params)
        response = cls._require_response_dict(payload, "Steam QueryFiles")
        raw_items = cls._require_response_list(payload, "publishedfiledetails", "Steam QueryFiles")
        items = [cls._normalize_query_file_item(item) for item in raw_items if isinstance(item, dict)]
        if filters and filters.get("force_details", filters.get("forceDetails", False)):
            detail_map = cls.fetch_published_file_service_details(
                [item["workshop_id"] for item in items if item.get("workshop_id")],
                language=normalized_filters["language"],
                options={
                    "language": normalized_filters["language"],
                    "return_playtime_stats": normalized_filters["return_playtime_stats"],
                    "strip_description_bbcode": False,
                },
            )
            items = [
                {**item, **detail_map.get(str(item.get("workshop_id") or ""), {})}
                for item in items
            ]
        if not bool((filters or {}).get("skip_author_profiles") or (filters or {}).get("skipAuthorProfiles")):
            items = cls._attach_author_profiles(items)
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
            "language": normalized_filters["language"],
            "filters": normalized_filters,
            "source": "steam_online",
        }

    @classmethod
    def search_workshop_items_enhanced(cls, query: str, cursor: str = "*", page_size: int = 100, sort: str = "relevance", filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """增强搜索普通工坊物品。QueryFiles 已返回完整列表展示字段，不重复拉取详情。"""
        next_filters = {**(filters or {}), "filetype": int(SteamPublishedFileMatchingFileType.ITEMS), "force_details": False, "strip_description_bbcode": False}
        return cls.search_workshop_enhanced(query, cursor=cursor, page_size=page_size, sort=sort, filters=next_filters)

    @classmethod
    def search_workshop_collections_enhanced(cls, query: str, cursor: str = "*", page_size: int = 100, sort: str = "relevance", filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """增强搜索合集，合集子项优先使用 QueryFiles 的 children 字段。"""
        next_filters = {**(filters or {}), "filetype": int(SteamPublishedFileMatchingFileType.COLLECTIONS), "force_details": False, "strip_description_bbcode": False}
        data = cls.search_workshop_enhanced(query, cursor=cursor, page_size=page_size, sort=sort, filters=next_filters)
        data["source"] = "steam_collection_online"
        return data

    @classmethod
    def search_workshop_dependents_enhanced(cls, workshop_id: str, *, cursor: str = "*", page_size: int = 20, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """搜索引用指定工坊项的关联生态。"""
        target_id = cls._require_workshop_id(workshop_id, "依赖工坊 ID")
        next_filters = {
            **(filters or {}),
            "child_publishedfileid": target_id,
            "filetype": int(SteamPublishedFileMatchingFileType.ITEMS),
            "force_details": False,
            "strip_description_bbcode": False,
            "days": 7,
        }
        return cls.search_workshop_enhanced("", cursor=cursor, page_size=page_size, sort="trend", filters=next_filters)

    @classmethod
    def get_enhanced_workshop_detail(cls, workshop_id: str, current_detail: dict[str, Any] | None = None) -> dict[str, Any]:
        """获取增强详情本体，不阻塞等待关联推荐。"""
        normalized_id = cls._require_workshop_id(workshop_id, "工坊 ID")
        detail = dict(current_detail or {})
        if not detail or not detail.get("description"):
            fetched_detail = cls.fetch_published_file_service_details([normalized_id]).get(normalized_id, {})
            detail = {**detail, **fetched_detail}
        if not detail:
            return {}
        if not detail.get("workshop_id"):
            detail["workshop_id"] = normalized_id
        if not detail.get("game_versions"):
            detail["game_versions"] = cls._extract_game_versions_from_tags(list(detail.get("tags") or []))
        if not detail.get("description"):
            detail["description"] = detail.get("short_description") or ""
        return detail

    @classmethod
    def get_workshop_dependencies_enhanced(cls, workshop_id: str, current_detail: dict[str, Any] | None = None, limit: int | None = None) -> dict[str, Any]:
        """获取当前工坊项依赖的父项详情；合集则返回合集子项详情。"""
        normalized_id = cls._require_workshop_id(workshop_id, "工坊 ID")
        detail = cls.get_enhanced_workshop_detail(normalized_id, current_detail=current_detail)
        if not detail:
            return {"items": [], "total": 0, "has_more": False, "source": "steam_dependencies"}
        # Steam 增强接口里 children 不是单一语义：
        # - 普通物品：children 表示当前项依赖的父项；
        # - 合集：children 表示合集包含的工坊项。
        # 下方通过 item_type 区分展示分组，避免把合集子项误当依赖项目。
        dependency_ids = [
            str(child.get("workshop_id") or child.get("publishedfileid") or "").strip()
            for child in (detail.get("children") or [])
            if str(child.get("workshop_id") or child.get("publishedfileid") or "").strip()
        ]
        if limit:
            dependency_ids = dependency_ids[:max(1, cls._safe_int(limit))]
        detail_map = cls.fetch_published_file_service_details(dependency_ids, options={"skip_author_profiles": True}) if dependency_ids else {}
        items = [
            detail_map.get(workshop_id) or {"workshop_id": workshop_id, "title": workshop_id, "name": workshop_id}
            for workshop_id in dependency_ids
            if workshop_id != normalized_id
        ]
        return {
            "items": items,
            "total": len(dependency_ids),
            "has_more": False,
            "item_type": detail.get("item_type") or "mod",
            "source": "steam_collection_children" if detail.get("item_type") == "collection" else "steam_dependencies",
        }

    @classmethod
    def get_workshop_same_author_enhanced(
        cls,
        workshop_id: str,
        *,
        author_steam_id: str = "",
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """增强模式：通过作者 SteamID 调 GetUserFiles，分页获取同作者作品。"""
        normalized_id = cls._require_workshop_id(workshop_id, "工坊 ID")
        author_id = str(author_steam_id or "").strip()
        if not author_id:
            detail = cls.get_enhanced_workshop_detail(normalized_id)
            author_id = str(detail.get("author_steam_id") or "").strip()
        if not author_id:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "has_more": False, "source": "steam_same_author"}
        normalized_page = max(1, cls._safe_int(page, default=1))
        normalized_page_size = cls._normalize_online_page_size(page_size)
        next_filters = {
            **(filters or {}),
            "filetype": int(SteamPublishedFileMatchingFileType.ITEMS),
            "return_vote_data": True,
        }
        author_files = cls.get_user_files(author_id, page=normalized_page, page_size=normalized_page_size, filters=next_filters)
        items = [
            item for item in author_files.get("items", [])
            if str(item.get("workshop_id") or "") != normalized_id
        ][:normalized_page_size]
        # GetUserFiles 的 total 包含当前详情项本身；同作者作品展示会过滤当前项。
        # 如果不同步修正 total，前端会误以为还差当前项这一条，导致“查看全部”和滚动加载一直触发。
        raw_total = cls._safe_int(author_files.get("total"))
        filtered_total = max(0, raw_total - 1)
        return {
            "items": items,
            "total": filtered_total,
            "page": normalized_page,
            "page_size": normalized_page_size,
            "has_more": normalized_page * normalized_page_size < filtered_total,
            "author_steam_id": author_id,
            "source": "steam_same_author",
        }

    @classmethod
    def _normalize_published_file_service_detail_item(cls, item: dict[str, Any]) -> dict[str, Any]:
        """整理 IPublishedFileService.GetDetails 返回的富详情。"""
        normalized = cls._normalize_published_file_item(item, source="service")
        normalized["result"] = cls._safe_int(item.get("result"))
        return normalized

    @classmethod
    def _cacheable_detail_fields(cls, item: dict[str, Any]) -> dict[str, object]:
        """截取在线缓存表能保存的字段，避免临时展示字段污染写库结构。"""
        return {
            "title": item.get("title") or item.get("name") or "",
            "short_description": item.get("short_description") or "",
            "description": item.get("description") or "",
            "author_steam_id": item.get("author_steam_id") or "",
            "preview_url": item.get("preview_url") or None,
            "tags": list(item.get("tags") or []),
            "children": list(item.get("children") or []),
            "screenshots": item.get("screenshots") or [],
            "time_created": cls._safe_int(item.get("time_created")),
            "time_updated": cls._safe_int(item.get("time_updated")),
            "stats": item.get("stats") or {},
            "item_type": item.get("item_type") or "mod",
            "consumer_app_id": cls._safe_int(item.get("consumer_app_id") or item.get("consumer_appid")),
            "file_size": cls._safe_int(item.get("file_size")),
            "status": item.get("status") or {},
            "maybe_inappropriate_sex": cls._normalize_service_bool(item.get("maybe_inappropriate_sex")),
            "maybe_inappropriate_violence": cls._normalize_service_bool(item.get("maybe_inappropriate_violence")),
            "revision_change_number": cls._safe_int(item.get("revision_change_number")),
            "kv_tags": item.get("kv_tags") or [],
            "playtime_stats": item.get("playtime_stats"),
        }

    @classmethod
    def fetch_published_file_service_details(
        cls,
        workshop_ids: list,
        *,
        language: Any = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """增强模式详情通道：精确 ID 批量获取，优先复用在线缓存，缺失时才调用 GetDetails。"""
        normalized_ids = cls._normalize_workshop_ids(workshop_ids)
        if not normalized_ids:
            return {}
        options = options or {}
        force_refresh = bool(options.get("force_refresh") or options.get("forceRefresh"))
        if force_refresh:
            result: dict[str, dict[str, Any]] = {}
            ids_to_fetch = normalized_ids
        else:
            result, ids_to_fetch = cls._load_cached_online_details(normalized_ids, cls.CACHE_TTL_MS)
        if not ids_to_fetch:
            return result

        api_key = cls._require_steam_web_api_key()
        for i in range(0, len(ids_to_fetch), 100):
            batch_ids = ids_to_fetch[i : i + 100]
            params: dict[str, Any] = {
                "key": api_key,
                "format": "json",
                "includetags": cls._normalize_service_bool(options.get("includetags", True)),
                "includeadditionalpreviews": cls._normalize_service_bool(options.get("includeadditionalpreviews", True)),
                "includechildren": cls._normalize_service_bool(options.get("includechildren", True)),
                "includekvtags": cls._normalize_service_bool(options.get("includekvtags", options.get("include_kv_tags", True))),
                "includevotes": cls._normalize_service_bool(options.get("includevotes", True)),
                "short_description": cls._normalize_service_bool(options.get("short_description", False)),
                "includeforsaledata": cls._normalize_service_bool(options.get("includeforsaledata", False)),
                "includemetadata": cls._normalize_service_bool(options.get("includemetadata", False)),
                "return_playtime_stats": cls._normalize_service_bool(options.get("return_playtime_stats", False)),
                "appid": cls._safe_int(options.get("appid"), default=cls.RIMWORLD_APP_ID),
                "strip_description_bbcode": cls._normalize_service_bool(options.get("strip_description_bbcode", False)),
                "language": cls._resolve_steam_query_language(language if language not in (None, "") else options.get("language")),
            }
            for key in ("desired_revision", "admin_query"):
                if options.get(key) not in (None, ""):
                    params[key] = options[key]
            cls._add_indexed_params(params, "publishedfileids", batch_ids)
            payload = cls._request_published_file_service("GetDetails", params=params)
            details = cls._require_response_list(payload, "publishedfiledetails", "Steam GetDetails")
            for item in details:
                if not isinstance(item, dict):
                    continue
                normalized_item = cls._normalize_published_file_service_detail_item(item)
                workshop_id = normalized_item.get("workshop_id")
                if workshop_id:
                    result[str(workshop_id)] = normalized_item
        fetched_result = {workshop_id: result[workshop_id] for workshop_id in ids_to_fetch if workshop_id in result}
        if fetched_result and not bool(options.get("skip_author_profiles") or options.get("skipAuthorProfiles")):
            cls._attach_author_profiles(list(fetched_result.values()))
        if fetched_result:
            sync_time = int(time.time() * 1000)
            cls._save_online_details(fetched_result, sync_time)
        return result

    @classmethod
    def get_or_fetch_details(cls, workshop_id: str, *, include_screenshot_fallback: bool = False):
        """
        普通模式详情本体；关联项由详情页独立接口并发加载。

        注意：
        - 这里允许使用公开 GetPublishedFileDetails 补全详情，但不能调用任何需要 API Key 的接口；
        - 截图抓取默认改为异步预热，避免点击详情时被网页抓取阻塞；
        - 只有显式要求时，才在这里同步触发截图抓取兜底。
        """
        meta = ExtDAO.get_merged_meta_by_workshop_id(workshop_id)
        current_time = int(time.time() * 1000)
        if not meta or not meta.get("description") or (current_time - int(meta.get("detail_last_sync_time") or meta.get("last_sync_time") or 0) > cls.CACHE_TTL_MS):
            cls.fetch_item_details([workshop_id], trace_label="workshop_detail:normal")
            meta = ExtDAO.get_merged_meta_by_workshop_id(workshop_id)
        if not meta: return None

        screenshots = list(meta.get("screenshots") or [])
        if include_screenshot_fallback and not screenshots:
            screenshots = cls._fetch_screenshots_via_scraper(workshop_id)
            if screenshots:
                cls._upsert_online_cache_batch([{
                    "workshop_id": str(workshop_id or "").strip(),
                    "screenshots": screenshots,
                    "last_sync_time": current_time,
                }])
                meta["screenshots"] = screenshots

        detail = ExtDAO.get_workshop_detail(workshop_id)
        if not detail or not detail.get("meta", {}): return None
        response = detail.get("meta", {})
        if not response.get("game_versions"):
            response["game_versions"] = cls._extract_game_versions_from_tags(list(response.get("tags") or []))
        if not response.get("description"):
            response["description"] = response.get("short_description") or ""
        response.update(
            {
                "replacement_mod": detail.get("replacement"),
            }
        )
        return response

    @classmethod
    def fetch_and_cache_screenshots(cls, workshop_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        """
        单独补当前项截图，供普通模式详情页后台增量更新使用。

        设计原因：
        - 列表和详情本体可以先靠公开详情秒开；
        - 网页抓图单独放后台，避免一次点击把公开详情、截图和关联信息串成同步长链路。
        """
        normalized_id = cls._require_workshop_id(workshop_id, "工坊 ID")
        meta = ExtDAO.get_merged_meta_by_workshop_id(normalized_id) or {}
        cached_screenshots = list(meta.get("screenshots") or [])
        if cached_screenshots and not force_refresh:
            return {"workshop_id": normalized_id, "screenshots": cached_screenshots}

        screenshots = cls._fetch_screenshots_via_scraper(normalized_id)
        if screenshots:
            cls._upsert_online_cache_batch([{
                "workshop_id": normalized_id,
                "screenshots": screenshots,
                "last_sync_time": int(time.time() * 1000),
            }])
        return {"workshop_id": normalized_id, "screenshots": screenshots}

    @classmethod
    def _require_workshop_id(cls, value: Any, field_name: str = "publishedfileid") -> str:
        workshop_id = normalize_workshop_id(value, digits_only=True, min_length=6, max_length=20)
        if not workshop_id:
            raise ValueError(f"{field_name} 不能为空或格式不正确")
        return workshop_id

    @classmethod
    def _require_service_payload_fields(cls, payload: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("请求参数必须是对象")
        missing = [field for field in fields if payload.get(field) in (None, "")]
        if missing:
            raise ValueError(f"缺少必要参数: {', '.join(missing)}")
        data = {key: value for key, value in payload.items() if value not in (None, "")}
        data["key"] = cls._require_steam_web_api_key()
        return data

    @classmethod
    def _add_payload_tags(cls, data: dict[str, Any], payload: dict[str, Any], field_name: str = "tags") -> None:
        tags = cls._normalize_online_search_terms(payload.get(field_name))
        if tags:
            data.pop(field_name, None)
            cls._add_indexed_params(data, field_name, tags)

    @classmethod
    def get_user_files(
        cls,
        steamid: str,
        *,
        page: int = 1,
        page_size: int = 25,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """获取某个 Steam 用户发布的工坊文件。"""
        if not str(steamid or "").strip():
            raise ValueError("SteamID 不能为空")
        filters = filters or {}
        normalized_filters = cls._normalize_online_search_filters(filters)
        params: dict[str, Any] = {
            "key": cls._require_steam_web_api_key(),
            "format": "json",
            "steamid": str(steamid).strip(),
            "appid": cls._safe_int(filters.get("appid"), default=cls.RIMWORLD_APP_ID),
            "page": max(1, cls._safe_int(page, default=1)),
            "numperpage": cls._normalize_online_page_size(page_size),
            "type": str(normalize_steam_user_ugc_list(filters.get("type"), SteamUserUGCList.MY_FILES)),
            "sortmethod": str(normalize_steam_user_ugc_sort(filters.get("sortmethod") or filters.get("sortMethod"), SteamUserUGCListSortOrder.LAST_UPDATED)),
            "filetype": normalized_filters["filetype"],
            "language": normalized_filters["language"],
            "return_vote_data": normalized_filters["return_vote_data"],
            "return_tags": 1,
            "return_previews": 1,
            "return_children": 1,
            "return_short_description": 0,
            "return_metadata": normalized_filters["return_metadata"],
            "return_kv_tags": normalized_filters["return_kv_tags"],
            "return_playtime_stats": normalized_filters["return_playtime_stats"],
            "return_details": normalized_filters["return_details"],
            "strip_description_bbcode": normalized_filters["strip_description_bbcode"],
        }
        # GetUserFiles 同样走 Steam Service 参数解析，数组必须使用 0 基索引形式。
        cls._add_indexed_params(params, "requiredtags", normalized_filters["required_tags"])
        cls._add_indexed_params(params, "excludedtags", normalized_filters["excluded_tags"])
        cls._add_indexed_dict_params(params, "required_kv_tags", normalized_filters.get("required_kv_tags"))
        if filters.get("privacy") not in (None, ""):
            params["privacy"] = cls._safe_int(filters.get("privacy"))
        cls._add_date_range_params(params, "date_range_created", normalized_filters.get("date_range_created"))
        cls._add_date_range_params(params, "date_range_updated", normalized_filters.get("date_range_updated"))
        payload = cls._request_published_file_service("GetUserFiles", params=params)
        response = cls._require_response_dict(payload, "Steam GetUserFiles")
        raw_items = cls._require_response_list(payload, "publishedfiledetails", "Steam GetUserFiles")
        items = [cls._normalize_published_file_service_detail_item(item) for item in (raw_items or []) if isinstance(item, dict)]
        if not bool(filters.get("skip_author_profiles") or filters.get("skipAuthorProfiles")):
            items = cls._attach_author_profiles(items)
        cls._save_online_search_summaries(items, int(time.time() * 1000))
        return {
            "items": items,
            "total": cls._safe_int(response.get("total") if isinstance(response, dict) else 0),
            "page": params["page"],
            "page_size": params["numperpage"],
            "source": "steam_user_files",
        }

    @classmethod
    def get_user_file_count(cls, steamid: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """获取用户发布文件数量。"""
        if not str(steamid or "").strip():
            raise ValueError("SteamID 不能为空")
        filters = filters or {}
        params = {
            "key": cls._require_steam_web_api_key(),
            "format": "json",
            "steamid": str(steamid).strip(),
            "appid": cls._safe_int(filters.get("appid"), default=cls.RIMWORLD_APP_ID),
            "type": str(normalize_steam_user_ugc_list(filters.get("type"), SteamUserUGCList.MY_FILES)),
            "filetype": int(normalize_steam_matching_file_type(filters.get("filetype"), SteamPublishedFileMatchingFileType.ITEMS)),
            "privacy": cls._safe_int(filters.get("privacy"), default=0),
        }
        return cls._request_published_file_service("GetUserFileCount", params=params).get("response", {})

    @classmethod
    def get_user_vote_summary(cls, workshop_ids: list) -> dict[str, Any]:
        """批量获取当前 Key 对工坊项的投票摘要。"""
        normalized_ids = cls._normalize_workshop_ids(workshop_ids)
        if not normalized_ids:
            raise ValueError("工坊 ID 不能为空")
        params = {"key": cls._require_steam_web_api_key(), "format": "json"}
        cls._add_indexed_params(params, "publishedfileids", normalized_ids)
        return cls._request_published_file_service("GetUserVoteSummary", params=params).get("response", {})

    @classmethod
    def can_subscribe(cls, workshop_id: str) -> dict[str, Any]:
        """检查当前 Key 是否可订阅指定工坊项。"""
        params = {
            "key": cls._require_steam_web_api_key(),
            "format": "json",
            "publishedfileid": cls._require_workshop_id(workshop_id),
        }
        return cls._request_published_file_service("CanSubscribe", params=params).get("response", {})

    @classmethod
    def subscribe_published_file(cls, workshop_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        """备用订阅接口。普通用户 Key 能否成功由 Steam 判定。"""
        options = options or {}
        data = {
            "key": cls._require_steam_web_api_key(),
            "publishedfileid": cls._require_workshop_id(workshop_id),
            "list_type": cls._safe_int(options.get("list_type"), default=0),
            "appid": cls._safe_int(options.get("appid"), default=cls.RIMWORLD_APP_ID),
            "notify_client": cls._normalize_service_bool(options.get("notify_client", True)),
            "include_dependencies": cls._normalize_service_bool(options.get("include_dependencies", options.get("includeDependencies", False))),
        }
        return cls._request_published_file_service("Subscribe", http_method="POST", data=data).get("response", {})

    @classmethod
    def unsubscribe_published_file(cls, workshop_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        """备用取消订阅接口。"""
        options = options or {}
        data = {
            "key": cls._require_steam_web_api_key(),
            "publishedfileid": cls._require_workshop_id(workshop_id),
            "list_type": cls._safe_int(options.get("list_type"), default=0),
            "appid": cls._safe_int(options.get("appid"), default=cls.RIMWORLD_APP_ID),
            "notify_client": cls._normalize_service_bool(options.get("notify_client", True)),
        }
        return cls._request_published_file_service("Unsubscribe", http_method="POST", data=data).get("response", {})

    @classmethod
    def publish_file(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """创建工坊文件记录。文件来源与权限由 Steam 接口判定。"""
        data = cls._require_service_payload_fields(payload, ["appid", "consumer_appid", "cloudfilename", "previewfile", "title", "description", "file_type", "visibility"])
        cls._add_payload_tags(data, payload)
        return cls._request_published_file_service("Publish", http_method="POST", data=data).get("response", {})

    @classmethod
    def update_file(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """更新工坊文件。"""
        data = cls._require_service_payload_fields(payload, ["appid", "publishedfileid"])
        data["publishedfileid"] = cls._require_workshop_id(data.get("publishedfileid"))
        cls._add_payload_tags(data, payload)
        return cls._request_published_file_service("Update", http_method="POST", data=data).get("response", {})

    @classmethod
    def delete_file(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """删除工坊文件。"""
        data = cls._require_service_payload_fields(payload, ["appid", "publishedfileid"])
        data["publishedfileid"] = cls._require_workshop_id(data.get("publishedfileid"))
        return cls._request_published_file_service("Delete", http_method="POST", data=data).get("response", {})

    @classmethod
    def update_tags(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """增删工坊标签。"""
        data = cls._require_service_payload_fields(payload, ["appid", "publishedfileid"])
        data["publishedfileid"] = cls._require_workshop_id(data.get("publishedfileid"))
        cls._add_payload_tags(data, payload, "add_tags")
        cls._add_payload_tags(data, payload, "remove_tags")
        if not any(key.startswith("add_tags[") or key.startswith("remove_tags[") for key in data):
            raise ValueError("需要提供要添加或移除的标签")
        return cls._request_published_file_service("UpdateTags", http_method="POST", data=data).get("response", {})

    @classmethod
    def update_key_value_tags(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """更新工坊 Key/Value 标签。"""
        data = cls._require_service_payload_fields(payload, ["appid", "publishedfileid"])
        data["publishedfileid"] = cls._require_workshop_id(data.get("publishedfileid"))
        cls._add_indexed_dict_params(data, "add_tags", payload.get("add_tags") or payload.get("addTags"))
        cls._add_indexed_params(data, "remove_tags", payload.get("remove_tags") or payload.get("removeTags"))
        return cls._request_published_file_service("UpdateKeyValueTags", http_method="POST", data=data).get("response", {})

    @classmethod
    def set_developer_metadata(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """设置开发者元数据。"""
        data = cls._require_service_payload_fields(payload, ["appid", "publishedfileid", "metadata"])
        data["publishedfileid"] = cls._require_workshop_id(data.get("publishedfileid"))
        return cls._request_published_file_service("SetDeveloperMetadata", http_method="POST", data=data).get("response", {})

    @classmethod
    def fetch_collection_children(cls, collection_id: str) -> list:
        """解析合集，返回包含的全部正常 Mod ID 列表。"""
        data = {"collectioncount": "1", "publishedfileids[0]": str(collection_id)}
        try:
            payload = cls._request_json("POST", cls.COLLECTION_DETAILS_URL, data=data)
            details = cls._require_response_list(payload, "collectiondetails", "Steam CollectionDetails")
            if not details or not isinstance(details[0], dict) or not isinstance(details[0].get("children"), list):
                raise RuntimeError("Steam CollectionDetails 返回缺少 response.collectiondetails[0].children")
            children = details[0]["children"]
            return [str(c.get("publishedfileid")) for c in children if c.get("filetype") == int(SteamPublishedFileMatchingFileType.ITEMS)]
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
            logger.debug(f"正在触发网页抓取回退：MOD {workshop_id}")
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
            logger.info(f"网页抓取找到 {len(screenshots)} 张截图：{workshop_id}")
        except Exception as e:
            logger.error(f"网页抓取回退失败：{workshop_id}，错误：{e}")

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
    
    # search_res = SteamWebAPI.search_workshop_enhanced("rim tuber")
    # print(f"搜索结果: {search_res}")
    
    
