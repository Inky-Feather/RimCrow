import ctypes
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, cast

from backend.platform.runtime import is_windows

MIN_WINDOW_WIDTH = 700
MIN_WINDOW_HEIGHT = 450
DEFAULT_WINDOW_WIDTH = 1400
DEFAULT_WINDOW_HEIGHT = 900
WINDOW_MARGIN = 32


@dataclass
class WindowGeometry:
    x: int = 0
    y: int = 0
    width: int = DEFAULT_WINDOW_WIDTH
    height: int = DEFAULT_WINDOW_HEIGHT


@dataclass
class WindowDisplayState:
    id: str = ""
    work_x: int = 0
    work_y: int = 0
    work_width: int = 0
    work_height: int = 0


@dataclass
class WindowStateConfig:
    version: int = 2
    placement: str = "normal"
    normal: WindowGeometry = field(default_factory=WindowGeometry)
    display: WindowDisplayState = field(default_factory=WindowDisplayState)


@dataclass
class DisplayInfo:
    id: str
    work_x: int
    work_y: int
    work_width: int
    work_height: int
    primary: bool = False
    screen: Any = None


@dataclass
class LaunchGeometry:
    x: int
    y: int
    width: int
    height: int
    maximized: bool = False
    screen: Any = None
    display: DisplayInfo | None = None
    reason: str = "normal"


def enable_per_monitor_dpi_awareness():
    """尽早启用每显示器 DPI 感知，避免多屏缩放下窗口尺寸被系统错换算。"""
    if not is_windows():
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def get_current_displays() -> list[DisplayInfo]:
    if is_windows():
        displays = _get_win32_displays()
        if displays:
            return displays
    return _get_pywebview_displays()


def _get_win32_displays() -> list[DisplayInfo]:
    try:
        import win32api
    except Exception:
        return []

    result: list[DisplayInfo] = []
    try:
        monitors = win32api.EnumDisplayMonitors()
    except Exception:
        return []

    for index, (handle, _dc, rect) in enumerate(monitors):
        try:
            info = win32api.GetMonitorInfo(cast(int, handle))
        except Exception:
            info = {}
        left, top, right, bottom = rect
        work_left, work_top, work_right, work_bottom = info.get("Work", rect)
        flags = int(info.get("Flags", 0) or 0)
        device = str(info.get("Device") or f"DISPLAY{index + 1}")
        result.append(DisplayInfo(
            id=device,
            work_x=int(work_left),
            work_y=int(work_top),
            work_width=int(work_right - work_left),
            work_height=int(work_bottom - work_top),
            primary=bool(flags & 1),
        ))
    return result


def _get_pywebview_displays() -> list[DisplayInfo]:
    try:
        import webview
        screens = list(getattr(webview, "screens", []) or [])
    except Exception:
        screens = []
    result = []
    for index, screen in enumerate(screens):
        x = _as_int(getattr(screen, "x", 0), 0)
        y = _as_int(getattr(screen, "y", 0), 0)
        width = max(1, _as_int(getattr(screen, "width", 0), 0))
        height = max(1, _as_int(getattr(screen, "height", 0), 0))
        result.append(DisplayInfo(
            id=f"screen:{x},{y},{width}x{height}",
            work_x=x,
            work_y=y,
            work_width=width,
            work_height=height,
            primary=index == 0,
            screen=screen,
        ))
    return result or [DisplayInfo(
        id="fallback",
        work_x=0,
        work_y=0,
        work_width=DEFAULT_WINDOW_WIDTH,
        work_height=DEFAULT_WINDOW_HEIGHT,
        primary=True,
    )]


def resolve_launch_geometry(state: WindowStateConfig, displays: Iterable[DisplayInfo]) -> LaunchGeometry:
    displays = list(displays) or _get_pywebview_displays()
    target = _select_display(state, displays)
    normalized_state = _coerce_state(state)
    normal = normalized_state.normal
    reason = "normal"

    if _display_changed(normalized_state.display, target):
        normal = _restore_by_ratio(normalized_state, target)
        reason = "display_changed"
    elif not _is_reasonable_window(normal, target):
        normal = _default_geometry(target)
        reason = "invalid_state"

    normal = _clamp_to_display(normal, target)
    maximized = normalized_state.placement == "maximized"
    return LaunchGeometry(
        x=normal.x,
        y=normal.y,
        width=normal.width,
        height=normal.height,
        maximized=maximized,
        screen=target.screen,
        display=target,
        reason=reason,
    )


