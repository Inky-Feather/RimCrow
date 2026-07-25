import unittest
import os

from backend.managers.mgr_network import NetworkManager, PROXY_ENV_KEYS
from backend.settings import settings


class TestNetworkManagerHostsCleanup(unittest.TestCase):
    def test_remove_custom_block_removes_legacy_rimmodmanager_hosts_block(self):
        manager = NetworkManager.__new__(NetworkManager)
        manager.marker_start = "# --- RimCrow Hosts Start ---\n"
        manager.marker_end = "# --- RimCrow Hosts End ---\n"
        content = (
            "before\n"
            "# --- RimModManager Hosts Start ---\n"
            "1.2.3.4\texample.invalid\n"
            "# --- RimModManager Hosts End ---\n"
            "after\n"
        )

        cleaned = manager._remove_custom_block(content)

        self.assertNotIn("RimModManager Hosts", cleaned)
        self.assertEqual(cleaned, "before\nafter\n")


class TestNetworkManagerProxyEnv(unittest.TestCase):
    def setUp(self):
        self._env_snapshot = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
        proxy = settings.config.network.proxy
        self._proxy_snapshot = {
            "enabled": proxy.enabled,
            "type": proxy.type,
            "host": proxy.host,
            "port": proxy.port,
            "username": proxy.username,
            "password": proxy.password,
            "bypass_list": list(proxy.bypass_list or []),
        }

    def tearDown(self):
        for key, value in self._env_snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        proxy = settings.config.network.proxy
        for key, value in self._proxy_snapshot.items():
            setattr(proxy, key, value)

    def test_disabled_manager_proxy_restores_existing_environment_proxy(self):
        for key in PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:7890"

        manager = NetworkManager.__new__(NetworkManager)
        manager._original_proxy_env = {key: os.environ.get(key) for key in PROXY_ENV_KEYS}
        settings.config.network.proxy.enabled = False
        settings.config.network.proxy.host = ""
        settings.config.network.proxy.port = 0

        manager.apply_proxy_settings()

        self.assertEqual(os.environ.get("HTTP_PROXY"), "http://127.0.0.1:7890")

    def test_enabled_manager_proxy_sets_requests_proxy_environment(self):
        for key in PROXY_ENV_KEYS:
            os.environ.pop(key, None)

        manager = NetworkManager.__new__(NetworkManager)
        manager._original_proxy_env = {key: None for key in PROXY_ENV_KEYS}
        proxy = settings.config.network.proxy
        proxy.enabled = True
        proxy.type = "http"
        proxy.host = "127.0.0.1"
        proxy.port = 10808
        proxy.username = ""
        proxy.password = ""
        proxy.bypass_list = ["localhost", "127.0.0.1"]

        manager.apply_proxy_settings()

        self.assertEqual(os.environ.get("HTTP_PROXY"), "http://127.0.0.1:10808")
        self.assertEqual(os.environ.get("http_proxy"), "http://127.0.0.1:10808")
        self.assertEqual(os.environ.get("ALL_PROXY"), "http://127.0.0.1:10808")
        self.assertEqual(os.environ.get("NO_PROXY"), "localhost,127.0.0.1")


if __name__ == "__main__":
    unittest.main()
