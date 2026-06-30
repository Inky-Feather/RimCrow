from types import SimpleNamespace

from dataclasses import asdict

from backend.window_state import (
    DisplayInfo,
    WindowGeometry,
    WindowStateManager,
    resolve_launch_geometry,
)


def make_state(**overrides):
    state = SimpleNamespace(
        version=2,
        placement="normal",
        normal=SimpleNamespace(x=100, y=80, width=1400, height=900),
        display=SimpleNamespace(id="DISPLAY1", work_x=0, work_y=0, work_width=1920, work_height=1040),
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def display(id="DISPLAY1", x=0, y=0, width=1920, height=1080, work_height=None):
    return DisplayInfo(
        id=id,
        work_x=x,
        work_y=y,
        work_width=width,
        work_height=work_height or height,
        primary=x == 0 and y == 0,
    )


def test_clamps_old_large_window_to_smaller_screen():
    state = make_state(normal=SimpleNamespace(x=60, y=40, width=3200, height=1800))

    launch = resolve_launch_geometry(state, [display(width=1366, height=768, work_height=728)])

    assert launch.width <= 1366 - 32
    assert launch.height <= 728 - 32
    assert launch.x >= 0
    assert launch.y >= 0


def test_small_old_window_is_raised_to_ui_minimum_when_screen_allows():
    state = make_state(normal=SimpleNamespace(x=50, y=50, width=640, height=420))

    launch = resolve_launch_geometry(state, [display(width=3840, height=2160, work_height=2080)])

    assert launch.width >= 1100
    assert launch.height >= 700


def test_negative_coordinate_display_can_be_restored():
    left = display(id="LEFT", x=-1600, y=0, width=1600, height=900, work_height=860)
    primary = display(id="PRIMARY", x=0, y=0, width=1920, height=1080, work_height=1040)
    state = make_state(
        normal=SimpleNamespace(x=-1500, y=80, width=1200, height=720),
        display=SimpleNamespace(id="LEFT", work_x=-1600, work_y=0, work_width=1600, work_height=860),
    )

    launch = resolve_launch_geometry(state, [primary, left])

    assert -1600 <= launch.x < 0
    assert launch.width <= 1600 - 32


def test_maximized_restore_keeps_normal_geometry_separate():
    state = make_state(placement="maximized", normal=SimpleNamespace(x=120, y=90, width=1300, height=820))

    launch = resolve_launch_geometry(state, [display(work_height=1040)])

    assert launch.maximized is True
    assert launch.width == 1300
    assert launch.height == 820


def test_manager_migrates_legacy_width_height_into_window_state():
    config = SimpleNamespace(window_width=1500, window_height=950, window_state=None)

    manager = WindowStateManager(SimpleNamespace(config=config, save=lambda: None), displays_provider=lambda: [display()])
    launch = manager.resolve_launch_geometry()

    assert config.window_state.normal.width == 1500
    assert config.window_state.normal.height == 950
    assert launch.width == 1500


def test_manager_migrates_default_empty_state_when_legacy_size_is_custom():
    config = SimpleNamespace(window_width=1500, window_height=950, window_state=make_state(display=SimpleNamespace(id="")))

    manager = WindowStateManager(SimpleNamespace(config=config, save=lambda: None), displays_provider=lambda: [display()])
    launch = manager.resolve_launch_geometry()

    assert config.window_state.normal.width == 1500
    assert config.window_state.normal.height == 950
    assert launch.width == 1500


def test_resized_and_moved_update_ratios_against_current_display():
    config = SimpleNamespace(window_state=make_state())
    manager = WindowStateManager(SimpleNamespace(config=config, save=lambda: None), displays_provider=lambda: [display(width=2000, height=1200, work_height=1100)])
    manager.current_display = display(width=2000, height=1200, work_height=1100)

    manager.on_moved(300, 200)
    manager.on_resized(1200, 700)

    assert config.window_state.normal.x == 300
    assert config.window_state.normal.width == 1200
    assert config.window_state.display.work_width == 2000
    assert config.window_state.display.work_height == 1100


def test_startup_resize_move_events_do_not_pollute_saved_normal_geometry():
    now = [1000.0]
    config = SimpleNamespace(window_state=make_state())
    manager = WindowStateManager(
        SimpleNamespace(config=config, save=lambda: None),
        displays_provider=lambda: [display()],
        clock=lambda: now[0],
    )

    manager.resolve_launch_geometry()
    manager.on_resized(1910, 1030)
    manager.on_moved(0, 0)

    assert config.window_state.normal.x == 100
    assert config.window_state.normal.width == 1400

    now[0] += 1.0
    manager.on_moved(220, 160)

    assert config.window_state.normal.x == 220


def test_move_to_another_display_records_that_display():
    primary = display(id="PRIMARY", x=0, y=0, width=1920, height=1080, work_height=1040)
    right = display(id="RIGHT", x=1920, y=0, width=2560, height=1440, work_height=1400)
    config = SimpleNamespace(window_state=make_state())
    manager = WindowStateManager(
        SimpleNamespace(config=config, save=lambda: None),
        displays_provider=lambda: [primary, right],
        startup_ignore_seconds=0,
    )

    manager.resolve_launch_geometry()
    manager.on_moved(2200, 200)
    manager.on_resized(1200, 800)

    assert config.window_state.display.id == "RIGHT"
    assert config.window_state.display.work_x == 1920


def test_window_state_serializes_only_required_fields():
    config = SimpleNamespace(window_state=make_state())
    manager = WindowStateManager(SimpleNamespace(config=config, save=lambda: None), displays_provider=lambda: [display(width=2000, height=1200, work_height=1100)])

    manager.resolve_launch_geometry()
    payload = asdict(config.window_state)

    assert set(payload) == {"version", "placement", "normal", "display"}
    assert set(payload["normal"]) == {"x", "y", "width", "height"}
    assert set(payload["display"]) == {"id", "work_x", "work_y", "work_width", "work_height"}
