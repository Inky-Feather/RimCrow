import argparse
import copy
import json
import os
import sys
import shutil
import subprocess
import tempfile
import zipfile
from contextlib import suppress
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

# 尝试导入 pathspec 用于 gitignore 匹配
try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False
    print("提示: 未安装 'pathspec' 库，.gitignore 过滤功能将不可用。")


APP_MAIN = "main.py"
APP_NAME = "RimCrow"
APP_COMPANY = "Inky Feather"
ICON_PATH = "icon.ico"
SPLASH_PATH = "splash.png"

DEFAULT_PACK_CONFIG: dict[str, Any] = {
    "steps": {
        "frontend": True,
        "app": True,
        "docs": True,
        "tree": True,
        "zip": True,
    },
    "app": {
        "upx_dir": "",
    },
    "docs": {
        "output_dir": "docs",
        "command": [],
        "command_python_executable": "",
        "required": False,
    },
    "tree": {
        "target_dir": ".",
        "output_file": "files_tree.txt",
        "max_depth": 5,
        "exclude_dirs": ["__init__.py", "tests", "Downloads", "submodules"],
        "use_gitignore": True,
    },
    "zip": {
        "include_docs": True,
    },
}

STEP_NAMES = tuple(DEFAULT_PACK_CONFIG["steps"].keys())


def load_pack_config(config_path: Path) -> dict[str, Any]:
    """读取本地打包配置；配置文件不存在时使用脚本默认值。"""
    config = copy.deepcopy(DEFAULT_PACK_CONFIG)
    if not config_path.is_file():
        print(f"提示: 未找到本地打包配置，使用默认参数: {config_path}")
        return config

    try:
        with config_path.open("r", encoding="utf-8") as file:
            user_config = json.load(file)
    except Exception as exc:
        print(f"警告: 读取本地打包配置失败，使用默认参数: {exc}")
        return config

    if not isinstance(user_config, dict):
        print(f"警告: 本地打包配置不是 JSON 对象，使用默认参数: {config_path}")
        return config

    print(f"已读取本地打包配置: {config_path}")
    for key, value in user_config.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    return config


def _apply_pack_cli_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    config = copy.deepcopy(config)
    steps = dict(config.get("steps", {}))

    skipped_steps = [item.strip().lower() for item in args.skip.split(",") if item.strip()]
    if skipped_steps:
        unknown = [name for name in skipped_steps if name not in STEP_NAMES]
        if unknown:
            raise ValueError(f"未知步骤: {', '.join(unknown)}，可用步骤: {', '.join(STEP_NAMES)}")
        for name in skipped_steps:
            steps[name] = False

    if args.upx_dir is not None:
        config.setdefault("app", {})["upx_dir"] = args.upx_dir
    config["steps"] = steps
    return config


def _append_pythonpath(env: dict[str, str], *paths: Path) -> None:
    existing_paths = [item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item]
    extra_paths = [str(path.resolve()) for path in paths if path.exists()]
    env["PYTHONPATH"] = os.pathsep.join([*extra_paths, *existing_paths])


def _prepare_pyinstaller_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    # uv 自带的 CPython 3.11.15 上，setuptools 69.x 的本地 distutils 接管会触发断言；
    # 打包阶段强制退回 stdlib distutils，避免 PyInstaller 启动前就崩溃。
    env["SETUPTOOLS_USE_DISTUTILS"] = "stdlib"
    return env


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


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with suppress(ValueError, OSError):
                reconfigure(encoding="utf-8")


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


def _is_windows() -> bool:
    return sys.platform.startswith(("win32", "cygwin", "msys"))


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _pyinstaller_add_data_arg(source: str, target: str) -> str:
    return f"{source}{os.pathsep}{target}"


def _pyinstaller_output_candidates(dist_dir: Path, app_name: str) -> list[Path]:
    candidates = []
    if _is_macos():
        candidates.extend([
            dist_dir / f"{app_name}.app",
            dist_dir / app_name / f"{app_name}.app",
            dist_dir / app_name,
        ])
    elif _is_windows():
        candidates.extend([
            dist_dir / f"{app_name}.exe",
            dist_dir / app_name / f"{app_name}.exe",
        ])
    else:
        candidates.extend([
            dist_dir / app_name,
            dist_dir / app_name / app_name,
        ])
    return candidates


