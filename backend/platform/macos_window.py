"""macOS 原生窗口外观适配。

pywebview 创建的 NSWindow 默认跟随系统外观：系统处于浅色模式时，即使应用主题是深色，
窗口标题栏也会呈现为白色（深色界面顶部多出一条“大白条”）。该模块用 pyobjc 在主线程给
主窗口显式设置 NSAppearance，让标题栏跟随应用主题的明暗。

约束：
- 只在 macOS 生效，其它平台调用直接返回 False，不导入任何 pyobjc 模块；
- 任何失败只写 debug 日志，绝不影响启动或主题切换本身。
"""

from __future__ import annotations

import sys

from backend.utils.logger import logger

_MAIN_WINDOW_TITLE = "RimCrow"
_APPEARANCE_CONSTANTS = {
    "dark": "NSAppearanceNameDarkAqua",
    "light": "NSAppearanceNameAqua",
}


def is_supported() -> bool:
    """当前平台是否支持原生窗口外观切换。"""
    return sys.platform == "darwin"


def normalize_appearance_mode(mode: str) -> str:
    """把外部传入的明暗模式归一化为 dark / light；无法识别时返回空串。"""
    normalized = str(mode or "").strip().lower()
    return normalized if normalized in _APPEARANCE_CONSTANTS else ""


def _find_main_window(appkit):
    """优先按标题匹配主窗口；匹配不到时退回第一个可见窗口。"""
    try:
        windows = list(appkit.NSApplication.sharedApplication().windows() or [])
    except Exception:
        logger.debug("读取 NSApplication 窗口列表失败", exc_info=True)
        return None
    for window in windows:
        try:
            if str(window.title() or "").strip() == _MAIN_WINDOW_TITLE and window.isVisible():
                return window
        except Exception:
            continue
    for window in windows:
        try:
            if window.isVisible():
                return window
        except Exception:
            continue
    return None


def _apply_on_main_thread(mode: str) -> bool:
    """必须在主线程执行：给主窗口设置 NSAppearance。"""
    try:
        import AppKit
    except Exception:
        logger.debug("pyobjc AppKit 不可用，跳过窗口外观切换", exc_info=True)
        return False
    window = _find_main_window(AppKit)
    if window is None:
        logger.debug("未找到可切换外观的主窗口，跳过窗口外观切换")
        return False
    try:
        appearance = AppKit.NSAppearance.appearanceNamed_(getattr(AppKit, _APPEARANCE_CONSTANTS[mode]))
    except Exception:
        logger.debug("解析 NSAppearance 常量失败: %s", mode, exc_info=True)
        return False
    if appearance is None:
        logger.debug("NSAppearance 解析结果为空: %s", mode)
        return False
    try:
        window.setAppearance_(appearance)
    except Exception:
        logger.debug("设置 NSWindow.appearance 失败: %s", mode, exc_info=True)
        return False
    logger.debug("窗口外观已切换: %s", mode)
    return True


def apply_window_appearance(mode: str) -> bool:
    """切换主窗口标题栏外观（dark / light）。

    返回 True 表示已成功应用（主线程直接执行）或已投递到主线程；False 表示当前平台
    不支持、pyobjc 不可用或投递失败。任何异常都被吞掉，调用方无需再做兜底。
    """
    if not is_supported():
        return False
    normalized = normalize_appearance_mode(mode)
    if not normalized:
        logger.debug("忽略非法的窗口外观模式: %s", mode)
        return False
    try:
        import AppKit
        from PyObjCTools import AppHelper
    except Exception:
        logger.debug("pyobjc 不可用，跳过窗口外观切换", exc_info=True)
        return False
    try:
        if AppKit.NSThread.isMainThread():
            return _apply_on_main_thread(normalized)
        # pywebview 的 js_api 调用运行在后台线程，必须切回 GUI 主线程再改窗口外观。
        AppHelper.callAfter(_apply_on_main_thread, normalized)
        return True
    except Exception:
        logger.debug("投递窗口外观切换失败: %s", normalized, exc_info=True)
        return False