class WindowStateManager:
    def __init__(
        self,
        settings_manager,
        displays_provider: Callable[[], list[DisplayInfo]] = get_current_displays,
        clock: Callable[[], float] = time.monotonic,
        startup_ignore_seconds: float = 0.5,
    ):
        self.settings = settings_manager
        self.displays_provider = displays_provider
        self.clock = clock
        self.startup_ignore_seconds = max(0, float(startup_ignore_seconds))
        self.current_display: DisplayInfo | None = None
        self._last_geometry: WindowGeometry | None = None
        self._ignore_events_until = 0.0

    def resolve_launch_geometry(self) -> LaunchGeometry:
        config = self.settings.config
        if getattr(config, "window_state", None) is None or _should_migrate_legacy_state(config.window_state, config):
            config.window_state = self._migrate_legacy_state()
        config.window_state = _coerce_state(config.window_state)
        displays = self.displays_provider()
        launch = resolve_launch_geometry(config.window_state, displays)
        self.current_display = launch.display
        self._last_geometry = WindowGeometry(launch.x, launch.y, launch.width, launch.height)
        self._ignore_events_until = self.clock() + self.startup_ignore_seconds
        _apply_geometry(config.window_state, self._last_geometry, self.current_display)
        self._log_launch(config.window_state, displays, launch)
        return launch

    def on_moved(self, x: int, y: int):
        geometry = self._current_geometry()
        geometry.x = _as_int(x, geometry.x)
        geometry.y = _as_int(y, geometry.y)
        self._update_normal_geometry(geometry)

    def on_resized(self, width: int, height: int):
        geometry = self._current_geometry()
        geometry.width = _as_int(width, geometry.width)
        geometry.height = _as_int(height, geometry.height)
        self._update_normal_geometry(geometry)

    def on_maximized(self):
        self.settings.config.window_state.placement = "maximized"

    def on_restored(self):
        self.settings.config.window_state.placement = "normal"

    def save(self):
        self.settings.save()

    def reset(self):
        self.settings.config.window_state = WindowStateConfig()
        self.settings.save()

    def _migrate_legacy_state(self) -> WindowStateConfig:
        width = _as_int(getattr(self.settings.config, "window_width", DEFAULT_WINDOW_WIDTH), DEFAULT_WINDOW_WIDTH)
        height = _as_int(getattr(self.settings.config, "window_height", DEFAULT_WINDOW_HEIGHT), DEFAULT_WINDOW_HEIGHT)
        displays = self.displays_provider()
        target = _select_display(WindowStateConfig(), displays)
        normal = _clamp_to_display(_center_geometry(width, height, target), target)
        state = WindowStateConfig(normal=normal)
        _apply_geometry(state, normal, target)
        return state

    def _current_geometry(self) -> WindowGeometry:
        if self._last_geometry is not None:
            return WindowGeometry(self._last_geometry.x, self._last_geometry.y, self._last_geometry.width, self._last_geometry.height)
        state = self.settings.config.window_state
        return WindowGeometry(state.normal.x, state.normal.y, state.normal.width, state.normal.height)

    def _update_normal_geometry(self, geometry: WindowGeometry):
        if self.clock() < self._ignore_events_until:
            return
        self._last_geometry = geometry
        state = self.settings.config.window_state
        if state.placement != "maximized":
            display = _select_display_for_geometry(geometry, self.displays_provider())
            geometry = _clamp_to_display(geometry, display)
            self.current_display = display
            self._last_geometry = geometry
            _apply_geometry(state, geometry, display)
            self.settings.config.window_width = geometry.width
            self.settings.config.window_height = geometry.height

    def _log_launch(self, state: WindowStateConfig, displays: list[DisplayInfo], launch: LaunchGeometry):
        from backend.utils.logger import logger

        display_summary = "; ".join(f"{d.id}:{d.work_width}x{d.work_height}@{d.work_x},{d.work_y}" for d in displays)
        logger.info(
            "[WindowState] restore resolved: reason=%s target=%s input=%sx%s output=%sx%s at %s,%s maximized=%s displays=%s",
            launch.reason,
            launch.display.id if launch.display else "",
            state.normal.width,
            state.normal.height,
            launch.width,
            launch.height,
            launch.x,
            launch.y,
            launch.maximized,
            display_summary,
        )


