from backend.managers.mgr_sub_browser import SubBrowserManager


class FakeWindow:
    def __init__(self, current_url="https://steamcommunity.com/sharedfiles/filedetails/?id=2023507013"):
        self.current_url = current_url
        self.title = ""
        self.scripts = []

    def get_current_url(self):
        return self.current_url

    def set_title(self, title):
        self.title = title

    def evaluate_js(self, script):
        self.scripts.append(script)


def test_loaded_injects_toolbar_for_direct_steam_workshop_page():
    manager = SubBrowserManager.__new__(SubBrowserManager)
    manager.window = FakeWindow()
    manager._mode = "workshop_proxy"
    manager._current_url = "https://steamcommunity.com/sharedfiles/filedetails/?id=2023507013"

    manager._on_loaded()

    assert manager.window.title == manager.window.current_url
    assert manager.window.scripts
    assert "rimcrow-direct-workshop-toolbar" in manager.window.scripts[-1]


def test_injected_workshop_toolbar_uses_pywebview_bridge_without_iframe():
    manager = SubBrowserManager.__new__(SubBrowserManager)
    manager.window = FakeWindow()

    manager._inject_workshop_toolbar("https://steamcommunity.com/sharedfiles/filedetails/?id=2023507013")

    script = manager.window.scripts[-1]
    assert "<iframe" not in script.lower()
    assert "window.pywebview" in script
    assert "workshop_browser_action(action, config.workshopId" in script
    assert "2023507013" in script
    assert "SteamCMD 下载" in script


def test_loaded_does_not_inject_toolbar_for_non_workshop_page():
    manager = SubBrowserManager.__new__(SubBrowserManager)
    manager.window = FakeWindow("https://example.com/")
    manager._mode = "external"
    manager._current_url = "https://example.com/"

    manager._on_loaded()

    assert manager.window.title == "https://example.com/"
    assert manager.window.scripts == []
