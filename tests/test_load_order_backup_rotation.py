import datetime
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.managers.mgr_load_order import LoadOrderManager
from backend.managers.mgr_profile import ProfileContext


class TestLoadOrderBackupRotation(unittest.TestCase):
    def _create_context(self, temp_dir: str) -> ProfileContext:
        game_dir = Path(temp_dir) / "game"
        user_dir = Path(temp_dir) / "user"
        game_dir.mkdir(parents=True, exist_ok=True)
        user_dir.mkdir(parents=True, exist_ok=True)
        context = ProfileContext(
            profile_id=f"backup-test-{uuid.uuid4().hex}",
            game_version="1.5.4069",
            game_install_path=str(game_dir),
            user_data_path=str(user_dir),
            prefer_steam_launch=False,
            use_workshop_mods=True,
            use_self_mods=False,
        )
        context.ensure_directories()
        return context

    @staticmethod
    def _set_mtime(path: Path, value: datetime.datetime) -> None:
        timestamp = value.timestamp()
        os.utime(path, (timestamp, timestamp))

    @staticmethod
    def _write_rml(path: Path) -> None:
        path.write_text(
            """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<savedModList><meta><modIds><li>author.mod</li></modIds></meta>
<modList><ids><li>author.mod</li></ids><names><li>Author Mod</li></names></modList>
</savedModList>""",
            encoding="utf-8",
        )

    def test_listing_backups_does_not_rotate_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            manager = LoadOrderManager(context, rotate_backups=False)
            now = datetime.datetime.now().replace(hour=0, minute=5, second=0, microsecond=0)
            path = Path(manager.today_dir) / "ModList_20000101_000000.rml"
            self._write_rml(path)
            self._set_mtime(path, now)
            latest_path = Path(manager.backup_root) / "Latest_ModList.rml"
            self._write_rml(latest_path)

            backups = manager.get_all_backups()

            self.assertTrue(path.exists())
            self.assertFalse((Path(manager.earlier_dir) / path.name).exists())
            self.assertEqual(backups["last_backup"][0]["path"], str(latest_path))

    def test_default_manager_init_does_not_rotate_backups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)

            with patch.object(LoadOrderManager, "_rotate_backups") as rotate_backups:
                LoadOrderManager(context)

            rotate_backups.assert_not_called()

    def test_explicit_manager_init_rotates_backups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)

            with patch.object(LoadOrderManager, "_rotate_backups") as rotate_backups:
                LoadOrderManager(context, rotate_backups=True)

            rotate_backups.assert_called_once()

    def test_backup_created_just_after_midnight_is_protected_for_six_hours(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            manager = LoadOrderManager(context, rotate_backups=False)
            now = datetime.datetime.now().replace(hour=0, minute=10, second=0, microsecond=0)
            created_at = now.replace(minute=5)
            path = Path(manager.today_dir) / "ModList_19990101_235959.rml"
            self._write_rml(path)
            self._set_mtime(path, created_at)

            with patch("backend.managers.mgr_load_order.settings.config.backup_retention_days", 30):
                manager._rotate_backups(now=now)
                self.assertTrue(path.exists())

                manager._rotate_backups(now=created_at + datetime.timedelta(days=1, hours=6, minutes=1))
                self.assertFalse(path.exists())
                self.assertTrue((Path(manager.earlier_dir) / path.name).exists())

    def test_same_day_long_term_backup_is_replaced_by_newer_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            manager = LoadOrderManager(context, rotate_backups=False)
            now = datetime.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
            old_time = now - datetime.timedelta(hours=22)
            new_time = now - datetime.timedelta(hours=20)
            date_part = old_time.strftime("%Y%m%d")
            old_path = Path(manager.earlier_dir) / f"ModList_{date_part}_140000.rml"
            new_path = Path(manager.today_dir) / f"ModList_{date_part}_160000.rml"
            self._write_rml(old_path)
            self._write_rml(new_path)
            self._set_mtime(old_path, old_time)
            self._set_mtime(new_path, new_time)

            with patch("backend.managers.mgr_load_order.settings.config.backup_retention_days", 30):
                manager._rotate_backups(now=now)

            self.assertFalse(old_path.exists())
            self.assertFalse(new_path.exists())
            archived = list(Path(manager.earlier_dir).glob("*.rml"))
            self.assertEqual([item.name for item in archived], [new_path.name])

    def test_archive_move_failure_keeps_existing_long_term_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            manager = LoadOrderManager(context, rotate_backups=False)
            now = datetime.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
            old_time = now - datetime.timedelta(hours=22)
            new_time = now - datetime.timedelta(hours=20)
            date_part = old_time.strftime("%Y%m%d")
            old_path = Path(manager.earlier_dir) / f"ModList_{date_part}_140000.rml"
            new_path = Path(manager.today_dir) / f"ModList_{date_part}_160000.rml"
            self._write_rml(old_path)
            self._write_rml(new_path)
            self._set_mtime(old_path, old_time)
            self._set_mtime(new_path, new_time)

            with patch("backend.managers.mgr_load_order.os.replace", side_effect=OSError("move failed")), \
                 patch("backend.managers.mgr_load_order.settings.config.backup_retention_days", 30):
                self.assertFalse(manager._rotate_backups(now=now))

            self.assertTrue(old_path.exists())
            self.assertTrue(new_path.exists())

    def test_main_save_creates_backup_without_rotating(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_path = Path(context.mods_config_file)
            config_path.write_text("<ModsConfigData><activeMods /></ModsConfigData>", encoding="utf-8")
            manager = LoadOrderManager(context, rotate_backups=False)
            manager._build_export_entries = lambda *_args, **_kwargs: [
                {"package_id": "new.mod", "package_token": "new.mod"},
            ]
            manager._create_backup = lambda: True
            calls = []

            def rotate_once(*_args, **_kwargs):
                calls.append("rotate")
                return True

            manager._rotate_backups = rotate_once

            self.assertTrue(manager.save_active_mods(["new.mod"], is_dirty=True))
            self.assertEqual(calls, [])

    def test_automatic_backup_skips_empty_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            Path(context.mods_config_file).write_text("<ModsConfigData><activeMods /></ModsConfigData>", encoding="utf-8")
            manager = LoadOrderManager(context, rotate_backups=False)
            manager.read_active_mods = lambda *_args, **_kwargs: {
                "active_mods": [],
                "mods": [],
                "errors": [],
            }

            manager._create_backup()

            self.assertEqual(len(list(Path(manager.today_dir).glob("*.rml"))), 0)

    def test_automatic_backups_overwrite_same_second_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            Path(context.mods_config_file).write_text("<ModsConfigData />", encoding="utf-8")
            manager = LoadOrderManager(context, rotate_backups=False)
            manager.read_active_mods = lambda *_args, **_kwargs: {
                "active_mods": ["author.mod"],
                "mods": [{"package_id": "author.mod", "package_token": "author.mod"}],
                "errors": [],
            }

            manager._create_backup()
            manager._create_backup()

            self.assertEqual(len(list(Path(manager.today_dir).glob("*.rml"))), 1)

    def test_automatic_backup_failure_keeps_main_config_save_successful(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_path = Path(context.mods_config_file)
            original = "<ModsConfigData><activeMods><li>old.mod</li></activeMods></ModsConfigData>"
            config_path.write_text(original, encoding="utf-8")
            manager = LoadOrderManager(context, rotate_backups=False)
            entries = [{"package_id": "new.mod", "package_token": "new.mod"}]
            manager._build_export_entries = lambda *_args, **_kwargs: entries
            manager._write_rml_file = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("backup unreadable"))

            self.assertTrue(manager.save_active_mods(["new.mod"], is_dirty=True))

            saved_text = config_path.read_text(encoding="utf-8")
            self.assertNotEqual(saved_text, original)
            self.assertIn("<li>new.mod</li>", saved_text)
            self.assertIn("备份", manager.last_backup_error)

    def test_latest_backup_failure_does_not_report_main_save_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_path = Path(context.mods_config_file)
            config_path.write_text("<ModsConfigData><activeMods /></ModsConfigData>", encoding="utf-8")
            manager = LoadOrderManager(context, rotate_backups=False)
            manager._build_export_entries = lambda *_args, **_kwargs: [
                {"package_id": "new.mod", "package_token": "new.mod"},
            ]
            manager._create_backup = lambda: None

            def fail_latest(path, _entries):
                if Path(path).name == "Latest_ModList.rml":
                    raise OSError("latest backup unavailable")

            with patch.object(manager, "_write_rml_file", side_effect=fail_latest):
                self.assertTrue(manager.save_active_mods(["new.mod"], is_dirty=True))

            self.assertIn("<li>new.mod</li>", config_path.read_text(encoding="utf-8"))

    def test_save_does_not_run_backup_rotation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_path = Path(context.mods_config_file)
            original = "<ModsConfigData><activeMods><li>old.mod</li></activeMods></ModsConfigData>"
            config_path.write_text(original, encoding="utf-8")
            manager = LoadOrderManager(context, rotate_backups=False)
            manager._build_export_entries = lambda *_args, **_kwargs: [
                {"package_id": "new.mod", "package_token": "new.mod"},
            ]
            manager._rotate_backups = lambda *_args, **_kwargs: self.fail("保存排序不应触发备份流转")
            manager._create_backup = lambda: True

            self.assertTrue(manager.save_active_mods(["new.mod"], is_dirty=True))

            saved_text = config_path.read_text(encoding="utf-8")
            self.assertNotEqual(saved_text, original)
            self.assertIn("<li>new.mod</li>", saved_text)
            self.assertEqual(manager.last_backup_error, "")

    def test_broken_config_backup_failure_keeps_main_config_save_successful(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            context = self._create_context(temp_dir)
            config_path = Path(context.mods_config_file)
            original = "<ModsConfigData>"
            config_path.write_text(original, encoding="utf-8")
            manager = LoadOrderManager(context, rotate_backups=False)
            manager._build_export_entries = lambda *_args, **_kwargs: [
                {"package_id": "new.mod", "package_token": "new.mod"},
            ]
            manager._rotate_backups = lambda *_args, **_kwargs: True
            manager._backup_broken_modsconfig = lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("cannot copy"))

            self.assertTrue(manager.save_active_mods(["new.mod"], is_dirty=False))

            saved_text = config_path.read_text(encoding="utf-8")
            self.assertNotEqual(saved_text, original)
            self.assertIn("<li>new.mod</li>", saved_text)
            self.assertIn("损坏", manager.last_backup_error)


if __name__ == "__main__":
    unittest.main()
