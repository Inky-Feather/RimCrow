# backend/platform/steamworks_ctypes.py
"""macOS Steamworks 后端（ctypes 直连 RimWorld 自带的 libsteam_api.dylib）。

设计目标：
* 不依赖、不打包、不分发 SteamworksPy 或 Valve 的 libsteam_api.dylib；
  运行时只在游戏安装目录里探测并加载，路径从配置/工坊目录推导，不写死本机路径；
* 找不到 dylib / Steam 未运行 / 未登录时返回结构化降级信息，不抛异常、不阻塞；
* 语义对齐 Windows 侧 `run_steam_worker`：probe_status / query_workshop_states /
  subscribe(_batch) / unsubscribe(_batch)，stdout 标记与原格式一致；
* 不 import 任何 GUI 模块，可独立单测。

注意：SteamAPI_Init 要求 cwd 下存在 steam_appid.txt；本模块只在必要时临时写入，
退出时恢复原文件（含删除临时目录），不改动游戏目录。
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

RIMWORLD_STEAM_APP_ID = "294100"
DYLIB_RELATIVE = (
    Path("RimWorldMac.app")
    / "Contents"
    / "PlugIns"
    / "steam_api.bundle"
    / "Contents"
    / "MacOS"
    / "libsteam_api.dylib"
)
# 不同 RimWorld/Steamworks SDK 版本导出的访问器版本号不同，按新到旧探测。
UGC_ACCESSOR_VERSIONS = ("v016", "v015", "v014")
USER_ACCESSOR_VERSIONS = ("v021", "v020", "v019", "v018", "v017", "v016", "v015", "v014", "v013")
CALLBACK_PUMP_INTERVAL = 0.1
FOLDER_BUFFER_SIZE = 1024


# =========================================================
#  定位：从配置 / 工坊目录 / 常见默认位置推导安装路径
# =========================================================
def _settings_config() -> Any:
    """尽力取得 backend.settings 的配置对象；单测/独立运行时允许不存在。"""
    try:
        from backend.settings import settings

        return getattr(settings, "config", None)
    except Exception:
        return None


def _steam_root_from_workshop_path(workshop_path: str) -> str:
    """<steam>/steamapps/workshop/content/294100 -> <steam>。"""
    try:
        path = Path(os.path.expanduser(str(workshop_path or "").strip()))
    except Exception:
        return ""
    if path.name != RIMWORLD_STEAM_APP_ID:
        return ""
    if path.parent.name != "content" or path.parent.parent.name != "workshop":
        return ""
    parents = path.parents
    if len(parents) < 4:
        return ""
    return str(parents[3])


def _direct_install_roots(install_path: str = "") -> list[str]:
    """不触发昂贵扫描的安装根目录候选（显式传入优先）。"""
    roots: list[str] = []

    def add(value: Any) -> None:
        text = os.path.expanduser(str(value or "").strip())
        if text and text not in roots:
            roots.append(text)

    add(install_path)
    config = _settings_config()
    if config is not None:
        # 老版本配置里可能存在 game_install_path（自动探测后写入）。
        add(getattr(config, "game_install_path", ""))
        steam_roots: list[Path] = []
        derived_root = _steam_root_from_workshop_path(str(getattr(config, "workshop_mods_path", "") or ""))
        if derived_root:
            steam_roots.append(Path(derived_root))
        steam_path = os.path.expanduser(str(getattr(config, "steam_path", "") or "").strip())
        if steam_path:
            steam_roots.append(Path(steam_path))
        for steam_root in steam_roots:
            add(steam_root / "steamapps" / "common" / "RimWorld")

    # 常见默认位置（Steam 默认库 + 非 Steam 安装位）。
    add(Path.home() / "Library" / "Application Support" / "Steam" / "steamapps" / "common" / "RimWorld")
    add(Path("/Applications") / "RimWorld")
    add(Path("/Applications") / "RimWorld.app")
    add(Path.home() / "Applications" / "RimWorld")
    return roots


def _autodetect_game_install_path() -> str:
    """兜底：用 GameManager 的自动探测（会扫 Steam 库，仅在直接候选全失败时调用）。"""
    try:
        from backend.managers.mgr_game import GameManager

        detected = GameManager.auto_detect_paths() or {}
        return str(detected.get("game_install_path") or "").strip()
    except Exception as exc:
        logger.debug("GameManager 自动探测安装路径失败: %s", exc)
        return ""


def _dylib_candidates(root: str) -> Iterable[Path]:
    try:
        path = Path(os.path.expanduser(str(root or "").strip()))
    except Exception:
        return []
    if not str(path):
        return []
    if path.is_file() and path.name == "libsteam_api.dylib":
        return [path]
    app_bundles = [path] if path.suffix.lower() == ".app" else [path / "RimWorldMac.app"]
    candidates: list[Path] = []
    for app in app_bundles:
        candidates.append(app / DYLIB_RELATIVE.relative_to("RimWorldMac.app"))
        candidates.append(app / "Contents" / "MacOS" / "libsteam_api.dylib")
        candidates.append(app / "Contents" / "Frameworks" / "libsteam_api.dylib")
    candidates.append(path / "libsteam_api.dylib")
    return candidates


def locate_steam_api_dylib(install_path: str = "") -> tuple[str, str]:
    """返回 (dylib 绝对路径, 状态)。找不到时返回 ("", "steamworks_dylib_not_found")。"""
    for root in _direct_install_roots(install_path):
        for candidate in _dylib_candidates(root):
            if candidate.is_file():
                return str(candidate), "ok"

    detected = _autodetect_game_install_path()
    if detected and detected not in _direct_install_roots(install_path):
        for candidate in _dylib_candidates(detected):
            if candidate.is_file():
                return str(candidate), "ok"
    return "", "steamworks_dylib_not_found"


# =========================================================
#  ctypes 会话
# =========================================================
class SteamworksUGC:
    """一次 SteamAPI 会话：定位 dylib -> 临时 appid -> Init -> UGC 调用 -> Shutdown。"""

    def __init__(self, dylib_path: str = "", install_path: str = "", workdir: str = ""):
        self.dylib_path = str(dylib_path or "").strip()
        self.install_path = str(install_path or "").strip()
        self._requested_workdir = str(workdir or "").strip()
        self.available = False
        self.running = False
        self.logged_in = False
        self.initialized = False
        self.detail = ""
        self.workdir = ""
        self.ugc_accessor = ""
        self.steam_user_accessor = ""
        self._lib: Any = None
        self._ugc: Any = None
        self._steam_user: Any = None
        self._fn: dict[str, Any] = {}
        self._cwd_before = ""
        self._appid_path: Path | None = None
        self._appid_original: str | None = None
        self._temp_workdir = ""

    # ---------- 准备阶段 ----------
    def _resolve_dylib(self) -> bool:
        if self.dylib_path:
            path = Path(os.path.expanduser(self.dylib_path))
            if path.is_file():
                self.dylib_path = str(path)
                self.available = True
                return True
            self.detail = "steamworks_dylib_not_found"
            return False
        path, detail = locate_steam_api_dylib(self.install_path)
        if not path:
            self.detail = detail
            return False
        self.dylib_path = path
        self.available = True
        return True

    def _prepare_workdir(self) -> bool:
        base = Path(os.path.expanduser(self._requested_workdir)) if self._requested_workdir else Path.cwd()
        if not base.is_dir():
            base = Path.cwd()
        self._cwd_before = os.getcwd()
        appid_path = base / "steam_appid.txt"
        try:
            existed = appid_path.is_file()
            content = appid_path.read_text(encoding="utf-8", errors="ignore") if existed else ""
        except OSError:
            existed, content = False, ""
        try:
            if not (existed and content.strip() == RIMWORLD_STEAM_APP_ID):
                appid_path.write_text(RIMWORLD_STEAM_APP_ID, encoding="utf-8")
                # None 表示原本不存在，退出时删除。
                self._appid_path = appid_path
                self._appid_original = content if existed else None
            os.chdir(base)
            self.workdir = str(base)
            return True
        except OSError as exc:
            logger.debug("cwd 不可写 steam_appid.txt，改用临时目录: %s", exc)
        try:
            temp_dir = tempfile.mkdtemp(prefix="rimcrow-steam-runtime-")
            Path(temp_dir, "steam_appid.txt").write_text(RIMWORLD_STEAM_APP_ID, encoding="utf-8")
            os.chdir(temp_dir)
            self._temp_workdir = temp_dir
            self.workdir = temp_dir
            return True
        except OSError as exc:
            self.detail = f"steamworks_runtime_dir_failed: {exc}"
            return False

    def _load_library(self) -> bool:
        try:
            self._lib = ctypes.CDLL(self.dylib_path)
        except OSError as exc:
            self.detail = f"steamworks_load_failed: {exc}"
            self.available = False
            return False
        try:
            self._fn["SteamAPI_Init"] = self._bind(self._lib, "SteamAPI_Init", ctypes.c_bool, [])
            self._fn["SteamAPI_Shutdown"] = self._bind(self._lib, "SteamAPI_Shutdown", None, [])
            self._fn["SteamAPI_RunCallbacks"] = self._bind(self._lib, "SteamAPI_RunCallbacks", None, [])
        except AttributeError as exc:
            self.detail = f"steamworks_symbol_missing: {exc}"
            self.available = False
            return False
        # 旧版 dylib 可能没有 IsSteamRunning，此时交给 Init 判断。
        is_running = getattr(self._lib, "SteamAPI_IsSteamRunning", None)
        if is_running is not None:
            is_running.restype = ctypes.c_bool
            is_running.argtypes = []
            self._fn["SteamAPI_IsSteamRunning"] = is_running
        return True

    @staticmethod
    def _bind(lib: Any, name: str, restype: Any, argtypes: list[Any]) -> Any:
        fn = getattr(lib, name, None)
        if fn is None:
            raise AttributeError(name)
        fn.restype = restype
        fn.argtypes = argtypes
        return fn

    def _prepare_runtime(self) -> bool:
        if not self._resolve_dylib():
            return False
        if not self._prepare_workdir():
            return False
        return self._load_library()

    def _resolve_accessor(self, prefix: str, versions: Iterable[str]) -> tuple[Any, str]:
        if self._lib is None:
            return None, ""
        for version in versions:
            name = f"SteamAPI_{prefix}_{version}"
            fn = getattr(self._lib, name, None)
            if fn is None:
                continue
            fn.restype = ctypes.c_void_p
            fn.argtypes = []
            try:
                pointer = fn()
            except Exception:
                continue
            if pointer:
                return pointer, name
        return None, ""

    def _bind_ugc_functions(self) -> None:
        """UGC 接口函数全部按可选绑定（不同 SDK 版本裁剪不一致）。"""
        assert self._lib is not None
        bindings = {
            "SteamAPI_ISteamUGC_GetItemState": (ctypes.c_uint32, [ctypes.c_void_p, ctypes.c_uint64]),
            "SteamAPI_ISteamUGC_SubscribeItem": (ctypes.c_uint64, [ctypes.c_void_p, ctypes.c_uint64]),
            "SteamAPI_ISteamUGC_UnsubscribeItem": (ctypes.c_uint64, [ctypes.c_void_p, ctypes.c_uint64]),
            "SteamAPI_ISteamUGC_GetNumSubscribedItems": (ctypes.c_uint32, [ctypes.c_void_p]),
            "SteamAPI_ISteamUGC_GetSubscribedItems": (
                ctypes.c_uint32,
                [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64), ctypes.c_uint32],
            ),
            "SteamAPI_ISteamUGC_GetItemInstallInfo": (
                ctypes.c_bool,
                [
                    ctypes.c_void_p,
                    ctypes.c_uint64,
                    ctypes.POINTER(ctypes.c_uint64),
                    ctypes.c_char_p,
                    ctypes.c_uint32,
                    ctypes.POINTER(ctypes.c_uint32),
                ],
            ),
            "SteamAPI_ISteamUGC_GetItemDownloadInfo": (
                ctypes.c_bool,
                [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64)],
            ),
        }
        for name, (restype, argtypes) in bindings.items():
            try:
                self._fn[name] = self._bind(self._lib, name, restype, argtypes)
            except AttributeError:
                logger.debug("steam_api.dylib 缺少可选符号: %s", name)

    # ---------- 生命周期 ----------
    def init(self) -> bool:
        if self.initialized:
            return True
        if not self._prepare_runtime():
            return False
        self.running = bool(self.is_steam_running())
        if not self.running:
            self.detail = "steamworks_not_running"
            return False
        try:
            if not bool(self._fn["SteamAPI_Init"]()):
                self.detail = "steamworks_init_failed"
                return False
        except Exception as exc:
            self.detail = f"steamworks_init_failed: {exc}"
            return False
        self.initialized = True
        self._ugc, self.ugc_accessor = self._resolve_accessor("SteamUGC", UGC_ACCESSOR_VERSIONS)
        if self._ugc is None:
            self.detail = "steamworks_ugc_interface_unavailable"
            return False
        self._steam_user, self.steam_user_accessor = self._resolve_accessor("SteamUser", USER_ACCESSOR_VERSIONS)
        self._bind_ugc_functions()
        logged_on = self._query_logged_on()
        self.logged_in = bool(logged_on) if logged_on is not None else True
        if not self.logged_in:
            self.detail = "steamworks_not_logged_in"
            return False
        self.detail = "steamworks_ready"
        return True

    def _query_logged_on(self) -> bool | None:
        if self._steam_user is None or self._lib is None:
            return None
        fn = getattr(self._lib, "SteamAPI_ISteamUser_BLoggedOn", None)
        if fn is None:
            return None
        fn.restype = ctypes.c_bool
        fn.argtypes = [ctypes.c_void_p]
        try:
            return bool(fn(self._steam_user))
        except Exception:
            return None

    def is_steam_running(self) -> bool:
        fn = self._fn.get("SteamAPI_IsSteamRunning")
        if fn is None:
            return True
        try:
            return bool(fn())
        except Exception:
            return False

    def close(self) -> None:
        if self.initialized:
            try:
                self._fn["SteamAPI_Shutdown"]()
            except Exception as exc:
                logger.debug("SteamAPI_Shutdown 失败: %s", exc)
            self.initialized = False
        try:
            if self._cwd_before and os.getcwd() != self._cwd_before:
                os.chdir(self._cwd_before)
        except OSError as exc:
            logger.debug("恢复 cwd 失败: %s", exc)
        if self._appid_path is not None:
            try:
                if self._appid_original is None:
                    self._appid_path.unlink(missing_ok=True)
                else:
                    self._appid_path.write_text(self._appid_original, encoding="utf-8")
            except OSError as exc:
                logger.debug("恢复 steam_appid.txt 失败: %s", exc)
            self._appid_path = None
        if self._temp_workdir:
            shutil.rmtree(self._temp_workdir, ignore_errors=True)
            self._temp_workdir = ""

    # ---------- UGC 调用 ----------
    def run_callbacks_once(self) -> bool:
        fn = self._fn.get("SteamAPI_RunCallbacks")
        if fn is None:
            return False
        try:
            fn()
            return True
        except Exception:
            return False

    def pump(self, seconds: float) -> bool:
        """泵 RunCallbacks，sleep 防 CPU 空转；返回期间是否至少成功跑过一次。"""
        deadline = time.time() + max(0.0, float(seconds))
        pumped = False
        while True:
            pumped = self.run_callbacks_once() or pumped
            if time.time() >= deadline:
                return pumped
            time.sleep(CALLBACK_PUMP_INTERVAL)

    def get_item_state(self, workshop_id: Any) -> int:
        fn = self._fn.get("SteamAPI_ISteamUGC_GetItemState")
        if fn is None:
            return 0
        try:
            return int(fn(self._ugc, int(workshop_id)))
        except Exception:
            return 0

    def get_subscribed_items(self) -> list[str]:
        count_fn = self._fn.get("SteamAPI_ISteamUGC_GetNumSubscribedItems")
        items_fn = self._fn.get("SteamAPI_ISteamUGC_GetSubscribedItems")
        if count_fn is None or items_fn is None:
            return []
        try:
            total = int(count_fn(self._ugc))
            if total <= 0:
                return []
            buffer = (ctypes.c_uint64 * total)()
            got = int(items_fn(self._ugc, buffer, total))
            return [str(int(buffer[index])) for index in range(min(got, total))]
        except Exception as exc:
            logger.debug("GetSubscribedItems 失败: %s", exc)
            return []

    def get_item_install_info(self, workshop_id: Any) -> dict[str, Any]:
        fn = self._fn.get("SteamAPI_ISteamUGC_GetItemInstallInfo")
        if fn is None:
            return {}
        folder = ctypes.create_string_buffer(FOLDER_BUFFER_SIZE)
        size = ctypes.c_uint64(0)
        timestamp = ctypes.c_uint32(0)
        try:
            ok = bool(
                fn(
                    self._ugc,
                    int(workshop_id),
                    ctypes.byref(size),
                    folder,
                    FOLDER_BUFFER_SIZE,
                    ctypes.byref(timestamp),
                )
            )
        except Exception:
            return {}
        if not ok:
            return {}
        return {
            "folder": folder.value.decode("utf-8", errors="replace"),
            "disk_size": int(size.value),
            "timestamp": int(timestamp.value),
        }

    def get_item_download_info(self, workshop_id: Any) -> dict[str, Any]:
        fn = self._fn.get("SteamAPI_ISteamUGC_GetItemDownloadInfo")
        if fn is None:
            return {}
        downloaded = ctypes.c_uint64(0)
        total = ctypes.c_uint64(0)
        try:
            ok = bool(fn(self._ugc, int(workshop_id), ctypes.byref(downloaded), ctypes.byref(total)))
        except Exception:
            return {}
        if not ok:
            return {}
        return {"downloaded": int(downloaded.value), "total": int(total.value)}

    def subscribe(self, workshop_id: Any) -> int:
        fn = self._fn.get("SteamAPI_ISteamUGC_SubscribeItem")
        if fn is None:
            return 0
        try:
            return int(fn(self._ugc, int(workshop_id)))
        except Exception:
            return 0

    def unsubscribe(self, workshop_id: Any) -> int:
        fn = self._fn.get("SteamAPI_ISteamUGC_UnsubscribeItem")
        if fn is None:
            return 0
        try:
            return int(fn(self._ugc, int(workshop_id)))
        except Exception:
            return 0

    def collect_item_state(self, workshop_id: Any) -> dict[str, Any]:
        """与 Windows 侧 `_collect_workshop_item_state` 保持同字段结构。"""
        raw_state = self.get_item_state(workshop_id)
        install_info = self.get_item_install_info(workshop_id)
        download_info = self.get_item_download_info(workshop_id)
        downloaded = int(download_info.get("downloaded") or 0)
        total = int(download_info.get("total") or 0)
        return {
            "workshop_id": str(workshop_id),
            "state": raw_state,
            "is_subscribed": bool(raw_state & 1),
            "is_installed": bool(raw_state & 4),
            "needs_update": bool(raw_state & 8),
            "is_downloading": bool(raw_state & 16),
            "is_download_pending": bool(raw_state & 32),
            "install_info": {
                "folder": str(install_info.get("folder") or "").strip(),
                "disk_size": int(install_info.get("disk_size") or 0),
                "timestamp": int(install_info.get("timestamp") or 0),
            },
            "download_info": {
                "downloaded": downloaded,
                "total": total,
                "progress": (downloaded / total) if total else 0.0,
            },
        }


# =========================================================
#  payload 解析（worker 参数：JSON 对象 / JSON 列表 / 逗号分隔 / "_"）
# =========================================================
def parse_workshop_ids(payload: str) -> list[str]:
    raw = str(payload or "").strip()
    if not raw or raw == "_":
        return []
    raw_items: Any = None
    try:
        if raw.startswith("{"):
            decoded = json.loads(raw)
            raw_items = decoded.get("ids") if isinstance(decoded, dict) else None
        elif raw.startswith("["):
            raw_items = json.loads(raw)
        else:
            raw_items = raw.split(",")
    except (ValueError, TypeError):
        raw_items = raw.split(",")
    if isinstance(raw_items, (str, int)):
        raw_items = [raw_items]
    if not isinstance(raw_items, (list, tuple, set)):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if text.isdigit() and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


# =========================================================
#  worker 动作（供 mgr_steam.run_steam_worker 的 Darwin 分支调用）
# =========================================================
def _base_result() -> dict[str, Any]:
    return {"available": False, "running": False, "logged_in": False, "ready": False, "detail": ""}


def _fill_session_status(result: dict[str, Any], session: SteamworksUGC, ready: bool) -> None:
    result["available"] = bool(session.available)
    result["running"] = bool(session.running)
    result["logged_in"] = bool(session.logged_in)
    result["ready"] = bool(ready)
    result["detail"] = session.detail or ("steamworks_ready" if ready else "steamworks_not_ready")


def probe_status(dylib_path: str = "", install_path: str = "") -> dict[str, Any]:
    result = _base_result()
    session = SteamworksUGC(dylib_path=dylib_path, install_path=install_path)
    try:
        ready = session.init()
        _fill_session_status(result, session, ready)
    finally:
        session.close()
    return result


def query_workshop_states(
    workshop_ids: Iterable[Any] = (),
    dylib_path: str = "",
    install_path: str = "",
) -> dict[str, Any]:
    result = _base_result()
    result["subscribed_items"] = []
    result["states"] = {}
    normalized_ids = [str(item).strip() for item in workshop_ids if str(item).strip().isdigit()]
    session = SteamworksUGC(dylib_path=dylib_path, install_path=install_path)
    try:
        if not session.init():
            _fill_session_status(result, session, False)
            return result
        if not normalized_ids:
            subscribed_items = session.get_subscribed_items()
            result["subscribed_items"] = subscribed_items
            normalized_ids = subscribed_items
        result["states"] = {workshop_id: session.collect_item_state(workshop_id) for workshop_id in normalized_ids}
        result["detail"] = "steamworks_workshop_state_ready"
        _fill_session_status(result, session, True)
        result["detail"] = "steamworks_workshop_state_ready"
    finally:
        session.close()
    return result


def _run_workshop_action(
    action: str,
    workshop_ids: Iterable[Any],
    dylib_path: str = "",
    install_path: str = "",
    pump_seconds: float | None = None,
) -> dict[str, Any]:
    result = _base_result()
    result.update({"action": action, "requested": 0, "failed": [], "call_handles": {}, "states": {}})
    normalized_ids = [str(item).strip() for item in workshop_ids if str(item).strip().isdigit()]
    if not normalized_ids:
        result["detail"] = f"steamworks_{action}_no_valid_ids"
        return result
    session = SteamworksUGC(dylib_path=dylib_path, install_path=install_path)
    try:
        if not session.init():
            _fill_session_status(result, session, False)
            return result
        for workshop_id in normalized_ids:
            call_handle = session.unsubscribe(workshop_id) if action == "unsubscribe" else session.subscribe(workshop_id)
            if call_handle:
                result["call_handles"][workshop_id] = call_handle
            else:
                result["failed"].append(workshop_id)
        result["requested"] = len(result["call_handles"])
        wait_seconds = pump_seconds if pump_seconds is not None else max(0.5, min(2.0, len(normalized_ids) * 0.3))
        session.pump(wait_seconds)
        result["states"] = {workshop_id: session.get_item_state(workshop_id) for workshop_id in normalized_ids}
        if result["requested"] == len(normalized_ids):
            result["detail"] = f"steamworks_{action}_requested"
        else:
            result["detail"] = f"steamworks_{action}_partially_requested"
        _fill_session_status(result, session, True)
    finally:
        session.close()
    return result


def subscribe_items(workshop_ids: Iterable[Any], dylib_path: str = "", install_path: str = "") -> dict[str, Any]:
    return _run_workshop_action("subscribe", workshop_ids, dylib_path=dylib_path, install_path=install_path)


def unsubscribe_items(workshop_ids: Iterable[Any], dylib_path: str = "", install_path: str = "") -> dict[str, Any]:
    return _run_workshop_action("unsubscribe", workshop_ids, dylib_path=dylib_path, install_path=install_path)


def run_mac_steam_worker_action(action: str, payload: str) -> None:
    """Darwin 版 worker 入口：stdout 标记与 Windows 侧保持一致，主进程只认这些标记。"""
    workshop_ids = parse_workshop_ids(payload)
    if action == "probe_status":
        result = probe_status()
        print(f"STEAM_STATUS_JSON:{json.dumps(result, ensure_ascii=False)}", flush=True)
        return
    if action == "query_workshop_states":
        result = query_workshop_states(workshop_ids)
        print(f"STEAM_WORKSHOP_STATE_JSON:{json.dumps(result, ensure_ascii=False)}", flush=True)
        return
    if action in ("subscribe", "subscribe_batch"):
        result = subscribe_items(workshop_ids)
    elif action in ("unsubscribe", "unsubscribe_batch"):
        result = unsubscribe_items(workshop_ids)
    else:
        logger.error("macOS Steamworks ctypes 不支持的 worker 动作: %s", action)
        return
    if result.get("requested"):
        print(f"SUCCESS: {action} request sent for {result['requested']} items", flush=True)
    print(f"STEAM_ACTION_JSON:{json.dumps(result, ensure_ascii=False)}", flush=True)
