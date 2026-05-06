# backend/managers/mgr_steam_api.py
import re
import time
from pathlib import Path

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

from backend.database.dao_ext import ExtDAO
from backend.database.models_ext import WorkshopOnlineCache, ext_db
from backend.settings import settings
from backend.utils.logger import logger


class SteamWebAPI:
    """Steam 官方无密钥开放接口，极致轻量。"""

    BASE_URL = "https://api.steampowered.com"
    CACHE_TTL_MS = 1 * 24 * 60 * 60 * 1000

    @classmethod
    def _normalize_workshop_ids(cls, workshop_ids: list) -> list[str]:
        """规范化并保序去重请求 ID，避免重复请求同一条 Steam 详情。"""
        normalized_ids: list[str] = []
        seen_ids: set[str] = set()
        for workshop_id in workshop_ids:
            normalized_id = str(workshop_id or "").strip()
            if not normalized_id or normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            normalized_ids.append(normalized_id)
        return normalized_ids

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
            if current_time - int(item.last_sync_time or 0) < cache_ttl_ms:
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
            url = f"{cls.BASE_URL}/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
            data = {
                "itemcount": len(batch_ids),
                "includepreviews": 1,
            }
            for idx, wid in enumerate(batch_ids):
                data[f"publishedfileids[{idx}]"] = str(wid)  # type: ignore

            try:
                res = requests.post(url, data=data, timeout=10)
                res_data = res.json().get("response", {}).get("publishedfiledetails", [])
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
    def _save_online_details(cls, details_map: dict[str, dict[str, object]], sync_time: int) -> None:
        """将统一结构的在线详情批量落入缓存表。"""
        cache_batch = [
            {
                "workshop_id": workshop_id,
                **detail,
                "last_sync_time": sync_time,
            }
            for workshop_id, detail in details_map.items()
        ]
        cls._upsert_online_cache_batch(cache_batch)

    @classmethod
    def _upsert_online_cache_batch(cls, cache_batch: list[dict[str, object]]):
        """批量写入在线缓存，并只覆盖在线字段。"""
        if not cache_batch:
            return
        with ext_db.atomic():
            WorkshopOnlineCache.insert_many(cache_batch).on_conflict(
                conflict_target=[WorkshopOnlineCache.workshop_id],
                preserve=[
                    WorkshopOnlineCache.title,
                    WorkshopOnlineCache.description,
                    WorkshopOnlineCache.preview_url,
                    WorkshopOnlineCache.screenshots,
                    WorkshopOnlineCache.time_updated,
                    WorkshopOnlineCache.last_sync_time,
                ],
            ).execute()

    @classmethod
    def fetch_item_details(cls, workshop_ids: list, force_refresh=False, only_cache=False, cache_ttl_hours=None):
        """
        获取 Mod 或合集详情，自带本地在线缓存拦截。

        在线缓存单独落在 `WorkshopOnlineCache` 中：
        - 文件导入阶段只更新 `WorkshopManifest`；
        - TTL 刷新阶段只更新 `WorkshopOnlineCache` 中的在线字段。
        """
        if not workshop_ids:
            return {}, []

        normalized_ids = cls._normalize_workshop_ids(workshop_ids)
        if not normalized_ids:
            return {}, []

        results: dict[str, dict] = {}
        cache_ttl_ms = cache_ttl_hours * 60 * 60 * 1000 if cache_ttl_hours else cls.CACHE_TTL_MS

        if not force_refresh:
            results, ids_to_fetch = cls._load_cached_online_details(normalized_ids, cache_ttl_ms)
            logger.debug(f"从在线缓存中获取 {len(results)} 条数据")
        else:
            ids_to_fetch = normalized_ids

        if only_cache:
            return results, ids_to_fetch

        if ids_to_fetch:
            logger.debug(f"需要从 Steam API 获取 {len(ids_to_fetch)} 条数据")
            current_time = int(time.time() * 1000)
            fetched_details = cls._request_published_file_details(ids_to_fetch)
            results.update(fetched_details)
            cls._save_online_details(fetched_details, current_time)

        return results, ids_to_fetch

    @classmethod
    def get_or_fetch_details(cls, workshop_id: str):
        """获取单个模组详情，包含图文、同作者推荐、反向依赖、替代方案。"""
        meta = ExtDAO.get_merged_meta_by_workshop_id(workshop_id)
        current_time = int(time.time() * 1000)
        if not meta or not meta.get("description") or (current_time - int(meta.get("last_sync_time") or 0) > cls.CACHE_TTL_MS):
            cls.fetch_item_details([workshop_id], force_refresh=True)
            meta = ExtDAO.get_merged_meta_by_workshop_id(workshop_id)
        if not meta:
            return None

        screenshots = list(meta.get("screenshots") or [])
        if not screenshots:
            screenshots = cls._fetch_screenshots_via_scraper(workshop_id)
            if screenshots:
                WorkshopOnlineCache.update(
                    screenshots=screenshots,
                ).where(WorkshopOnlineCache.workshop_id == workshop_id).execute()
                meta["screenshots"] = screenshots

        detail = ExtDAO.get_workshop_detail_extended(workshop_id)
        if not detail or not detail.get("meta", {}):
            return None

        response = detail.get("meta", {})
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
        url = f"{cls.BASE_URL}/ISteamRemoteStorage/GetCollectionDetails/v1/"
        data = {"collectioncount": "1", "publishedfileids[0]": str(collection_id)}
        try:
            res = requests.post(url, data=data, timeout=10)
            children = res.json().get("response", {}).get("collectiondetails", [{}])[0].get("children", [])
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
        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={workshop_id}"
        screenshots = []

        try:
            # 使用 network_mgr 提供的代理环境
            # proxies = network_mgr.get_proxy_env()
            lang = settings.config.language.lower()
            prefix, suffix = lang.split("-", 1)
            steam_lang = f"{prefix}-{suffix.upper()}"
            # 伪装浏览器 User-Agent 避免被拦截
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": f"{steam_lang};q=0.9,en;q=0.8",
            }
            logger.debug(f"Triggering Scraper Fallback for Mod: {workshop_id}")
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            html_content = resp.text
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
    # 测试用例：解析合集
    collection_id = "3670074636"
    # children = SteamWebAPI.fetch_collection_children(collection_id)
    # print(f"合集 {collection_id} 包含 {len(children)} 个 Mod")
    #  # 测试用例：解析 Mod 详情
    mod_id = '3009527756'
    details = SteamWebAPI.fetch_item_details([mod_id], True)
    print(f"Mod {mod_id} 详情: {details}")
    
    # screenshots = SteamWebAPI._fetch_screenshots_via_scraper(mod_id)
    # print(f"Mod 截图: {screenshots}")
    
