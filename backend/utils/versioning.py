import re
from typing import Iterable


def extract_major_game_version(version: str) -> str:
    """
    提取主版本号。

    示例：
    - 1.5.4069 rev95 -> 1.5
    - 1.6 -> 1.6
    - 1 -> 1
    """
    text = str(version or "").strip()
    if not text: return ""
    match = re.search(r"(\d+)(?:\.(\d+))?", text)
    if not match: return ""
    major = match.group(1)
    minor = match.group(2)
    return f"{major}.{minor}" if minor is not None else major


def matches_major_game_version(current_version: str, candidate_version: str) -> bool:
    current_major = extract_major_game_version(current_version)
    candidate_major = extract_major_game_version(candidate_version)
    if not current_major or not candidate_major: return False
    return current_major == candidate_major


def _version_tuple(version: str) -> tuple[int, int]:
    major = extract_major_game_version(version)
    if not major: return (-1, -1)
    parts = major.split(".")
    head = int(parts[0]) if parts and parts[0].isdigit() else -1
    tail = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return (head, tail)


def version_preference_key(current_version: str, candidate_versions: Iterable[str] | None) -> tuple[int, int, int, int]:
    """
    版本优先级排序键。

    排序优先级：
    1. 支持当前游戏版本
    2. 若不支持当前版本，则优先支持更高版本
    3. 再比较可支持的最高版本
    4. 再比较支持范围数量
    """
    values = [extract_major_game_version(str(v or "").strip()) for v in (candidate_versions or [])]
    values = [value for value in values if value]
    if not values: return (1, -1, -1, 0)

    unique_values = sorted({_version_tuple(value) for value in values})
    current_tuple = _version_tuple(current_version)
    supports_current = current_tuple in unique_values
    max_tuple = unique_values[-1] if unique_values else (-1, -1)
    supports_higher = current_tuple != (-1, -1) and max_tuple > current_tuple
    tier = 3 if supports_current else 2 if supports_higher else 0
    return (tier, max_tuple[0], max_tuple[1], len(unique_values))


def score_version_support(current_version: str, candidate_versions: Iterable[str] | None) -> int:
    """
    版本支持打分。

    返回值：
    - 2: 存在主版本匹配
    - 1: 没提供版本信息
    - 0: 明确存在版本列表，但没有匹配
    """
    values = [str(v or "").strip() for v in (candidate_versions or []) if str(v or "").strip()]
    if not values: return 1
    return 2 if any(matches_major_game_version(current_version, value) for value in values) else 0
