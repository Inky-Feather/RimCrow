import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from backend.paths.core import canonicalize_path_text, path_key


def _canonicalize_path(raw_path: str) -> str:
    value = str(raw_path or "").strip()
    if not value:
        raise ValueError("用户数据路径不能为空")
    return canonicalize_path_text(value)


@dataclass(frozen=True)
class UserDataRoot:
    """
    表达 RimWorld 用户数据根目录的值对象。

    这个 Module 的职责是把所有根目录 canonicalize、默认路径误填纠偏、
    以及 `Config` / `Saves` / `ModsConfig.xml` 的派生收敛到一处。
    """

    root_path: str
    was_corrected: bool = False

    @classmethod
    def from_raw(cls, raw_path: str, default_roots: Sequence[str] | None = None):
        normalized = _canonicalize_path(raw_path)
        fixed_root = cls._try_fix_default_like_path(normalized, default_roots or [])
        if fixed_root:
            return cls(root_path=fixed_root, was_corrected=path_key(fixed_root) != path_key(normalized))
        if cls._looks_like_child_path(normalized):
            raise ValueError("user_data_path 必须指向用户数据根目录，不能直接指向 Config、Saves 或 ModsConfig.xml")
        return cls(root_path=normalized, was_corrected=False)

    @staticmethod
    def _try_fix_default_like_path(path: str, default_roots: Sequence[str]) -> str:
        normalized_path = _canonicalize_path(path)
        for default_root_raw in default_roots:
            default_root = _canonicalize_path(default_root_raw)
            config_dir = os.path.join(default_root, "Config")
            saves_dir = os.path.join(default_root, "Saves")
            mods_config = os.path.join(config_dir, "ModsConfig.xml")
            if path_key(normalized_path) in {
                path_key(default_root),
                path_key(config_dir),
                path_key(saves_dir),
                path_key(mods_config),
            }:
                return default_root
        return ""

    @staticmethod
    def _looks_like_child_path(path: str) -> bool:
        path_obj = Path(str(path or ""))
        name = path_obj.name.lower()
        parent_name = path_obj.parent.name.lower() if path_obj.parent else ""
        if name in {"config", "saves"}:
            return True
        if name == "modsconfig.xml" and parent_name == "config":
            return True
        return False

    def equivalent_to(self, other_path: str) -> bool:
        return path_key(self.root_path) == path_key(_canonicalize_path(other_path))

    @property
    def config_dir(self) -> str:
        return os.path.join(self.root_path, "Config")

    @property
    def saves_dir(self) -> str:
        return os.path.join(self.root_path, "Saves")

    @property
    def mods_config_file(self) -> str:
        return os.path.join(self.config_dir, "ModsConfig.xml")