def _resolve_pyinstaller_output(dist_dir: Path, app_name: str) -> Path:
    for candidate in _pyinstaller_output_candidates(dist_dir, app_name):
        if candidate.exists():
            return candidate
    searched = "\n - ".join(str(path) for path in _pyinstaller_output_candidates(dist_dir, app_name))
    raise FileNotFoundError(f"未找到打包产物，已检查:\n - {searched}")


def _iter_release_output_files(output_path: Path):
    if output_path.is_file():
        yield output_path, Path(output_path.name)
        return

    if output_path.is_dir():
        root_parent = output_path.parent
        for file_path in output_path.rglob("*"):
            if file_path.is_file():
                yield file_path, file_path.relative_to(root_parent)
        return

    raise FileNotFoundError(f"未找到打包产物: {output_path}")


def _steamworks_runtime_files(project_root: Path) -> list[Path]:
    names_by_platform = {
        "win32": ["SteamworksPy64.dll", "steam_api64.dll"],
        "darwin": ["SteamworksPy.dylib", "libsteam_api.dylib"],
        "linux": ["SteamworksPy.so", "libsteam_api.so"],
    }
    platform_key = "win32" if sys.platform.startswith(("win32", "cygwin", "msys")) else "darwin" if sys.platform == "darwin" else "linux"
    runtime_dir = project_root / "tools" / "steamworks"
    files = [runtime_dir / name for name in names_by_platform[platform_key]]
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少当前平台 Steamworks 运行库: " + ", ".join(str(path) for path in missing))
    return files


def create_pyinstaller_hook_dir():
    """
    生成临时 PyInstaller hook 目录。

    对 litellm 保留必需数据文件，但排除桌面端未使用的 proxy 静态资源，
    例如 proxy/_experimental 和 proxy/swagger。
    """
    hook_dir = tempfile.mkdtemp(prefix="pyi_hooks_")
    hook_path = os.path.join(hook_dir, "hook-litellm.py")
    hook_content = """from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files(
    "litellm",
    excludes=[
        "proxy/_experimental",
        "proxy/_experimental/*",
        "proxy/_experimental/**",
        "proxy/swagger",
        "proxy/swagger/*",
        "proxy/swagger/**",
    ],
)
"""
    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(hook_content)
    return hook_dir


def resolve_upx_dir(raw_dir: str = "") -> str:
    """解析 UPX 目录；未显式配置时不启用 UPX，避免换机器打包直接失败。"""
    raw_path = str(raw_dir or os.environ.get("UPX_DIR", "")).strip()
    if not raw_path:
        print("提示: 未配置 UPX 目录，已跳过压缩参数。")
        return ""
    upx_path = Path(raw_path)
    if upx_path.is_file():
        upx_path = upx_path.parent
    if upx_path.exists():
        return str(upx_path)
    print(f"提示: 未找到 UPX 目录，已跳过压缩参数: {upx_path}")
    return ""


