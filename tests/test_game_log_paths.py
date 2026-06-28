import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.ai.ai_contracts import AttachmentDraft
from backend.ai.ai_tools import AIToolExecutor, GetLogContextArgs
from backend.ai.def_attachments import AttachmentResolver, get_attachment_definitions
from backend.api import API
from backend.managers.mgr_game import GameManager
from backend.managers.mgr_game_logs import GameLogManager
from backend.utils.logger import AppLogReader


class _DefinitionManagerStub:
    def __init__(self):
        self.attachment_definitions = get_attachment_definitions()

    def get_attachment_projection_fields(self, kind, prompt_id=None, options=None):
        return []


class _LlmStub:
    def estimate_text_tokens(self, text, model_name):
        return len(text)


class TestGameLogPathResolution(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp_dir, ignore_errors=True)

    def test_windows_default_player_log_paths_are_fixed_under_locallow(self):
        fake_home = self.temp_dir / "winhome"
        with patch("backend.managers.mgr_game.platform.system", return_value="Windows"), \
             patch("backend.managers.mgr_game.os.getenv", return_value=str(fake_home)), \
             patch("backend.managers.mgr_game.os.path.expanduser", return_value=str(fake_home)):
            paths = GameManager.get_default_player_log_paths("Player.log")

        self.assertEqual(paths, [
            str(fake_home / "AppData" / "LocalLow" / "Ludeon Studios" / "RimWorld by Ludeon Studios" / "Player.log")
        ])

    def test_macos_default_player_log_paths_cover_unity_and_company_locations(self):
        fake_home = self.temp_dir / "machome"
        with patch("backend.managers.mgr_game.platform.system", return_value="Darwin"), \
             patch("backend.managers.mgr_game.os.path.expanduser", return_value=str(fake_home)):
            paths = GameManager.get_default_player_log_paths("Player.log")

        self.assertEqual(paths, [
            str(fake_home / "Library" / "Logs" / "Ludeon Studios" / "RimWorld by Ludeon Studios" / "Player.log"),
            str(fake_home / "Library" / "Logs" / "Unity" / "Player.log"),
        ])

    def test_linux_default_user_data_paths_include_flatpak_fallback(self):
        fake_home = self.temp_dir / "linuxhome"
        with patch("backend.managers.mgr_game.platform.system", return_value="Linux"), \
             patch("backend.managers.mgr_game.os.path.expanduser", return_value=str(fake_home)):
            roots = GameManager.get_default_user_data_paths()

        self.assertEqual(roots, [
            str(fake_home / ".config" / "unity3d" / "Ludeon Studios" / "RimWorld by Ludeon Studios"),
            str(fake_home / ".var" / "app" / "com.valvesoftware.Steam" / "config" / "unity3d" / "Ludeon Studios" / "RimWorld by Ludeon Studios"),
        ])

    def test_game_log_manager_reads_player_log_from_default_root_not_profile_root(self):
        default_root = self.temp_dir / "default-userdata"
        profile_root = self.temp_dir / "profile-userdata"
        default_root.mkdir(parents=True)
        profile_root.mkdir(parents=True)
        (default_root / "Player.log").write_text("default failure line\n  at stack", encoding="utf-8")
        (profile_root / "Player.log").write_text("profile failure line\n  at stack", encoding="utf-8")

        manager = GameLogManager(SimpleNamespace(user_data_path=str(profile_root)))
        with patch("backend.managers.mgr_game_logs.GameManager.get_default_user_data_paths", return_value=[str(default_root)]), \
             patch("backend.managers.mgr_game_logs.GameManager.get_default_player_log_paths", return_value=[str(default_root / "Player.log")]):
            files = manager.get_log_files()
            page = manager.read_log_page("Player.log", page=1, page_size=20)

        self.assertEqual(files[0]["path"], str(default_root / "Player.log"))
        self.assertEqual(page["status"], "success")
        self.assertIn("default failure line", page["blocks"][0]["message"])

    def test_game_log_manager_reads_rmm_realtime_from_profile_root(self):
        default_root = self.temp_dir / "default-userdata"
        profile_root = self.temp_dir / "profile-userdata"
        default_root.mkdir(parents=True)
        profile_root.mkdir(parents=True)
        (default_root / "RMM_Realtime.log").write_text('{"message":"default realtime"}\n', encoding="utf-8")
        (profile_root / "RMM_Realtime.log").write_text('{"message":"profile realtime"}\n', encoding="utf-8")

        manager = GameLogManager(SimpleNamespace(user_data_path=str(profile_root)))
        with patch("backend.managers.mgr_game_logs.GameManager.get_default_user_data_paths", return_value=[str(default_root)]):
            filepath = manager.resolve_log_file_path("RMM_Realtime.log")
            page = manager.read_log_page("RMM_Realtime.log", page=1, page_size=20)

        self.assertEqual(filepath, str(profile_root / "RMM_Realtime.log"))
        self.assertEqual(page["status"], "success")
        self.assertIn("profile realtime", page["blocks"][0]["message"])

    def test_game_log_page_can_reach_older_blocks_beyond_cache_limit(self):
        profile_root = self.temp_dir / "profile-userdata"
        profile_root.mkdir(parents=True)
        log_file = profile_root / "RMM_Realtime.log"
        log_file.write_text(
            "\n".join(f'{{"level":"INFO","message":"game line {idx}"}}' for idx in range(20005)) + "\n",
            encoding="utf-8",
        )

        manager = GameLogManager(SimpleNamespace(user_data_path=str(profile_root)))
        with patch("backend.managers.mgr_game_logs.GameManager.get_default_user_data_paths", return_value=[]), \
             patch("backend.managers.mgr_game_logs.LoadOrderManager") as load_order_manager_cls:
            load_order_manager_cls.return_value.read_active_mods.return_value = {"active_mods": []}
            page = manager.read_log_page("RMM_Realtime.log", page=41, page_size=500)

        self.assertEqual(page["status"], "success")
        self.assertFalse(page["has_more"])
        self.assertEqual(page["total_pages"], 41)
        self.assertEqual(page["blocks"][0]["message"], "game line 0")

    def test_app_log_page_can_reach_older_blocks_beyond_cache_limit(self):
        log_dir = self.temp_dir / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "app.log"
        log_file.write_text(
            "\n".join(f'{{"level":"INFO","message":"app line {idx}"}}' for idx in range(20005)) + "\n",
            encoding="utf-8",
        )

        reader = AppLogReader()
        reader.log_dir = log_dir
        page = reader.read_log_page("app.log", page=41, page_size=500)

        self.assertEqual(page["status"], "success")
        self.assertFalse(page["has_more"])
        self.assertEqual(page["total_pages"], 41)
        self.assertEqual(page["blocks"][0]["message"], "app line 0")

    def test_ai_tool_get_log_context_uses_reader_resolved_game_log_path(self):
        log_file = self.temp_dir / "Player.log"
        log_file.write_text("error line\n  at stack", encoding="utf-8")
        reader = Mock()
        reader.resolve_log_file_path.return_value = str(log_file)
        reader.get_raw_logs_by_lines.return_value = [{
            "level": "ERROR",
            "message": "error line",
            "details": "at stack",
            "raw_lines": [1],
            "count": 1,
        }]

        with patch("backend.ai.ai_tools.LoadOrderManager") as load_order_manager_cls:
            load_order_manager_cls.return_value.read_active_mods.return_value = {"active_mods": []}
            executor = AIToolExecutor(
                SimpleNamespace(is_healthy=True, user_data_path=str(self.temp_dir / "profile")),
                {"log_source_type": "game", "filename": "Player.log"},
                reader,
            )
            result = executor._tool_get_log_context(GetLogContextArgs(target_line=1))

        reader.resolve_log_file_path.assert_called_once_with("Player.log")
        self.assertIn("error line", result["context_content"])

    def test_attachment_resolver_uses_reader_resolved_game_log_path(self):
        log_file = self.temp_dir / "Player.log"
        log_file.write_text("error line\n  at stack", encoding="utf-8")
        reader = Mock()
        reader.resolve_log_file_path.return_value = str(log_file)
        reader.get_raw_logs_by_lines.return_value = [{
            "level": "ERROR",
            "message": "error line",
            "details": "at stack",
            "raw_lines": [1],
            "count": 1,
        }]

        resolver = AttachmentResolver(_DefinitionManagerStub(), _LlmStub())
        draft = AttachmentDraft.model_validate({
            "kind": "diagnosis_context",
            "source": {
                "owner_type": "assistant",
                "source_type": "game",
                "filename": "Player.log",
            },
            "selector": {
                "mode": "summary",
                "values": [1],
            },
            "snapshot": {
                "summary": "1 条已选日志",
            },
        })

        attachment = resolver.resolve_one(
            draft,
            active_context=SimpleNamespace(user_data_path=str(self.temp_dir / "profile")),
            reader=reader,
        )

        reader.resolve_log_file_path.assert_called_once_with("Player.log")
        self.assertEqual(attachment.facts["filename"], "Player.log")
        self.assertEqual(attachment.facts["source_type"], "game")


if __name__ == "__main__":
    unittest.main()
