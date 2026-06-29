from __future__ import annotations

import base64
import json
import os
import platform
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.managers.mgr_game import GameManager
from backend.settings import BASE_RESOURCE_DIR, DATA_DIR
from backend.utils.constants import RIMWORLD_STEAM_APP_ID_STR
from backend.utils.logger import logger
from backend.utils.tools import current_ms

KNOWN_INSTALLS_PATH = DATA_DIR / "known_game_installs.json"


def _canonicalize_path_text(path_str: str) -> str:
    """
    统一路径文本。

    这里优先用 `Path.resolve(strict=False)`，是为了把 Windows 的 8.3 短路径
    尽量展开成长路径；失败时再回退到 `abspath`，避免因为单个异常把缓存流程打断。
    """
    raw_value = str(path_str or "").strip()
    if not raw_value:
        return ""
    try:
        return os.path.normpath(str(Path(raw_value).expanduser().resolve(strict=False)))
    except Exception:
        return os.path.normpath(os.path.abspath(raw_value))


@dataclass(frozen=True)
class GameInstallFacts:
    install_path: str = ""
    executable_path: str = ""
    game_version: str = ""
    is_steam: bool = False
    is_steam_managed: bool = False
    steam_api_path: str = ""
    steam_appid_path: str = ""
    steam_api_probe: str = "skipped"
    signals: list[str] = field(default_factory=list)
    checked_at: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GameInstallFacts":
        if not data:
            return cls()
        return cls(
            install_path=str(data.get("install_path") or ""),
            executable_path=str(data.get("executable_path") or ""),
            game_version=str(data.get("game_version") or ""),
            is_steam=bool(data.get("is_steam")),
            is_steam_managed=bool(data.get("is_steam_managed")),
            steam_api_path=str(data.get("steam_api_path") or ""),
            steam_appid_path=str(data.get("steam_appid_path") or ""),
            steam_api_probe=str(data.get("steam_api_probe") or "skipped"),
            signals=[str(item) for item in (data.get("signals") or []) if str(item).strip()],
            checked_at=int(data.get("checked_at") or 0),
        )


def detect_is_steam_managed_install(path_str: str) -> bool:
    """
    只返回“路径是否位于 Steam 主库目录”这一条弱事实。

    注意：
    - 它不代表正版；
    - 它不代表当前副本一定可被 Steam 正常接管；
    - 最终 `is_steam_managed` 必须建立在 `is_steam=True` 之上。
    """
    normalized_parts = [part.lower() for part in Path(os.path.normpath(str(path_str or ""))).parts]
    return any(
        normalized_parts[index:index + 2] == ["steamapps", "common"]
        for index in range(max(0, len(normalized_parts) - 1))
    )


class GameInstallRegistry:
    def __init__(self, path: Path = KNOWN_INSTALLS_PATH):
        # 只作为缓存文件定位，不需要暴露给 pywebview 的 API 反射层。
        self._path = path
        self._cache: dict[str, Any] | None = None
        self._write_lock = threading.Lock()

    def _normalize_key(self, install_path: str) -> str:
        return os.path.normcase(_canonicalize_path_text(install_path))

    def _load(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = {"installs": {}}
            return self._cache
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            installs = payload.get("installs") if isinstance(payload, dict) else {}
            self._cache = {"installs": installs if isinstance(installs, dict) else {}}
        except Exception as exc:
            logger.warning(f"读取已知游戏本体缓存失败，将回退到空缓存: {exc}")
            try:
                corrupt_path = self._path.with_name(self._path.name + ".corrupt")
                self._path.replace(corrupt_path)
            except Exception:
                pass
            self._cache = {"installs": {}}
        return self._cache

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_name(self._path.name + ".tmp")
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, self._path)

    def get(self, install_path: str) -> GameInstallFacts | None:
        key = self._normalize_key(install_path)
        if not key:
            return None
        payload = self._load()["installs"].get(key)
        return GameInstallFacts.from_dict(payload) if isinstance(payload, dict) else None

    def set(self, facts: GameInstallFacts) -> None:
        key = self._normalize_key(facts.install_path)
        if not key:
            return
        with self._write_lock:
            payload = self._load()
            payload["installs"][key] = asdict(facts)
            self._write_payload(payload)

    def prune_invalid_entries(self) -> int:
        """
        启动阶段清理 `known_game_installs.json`。

        这里集中处理三类历史脏数据：
        1. 安装目录已失效，或已找不到游戏可执行文件；
        2. 同一路径因为短路径/长路径差异产生了重复 key；
        3. 旧缓存里 `is_steam_managed` 沿用了“只看路径”的旧语义。
        """
        payload = self._load()
        installs = payload.get("installs")
        if not isinstance(installs, dict) or not installs:
            return 0

        normalized_installs: dict[str, dict[str, Any]] = {}
        removed_count = 0
        changed = False

        for raw_key, raw_item in installs.items():
            facts = GameInstallFacts.from_dict(raw_item if isinstance(raw_item, dict) else None)
            install_path = _canonicalize_path_text(facts.install_path or raw_key)
            executable_path = str(GameManager.detect_executable(install_path) or "") if install_path else ""
            if not install_path or not executable_path:
                removed_count += 1
                changed = True
                continue

            normalized_facts = GameInstallFacts(
                install_path=install_path,
                executable_path=executable_path,
                game_version=facts.game_version,
                is_steam=bool(facts.is_steam),
                is_steam_managed=bool(facts.is_steam and detect_is_steam_managed_install(install_path)),
                steam_api_path=str(facts.steam_api_path or ""),
                steam_appid_path=str(facts.steam_appid_path or ""),
                steam_api_probe=str(facts.steam_api_probe or "skipped"),
                signals=list(facts.signals or []),
                checked_at=int(facts.checked_at or 0),
            )
            normalized_payload = asdict(normalized_facts)
            normalized_key = self._normalize_key(install_path)
            existing = normalized_installs.get(normalized_key)
            if existing is None or int(existing.get("checked_at") or 0) <= normalized_facts.checked_at:
                normalized_installs[normalized_key] = normalized_payload

            if raw_key != normalized_key or normalized_payload != (raw_item if isinstance(raw_item, dict) else {}):
                changed = True

        if not changed:
            return removed_count

        self._cache = {"installs": normalized_installs}
        self._write_payload(self._cache)
        return removed_count


