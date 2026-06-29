import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False
    print("提示: 未安装 'pathspec' 库，.gitignore 过滤功能将不可用。")


def _append_pythonpath(env: dict[str, str], *paths: Path) -> None:
    existing_paths = [item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item]
    extra_paths = [str(path.resolve()) for path in paths if path.exists()]
    env["PYTHONPATH"] = os.pathsep.join([*extra_paths, *existing_paths])


def _resolve_steamworkspy_source_dir(project_root: Path) -> Path:
    source_dir = project_root / "submodules" / "SteamworksPy"
    if not (source_dir / "steamworks" / "__init__.py").exists():
        raise FileNotFoundError(f"未找到 SteamworksPy 源码目录: {source_dir}")
    return source_dir


def _run_command_with_log(cmd: list[str], log_path: Path, env: dict[str, str] | None = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_file.write(line)
        return process.wait()


def _npm_command() -> str:
    if sys.platform == "win32":
        return shutil.which("npm.cmd") or "npm.cmd"
    return shutil.which("npm") or "npm"


def _platform_tag() -> str:
    if sys.platform.startswith(("win32", "cygwin", "msys")):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in sys.platform).strip("-") or "unknown"


def _release_zip_name(app_name: str, version: str) -> str:
    version_text = str(version or "0.0.0").strip().lstrip("vV") or "0.0.0"
    return f"{app_name}-v{version_text}-{_platform_tag()}.zip"


def _find_upx_binary(upx_dir: str = "") -> str:
    raw_path = os.environ.get("UPX_DIR") or upx_dir
    if not raw_path:
        return ""
    upx_path = Path(raw_path)
    if upx_path.is_dir():
        upx_path = upx_path / "upx.exe"
    return str(upx_path) if upx_path.exists() else ""


def _normal_version(version: str) -> str:
    parts = str(version or "1.0.0").split(".")
    numeric_parts = []
    for part in parts[:4]:
        try:
            numeric_parts.append(str(int(part)))
        except ValueError:
            numeric_parts.append("0")
    while len(numeric_parts) < 4:
        numeric_parts.append("0")
    return ".".join(numeric_parts)


def _add_existing_data_dir(cmd: list[str], source: Path, target: str) -> None:
    if source.exists():
        cmd.append(f"--include-data-dir={source.as_posix()}={target}")
    else:
        print(f"警告: 资源目录不存在，已跳过 {source}")


