import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path | str, payload: Any, *, indent: int = 4, lock: Any = None) -> None:
    """
    以“同目录临时文件 + fsync + os.replace”写入 JSON。
    同目录替换能保证跨平台原子性；fsync 用于降低断电或崩溃时写入半截文件的风险。
    """
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    def _write() -> None:
        fd = None
        temp_path: Path | None = None
        try:
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{target_path.stem}.",
                suffix=".tmp",
                dir=str(target_path.parent),
            )
            temp_path = Path(temp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None
                json.dump(payload, handle, indent=indent, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target_path)
        except Exception:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    if lock is None:
        _write()
        return
    with lock:
        _write()