def _clear_titlebar_background(appkit, window) -> None:
    """清掉 pywebview 给标题栏 view 设的 windowBackgroundColor。

    pywebview 在非 frameless 窗口里执行过：
        contentView().superview().subviews().lastObject().setBackgroundColor_(NSColor.windowBackgroundColor())
    而窗口外观被我们设成 DarkAqua 后，这个语义色会解析成深灰（~#323232），
    在内容铺满窗口的情况下仍会盖出顶部一条灰条。这里把标题栏相关 view 的背景清成透明。
    """
    targets = []
    try:
        close_button = window.standardWindowButton_(appkit.NSWindowCloseButton)
        titlebar_view = close_button.superview() if close_button is not None else None
        if titlebar_view is not None:
            targets.append(titlebar_view)
            container_view = titlebar_view.superview()
            if container_view is not None:
                targets.append(container_view)
    except Exception:
        logger.debug("读取标题栏按钮视图失败", exc_info=True)
    try:
        content_view = window.contentView()
        frame_view = content_view.superview() if content_view is not None else None
        if frame_view is not None:
            for subview in list(frame_view.subviews() or []):
                try:
                    class_name = str(subview.className() or "")
                except Exception:
                    class_name = ""
                if "Titlebar" in class_name:
                    targets.append(subview)
    except Exception:
        logger.debug("遍历窗口 frame view 失败", exc_info=True)
    for view in targets:
        try:
            background_setter = getattr(view, "setBackgroundColor_", None)
            if background_setter is not None:
                background_setter(appkit.NSColor.clearColor())
            draws_background_setter = getattr(view, "setDrawsBackground_", None)
            if draws_background_setter is not None:
                draws_background_setter(False)
        except Exception:
            logger.debug("清理标题栏背景失败", exc_info=True)


# NSWindowTitlebarSeparatorStyleNone 是 macOS 11+ 的枚举，部分 pyobjc 版本没有导出模块常量。
_TITLEBAR_SEPARATOR_STYLE_NONE = 0


def _apply_unified_titlebar_on_main_thread() -> bool:
    """必须在主线程执行：把标题栏改成与应用内容融合的样式。"""
    try:
        import AppKit
    except Exception:
        logger.debug("pyobjc AppKit 不可用，跳过标题栏融合", exc_info=True)
        return False
    window = _find_main_window(AppKit)
    if window is None:
        logger.debug("未找到可融合的主窗口，跳过标题栏融合")
        return False
    try:
        # FullSizeContentView：让 WKWebView 内容铺满整个窗口（含标题栏区域）；
        # 透明标题栏 + 隐藏标题后，红绿灯悬浮在应用自己的背景上。
        style_mask = window.styleMask() | AppKit.NSWindowStyleMaskFullSizeContentView
        window.setStyleMask_(style_mask)
        window.setTitlebarAppearsTransparent_(True)
        window.setTitleVisibility_(AppKit.NSWindowTitleHidden)
        # 去掉标题栏底部分隔线；老系统/老 pyobjc 没有这个方法时静默跳过。
        separator_setter = getattr(window, "setTitlebarSeparatorStyle_", None)
        if separator_setter is not None:
            separator_setter(getattr(AppKit, "NSWindowTitlebarSeparatorStyleNone", _TITLEBAR_SEPARATOR_STYLE_NONE))
        # pywebview 给标题栏 view 刷过 windowBackgroundColor，必须清掉这层底色，否则仍有一条灰条。
        _clear_titlebar_background(AppKit, window)
    except Exception:
        logger.debug("应用标题栏融合失败", exc_info=True)
        return False
    logger.debug("标题栏已与应用内容融合")
    return True


def apply_unified_titlebar() -> bool:
    """让主窗口标题栏与应用内容融合（等价于 Electron 的 titleBarStyle=hiddenInset）。

    返回 True 表示已应用或已投递到主线程；非 macOS / pyobjc 不可用 / 找不到窗口时返回
    False 并只写 debug 日志。幂等：重复调用结果一致。
    """
    if not is_supported():
        return False
    try:
        import AppKit
        from PyObjCTools import AppHelper
    except Exception:
        logger.debug("pyobjc 不可用，跳过标题栏融合", exc_info=True)
        return False
    try:
        if AppKit.NSThread.isMainThread():
            return _apply_unified_titlebar_on_main_thread()
        AppHelper.callAfter(_apply_unified_titlebar_on_main_thread)
        return True
    except Exception:
        logger.debug("投递标题栏融合失败", exc_info=True)
        return False