def _build_nuitka_args(
    main_file: str,
    icon_path: str,
    name: str,
    splash_path: str,
    version: str,
    company: str,
    mode: str,
    upx_dir: str = "",
) -> list[str]:
    project_root = Path(__file__).resolve().parent
    _resolve_steamworkspy_source_dir(project_root)
    normalized_version = _normal_version(version)
    mode = mode if mode in {"onefile", "standalone"} else "onefile"

    cmd = [
        "uv", "run", "python", "-m", "nuitka",
        f"--mode={mode}",
        "--assume-yes-for-downloads",
        "--show-progress",
        "--remove-output",
        "--deployment",
        "--report=dist/nuitka-compilation-report.xml",
        "--output-dir=dist",
        f"--output-filename={name}",

        # 动态导入和包数据：与 PyInstaller 配置保持同一运行能力。
        "--enable-plugins=pywebview",
        "--include-package=pygments",
        "--include-package=send2trash",
        "--include-package=steamworks",
        "--include-package=tiktoken",
        "--include-package=tiktoken_ext",
        "--include-module=tiktoken_ext.openai_public",
        "--include-package=litellm.litellm_core_utils.llm_response_utils",
        "--include-package-data=tiktoken",
        "--include-package-data=litellm",
        "--noinclude-data-files=litellm/proxy/_experimental/**",
        "--noinclude-data-files=litellm/proxy/swagger/**",

        # anti-bloat 插件官方参数，用于避免部署包跟进无用的大型开发依赖。
        "--noinclude-setuptools-mode=nofollow",
        "--noinclude-pytest-mode=nofollow",
        "--noinclude-unittest-mode=nofollow",
    ]

    if sys.platform == "win32":
        # Nuitka 官方建议优先使用 Visual Studio 2022+；需要 MinGW 时可改回 --mingw64。
        cmd.extend([
            "--windows-console-mode=disable",
            "--msvc=latest",

            # Windows 版本信息。
            f"--company-name={company}",
            f"--product-name={name}",
            f"--file-version={normalized_version}",
            f"--product-version={normalized_version}",
            f"--file-description={name} 模组管理器",
            f"--copyright=Copyright (C) {company}",
        ])
        upx_binary = _find_upx_binary(upx_dir)
        if upx_binary:
            cmd.extend(["--enable-plugins=upx", f"--upx-binary={upx_binary}"])
        else:
            print("提示: 未找到 UPX，Nuitka 将不压缩二进制文件。")

    frontend_dist = project_root / "frontend" / "dist"
    _add_existing_data_dir(cmd, frontend_dist, "frontend/dist")
    if mode == "onefile" and frontend_dist.exists():
        cmd.append("--include-data-files-external=frontend/dist/**")

    if sys.platform == "win32":
        if mode == "onefile" and splash_path and Path(splash_path).exists():
            cmd.append(f"--onefile-windows-splash-screen-image={Path(splash_path).as_posix()}")
        if icon_path and Path(icon_path).exists():
            cmd.append(f"--windows-icon-from-ico={Path(icon_path).as_posix()}")
        elif icon_path:
            print(f"警告: 图标文件不存在，已跳过 {icon_path}")

    cmd.append(f"--main={main_file}")
    return cmd


def packApplication(
    main_file: str = "main.py",
    icon_path: str = "",
    name: str = "",
    splash_path: str = "",
    version: str = "1.0.0",
    company: str = "",
    mode: str = "onefile",
    upx_dir: str = "",
) -> bool:
    """
    使用 Nuitka 打包应用程序。
    """
    try:
        if not os.path.exists(main_file):
            raise FileNotFoundError(f"主程序文件 '{main_file}' 不存在")

        cmd = _build_nuitka_args(main_file, icon_path, name, splash_path, version, company, mode, upx_dir=upx_dir)
        env = os.environ.copy()
        _append_pythonpath(env, _resolve_steamworkspy_source_dir(Path(__file__).resolve().parent))

        print(f"执行命令: {' '.join(cmd)}")
        build_log_path = Path("dist") / "nuitka-build.log"
        returncode = _run_command_with_log(cmd, build_log_path, env=env)
        if returncode == 0:
            print("\n" + "=" * 30)
            print("★ 打包成功！")
            print(f"★ 输出目录: {Path('dist').resolve()}")
            print(f"★ 构建日志: {build_log_path.resolve()}")
            print("=" * 30 + "\n")
            return True

        print("打包失败！")
        print(f"Nuitka 退出码: {returncode}")
        print(f"构建日志: {build_log_path.resolve()}")
        report_path = Path("dist") / "nuitka-compilation-report.xml"
        if report_path.exists():
            print(f"编译报告: {report_path.resolve()}")
        return False
    except Exception as e:
        print(f"打包过程中出错: {str(e)}")
        return False


def _iter_toolmods_files(toolmods_dir: Path):
    """遍历 ToolMods 发布文件，排除任意层级下以 Source 开头的目录内容。"""
    if not toolmods_dir.exists():
        return
    archive_root = Path("toolmods") / toolmods_dir.name
    for current_root, dirnames, filenames in os.walk(toolmods_dir, followlinks=True):
        current_path = Path(current_root)
        relative_dir = current_path.relative_to(toolmods_dir)
        dirnames[:] = [name for name in dirnames if not name.startswith("Source")]
        if any(part.startswith("Source") for part in relative_dir.parts):
            continue
        for filename in filenames:
            file_path = current_path / filename
            yield file_path, archive_root / file_path.relative_to(toolmods_dir)


