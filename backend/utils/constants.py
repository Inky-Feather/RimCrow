from enum import IntEnum, StrEnum
from typing import Any

from backend.i18n.language_registry import (
    LANGUAGE_SPECS, SUPPORTED_LANGUAGE_CODES, get_language_english_name,
    get_language_label, get_language_options, get_language_spec,
    get_steam_elanguage_options, normalize_language_code, normalize_language_codes,
    to_external_language, to_steam_elanguage,
)

# 兼容旧调用名：历史上该函数用于返回 RimWorld Languages 目录名。
def get_lang_by_code(code):
    return get_language_english_name(code, default="English")


def to_steam_webapi_language_code(value, default: str = "en") -> str:
    return str(to_external_language(value, "code", default=default))


LANGUAGE_MAP = {spec.english_name: spec.code for spec in LANGUAGE_SPECS}
STEAM_WEBAPI_LANGUAGE_CODES = SUPPORTED_LANGUAGE_CODES


RIMWORLD_STEAM_APP_ID = 294100
RIMWORLD_STEAM_APP_ID_STR = str(RIMWORLD_STEAM_APP_ID)
RIMWORLD_WORKSHOP_CONTENT_PARTS = ("steamapps", "workshop", "content", RIMWORLD_STEAM_APP_ID_STR)
RIMWORLD_APPMANIFEST_NAME = f"appmanifest_{RIMWORLD_STEAM_APP_ID_STR}.acf"
RIMWORLD_APPWORKSHOP_NAME = f"appworkshop_{RIMWORLD_STEAM_APP_ID_STR}.acf"

RIMWORLD_DLC_APPID_PACKAGE_MAP = {
    RIMWORLD_STEAM_APP_ID: "ludeon.rimworld",
    1149640: "ludeon.rimworld.royalty",
    1392840: "ludeon.rimworld.ideology",
    1826140: "ludeon.rimworld.biotech",
    2380740: "ludeon.rimworld.anomaly",
    3022790: "ludeon.rimworld.odyssey",
}

RIMWORLD_DLC_OPTIONS = [
    {"label": "Core", "appid": RIMWORLD_STEAM_APP_ID, "package_id": "ludeon.rimworld"},
    {"label": "Royalty", "appid": 1149640, "package_id": "ludeon.rimworld.royalty"},
    {"label": "Ideology", "appid": 1392840, "package_id": "ludeon.rimworld.ideology"},
    {"label": "Biotech", "appid": 1826140, "package_id": "ludeon.rimworld.biotech"},
    {"label": "Anomaly", "appid": 2380740, "package_id": "ludeon.rimworld.anomaly"},
    {"label": "Odyssey", "appid": 3022790, "package_id": "ludeon.rimworld.odyssey"},
]


# --- Steam 工坊 Web API 枚举 -------------------------------------------------
# 这些值来自 SteamTracking / Steamworks 文档，集中放在这里避免请求代码里继续散落魔法数字。

class SteamPublishedFileQueryType(IntEnum):
    """IPublishedFileService.QueryFiles 的 query_type。"""

    RANKED_BY_VOTE = 0  # 按评分/投票排序
    RANKED_BY_PUBLICATION_DATE = 1  # 按发布时间排序
    ACCEPTED_FOR_GAME_RANKED_BY_ACCEPTANCE_DATE = 2  # 已被游戏接受的项目，按接受时间排序
    RANKED_BY_TREND = 3  # 趋势/热门排序
    FAVORITED_BY_FRIENDS_RANKED_BY_PUBLICATION_DATE = 4  # 好友收藏，按发布时间排序
    CREATED_BY_FRIENDS_RANKED_BY_PUBLICATION_DATE = 5  # 好友创建，按发布时间排序
    RANKED_BY_NUM_TIMES_REPORTED = 6  # 按举报数排序
    CREATED_BY_FOLLOWED_USERS_RANKED_BY_PUBLICATION_DATE = 7  # 关注用户创建，按发布时间排序
    NOT_YET_RATED = 8  # 尚未评分
    RANKED_BY_TOTAL_UNIQUE_SUBSCRIPTIONS = 9  # 按总订阅数排序
    RANKED_BY_TOTAL_VOTES_ASC = 10  # 按总投票数升序
    RANKED_BY_VOTES_UP = 11  # 按赞成票排序
    RANKED_BY_TEXT_SEARCH = 12  # 按文本相关性排序
    RANKED_BY_PLAYTIME_TREND = 13  # 按近期游玩时长趋势排序
    RANKED_BY_TOTAL_PLAYTIME = 14  # 按总游玩时长排序
    RANKED_BY_AVERAGE_PLAYTIME_TREND = 15  # 按近期平均游玩时长趋势排序
    RANKED_BY_LIFETIME_AVERAGE_PLAYTIME = 16  # 按生命周期平均游玩时长排序
    RANKED_BY_PLAYTIME_SESSIONS_TREND = 17  # 按近期游玩次数趋势排序
    RANKED_BY_LIFETIME_PLAYTIME_SESSIONS = 18  # 按生命周期游玩次数排序
    RANKED_BY_INAPPROPRIATE_CONTENT_RATING = 19  # 按不当内容评分排序
    RANKED_BY_BAN_CONTENT_CHECK = 20  # 按封禁内容检查结果排序
    RANKED_BY_LAST_UPDATED_DATE = 21  # 按最后更新时间排序
    RANKED_BY_NUM_PARENT_ITEMS = 22  # 按父项目数量排序
    RANKED_BY_NUM_PARENT_COLLECTIONS = 23  # 按父合集数量排序


