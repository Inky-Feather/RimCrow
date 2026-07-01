import zipfile
from pathlib import Path

import pack_pyinstaller


def _prepare_pack_root(root: Path) -> None:
    (root / "submodules" / "SteamworksPy" / "steamworks").mkdir(parents=True)
    (root / "submodules" / "SteamworksPy" / "steamworks" / "__init__.py").write_text("", encoding="utf-8")
    steamworks_dir = root / "tools" / "steamworks"
    steamworks_dir.mkdir(parents=True)
    for name in ("SteamworksPy.dylib", "libsteam_api.dylib"):
        (steamworks_dir / name).write_text("", encoding="utf-8")


def test_pyinstaller_output_candidates_use_macos_app_layout(monkeypatch):
    monkeypatch.setattr(pack_pyinstaller.sys, "platform", "darwin")

    candidates = list(pack_pyinstaller._pyinstaller_output_candidates(Path("dist"), "RimCrow"))

    assert candidates == [Path("dist") / "RimCrow.app", Path("dist") / "RimCrow"]


def test_create_release_zip_includes_macos_app_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(pack_pyinstaller, "__file__", str(tmp_path / "pack_pyinstaller.py"))
    monkeypatch.setattr(pack_pyinstaller.sys, "platform", "darwin")
    app_binary = tmp_path / "dist" / "RimCrow.app" / "Contents" / "MacOS" / "RimCrow"
    app_binary.parent.mkdir(parents=True)
    app_binary.write_text("binary", encoding="utf-8")

    zip_path = pack_pyinstaller.create_release_zip("RimCrow", "1.2.3")

    with zipfile.ZipFile(zip_path) as archive:
        assert "RimCrow/RimCrow.app/Contents/MacOS/RimCrow" in archive.namelist()


def test_pack_application_uses_macos_onedir_and_skips_windows_options(monkeypatch, tmp_path):
    _prepare_pack_root(tmp_path)
    main_file = tmp_path / "main.py"
    main_file.write_text("print('ok')", encoding="utf-8")
    captured = {}

    monkeypatch.setattr(pack_pyinstaller, "__file__", str(tmp_path / "pack_pyinstaller.py"))
    monkeypatch.setattr(pack_pyinstaller.sys, "platform", "darwin")
    monkeypatch.setattr(pack_pyinstaller, "create_pyinstaller_hook_dir", lambda: str(tmp_path / "hooks"))
    monkeypatch.setattr(pack_pyinstaller, "_run_command_with_log", lambda cmd, log_path, env=None: captured.setdefault("cmd", cmd) and 0)

    assert pack_pyinstaller.packApplication(
        main_file=str(main_file),
        icon_path="",
        name="RimCrow",
        splash_path="splash.png",
        version="1.2.3",
        company="Inky Feather",
        upx_dir="/tmp/upx",
    )

    cmd = captured["cmd"]
    assert "-D" in cmd
    assert "-F" not in cmd
    assert "--version-file" not in cmd
    assert "--splash" not in cmd
    assert "--upx-dir" not in cmd