def _coerce_state(value) -> WindowStateConfig:
    if value is None:
        value = WindowStateConfig()
    return WindowStateConfig(
        version=2,
        placement="maximized" if str(getattr(value, "placement", "") or "").lower() == "maximized" else "normal",
        normal=_coerce_geometry(getattr(value, "normal", None)),
        display=_coerce_display_state(getattr(value, "display", None)),
    )


def _should_migrate_legacy_state(state, config) -> bool:
    if state is None:
        return True
    display_state = getattr(state, "display", None)
    if str(getattr(display_state, "id", "") or ""):
        return False
    legacy_width = _as_int(getattr(config, "window_width", DEFAULT_WINDOW_WIDTH), DEFAULT_WINDOW_WIDTH)
    legacy_height = _as_int(getattr(config, "window_height", DEFAULT_WINDOW_HEIGHT), DEFAULT_WINDOW_HEIGHT)
    return legacy_width != DEFAULT_WINDOW_WIDTH or legacy_height != DEFAULT_WINDOW_HEIGHT


def _coerce_geometry(value) -> WindowGeometry:
    return WindowGeometry(
        x=_as_int(getattr(value, "x", 0), 0),
        y=_as_int(getattr(value, "y", 0), 0),
        width=_as_int(getattr(value, "width", DEFAULT_WINDOW_WIDTH), DEFAULT_WINDOW_WIDTH),
        height=_as_int(getattr(value, "height", DEFAULT_WINDOW_HEIGHT), DEFAULT_WINDOW_HEIGHT),
    )


def _coerce_display_state(value) -> WindowDisplayState:
    return WindowDisplayState(
        id=str(getattr(value, "id", "") or ""),
        work_x=_as_int(getattr(value, "work_x", 0), 0),
        work_y=_as_int(getattr(value, "work_y", 0), 0),
        work_width=_as_int(getattr(value, "work_width", 0), 0),
        work_height=_as_int(getattr(value, "work_height", 0), 0),
    )


def _select_display(state: WindowStateConfig, displays: list[DisplayInfo]) -> DisplayInfo:
    saved = getattr(state, "display", WindowDisplayState())
    for display in displays:
        if saved.id and display.id == saved.id:
            return display
    for display in displays:
        if _rect_close(saved.work_x, saved.work_y, saved.work_width, saved.work_height, display.work_x, display.work_y, display.work_width, display.work_height):
            return display
    center_x = getattr(state.normal, "x", 0) + getattr(state.normal, "width", 0) / 2
    center_y = getattr(state.normal, "y", 0) + getattr(state.normal, "height", 0) / 2
    for display in displays:
        if display.work_x <= center_x <= display.work_x + display.work_width and display.work_y <= center_y <= display.work_y + display.work_height:
            return display
    return next((display for display in displays if display.primary), displays[0])


def _select_display_for_geometry(geometry: WindowGeometry, displays: list[DisplayInfo]) -> DisplayInfo:
    center_x = geometry.x + geometry.width / 2
    center_y = geometry.y + geometry.height / 2
    for display in displays:
        if display.work_x <= center_x <= display.work_x + display.work_width and display.work_y <= center_y <= display.work_y + display.work_height:
            return display
    return next((display for display in displays if display.primary), displays[0])


def _rect_close(*values: int) -> bool:
    a_x, a_y, a_w, a_h, b_x, b_y, b_w, b_h = values
    return abs(a_x - b_x) <= 8 and abs(a_y - b_y) <= 8 and abs(a_w - b_w) <= 16 and abs(a_h - b_h) <= 16


