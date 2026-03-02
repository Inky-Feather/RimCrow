# backend/managers/mgr_steam_api.py
from pathlib import Path
import re
import requests
import time


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

from backend.utils.logger import logger
from backend.settings import settings
# from backend.managers.mgr_network import network_mgr
from backend.database.models_ext import WorkshopMeta, ext_db

class SteamWebAPI:
    """Steam 官方无密钥开放接口，极致轻量"""
    BASE_URL = "https://api.steampowered.com"
    CACHE_TTL_MS = 1 * 24 * 60 * 60 * 1000  # 缓存有效期 1 天
    
    @classmethod
    def fetch_item_details(cls, workshop_ids: list, force_refresh=False, only_cache=False, cache_ttl_hours=None) :
        """
        获取 Mod 或 合集 的详情，自带本地 SQLite 缓存拦截。
        返回格式: { "12345": { "title": "...", "time_updated": 123, ... } }
        """
        if not workshop_ids: return {}
        
        current_time = int(time.time() * 1000)
        results = {}
        ids_to_fetch = []
        # 自定义缓存有效期
        cache_ttl_ms = cache_ttl_hours * 60 * 60 * 1000 if cache_ttl_hours else cls.CACHE_TTL_MS

        # 1. 检查本地缓存
        if not force_refresh:
            cached_items = WorkshopMeta.select().where(WorkshopMeta.workshop_id.in_(workshop_ids)) # type: ignore
            for item in cached_items:
                if current_time - item.last_sync_time < cache_ttl_ms:
                    results[item.workshop_id] = {
                        "title": item.title,
                        "description": item.description,
                        "preview_url": item.preview_url,
                        "time_updated": item.time_updated
                    }
            logger.debug(f"从缓存中获取 {len(results)} 条数据")
            # 挑出缓存失效或不存在的 ID
            ids_to_fetch = [wid for wid in workshop_ids if wid not in results]
        else:
            ids_to_fetch = workshop_ids
            
        # 仅返回缓存数据
        if only_cache: return results, ids_to_fetch
    
        # 2. 从网络获取缺失的数据
        if ids_to_fetch:
            logger.debug(f"需要从 Steam API 获取 {len(ids_to_fetch)} 条数据")
            # 每次最多 100 个，分批请求
            for i in range(0, len(ids_to_fetch), 100):
                batch_ids = ids_to_fetch[i:i+100]
                url = f"{cls.BASE_URL}/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
                data = {
                    "itemcount": len(batch_ids),
                    "includepreviews": 1 # 【关键】强制要求返回预览图列表
                }
                for idx, wid in enumerate(batch_ids):
                    data[f"publishedfileids[{idx}]"] = str(wid) # type: ignore
                try:
                    res = requests.post(url, data=data, timeout=10)
                    res_data = res.json().get("response", {}).get("publishedfiledetails", [])
                    # print(f"Steam API 返回 {len(res_data)} 条数据",res_data)
                    cache_batch = []
                    for item in res_data:
                        wid = str(item.get("publishedfileid"))
                        # 【解析截图】提取所有 type 为 0 的图片地址
                        previews = item.get("previews", [])
                        screenshots = [p.get("url") for p in previews if p.get("preview_type") == 0]
                        # 【兜底】如果 API 未返回截图，尝试从 HTML 中提取
                        # if not screenshots: 
                        #     screenshots = cls._fetch_screenshots_via_scraper(wid)
                        detail = {
                            "title": item.get("title"),
                            "description": item.get("description", ""),
                            "preview_url": item.get("preview_url"),
                            "screenshots": screenshots,
                            "time_updated": int(item.get("time_updated", 0)) * 1000
                        }
                        results[wid] = detail
                        # 准备写入缓存
                        cache_batch.append({
                            "workshop_id": wid,
                            **detail,
                            "last_sync_time": current_time
                        })
                    
                    # 获取 user_data_list 中出现过的所有键，取交集，确保只更新传入的字段
                    input_keys = set().union(*(d.keys() for d in cache_batch))
                    update_fields = [
                        field for field in WorkshopMeta._meta.sorted_fields  # type: ignore
                        if field.name in input_keys and field.name != "workshop_id"
                    ]
                    # 批量更新缓存
                    with ext_db.atomic():
                        WorkshopMeta.insert_many(cache_batch).on_conflict(
                            conflict_target=[WorkshopMeta.workshop_id],
                            preserve=update_fields
                        ).execute()
                        
                except Exception as e:
                    logger.error(f"Steam API 请求失败: {e}")

        return results, ids_to_fetch
    
    @classmethod
    def get_or_fetch_details(cls, workshop_id: str):
        """获取单个模组详情（缓存命中则直接返回，否则触发拉取）"""
        meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == workshop_id)
        current_time = int(time.time() * 1000)
        # 检查是否需要更新缓存
        if not meta or not meta.description or (current_time - meta.last_sync_time > cls.CACHE_TTL_MS):
            cls.fetch_and_cache_batch([workshop_id])
            meta = WorkshopMeta.get_or_none(WorkshopMeta.workshop_id == workshop_id)
        if not meta: return None
        screenshots = cls._fetch_screenshots_via_scraper(workshop_id)
        return {
            "workshop_id": meta.workshop_id,
            "title": meta.name,
            "package_id": meta.package_id,
            "description": meta.description,
            "preview_url": meta.preview_url,
            "screenshots": screenshots,
            "time_updated": meta.time_updated,
            "dependencies_mods": meta.dependencies_mods
        }

    @classmethod
    def fetch_and_cache_batch(cls, workshop_ids: list):
        """批量从 Steam 获取并写入外置数据库"""
        if not workshop_ids: return
        current_time = int(time.time() * 1000)
        for i in range(0, len(workshop_ids), 100):
            batch_ids = workshop_ids[i:i+100]
            url = f"{cls.BASE_URL}/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
            data = {"itemcount": len(batch_ids)}
            for idx, wid in enumerate(batch_ids):
                data[f"publishedfileids[{idx}]"] = str(wid) # type: ignore
            try:
                res = requests.post(url, data=data, timeout=10)
                res_data = res.json().get("response", {}).get("publishedfiledetails", [])
                
                with ext_db.atomic():
                    for item in res_data:
                        wid = str(item.get("publishedfileid"))
                        # SQLite Upsert (On Conflict Update)
                        WorkshopMeta.insert(
                            workshop_id=wid,
                            description=item.get("description", ""),
                            preview_url=item.get("preview_url", ""),
                            time_updated=int(item.get("time_updated", 0)) * 1000,
                            last_sync_time=current_time
                        ).on_conflict()(
                            conflict_target=[WorkshopMeta.workshop_id],
                            preserve=[WorkshopMeta.description, WorkshopMeta.preview_url, WorkshopMeta.time_updated, WorkshopMeta.last_sync_time]
                        ).execute()
            except Exception as e:
                logger.error(f"Steam API 同步失败: {e}")

    @classmethod
    def fetch_collection_children(cls, collection_id: str) -> list:
        """解析合集，返回包含的全部正常 Mod ID 列表"""
        url = f"{cls.BASE_URL}/ISteamRemoteStorage/GetCollectionDetails/v1/"
        data = {"collectioncount": "1", "publishedfileids[0]": str(collection_id)}
        try:
            res = requests.post(url, data=data, timeout=10)
            children = res.json().get('response', {}).get('collectiondetails', [{}])[0].get('children', [])
            return [str(c.get('publishedfileid')) for c in children if c.get('filetype') == 0]
        except Exception as e:
            logger.error(f"解析合集失败: {e}")
            return []
    
    @classmethod
    def _fetch_screenshots_via_scraper(cls, workshop_id: str) -> list:
        """
        网页爬取备选方案：正则提取 rgScreenshotURLs
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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': f'{steam_lang};q=0.9,en;q=0.8'
            }
            logger.debug(f"Triggering Scraper Fallback for Mod: {workshop_id}")
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            html_content = resp.text
            # 核心：正则匹配变量内容
            # 匹配 rgScreenshotURLs = { ... }; 
            pattern = re.compile(r'rgScreenshotURLs\s*=\s*\{(.*?)\};', re.DOTALL)
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
    mod_id = '3671245310'
    
    # details = SteamWebAPI.fetch_item_details([mod_id], True)
    details = SteamWebAPI.get_or_fetch_details(mod_id)
    print(f"Mod {mod_id} 详情: {details}")
    
    # screenshots = SteamWebAPI._fetch_screenshots_via_scraper(mod_id)
    # print(f"Mod 截图: {screenshots}")
    
    
    
