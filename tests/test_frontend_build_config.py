from pathlib import Path

import pack_nuitka
import pack_pyinstaller


def test_codemirror_manual_chunk_keeps_runtime_dependencies_together():
    config_text = Path("frontend/vite.config.js").read_text(encoding="utf-8")

    for package_name in ("style-mod", "w3c-keyname", "crelt", "@marijn/find-cluster-break"):
        assert f"/node_modules/{package_name}/" in config_text


def test_steamworks_runtime_is_embedded_not_zipped():
    root = Path.cwd()

    for packer in (pack_pyinstaller, pack_nuitka):
        assert [path.name for path in packer._steamworks_runtime_files(root)] == ["SteamworksPy64.dll", "steam_api64.dll"]
        assert not any(
            archive_path.parts[:2] == ("tools", "steamworks")
            for _, archive_path in packer._iter_tools_files(root / "tools")
        )
