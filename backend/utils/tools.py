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








