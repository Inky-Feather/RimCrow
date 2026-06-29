import io
import json
import zipfile
from unittest.mock import patch

from backend.managers.mgr_multiplayer_compat import MultiplayerCompatibilityManager
from backend.settings import settings


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _base_mods():
    return [
        {"package_id": "rwmt.Multiplayer", "name": "Multiplayer", "workshop_id": "2606448745", "file_stats": {"code_dll": 1}},
        {"package_id": "example.official", "name": "Official Rated", "workshop_id": "111", "file_stats": {"code_dll": 0}},
        {"package_id": "example.xmlonly", "name": "XML Only", "workshop_id": "222", "file_stats": {"code_dll": 0}},
        {"package_id": "example.assembly", "name": "Unknown Assembly", "workshop_id": "333", "file_stats": {"code_dll": 1}},
        {"package_id": "example.patch", "name": "Patch Target", "workshop_id": "444", "file_stats": {"code_dll": 1}},
    ]


def _source_archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_multiplayer_compatibility_requires_feature_and_multiplayer(tmp_path):
    official_path = _write_json(tmp_path / "mp.json", [])
    package_path = _write_json(tmp_path / "mp_compat_ids.json", [])
    manager = MultiplayerCompatibilityManager()

    with patch.object(settings.config, "enable_multiplayer_compatibility_check", False), \
         patch.object(settings.config, "multiplayer_compatibility_path", official_path), \
         patch.object(settings.config, "mp_compat_package_ids_path", package_path):
        mods = _base_mods()
        state = manager.enrich_mods(mods, ["rwmt.Multiplayer"])

    assert state["enabled"] is False
    assert state["feature_enabled"] is False
    assert state["multiplayer_installed"] is True
    assert state["multiplayer_active"] is True
    assert all(mod["multiplayer_compat"]["search_values"] == [] for mod in mods)

    with patch.object(settings.config, "enable_multiplayer_compatibility_check", True), \
         patch.object(settings.config, "multiplayer_compatibility_path", official_path), \
         patch.object(settings.config, "mp_compat_package_ids_path", package_path):
        mods = [mod for mod in _base_mods() if mod["package_id"] != "rwmt.Multiplayer"]
        state = manager.enrich_mods(mods, [])

    assert state["enabled"] is False
    assert state["feature_enabled"] is True
    assert state["multiplayer_installed"] is False
    assert state["multiplayer_active"] is False


def test_multiplayer_compatibility_effective_status_and_patch_scope(tmp_path):
    official_path = _write_json(tmp_path / "mp.json", [
        {"workshopId": "111", "name": "Official Rated", "status": 2, "notes": "Major feature issue"},
        {"workshopId": "444", "name": "Patch Target", "status": 1},
    ])
    package_path = _write_json(tmp_path / "mp_compat_ids.json", {"packageIds": ["example.patch"]})
    manager = MultiplayerCompatibilityManager()

    with patch.object(settings.config, "enable_multiplayer_compatibility_check", True), \
         patch.object(settings.config, "multiplayer_compatibility_path", official_path), \
         patch.object(settings.config, "mp_compat_package_ids_path", package_path):
        mods = _base_mods()
        state = manager.enrich_mods(mods, ["rwmt.Multiplayer", "rwmt.MultiplayerCompatibility", "example.patch"])

    by_id = {mod["package_id"].lower(): mod["multiplayer_compat"] for mod in mods}
    assert state["enabled"] is True
    assert state["multiplayer_active"] is True
    assert state["mp_compat_active"] is True

    # 官方 1-4 级始终优先，即使本地没有 DLL，也不被 XML-only 兜底覆盖。
    assert by_id["example.official"]["effective_status"] == 2
    assert by_id["example.official"]["status_source"] == "official"
    assert by_id["example.official"]["notes"] == "Major feature issue"

    assert by_id["example.xmlonly"]["effective_status"] == 4
    assert by_id["example.xmlonly"]["status_source"] == "xml_only"
    assert by_id["example.assembly"]["effective_status"] == 0
    assert by_id["example.assembly"]["status_source"] == "unknown"

    assert by_id["example.patch"]["effective_status"] == 1
    assert by_id["example.patch"]["has_mp_compat_patch"] is True
    assert by_id["example.patch"]["mp_compat_effective"] is True
    assert "可修正" in by_id["example.patch"]["search_values"]


def test_mp_compat_patch_only_effective_for_active_mods(tmp_path):
    official_path = _write_json(tmp_path / "mp.json", [{"workshopId": "444", "name": "Patch Target", "status": 1}])
    package_path = _write_json(tmp_path / "mp_compat_ids.json", ["example.patch"])
    manager = MultiplayerCompatibilityManager()

    with patch.object(settings.config, "enable_multiplayer_compatibility_check", True), \
         patch.object(settings.config, "multiplayer_compatibility_path", official_path), \
         patch.object(settings.config, "mp_compat_package_ids_path", package_path):
        mods = _base_mods()
        manager.enrich_mods(mods, ["rwmt.Multiplayer", "rwmt.MultiplayerCompatibility"])

    patch_status = next(mod["multiplayer_compat"] for mod in mods if mod["package_id"] == "example.patch")
    assert patch_status["has_mp_compat_patch"] is True
    assert patch_status["mp_compat_active"] is True
    assert patch_status["mp_compat_effective"] is False


def test_mp_compat_package_ids_can_be_generated_from_source_archive(tmp_path):
    archive_bytes = _source_archive({
        "Multiplayer-Compatibility-master/Source/Mods/Example.cs": '''
            [MpCompatFor("Example.Target")]
            [MpCompatFor("Example.Other")]
            public class ExampleCompat {}
        ''',
        "Multiplayer-Compatibility-master/Source_Referenced/Referenced.cs": '''
            [MpCompatFor("Referenced.Target")]
            public class ReferencedCompat {}
        ''',
        "Multiplayer-Compatibility-master/Docs/Ignored.cs": '[MpCompatFor("Ignored.Target")]',
    })
    manager = MultiplayerCompatibilityManager()
    target_path = tmp_path / "mpCompatPackageIds.json"

    with patch.object(manager, "_download_source_archive", return_value=(
        archive_bytes,
        {"Last-Modified": "Wed, 11 Jun 2025 12:00:00 GMT", "ETag": '"source-etag"'},
        "https://example.invalid/source.zip",
    )):
        result = manager.update_mp_compat_package_ids("https://example.invalid/source.zip", str(target_path))

    payload = json.loads(target_path.read_text(encoding="utf-8"))
    assert result["count"] == 3
    assert payload["package_ids"] == ["example.other", "example.target", "referenced.target"]
    assert payload["source"]["etag"] == "source-etag"


def test_official_compatibility_file_is_formatted_after_download(tmp_path):
    target_path = tmp_path / "multiplayerCompatibility.json"
    target_path.write_text('{"mods":[{"name":"测试","status":4}]}', encoding="utf-8")
    manager = MultiplayerCompatibilityManager()

    manager.format_official_compatibility_file(str(target_path))

    text = target_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert '\n  "mods": [' in text
    assert json.loads(text)["mods"][0]["name"] == "测试"