class GameInstallInspector:
    _startup_prune_lock = threading.Lock()
    _startup_pruned = False

    def __init__(self):
        self.registry = GameInstallRegistry()
        with self._startup_prune_lock:
            if not self.__class__._startup_pruned:
                # `quick_inspect()` 在 UI 路径检查里会高频实例化；
                # 启动清理只做一次，避免每次输入框失焦都扫缓存文件。
                removed_count = self.registry.prune_invalid_entries()
                if removed_count:
                    logger.info(f"启动时已剔除 {removed_count} 条无效游戏本体缓存记录。")
                self.__class__._startup_pruned = True

    @staticmethod
    def _normalize_install_path(install_path: str) -> str:
        return _canonicalize_path_text(install_path)

    @staticmethod
    def _read_appid(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return ""

    @staticmethod
    def _dedupe_paths(paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        result: list[Path] = []
        for path in paths:
            normalized = os.path.normcase(os.path.normpath(str(path)))
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(path)
        return result

    def _find_app_bundle_path(self, executable_path: str) -> Path | None:
        exe_path = Path(str(executable_path or ""))
        if exe_path.suffix.lower() == ".app":
            return exe_path
        for candidate in [exe_path, *exe_path.parents]:
            if candidate.suffix.lower() == ".app":
                return candidate
        return None

    def _unity_data_dir_candidates(self, root: Path, executable_path: str) -> list[Path]:
        exe_path = Path(str(executable_path or ""))
        names = {name for name in (exe_path.stem, "RimWorldWin64", "RimWorldWin", "RimWorldLinux") if name}
        return self._dedupe_paths([root / f"{name}_Data" for name in names])

    def _candidate_appid_paths(self, install_path: str, executable_path: str = "") -> list[Path]:
        """
        收集 RimWorld 各平台常见的 `steam_appid.txt` 位置。

        对 RimWorld 来说，Windows/Linux 通常在安装根目录；
        macOS Steam 版常见于 `.app` 根目录，某些直启场景也可能跟随 `Contents/MacOS`。
        """
        root = Path(install_path)
        candidates = [root / "steam_appid.txt"]
        if executable_path:
            exe_path = Path(executable_path)
            candidates.append(exe_path.parent / "steam_appid.txt")
            app_bundle = self._find_app_bundle_path(executable_path)
            if app_bundle:
                candidates.append(app_bundle / "steam_appid.txt")
                candidates.append(app_bundle / "Contents" / "MacOS" / "steam_appid.txt")
        candidates.append(root / "RimWorldMac.app" / "steam_appid.txt")
        return self._dedupe_paths(candidates)

    def _candidate_steam_api_paths(self, install_path: str, executable_path: str = "") -> list[Path]:
        """
        收集 RimWorld 各平台常见的 Steam API 动态库位置。

        这里按 RimWorld 实际发布布局收口，不再泛化假设“总在 exe 同级”：
        - Windows: `RimWorldWin64_Data/Plugins/x86_64/steam_api64.dll`
        - Linux: `RimWorldLinux_Data/Plugins/libsteam_api.so`
        - macOS: `RimWorldMac.app/Contents/PlugIns/steam_api.bundle/...`
        """
        root = Path(install_path)
        system = platform.system()
        candidates: list[Path] = []

        if system == "Windows":
            # Steam 版根目录仍可能直接放 DLL，但 RimWorld 当前主布局在 Unity Data/Plugins 下。
            candidates.extend([root / "steam_api64.dll", root / "steam_api.dll"])
            for data_dir in self._unity_data_dir_candidates(root, executable_path):
                candidates.extend(
                    [
                        data_dir / "Plugins" / "x86_64" / "steam_api64.dll",
                        data_dir / "Plugins" / "x86" / "steam_api.dll",
                        data_dir / "Plugins" / "steam_api64.dll",
                        data_dir / "Plugins" / "steam_api.dll",
                    ]
                )
        elif system == "Linux":
            candidates.append(root / "libsteam_api.so")
            for data_dir in self._unity_data_dir_candidates(root, executable_path):
                candidates.append(data_dir / "Plugins" / "libsteam_api.so")
        elif system == "Darwin":
            # macOS Steam 版常见于 `steam_api.bundle`，同时保留较保守的 fallback 目录。
            app_bundle = self._find_app_bundle_path(executable_path) or (root if root.suffix.lower() == ".app" else root / "RimWorldMac.app")
            candidates.extend(
                [
                    app_bundle / "Contents" / "PlugIns" / "steam_api.bundle" / "Contents" / "MacOS" / "libsteam_api.dylib",
                    app_bundle / "Contents" / "MacOS" / "libsteam_api.dylib",
                    app_bundle / "Contents" / "Frameworks" / "libsteam_api.dylib",
                    app_bundle / "Contents" / "MacOS" / "libsteam_api.so",
                    app_bundle / "Contents" / "Frameworks" / "libsteam_api.so",
                ]
            )

        if executable_path:
            exe_path = Path(executable_path)
            candidates.extend(
                [
                    exe_path.parent / "steam_api64.dll",
                    exe_path.parent / "steam_api.dll",
                    exe_path.parent / "libsteam_api.so",
                    exe_path.parent / "libsteam_api.dylib",
                ]
            )
        return self._dedupe_paths(candidates)

    def _find_steam_api_path(self, install_path: str, executable_path: str = "") -> str:
        for candidate in self._candidate_steam_api_paths(install_path, executable_path):
            if candidate.is_file():
                return str(candidate)
        return ""

    def _find_appid_path(self, install_path: str, executable_path: str = "") -> str:
        for candidate in self._candidate_appid_paths(install_path, executable_path):
            if candidate.is_file():
                return str(candidate)
        return ""

    def _scan_install_layout(self, normalized_path: str) -> dict[str, Any]:
        executable = GameManager.detect_executable(normalized_path)
        executable_path = str(executable or "")
        steam_api_path = self._find_steam_api_path(normalized_path, executable_path)
        steam_appid_path = self._find_appid_path(normalized_path, executable_path)
        appid_match = bool(
            steam_appid_path
            and self._read_appid(Path(steam_appid_path)) == RIMWORLD_STEAM_APP_ID_STR
        )
        is_steam_library_path = detect_is_steam_managed_install(normalized_path)

        signals: list[str] = []
        if appid_match:
            signals.append("steam_appid")
        if steam_api_path:
            signals.append("steam_api")
        if is_steam_library_path:
            signals.append("steam_library_path")

        return {
            "executable_path": executable_path,
            "game_version": GameManager.get_game_version(normalized_path) if executable_path else "",
            "steam_api_path": steam_api_path,
            "steam_appid_path": steam_appid_path,
            "appid_match": appid_match,
            "is_steam_library_path": is_steam_library_path,
            "signals": signals,
        }

    def _probe_official_steam_api(self, install_path: str, steam_api_path: str, steam_appid_path: str = "") -> str:
        """
        用“伪造 appid + 原始安装目录”校验当前副本实际会加载的 Steam API。

        原理：
        - 官方 `steam_api` 在假 AppID 下通常初始化失败；
        - 常见破解模拟器会直接返回成功；
        - 探针直接在真实游戏目录执行，避免复制 DLL 后改变它的装载环境。
        """
        if not install_path or not steam_api_path or not os.path.isfile(steam_api_path):
            return "missing"

        target_appid_path = steam_appid_path or str(Path(install_path) / "steam_appid.txt")
        payload = base64.urlsafe_b64encode(json.dumps({
            "install_path": install_path,
            "steam_api_path": steam_api_path,
            "steam_appid_path": target_appid_path,
        }, ensure_ascii=False).encode("utf-8")).decode("ascii").rstrip("=")
        cmd = [sys.executable]
        if not getattr(sys, "frozen", False):
            cmd.append(str(BASE_RESOURCE_DIR / "main.py"))
        cmd.extend(["--steam-worker", "steam-api-probe", payload])

        current_env = os.environ.copy()
        current_env["_PYI_SPLASH_IPC"] = "0"
        current_env["PYINSTALLER_SUPPRESS_SPLASH_SCREEN"] = "1"
        current_env["PYTHONIOENCODING"] = "utf-8"
        startupinfo = None
        if platform.system() == "Windows" and hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            completed = subprocess.run(
                cmd,
                cwd=install_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                check=False,
                startupinfo=startupinfo,
                env=current_env,
            )
        except subprocess.TimeoutExpired:
            return "timeout"
        except Exception as exc:
            logger.debug(f"Steam API 校验启动失败: {exc}")
            return "probe_error"

        marker = "STEAM_API_PROBE_RESULT:"
        for line in reversed(str(completed.stdout or "").splitlines()):
            if line.startswith(marker):
                result = line[len(marker):].strip().lower()
                if result in {"official", "emulator", "missing"}:
                    return result
                return "probe_error"
        if completed.returncode != 0:
            return "probe_error"
        return "unknown"

    def quick_inspect(self, install_path: str) -> GameInstallFacts:
        """
        读穿缓存探测。

        用途：
        - 已有记录：直接复用完整探测缓存；
        - 新路径：立即补一次完整探测并落缓存，避免前后结果不一致；
        - 运行时仍然按当前路径动态刷新 `is_steam_managed`。
        """
        normalized_path = self._normalize_install_path(install_path)
        if not normalized_path:
            return GameInstallFacts()

        cached = self.registry.get(normalized_path)
        if not cached:
            return self.inspect(normalized_path, force=True)

        layout = self._scan_install_layout(normalized_path)
        signals = list(layout["signals"])
        signals.append("known_install_cache")
        return GameInstallFacts(
            install_path=normalized_path,
            executable_path=layout["executable_path"],
            game_version=layout["game_version"],
            is_steam=bool(cached.is_steam),
            is_steam_managed=bool(cached.is_steam and layout["is_steam_library_path"]),
            steam_api_path=layout["steam_api_path"],
            steam_appid_path=layout["steam_appid_path"],
            steam_api_probe=cached.steam_api_probe or "skipped",
            signals=signals,
            checked_at=cached.checked_at,
        )

    def inspect(self, install_path: str, *, force: bool = False) -> GameInstallFacts:
        """
        完整探测并写入已知本体缓存。

        触发时机应尽量收敛到：
        - 环境创建；
        - 游戏安装路径变更；
        - 升级迁移归一化。
        这样既能保证结果可信，也不会把 Steam API 探针变成高频操作。
        """
        normalized_path = self._normalize_install_path(install_path)
        if not normalized_path:
            return GameInstallFacts()

        cached = self.registry.get(normalized_path)
        if cached and not force:
            return cached

        layout = self._scan_install_layout(normalized_path)
        probe_result = self._probe_official_steam_api(
            normalized_path,
            layout["steam_api_path"],
            layout["steam_appid_path"],
        )
        signals = list(layout["signals"])
        if probe_result == "official":
            signals.append("steam_api_verified")
            is_steam = True
        elif probe_result == "emulator":
            signals.append("steam_api_emulator")
            is_steam = False
        else:
            if probe_result not in {"missing", "skipped"}:
                signals.append(f"probe_fallback:{probe_result}")
            # 探针异常时回退到“appid + 官方接口文件存在”的弱判定，
            # 避免因为系统动态库装载差异把真实 Steam 副本误判成非 Steam。
            # 这条回退规则只在探针本身失败时生效；若探针明确命中模拟器，则直接判否。
            is_steam = bool(
                layout["steam_api_path"]
                and layout["steam_appid_path"]
                and self._read_appid(Path(layout["steam_appid_path"])) == RIMWORLD_STEAM_APP_ID_STR
            )

        facts = GameInstallFacts(
            install_path=normalized_path,
            executable_path=layout["executable_path"],
            game_version=layout["game_version"],
            is_steam=is_steam,
            is_steam_managed=bool(is_steam and layout["is_steam_library_path"]),
            steam_api_path=layout["steam_api_path"],
            steam_appid_path=layout["steam_appid_path"],
            steam_api_probe=probe_result,
            signals=signals,
            checked_at=current_ms(),
        )
        self.registry.set(facts)
        return facts