class SteamPublishedFileMatchingFileType(IntEnum):
    """IPublishedFileService.QueryFiles/GetUserFiles 的 filetype 筛选枚举。"""

    ITEMS = 0  # 普通工坊项目
    COLLECTIONS = 1  # 合集
    ART = 2  # 艺术作品
    VIDEOS = 3  # 视频
    SCREENSHOTS = 4  # 截图
    COLLECTION_ELIGIBLE = 5  # 可加入合集的项目
    GAMES = 6  # 已废弃/未使用
    SOFTWARE = 7  # 已废弃/未使用
    CONCEPTS = 8  # 已废弃/未使用
    GREENLIGHT_ITEMS = 9  # 已废弃/未使用
    ALL_GUIDES = 10  # 指南
    WEB_GUIDES = 11  # Steam 网页指南
    INTEGRATED_GUIDES = 12  # 应用内指南
    USABLE_IN_GAME = 13  # 可在游戏中使用
    MERCH = 14  # 周边/商品投票项
    CONTROLLER_BINDINGS = 15  # 控制器绑定
    STEAMWORKS_ACCESS_INVITES = 16  # Steam 内部使用
    ITEMS_MTX = 17  # 可在游戏内销售的工坊项目
    ITEMS_READY_TO_USE = 18  # 用户可直接使用的工坊项目
    WORKSHOP_SHOWCASE = 19  # 工坊展示
    GAME_MANAGED_ITEMS = 20  # 完全由游戏管理的项目


class SteamWorkshopFileType(IntEnum):
    """Steam 返回字段 file_type 使用的 EWorkshopFileType。"""

    COMMUNITY = 0  # 普通可订阅工坊项目
    MICROTRANSACTION = 1  # 游戏内售卖候选项
    COLLECTION = 2  # 合集
    ART = 3  # 艺术作品
    VIDEO = 4  # 外部视频
    SCREENSHOT = 5  # 截图
    GAME = 6  # 已废弃/未使用
    SOFTWARE = 7  # 已废弃/未使用
    CONCEPT = 8  # 已废弃/未使用
    WEB_GUIDE = 9  # Steam 网页指南
    INTEGRATED_GUIDE = 10  # 应用内指南
    MERCH = 11  # 周边/商品投票项
    CONTROLLER_BINDING = 12  # 控制器绑定
    STEAMWORKS_ACCESS_INVITE = 13  # Steam 内部使用
    STEAM_VIDEO = 14  # Steam 视频
    GAME_MANAGED_ITEM = 15  # 完全由游戏管理的项目
    MAX = 16  # 枚举边界


class SteamRemoteStoragePublishedFileVisibility(IntEnum):
    """工坊项目可见性。"""

    PUBLIC = 0  # 公开
    FRIENDS_ONLY = 1  # 仅好友可见
    PRIVATE = 2  # 仅作者可见
    UNLISTED = 3  # 不在全局查询中展示


class SteamUserUGCList(StrEnum):
    """GetUserFiles 的 type 字符串枚举。"""

    MY_FILES = "myfiles"  # 用户自己发布的内容
    VOTED_ON = "votedon"  # 用户投票过的内容
    VOTED_UP = "votedup"  # 用户赞过的内容
    VOTED_DOWN = "voteddown"  # 用户踩过的内容
    WILL_VOTE_LATER = "willvotelater"  # 稍后投票
    FAVORITES = "favorites"  # 收藏
    SUBSCRIBED = "subscribed"  # 已订阅
    USED_ITEMS = "used_items"  # 使用/游玩过
    FOLLOWED = "followed"  # 关注内容


