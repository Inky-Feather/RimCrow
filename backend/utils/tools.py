import os
import hashlib
import time

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