def create_version_file(version="1.0.0.0", company_name="", file_description="", internal_name="", legal_copyright="", product_name=""):
    """
    生成 PyInstaller 所需的版本信息文件
    """
    # 将版本号字符串 "1.0.0" 转换为元组 (1, 0, 0, 0)
    try:
        v = str(version).split(".")
        while len(v) < 4:
            v.append("0")
        v_tuple = tuple(map(int, v[:4]))
    except (TypeError, ValueError):
        v_tuple = (1, 0, 0, 0)
        
    version_str = str(v_tuple)

    content = f"""
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_str},
    prodvers={version_str},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'080404b0',
        [StringStruct(u'CompanyName', u'{company_name}'),
        StringStruct(u'FileDescription', u'{file_description}'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'{internal_name}'),
        StringStruct(u'LegalCopyright', u'{legal_copyright}'),
        StringStruct(u'OriginalFilename', u'{internal_name}.exe'),
        StringStruct(u'ProductName', u'{product_name}'),
        StringStruct(u'ProductVersion', u'{version}')])
      ]), 
    VarFileInfo([VarStruct(u'Translation', [2052, 1200])])
  ]
)
"""
    try:
        # 创建临时文件
        fd, path = tempfile.mkstemp(suffix=".txt", text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path
    except Exception as e:
        print(f"生成版本文件失败: {e}")
        return None

def packApplication(main_file="main.py", icon_path="", name="", splash_path="", version="1.0.0", company="", upx_dir=""):
    """
    使用 PyInstaller 打包应用程序
    Args:
        main_file (str): 主程序文件路径
        icon_path (str): 图标文件路径
        name (str): 程序名称
    """
    version_file_path = None
    hook_dir_path = None
    try:
        project_root = Path(__file__).resolve().parent
        steamworkspy_source_dir = _resolve_steamworkspy_source_dir(project_root)
        if not os.path.exists(main_file): raise FileNotFoundError(f"主程序文件 '{main_file}' 不存在")
        
        print("正在生成版本信息...")
        # Windows 才需要版本资源；macOS/Linux 传入该参数没有收益，反而容易造成打包失败。
        if _is_windows():
            version_file_path = create_version_file(
                version=version,
                company_name=company,
                file_description=f"{name} 模组管理器",
                internal_name=name,
                legal_copyright=f"Copyright (C) {company}",
                product_name=name
            )
        hook_dir_path = create_pyinstaller_hook_dir()
        upx_dir_path = resolve_upx_dir(upx_dir) if _is_windows() else ""
        steamworks_data_args = []
        for runtime_file in _steamworks_runtime_files(project_root):
            steamworks_data_args.extend(["--add-data", _pyinstaller_add_data_arg(str(runtime_file), "tools/steamworks")])
        # 2. 构建命令
        # 这些模块在源码运行时可以被 Python 正常动态发现，
        # 但在 PyInstaller 单文件模式下，命名空间插件和动态加载模块经常会漏收。
        # 这里显式补齐 tiktoken / tiktoken_ext，避免打包后出现：
        # Unknown encoding cl100k_base / Plugins found: []
        pyinstaller_args = [
            "uv", "run", "pyinstaller", # 使用uv运行pyinstaller
            "-w",  # 无控制台窗口
            "--noconfirm",  # 跳过确认提示
            "--paths", str(steamworkspy_source_dir),
            "--additional-hooks-dir", hook_dir_path,
            "--add-data", _pyinstaller_add_data_arg("frontend/dist", "frontend/dist"),
            *steamworks_data_args,
            "--collect-binaries", "tiktoken",
            "--collect-data", "tiktoken",
            "--collect-submodules", "steamworks",
            "--collect-submodules", "tiktoken",
            "--collect-submodules", "tiktoken_ext",
            "--hidden-import", "tiktoken_ext",
            "--hidden-import", "tiktoken_ext.openai_public",
            
            # 排除一些可能导致问题的模块
            "--exclude-module", "setuptools",  # 排除这个模块， 避免打包时出现问题
            # "--exclude-module", "_distutils_hack.override",
            "--exclude-module", "pkg_resources", # 通常这两个是一起出现的，建议一并排除
            
            "--clean",  # 清理旧构建文件
            "-n", name,  # 指定名称
            main_file  # 主程序文件
        ]
        if _is_macos():
            pyinstaller_args.insert(3, "-D")
        else:
            pyinstaller_args.insert(3, "-F")
        cmd = pyinstaller_args
        if upx_dir_path and _is_windows():
            cmd.extend(["--upx-dir", upx_dir_path])
        if icon_path and os.path.exists(icon_path):
            if not _is_macos() or Path(icon_path).suffix.lower() == ".icns":
                cmd.extend(["-i", icon_path])
            else:
                print(f"提示: macOS 打包已跳过非 .icns 图标: {icon_path}")
        if splash_path and os.path.exists(splash_path) and _is_windows():
            cmd.extend(["--splash", splash_path])
        if version_file_path:
            cmd.extend(["--version-file", version_file_path])
        if _is_macos():
            cmd.extend(["--osx-bundle-identifier", "com.inkyfeather.rimcrow"])
        
        env = _prepare_pyinstaller_env()
        _append_pythonpath(env, steamworkspy_source_dir)

        print(f"执行命令: {' '.join(cmd)}")
        # 3. 执行打包
        build_log_path = Path("dist") / "pyinstaller-build.log"
        returncode = _run_command_with_log(cmd, build_log_path, env=env)
        if returncode == 0:
            output_path = _resolve_pyinstaller_output(Path("dist"), name)
            print("\n" + "="*30)
            print("★ 打包成功！")
            print(f"★ 输出产物: {output_path}")
            print(f"★ 构建日志: {build_log_path.resolve()}")
            print("="*30 + "\n")
            return True
        else:
            print("打包失败！")
            print(f"PyInstaller 退出码: {returncode}")
            print(f"构建日志: {build_log_path.resolve()}")
            return False
    except Exception as e:
        print(f"打包过程中出错: {str(e)}")
        return False
    finally:
        # 清理临时版本文件
        if version_file_path and os.path.exists(version_file_path):
            with suppress(OSError):
                os.remove(version_file_path)
        if hook_dir_path and os.path.exists(hook_dir_path):
            with suppress(OSError):
                shutil.rmtree(hook_dir_path)


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
    allowed_tool_dirs = {"ripgrep", "steamcmd", "texture_tools"}
    for file_path in tools_dir.rglob("*"):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(tools_dir)
        normalized_parts = [part.lower() for part in relative_path.parts]
        if normalized_parts and normalized_parts[0] not in allowed_tool_dirs:
            continue
        if normalized_parts and normalized_parts[0] == "ripgrep" and relative_path.name.lower() not in {"rg.exe", "rg"}:
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
        Path("multiplayerCompatibility.json"),
        Path("mpCompatPackageIds.json"),
        Path("git_catalogs") / "rjw.json",
        Path("git_catalogs") / "mlie.json",
    ]
    for relative_path in required_files:
        file_path = data_dir / relative_path
        if file_path.exists() and file_path.is_file():
            yield file_path, Path("data") / relative_path
        else:
            print(f"警告: 发布数据文件缺失，已跳过 {file_path}")


