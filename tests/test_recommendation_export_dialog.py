from pathlib import Path
from unittest.mock import patch

from backend.api import API


class FakeRecommendationExportManager:
    def default_filename(self, payload):
        return "推荐.txt"

    def file_types_for_format(self, export_format):
        return ("Text Files (*.txt)", "All Files (*.*)")

    def ensure_extension(self, target_path, export_format):
        return target_path

    def export(self, payload, target_path=None, target_dir=None):
        return {"path": target_path or target_dir}


def test_recommendation_export_dialogs_start_from_desktop(tmp_path: Path):
    api = API.__new__(API)
    api.recommendation_export_mgr = FakeRecommendationExportManager()

    with (
        patch("backend.api.get_desktop_directory", return_value=str(tmp_path)),
        patch("backend.api.file_mgr.save_file_dialog", return_value=str(tmp_path / "推荐.txt")) as save_dialog,
        patch("backend.api.file_mgr.select_folder_dialog", return_value=str(tmp_path)) as folder_dialog,
    ):
        api.recommendation_export({"format": "txt", "mods": [{"package_id": "a"}]})
        api.recommendation_export({"format": "markdown", "mods": [{"package_id": "a"}]})

    assert save_dialog.call_args.kwargs["initial_dir"] == str(tmp_path)
    assert folder_dialog.call_args.args[0] == str(tmp_path)