class SteamUserUGCListSortOrder(StrEnum):
    """GetUserFiles 的 sortmethod 字符串枚举。"""

    NEWEST_FIRST = "newestfirst"  # 创建时间降序
    OLDEST_FIRST = "oldestfirst"  # 创建时间升序
    TITLE_ASC = "alpha"  # 标题 A-Z
    LAST_UPDATED = "lastupdated"  # 最后更新时间降序
    SUBSCRIPTION_DATE = "subscriptiondate"  # 订阅时间降序
    SCORE = "score"  # 评分/好评率
    FOR_MODERATION = "formoderation"  # 管理审核排序


class SteamSearchTextTarget(IntEnum):
    """QueryFiles 的 search_text_target。"""

    TITLE_AND_DESCRIPTION = 0  # 默认：标题和描述
    TITLE = 1  # 仅标题
    DESCRIPTION = 2  # 仅描述


def _coerce_int_enum(enum_cls: type[IntEnum], value: Any, default: IntEnum) -> IntEnum:
    """把前端传入的数字、枚举名或业务别名收束到明确枚举值。"""
    if isinstance(value, enum_cls):
        return value
    if value not in (None, ""):
        try:
            return enum_cls(int(value))
        except (TypeError, ValueError):
            normalized = str(value).strip().upper().replace("-", "_")
            if normalized in enum_cls.__members__:
                return enum_cls[normalized]
    return default


def normalize_steam_query_type(value: Any, default: SteamPublishedFileQueryType = SteamPublishedFileQueryType.RANKED_BY_TEXT_SEARCH) -> SteamPublishedFileQueryType:
    return _coerce_int_enum(SteamPublishedFileQueryType, value, default)


def normalize_steam_matching_file_type(value: Any, default: SteamPublishedFileMatchingFileType = SteamPublishedFileMatchingFileType.ITEMS) -> SteamPublishedFileMatchingFileType:
    aliases = {
        "mod": SteamPublishedFileMatchingFileType.ITEMS,
        "mods": SteamPublishedFileMatchingFileType.ITEMS,
        "item": SteamPublishedFileMatchingFileType.ITEMS,
        "items": SteamPublishedFileMatchingFileType.ITEMS,
        "collection": SteamPublishedFileMatchingFileType.COLLECTIONS,
        "collections": SteamPublishedFileMatchingFileType.COLLECTIONS,
    }
    normalized = str(value or "").strip().lower()
    if normalized in aliases:
        return aliases[normalized]
    return _coerce_int_enum(SteamPublishedFileMatchingFileType, value, default)


def normalize_steam_workshop_file_type(value: Any, default: SteamWorkshopFileType = SteamWorkshopFileType.COMMUNITY) -> SteamWorkshopFileType:
    return _coerce_int_enum(SteamWorkshopFileType, value, default)


def normalize_steam_search_text_target(value: Any, default: SteamSearchTextTarget = SteamSearchTextTarget.TITLE_AND_DESCRIPTION) -> SteamSearchTextTarget:
    aliases = {
        "all": SteamSearchTextTarget.TITLE_AND_DESCRIPTION,
        "both": SteamSearchTextTarget.TITLE_AND_DESCRIPTION,
        "title_description": SteamSearchTextTarget.TITLE_AND_DESCRIPTION,
        "title_and_description": SteamSearchTextTarget.TITLE_AND_DESCRIPTION,
    }
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in aliases:
        return aliases[normalized]
    return _coerce_int_enum(SteamSearchTextTarget, value, default)


def normalize_steam_user_ugc_list(value: Any, default: SteamUserUGCList = SteamUserUGCList.MY_FILES) -> SteamUserUGCList:
    try:
        return SteamUserUGCList(str(value or "").strip().lower())
    except ValueError:
        return default


def normalize_steam_user_ugc_sort(value: Any, default: SteamUserUGCListSortOrder = SteamUserUGCListSortOrder.LAST_UPDATED) -> SteamUserUGCListSortOrder:
    try:
        return SteamUserUGCListSortOrder(str(value or "").strip().lower())
    except ValueError:
        return default


def steam_appids_to_rimworld_package_ids(values) -> list[str]:
    """把 RimWorld / DLC 的 Steam AppID 转成缓存依赖里使用的 package_id。"""
    if isinstance(values, (str, int)):
        raw_values = [values]
    elif isinstance(values, (list, tuple, set)):
        raw_values = values
    else:
        raw_values = []

    package_ids: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        try:
            appid = int(str(value or "").strip())
        except (TypeError, ValueError):
            continue
        package_id = RIMWORLD_DLC_APPID_PACKAGE_MAP.get(appid)
        if not package_id or package_id in seen:
            continue
        seen.add(package_id)
        package_ids.append(package_id)
    return package_ids
