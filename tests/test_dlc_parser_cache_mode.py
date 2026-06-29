import json

from backend.scanner import parser_dlc
from backend.scanner.parser_dlc import DLCParser


def _write_core_defs(data_path):
    defs_dir = data_path / "Core" / "Defs" / "Misc" / "ExpansionDefs"
    defs_dir.mkdir(parents=True)
    (defs_dir / "ExpansionDefs.xml").write_text(
        "<Defs><ExpansionDef><defName>Core</defName><label>Core</label><description>Base game</description></ExpansionDef></Defs>",
        encoding="utf-8",
    )


def test_dlc_parser_light_mode_reads_cache_without_scanning_tar(tmp_path, monkeypatch):
    data_path = tmp_path / "Data"
    languages_dir = data_path / "Core" / "Languages"
    languages_dir.mkdir(parents=True)
    _write_core_defs(data_path)
    (languages_dir / "ChineseSimplified.tar").write_bytes(b"not a real tar")

    cache_file = tmp_path / "dlc_i18n_all.json"
    cache_file.write_text(
        json.dumps({
            "translations": {"ChineseSimplified": {"Core": {"label": "核心"}}},
            "meta": {"ChineseSimplified.tar": 0},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(parser_dlc, "CACHE_FILE", str(cache_file))

    def fail_extract(*args, **kwargs):
        raise AssertionError("light mode should not scan language tar files")

    monkeypatch.setattr(DLCParser, "_extract_translations_from_tar", fail_extract)

    dlc_parser = DLCParser(str(data_path), sync_translations=False)

    assert dlc_parser.translations["zh-CN"]["Core"]["label"] == "核心"


def test_dlc_parser_default_mode_keeps_syncing_tar_files(tmp_path, monkeypatch):
    data_path = tmp_path / "Data"
    languages_dir = data_path / "Core" / "Languages"
    languages_dir.mkdir(parents=True)
    _write_core_defs(data_path)
    tar_path = languages_dir / "ChineseSimplified.tar"
    tar_path.write_bytes(b"not a real tar")

    monkeypatch.setattr(parser_dlc, "CACHE_FILE", str(tmp_path / "dlc_i18n_all.json"))
    scanned = []

    def fake_extract(self, path):
        scanned.append(path)
        return {"Core": {"label": "核心"}}

    monkeypatch.setattr(DLCParser, "_extract_translations_from_tar", fake_extract)

    dlc_parser = DLCParser(str(data_path))

    assert scanned == [str(tar_path)]
    assert dlc_parser.translations["zh-CN"]["Core"]["label"] == "核心"


def test_dlc_parser_syncs_only_requested_language_when_configured(tmp_path, monkeypatch):
    data_path = tmp_path / "Data"
    languages_dir = data_path / "Core" / "Languages"
    languages_dir.mkdir(parents=True)
    _write_core_defs(data_path)
    zh_tar = languages_dir / "ChineseSimplified.tar"
    fr_tar = languages_dir / "French.tar"
    zh_tar.write_bytes(b"not a real tar")
    fr_tar.write_bytes(b"not a real tar")

    monkeypatch.setattr(parser_dlc, "CACHE_FILE", str(tmp_path / "dlc_i18n_all.json"))
    scanned = []

    def fake_extract(self, path):
        scanned.append(path)
        return {"Core": {"label": "核心" if path == str(zh_tar) else "Coeur"}}

    monkeypatch.setattr(DLCParser, "_extract_translations_from_tar", fake_extract)

    dlc_parser = DLCParser(str(data_path), current_language_code="zh-CN")

    assert scanned == [str(zh_tar)]
    assert dlc_parser.translations["zh-CN"]["Core"]["label"] == "核心"
