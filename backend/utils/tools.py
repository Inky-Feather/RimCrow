import os
import shutil
import time
import zipfile
import hashlib
from pathlib import Path
from typing import Any
from send2trash import send2trash

def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """对字符串列表做保序去重。"""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

def generate_path_hash(path: str) -> str:
    """
    根据路径生成唯一的哈希值。
    统一使用规范化的绝对路径并转为小写，以处理 Windows 的大小写不敏感问题。
    """
    if not path:
        return ""
    normalized_path = os.path.abspath(path).lower()
    return hashlib.md5(normalized_path.encode('utf-8')).hexdigest()


def current_ms():
    """获取当前的毫秒级时间戳"""
    return int(time.time() * 1000)


def get_folder_size(path: str) -> int:
    """
    高效计算文件夹总大小 (字节)
    """
    total_size = 0
    try:
        # 使用栈代替递归，防止层级过深，且在 Python 中通常更快
        stack = [path]
        while stack:
            current_path = stack.pop()
            with os.scandir(current_path) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False):
                        total_size += entry.stat().st_size
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
    except Exception:
        # 如果遇到权限问题或路径消失，忽略该部分大小
        pass
    return total_size


def extract_zip(zip_path: str, target_dir: str) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(target_dir)


def normalize_package_id(package_id: Any) -> str:
    return str(package_id or "").strip().lower()


def normalize_package_ids(package_ids: list[Any]) -> list[str]:
    """
    批量规范化 package_id，并在保持输入顺序的前提下去重。

    这个函数适合“批量接口入口清洗”这类弱领域场景：
    它不依赖数据库模型，也不关心调用方是 DAO、导入检查还是 API。
    """
    normalized = [normalize_package_id(package_id) for package_id in package_ids]
    return _dedupe_preserve_order([package_id for package_id in normalized if package_id])


def is_hex_color(color: Any) -> bool:
    """判断字符串是否是 `#RRGGBB` 形式的颜色值。"""
    text = str(color or "").strip()
    if len(text) != 7 or not text.startswith("#"):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in text[1:])


def normalize_hex_color(color: Any, default: str = "#ffffff") -> str:
    """
    规范化颜色值；不合法时回退到默认值。

    这里不抛异常，适合“尽量纠正输入”的场景；
    如果调用方需要严格校验，可以先调用 `is_hex_color()`。
    """
    text = str(color or "").strip()
    if is_hex_color(text):
        return text
    return default


def normalize_workshop_id(
    workshop_id: Any,
    *,
    digits_only: bool = False,
    min_length: int = 1,
    max_length: int | None = None,
    zero_is_empty: bool = True,
) -> str:
    value = str(workshop_id or "").strip()
    if not value:
        return ""
    if digits_only and not value.isdigit():
        return ""
    if zero_is_empty:
        if value == "0":
            return ""
        if value.isdigit() and int(value) == 0:
            return ""
    if len(value) < min_length:
        return ""
    if max_length is not None and len(value) > max_length:
        return ""
    return value



def delete_fs_path(path: str, force: bool = False) -> bool:
    """Delete a file or directory.

    When ``force`` is False, move the target to the system trash/recycle bin.
    When ``force`` is True, remove it permanently.
    """
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        return False

    if force:
        if os.path.isdir(abs_path) and not os.path.islink(abs_path):
            shutil.rmtree(abs_path)
        else:
            Path(abs_path).unlink()
    else:
        send2trash(abs_path)

    return True