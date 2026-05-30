import json
import re
import uuid
from pathlib import Path
from typing import Any

from backend.settings import DATA_DIR


THEMES_PATH = DATA_DIR / "themes.json"
THEME_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


class ThemeStore:
    """管理用户自定义主题；内置主题由前端只读资源提供。"""

    def __init__(self, path: Path = THEMES_PATH):
        self.path = path

    def _empty_payload(self) -> dict[str, Any]:
        return {"schema_version": 1, "themes": []}

    def _load_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty_payload()
        with open(self.path, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("themes.json 根节点必须是对象")
        themes = payload.get("themes", [])
        if not isinstance(themes, list):
            raise ValueError("themes.json themes 必须是数组")
        return {"schema_version": int(payload.get("schema_version") or 1), "themes": themes}

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(self.path.name + ".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
        temp_path.replace(self.path)

    def _normalize_theme(self, theme: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(theme, dict):
            raise ValueError("主题数据必须是对象")
        theme_id = str(theme.get("id") or "").strip()
        if not theme_id:
            theme_id = f"custom-theme-{uuid.uuid4().hex[:8]}"
        if not THEME_ID_PATTERN.match(theme_id):
            raise ValueError("主题 ID 只能包含小写字母、数字、短横线和下划线，长度 2-64")
        name = str(theme.get("name") or "").strip()
        if not name:
            raise ValueError("主题名称不能为空")
        tokens = theme.get("tokens")
        if not isinstance(tokens, dict):
            raise ValueError("主题 tokens 必须是对象")
        return {
            "id": theme_id,
            "name": name,
            "builtin": False,
            "tokens": tokens,
        }

    def list_user_themes(self) -> list[dict[str, Any]]:
        payload = self._load_payload()
        return [self._normalize_theme(theme) for theme in payload["themes"]]

    def save_user_theme(self, theme: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_theme(theme)
        payload = self._load_payload()
        themes = []
        replaced = False
        for item in payload["themes"]:
            existing_id = str(item.get("id") or "")
            if existing_id == normalized["id"]:
                themes.append(normalized)
                replaced = True
            else:
                themes.append(item)
        if not replaced:
            themes.append(normalized)
        payload["themes"] = themes
        self._write_payload(payload)
        return normalized

    def delete_user_theme(self, theme_id: str) -> bool:
        normalized_id = str(theme_id or "").strip()
        if not THEME_ID_PATTERN.match(normalized_id):
            raise ValueError("主题 ID 不合法")
        payload = self._load_payload()
        themes = [theme for theme in payload["themes"] if str(theme.get("id") or "") != normalized_id]
        changed = len(themes) != len(payload["themes"])
        if changed:
            payload["themes"] = themes
            self._write_payload(payload)
        return changed
