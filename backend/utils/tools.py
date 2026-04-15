import os
import hashlib
import time
import zipfile
from typing import Any

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


def normalize_workshop_id( workshop_id: Any, *, digits_only: bool = False, min_length: int = 1, max_length: int | None = None, zero_is_empty: bool = True ) -> str:
    value = str(workshop_id or "").strip()
    if not value: return ""
    if digits_only and not value.isdigit(): return ""
    if zero_is_empty:
        if value == "0": return ""
        if value.isdigit() and int(value) == 0: return ""
    if len(value) < min_length: return ""
    if max_length is not None and len(value) > max_length: return ""
    return value