def _should_include_steamcmd_file(relative_path: Path) -> bool:
    if sys.platform == "win32":
        return relative_path.name.lower() == "steamcmd.exe"
    return relative_path.name == "steamcmd.sh"


def _iter_tools_files(tools_dir: Path):
    """遍历 tools 发布文件，只保留发布包运行需要的工具资源。"""
    if not tools_dir.exists():
        return
    allowed_tool_dirs = {"ripgrep", "steamcmd", "steamworks", "texture_tools"}
    for file_path in tools_dir.rglob("*"):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(tools_dir)
        normalized_parts = [part.lower() for part in relative_path.parts]
        if normalized_parts and normalized_parts[0] not in allowed_tool_dirs:
            continue
        if normalized_parts and normalized_parts[0] == "steamcmd" and not _should_include_steamcmd_file(relative_path):
            continue
        yield file_path, Path("tools") / relative_path


def _iter_data_files(data_dir: Path):
    """遍历 data 发布文件，仅保留发布包运行所需的固定数据文件。"""
    required_files = [
        Path("rules") / "communityRules.json",
        Path("steamDB.json"),
        Path("replacements.json.gz"),
    ]
    for relative_path in required_files:
        file_path = data_dir / relative_path
        if file_path.exists() and file_path.is_file():
            yield file_path, Path("data") / relative_path
        else:
            print(f"警告: 发布数据文件缺失，已跳过 {file_path}")


def _iter_frontend_dist_files(frontend_dist_dir: Path):
    """遍历前端构建产物，供 Nuitka onefile 外置资源使用。"""
    if not frontend_dist_dir.exists():
        print(f"警告: 前端构建目录缺失，已跳过 {frontend_dist_dir}")
        return
    for file_path in frontend_dist_dir.rglob("*"):
        if file_path.is_file():
            yield file_path, Path("frontend") / "dist" / file_path.relative_to(frontend_dist_dir)


def _iter_nuitka_output_files(dist_dir: Path, app_name: str, mode: str):
    """遍历 Nuitka 输出产物，onefile 取 exe，standalone 取完整 .dist 目录。"""
    exe_path = dist_dir / f"{app_name}.exe"
    if mode == "onefile":
        if not exe_path.exists():
            raise FileNotFoundError(f"未找到打包产物: {exe_path}")
        yield exe_path, Path(exe_path.name)
        return

    app_dist_dir = dist_dir / f"{app_name}.dist"
    if not app_dist_dir.exists():
        raise FileNotFoundError(f"未找到打包目录: {app_dist_dir}")
    for file_path in app_dist_dir.rglob("*"):
        if file_path.is_file():
            yield file_path, file_path.relative_to(app_dist_dir)


def create_release_zip(app_name: str, version: str, mode: str = "onefile"):
    """基于 Nuitka 产物生成发布压缩包，并附带运行所需的外部资源。"""
    project_root = Path(__file__).resolve().parent
    dist_dir = project_root / "dist"
    zip_path = dist_dir / _release_zip_name(app_name, version)
    archive_root = Path(app_name)

    release_items = list(_iter_nuitka_output_files(dist_dir, app_name, mode))
    if mode == "onefile":
        release_items.extend(_iter_frontend_dist_files(project_root / "frontend" / "dist") or [])
    release_items.extend(_iter_toolmods_files(project_root / "toolmods" / "RimCrowCompanion") or [])
    release_items.extend(_iter_tools_files(project_root / "tools") or [])
    release_items.extend(_iter_data_files(project_root / "data") or [])

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source_path, archive_path in release_items:
            archive.write(source_path, arcname=(archive_root / archive_path).as_posix())

    print("\n" + "=" * 30)
    print("★ 发布压缩包已生成！")
    print(f"★ 输出文件: {zip_path}")
    print("=" * 30 + "\n")
    return zip_path


