import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.settings import AIConfig, settings
from backend.utils.redaction import fingerprint_secret, redact_sensitive_data
from backend.utils.secret_store import SecretStore


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, key):
        return self.values.get((service, key))

    def set_password(self, service, key, value):
        self.values[(service, key)] = value

    def delete_password(self, service, key):
        self.values.pop((service, key), None)


class MissingDeleteKeyring(FakeKeyring):
    def get_password(self, service, key):
        return "stale-secret"

    def delete_password(self, service, key):
        raise RuntimeError("Password could not be found")


class FailingDeleteKeyring(FakeKeyring):
    def delete_password(self, service, key):
        raise RuntimeError("delete should not be called")


class FailingSetKeyring(FakeKeyring):
    def set_password(self, service, key, value):
        raise RuntimeError("credential store locked")


class TestSecurityStorage(unittest.TestCase):
    def test_redaction_masks_nested_sensitive_fields(self):
        redacted = redact_sensitive_data({
            "api_key": "sk-1234567890abcdef",
            "nested": {"password": "secret-password", "max_output_tokens": 128},
            "items": [{"access_token": "access-token-value"}],
        })

        self.assertEqual(redacted["api_key"], "sk-1...cdef")
        self.assertEqual(redacted["nested"]["password"], "secr...word")
        self.assertEqual(redacted["nested"]["max_output_tokens"], 128)
        self.assertNotEqual(redacted["items"][0]["access_token"], "access-token-value")

    def test_secret_store_uses_keyring_backend_and_reports_status(self):
        fake = FakeKeyring()
        store = SecretStore(service_name="test-service", backend=fake)

        store.set_secret("ai.api_key", "sk-test-secret")

        self.assertEqual(store.get_secret("ai.api_key"), "sk-test-secret")
        self.assertEqual(store.status("ai.api_key").hint, "sk-t...cret")
        store.delete_secret("ai.api_key")
        self.assertEqual(store.get_secret("ai.api_key"), "")

    def test_secret_store_treats_missing_delete_as_success(self):
        store = SecretStore(service_name="test-service", backend=MissingDeleteKeyring())

        store.delete_secret("ai.api_key")

        self.assertEqual(store.last_error, "")

    def test_default_secret_store_migrates_legacy_service_name(self):
        fake = FakeKeyring()
        fake.values[("RimModManager", "ai.api_key")] = "sk-legacy-secret"
        store = SecretStore(backend=fake)

        self.assertEqual(store.get_secret("ai.api_key"), "sk-legacy-secret")
        self.assertEqual(fake.values.get(("RimCrow", "ai.api_key")), "sk-legacy-secret")
        self.assertNotIn(("RimModManager", "ai.api_key"), fake.values)

    def test_empty_secret_input_deletes_saved_secret(self):
        fake = FakeKeyring()
        store = SecretStore(service_name="test-service", backend=fake)
        runtime_config = {"ai": {"api_key": "sk-old-secret"}}
        data = {"ai": {"api_key": ""}}
        store.set_secret("ai.api_key", "sk-old-secret")

        changed = store.apply_secret_inputs(runtime_config, data)

        self.assertTrue(changed)
        self.assertEqual(store.get_secret("ai.api_key"), "")
        self.assertEqual(runtime_config["ai"]["api_key"], "")

    def test_preserve_marker_keeps_saved_secret_when_loading_failed(self):
        fake = FakeKeyring()
        store = SecretStore(service_name="test-service", backend=fake)
        runtime_config = {"ai": {"api_key": "sk-old-secret"}}
        data = {"ai": {"api_key": ""}, "_preserve_secret_keys": ["ai.api_key"]}
        store.set_secret("ai.api_key", "sk-old-secret")

        changed = store.apply_secret_inputs(runtime_config, data)

        self.assertFalse(changed)
        self.assertEqual(store.get_secret("ai.api_key"), "sk-old-secret")
        self.assertEqual(runtime_config["ai"]["api_key"], "sk-old-secret")
        self.assertNotIn("_preserve_secret_keys", data)

    def test_empty_secret_input_without_old_value_does_not_touch_keyring(self):
        store = SecretStore(service_name="test-service", backend=FailingDeleteKeyring())
        runtime_config = {"ai": {"api_key": ""}}
        data = {"ai": {"api_key": ""}}

        changed = store.apply_secret_inputs(runtime_config, data)

        self.assertFalse(changed)
        self.assertEqual(runtime_config["ai"]["api_key"], "")

    def test_failed_migration_preserves_legacy_plaintext_until_retry(self):
        import backend.settings as settings_module

        store = SecretStore(service_name="test-service", backend=FailingSetKeyring())
        runtime_config = {"ai": {"api_key": "sk-old-secret"}}

        changed = store.migrate_and_hydrate(runtime_config)

        self.assertFalse(changed)
        self.assertIn("ai.api_key", store.fallback_keys)
        self.assertFalse(store.status("ai.api_key", runtime_config["ai"]["api_key"]).available)

        previous_ai = settings.config.ai
        try:
            settings.config.ai = AIConfig(api_key="sk-old-secret")
            with patch.object(settings_module, "secret_store", store):
                payload = settings.to_storage_dict()
        finally:
            settings.config.ai = previous_ai

        self.assertEqual(payload["ai"]["api_key"], "sk-old-secret")

    def test_settings_storage_payload_excludes_runtime_secrets(self):
        previous_ai = settings.config.ai
        previous_steam_key = settings.config.steam_web_api_key
        previous_proxy_username = settings.config.network.proxy.username
        previous_proxy_password = settings.config.network.proxy.password
        try:
            settings.config.ai = AIConfig(api_key="sk-runtime-secret")
            settings.config.steam_web_api_key = "steam-secret"
            settings.config.network.proxy.username = "proxy-user"
            settings.config.network.proxy.password = "proxy-pass"

            payload = settings.to_storage_dict()
        finally:
            settings.config.ai = previous_ai
            settings.config.steam_web_api_key = previous_steam_key
            settings.config.network.proxy.username = previous_proxy_username
            settings.config.network.proxy.password = previous_proxy_password

        self.assertEqual(payload["ai"]["api_key"], "")
        self.assertEqual(payload["steam_web_api_key"], "")
        self.assertEqual(payload["network"]["proxy"]["username"], "")
        self.assertEqual(payload["network"]["proxy"]["password"], "")

    def test_backup_config_for_update_only_writes_data_update_backup(self):
        import backend.settings as settings_module

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            data_dir.mkdir()
            config_path = data_dir / "config.json"
            update_backup_path = data_dir / "config.json.update.bak"
            backup_dir = root / "backups"
            config_path.write_text(json.dumps({"ai": {"api_key": "old-secret"}}), encoding="utf-8")

            with patch.object(settings_module, "CONFIG_PATH", config_path), \
                    patch.object(settings_module, "CONFIG_UPDATE_BACKUP_PATH", update_backup_path), \
                    patch.object(settings_module, "BACKUP_DIR", backup_dir):
                self.assertTrue(settings_module.backup_config_for_update())

            self.assertTrue(update_backup_path.exists())
            self.assertFalse((backup_dir / "config").exists())
            self.assertEqual(json.loads(update_backup_path.read_text(encoding="utf-8"))["ai"]["api_key"], "old-secret")

    def test_secret_fingerprint_does_not_contain_plaintext(self):
        fingerprint = fingerprint_secret("sk-secret-value")

        self.assertTrue(fingerprint)
        self.assertNotIn("sk-secret-value", fingerprint)


if __name__ == "__main__":
    unittest.main()
