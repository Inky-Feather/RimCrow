import unittest

from backend.managers.mgr_network import NetworkManager


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


if __name__ == "__main__":
    unittest.main()