def buildFrontend(start_path: str = "frontend"):
    """
    构建前端项目。
    """
    subprocess.run([_npm_command(), "run", "build"], cwd=start_path, check=True, text=True, encoding="utf-8")


def get_gitignore_spec(root_path: str):
    """读取并解析 .gitignore 文件。"""
    if not HAS_PATHSPEC:
        return None

    gitignore_path = os.path.join(root_path, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f)
    return None


def filestree(
    start_path: str = ".",
    exclude_dirs: list[str] = [],
    max_depth: int = -1,
    use_gitignore: bool = True,
) -> str:
    """
    生成目录树结构字符串，支持 .gitignore 过滤。
    """
    if exclude_dirs is None:
        exclude_dirs = []
    output_lines = []
    spec = get_gitignore_spec(start_path) if use_gitignore else None
    root_name = os.path.basename(os.path.abspath(start_path))
    output_lines.append(f"·[{root_name}]")

    def _tree_body(current_path: str, prefix: str = "", depth: int = 0):
        if max_depth != -1 and depth >= max_depth:
            return
        try:
            entries = os.listdir(current_path)
        except PermissionError:
            return

        items = []
        for entry in entries:
            if entry in exclude_dirs:
                continue
            full_path = os.path.join(current_path, entry)
            rel_path = os.path.relpath(full_path, start_path)
            if spec and spec.match_file(rel_path.replace(os.sep, "/")):
                continue
            items.append(entry)

        items.sort(key=lambda item: (not os.path.isdir(os.path.join(current_path, item)), item.lower()))
        count = len(items)
        for index, entry in enumerate(items):
            full_path = os.path.join(current_path, entry)
            is_last = index == count - 1
            is_dir = os.path.isdir(full_path)
            connector = "└── " if is_last else "├── "
            display_name = f"·[{entry}]" if is_dir else f" {entry}"
            output_lines.append(f"{prefix}{connector}{display_name}")
            if is_last:
                output_lines.append(f"{prefix}")
            if is_dir:
                extension = "    " if is_last else "│   "
                _tree_body(full_path, prefix + extension, depth + 1)

    _tree_body(start_path)
    return "\n".join(output_lines)


if __name__ == "__main__":
    from backend._version import __version__

    pack_zip = True
    APP_MAIN = "main.py"
    APP_NAME = "RimCrow"
    APP_VERSION = __version__
    APP_COMPANY = "Inky Feather"
    ICON_PATH = "icon.ico"
    SPLASH_PATH = "splash.png"
    NUITKA_MODE = "onefile"  # 可改为 "standalone" 便于排查 Nuitka 输出目录问题。
    DEFAULT_UPX_DIR = r"D:\Environment\upx-5.0.0-win64"

    os.environ["SETUPTOOLS_USE_DISTUTILS"] = "local"

    buildFrontend(start_path="frontend")

    print(f"=== 开始 Nuitka 打包 {APP_NAME} v{APP_VERSION} ===")
    packed = packApplication(
        main_file=APP_MAIN,
        icon_path=ICON_PATH,
        name=APP_NAME,
        splash_path=SPLASH_PATH,
        version=APP_VERSION,
        company=APP_COMPANY,
        mode=NUITKA_MODE,
        upx_dir=DEFAULT_UPX_DIR,
    )

    if packed and pack_zip:
        print(f"=== 生成发布压缩包 {_release_zip_name(APP_NAME, APP_VERSION)} ===")
        create_release_zip(APP_NAME, APP_VERSION, mode=NUITKA_MODE)

    print("\n=== 生成项目目录树 ===")
    excludes = [
        "__pycache__", ".git", ".venv", ".idea", ".vscode",
        "build", "dist", "node_modules",
        "cache", "temp", "backups", "Downloads", "updates",
    ]
    tree_text = filestree(".", exclude_dirs=excludes, use_gitignore=True, max_depth=5)
    output_file = "files_tree.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(tree_text)

    print(f"目录树已保存至: {output_file}")