def _display_changed(saved: WindowDisplayState, target: DisplayInfo) -> bool:
    if not saved.work_width or not saved.work_height:
        return False
    return not _rect_close(saved.work_x, saved.work_y, saved.work_width, saved.work_height, target.work_x, target.work_y, target.work_width, target.work_height)


def _is_reasonable_window(geometry: WindowGeometry, display: DisplayInfo) -> bool:
    if geometry.width <= 0 or geometry.height <= 0:
        return False
    if geometry.width < min(MIN_WINDOW_WIDTH, max(1, display.work_width - WINDOW_MARGIN)):
        return False
    if geometry.height < min(MIN_WINDOW_HEIGHT, max(1, display.work_height - WINDOW_MARGIN)):
        return False
    visible_width = min(geometry.x + geometry.width, display.work_x + display.work_width) - max(geometry.x, display.work_x)
    visible_height = min(geometry.y + geometry.height, display.work_y + display.work_height) - max(geometry.y, display.work_y)
    visible_area = max(0, visible_width) * max(0, visible_height)
    return visible_area >= geometry.width * geometry.height * 0.4


def _restore_by_ratio(state: WindowStateConfig, display: DisplayInfo) -> WindowGeometry:
    old_work_width = state.display.work_width or display.work_width
    old_work_height = state.display.work_height or display.work_height
    width_ratio = state.normal.width / max(1, old_work_width)
    height_ratio = state.normal.height / max(1, old_work_height)
    center_x_ratio = (state.normal.x + state.normal.width / 2 - state.display.work_x) / max(1, old_work_width)
    center_y_ratio = (state.normal.y + state.normal.height / 2 - state.display.work_y) / max(1, old_work_height)
    width = int(display.work_width * _clamp_float(width_ratio, 0.4, 0.95))
    height = int(display.work_height * _clamp_float(height_ratio, 0.4, 0.95))
    center_x = display.work_x + int(display.work_width * _clamp_float(center_x_ratio, 0, 1))
    center_y = display.work_y + int(display.work_height * _clamp_float(center_y_ratio, 0, 1))
    return WindowGeometry(center_x - width // 2, center_y - height // 2, width, height)


def _default_geometry(display: DisplayInfo) -> WindowGeometry:
    width = min(DEFAULT_WINDOW_WIDTH, int(display.work_width * 0.82))
    height = min(DEFAULT_WINDOW_HEIGHT, int(display.work_height * 0.84))
    return _center_geometry(width, height, display)


def _center_geometry(width: int, height: int, display: DisplayInfo) -> WindowGeometry:
    return WindowGeometry(
        x=display.work_x + (display.work_width - width) // 2,
        y=display.work_y + (display.work_height - height) // 2,
        width=width,
        height=height,
    )


def _clamp_to_display(geometry: WindowGeometry, display: DisplayInfo) -> WindowGeometry:
    max_width = max(1, display.work_width - WINDOW_MARGIN)
    max_height = max(1, display.work_height - WINDOW_MARGIN)
    min_width = min(MIN_WINDOW_WIDTH, max_width)
    min_height = min(MIN_WINDOW_HEIGHT, max_height)
    width = min(max(_as_int(geometry.width, DEFAULT_WINDOW_WIDTH), min_width), max_width)
    height = min(max(_as_int(geometry.height, DEFAULT_WINDOW_HEIGHT), min_height), max_height)
    max_x = display.work_x + display.work_width - width
    max_y = display.work_y + display.work_height - height
    x = min(max(_as_int(geometry.x, display.work_x), display.work_x), max_x)
    y = min(max(_as_int(geometry.y, display.work_y), display.work_y), max_y)
    return WindowGeometry(x=x, y=y, width=width, height=height)


def _apply_geometry(state: WindowStateConfig, geometry: WindowGeometry, display: DisplayInfo | None):
    state.normal = geometry
    if not display:
        return
    state.display = WindowDisplayState(
        id=display.id,
        work_x=display.work_x,
        work_y=display.work_y,
        work_width=display.work_width,
        work_height=display.work_height,
    )


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp_float(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