def _count_release_pdfs(output_dir: Path) -> int:
    return sum(1 for path in output_dir.rglob("*.pdf") if path.is_file()) if output_dir.exists() else 0


def _resolve_docs_command(docs_config: dict[str, Any]) -> list[str]:
    """执行 Python 脚本时优先使用配置解释器，未配置则沿用当前解释器。"""
    raw_command = docs_config.get("command", [])
    if not raw_command:
        return []
    if not isinstance(raw_command, list):
        print("警告: docs.command 应为命令数组，已跳过发布文档生成。")
        return []
    command = [str(item) for item in raw_command if str(item).strip()]
    if command and Path(command[0]).suffix.lower() == ".py":
        command_python = str(docs_config.get("command_python_executable", "")).strip() or sys.executable
        command.insert(0, command_python)
    return command


def build_release_docs(
    project_root: Path,
    output_dir: Path,
    docs_config: dict[str, Any] | None = None,
) -> None:
    """按本地配置执行发布文档命令。"""
    docs_config = docs_config or {}
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    command = _resolve_docs_command(docs_config)
    if not command:
        print(f"提示: 未配置发布文档命令，发布文档目录现有 PDF: {_count_release_pdfs(output_dir)} 个。")
        return

    print(f"执行发布文档命令: {' '.join(command)}")
    process = subprocess.run(
        command,
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout:
        print(process.stdout, end="" if process.stdout.endswith("\n") else "\n")
    if process.returncode != 0:
        message = f"发布文档命令失败，退出码: {process.returncode}"
        if bool(docs_config.get("required", False)):
            raise subprocess.CalledProcessError(process.returncode, command, output=process.stdout)
        print(f"警告: {message}，已继续后续流程。")

    print(f"PDF 文档处理完成，共 {_count_release_pdfs(output_dir)} 个文件。")


def _iter_release_docs_files(docs_dir: Path):
    """遍历发布 PDF 文档。"""
    if not docs_dir.exists():
        return
    for file_path in docs_dir.rglob("*.pdf"):
        if file_path.is_file():
            yield file_path, file_path.relative_to(docs_dir)


def create_release_zip(app_name: str, version: str, docs_dir: Path | None = None, include_docs: bool = True):
    """基于 dist 中的平台产物生成发布压缩包，并附带运行所需的外部资源。"""
    project_root = Path(__file__).resolve().parent
    dist_dir = project_root / "dist"
    output_path = _resolve_pyinstaller_output(dist_dir, app_name)
    zip_path = dist_dir / _release_zip_name(app_name, version)
    archive_root = Path(app_name)

    release_items = list(_iter_release_output_files(output_path))
    release_items.extend(_iter_toolmods_files(project_root / "toolmods" / "RimCrowCompanion") or [])
    release_items.extend(_iter_tools_files(project_root / "tools") or [])
    release_items.extend(_iter_data_files(project_root / "data") or [])
    if include_docs:
        resolved_docs_dir = docs_dir or (project_root / "docs")
        if not resolved_docs_dir.is_absolute():
            resolved_docs_dir = project_root / resolved_docs_dir
        release_items.extend(_iter_release_docs_files(resolved_docs_dir) or [])

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source_path, archive_path in release_items:
            archive.write(source_path, arcname=(archive_root / archive_path).as_posix())

    print("\n" + "="*30)
    print("★ 发布压缩包已生成！")
    print(f"★ 输出文件: {zip_path}")
    print("="*30 + "\n")
    return zip_path

def buildFrontend(start_path: str = 'frontend'):
    """
    构建前端项目
    """
    subprocess.run([_npm_command(), "run", "build"], cwd=start_path, check=True, text=True, encoding='utf-8')


# --- 优化后的目录树生成 ---

def get_gitignore_spec(root_path: str):
    """读取并解析 .gitignore 文件"""
    if not HAS_PATHSPEC:
        return None
    
    gitignore_path = os.path.join(root_path, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            return pathspec.PathSpec.from_lines('gitwildmatch', f)
    return None


def filestree(start_path: str = '.', exclude_dirs: list[str] | None = None, max_depth: int = -1, use_gitignore: bool = True) -> str:
    """
    生成目录树结构字符串（重构版：递归逻辑更清晰，支持 .gitignore）
    
    Args:
        start_path: 起始路径
        exclude_dirs: 要强制排除的目录名列表 (如 ['.git', '__pycache__'])
        max_depth: 最大深度，-1 表示无限
        use_gitignore: 是否读取 .gitignore 进行过滤
    """
    if exclude_dirs is None:
        exclude_dirs = []
    exclude_patterns = [pattern.replace(os.sep, '/') for pattern in exclude_dirs]
    output_lines = []
    # 准备 gitignore spec
    spec = get_gitignore_spec(start_path) if use_gitignore else None
    # 获取根目录名
    root_name = os.path.basename(os.path.abspath(start_path))
    output_lines.append(f"·[{root_name}]")
    def _tree_body(current_path: str, prefix: str = "", depth: int = 0):
        if max_depth != -1 and depth >= max_depth:
            return
        # 获取当前目录下的所有项目
        try:
            entries = os.listdir(current_path)
        except PermissionError:
            return

        # 过滤和排序
        # 1. 基础过滤
        items = []
        for entry in entries:
            # 排除特定目录名
            if entry in exclude_dirs:
                continue
            full_path = os.path.join(current_path, entry)
            rel_path = os.path.relpath(full_path, start_path)
            rel_match_path = rel_path.replace(os.sep, '/')
            is_dir = os.path.isdir(full_path)
            # 2. .gitignore 过滤
            # pathspec 的目录规则（如 .*/）需要尾部斜杠才能命中。
            if spec and (spec.match_file(rel_match_path) or (is_dir and spec.match_file(f"{rel_match_path}/"))):
                continue
            if exclude_patterns and any(fnmatch(rel_match_path, pattern) or (is_dir and fnmatch(f"{rel_match_path}/", pattern)) for pattern in exclude_patterns):
                continue
            items.append(entry)

        # 3. 排序：文件夹在前，然后按字母顺序
        items.sort(key=lambda x: (not os.path.isdir(os.path.join(current_path, x)), x.lower()))
        count = len(items)
        for index, entry in enumerate(items):
            full_path = os.path.join(current_path, entry)
            is_last = (index == count - 1)
            is_dir = os.path.isdir(full_path)
            # 构建连接符
            connector = "└── " if is_last else "├── "
            # 构建显示名称
            display_name = f"·[{entry}]" if is_dir else f" {entry}"
            output_lines.append(f"{prefix}{connector}{display_name}")
            if is_last:
                output_lines.append(f"{prefix}")
            if is_dir:
                # 递归下一级
                # 如果当前是最后一个，子级的前缀是空格；否则是竖线
                extension = "    " if is_last else "│   "
                _tree_body(full_path, prefix + extension, depth + 1)

    # 开始递归
    _tree_body(start_path)
    return "\n".join(output_lines)


def build_file_tree(project_root: Path, tree_config: dict[str, Any]) -> Path:
    """按配置生成项目目录树文本。"""
    target_dir = Path(str(tree_config.get("target_dir", ".")))
    if not target_dir.is_absolute():
        target_dir = project_root / target_dir
    output_file = Path(str(tree_config.get("output_file", "files_tree.txt")))
    if not output_file.is_absolute():
        output_file = project_root / output_file
    exclude_dirs = list(tree_config.get("exclude_dirs", []))
    max_depth = int(tree_config.get("max_depth", 5))
    use_gitignore = bool(tree_config.get("use_gitignore", True))

    tree_text = filestree(str(target_dir), exclude_dirs=exclude_dirs, use_gitignore=use_gitignore, max_depth=max_depth)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(tree_text, encoding="utf-8")
    print(f"目录树已保存至: {output_file}")
    return output_file


def _parse_pack_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RimCrow 发布打包脚本")
    parser.add_argument("--config", default="pack.local.json", help="本地打包配置文件路径，默认 pack.local.json")
    parser.add_argument("--skip", default="", help=f"跳过指定步骤，逗号分隔。可选: {', '.join(STEP_NAMES)}")
    parser.add_argument("--upx-dir", default=None, help="临时覆盖 UPX 目录，空字符串表示不启用")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    from backend._version import __version__

    _configure_utf8_stdio()
    project_root = Path(__file__).resolve().parent
    args = _parse_pack_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path

    try:
        config = _apply_pack_cli_overrides(load_pack_config(config_path), args)
    except ValueError as exc:
        print(f"配置错误: {exc}")
        return 2

    os.environ["SETUPTOOLS_USE_DISTUTILS"] = "local"
    steps = config.get("steps", {})
    app_config = config.get("app", {})
    docs_config = config.get("docs", {})
    tree_config = config.get("tree", {})
    zip_config = config.get("zip", {})

    app_version = __version__
    upx_dir = str(app_config.get("upx_dir", ""))

    if steps.get("frontend", True):
        print("=== 构建前端项目 ===")
        buildFrontend(start_path="frontend")
    else:
        print("提示: 已跳过前端构建。")

    if steps.get("app", True):
        print(f"=== 开始打包 {APP_NAME} v{app_version} ===")
        if not packApplication(
            main_file=APP_MAIN,
            icon_path=ICON_PATH,
            name=APP_NAME,
            splash_path=SPLASH_PATH,
            version=app_version,
            company=APP_COMPANY,
            upx_dir=upx_dir,
        ):
            return 1
    else:
        print("提示: 已跳过程序打包，将复用已有 dist 产物。")

    docs_output_dir = Path(str(docs_config.get("output_dir", "docs")))
    if steps.get("docs", True):
        print("=== 生成/检查发布文档 PDF ===")
        build_release_docs(
            project_root=project_root,
            output_dir=docs_output_dir,
            docs_config=docs_config,
        )
    else:
        print("提示: 已跳过 PDF 文档生成。")

    if steps.get("tree", True):
        print("\n=== 生成项目目录树 ===")
        build_file_tree(project_root, tree_config)
    else:
        print("提示: 已跳过目录树生成。")

    if steps.get("zip", True):
        print(f"=== 生成发布压缩包 {_release_zip_name(APP_NAME, app_version)} ===")
        create_release_zip(
            APP_NAME,
            app_version,
            docs_dir=docs_output_dir,
            include_docs=bool(zip_config.get("include_docs", True)),
        )
    else:
        print("提示: 已跳过发布压缩包生成。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
