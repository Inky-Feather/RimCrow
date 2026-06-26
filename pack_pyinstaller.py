import os
import sys
import shutil
import subprocess
import tempfile
import zipfile
from contextlib import suppress
from pathlib import Path
from typing import List

# 尝试导入 pathspec 用于 gitignore 匹配
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


def _pyinstaller_add_data_arg(source: str, target: str) -> str:
    return f"{source}{os.pathsep}{target}"


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

def resolve_upx_dir(default_dir: str = "") -> str:
    """解析 UPX 目录，不存在时跳过压缩参数，避免换机器打包直接失败。"""
    raw_path = os.environ.get("UPX_DIR") or default_dir
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
        
        # 1. 生成版本信息文件
        print("正在生成版本信息...")
        version_file_path = create_version_file(
            version=version,
            company_name=company,
            file_description=f"{name} 模组管理器",
            internal_name=name,
            legal_copyright=f"Copyright (C) {company}",
            product_name=name
        )
        hook_dir_path = create_pyinstaller_hook_dir()
        upx_dir_path = resolve_upx_dir(upx_dir)

        # 2. 构建命令
        # 这些模块在源码运行时可以被 Python 正常动态发现，
        # 但在 PyInstaller 单文件模式下，命名空间插件和动态加载模块经常会漏收。
        # 这里显式补齐 tiktoken / tiktoken_ext，避免打包后出现：
        # Unknown encoding cl100k_base / Plugins found: []
        pyinstaller_args = [
            "uv", "run", "pyinstaller", # 使用uv运行pyinstaller
            "-F",  # 打包成单个文件
            # "-D",  # 打包成目录
            "-w",  # 无控制台窗口
            "--noconfirm",  # 跳过确认提示
            "--paths", str(steamworkspy_source_dir),
            "--additional-hooks-dir", hook_dir_path,
            "--add-data", _pyinstaller_add_data_arg("frontend/dist", "frontend/dist"),
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
        cmd = pyinstaller_args
        if upx_dir_path:
            cmd.extend(["--upx-dir", upx_dir_path])
        if icon_path and os.path.exists(icon_path):
            cmd.extend(["-i", icon_path])
        if splash_path and os.path.exists(splash_path):
            cmd.extend(["--splash", splash_path])
        if version_file_path:
            cmd.extend(["--version-file", version_file_path])
        
        env = os.environ.copy()
        _append_pythonpath(env, steamworkspy_source_dir)

        print(f"执行命令: {' '.join(cmd)}")
        # 3. 执行打包
        build_log_path = Path("dist") / "pyinstaller-build.log"
        returncode = _run_command_with_log(cmd, build_log_path, env=env)
        if returncode == 0:
            print("\n" + "="*30)
            print("★ 打包成功！")
            print(f"★ 输出文件: dist/{name}.exe")
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
            with suppress(OSError): os.remove(version_file_path)
        if hook_dir_path and os.path.exists(hook_dir_path):
            with suppress(OSError): shutil.rmtree(hook_dir_path)

def _iter_toolmods_files(toolmods_dir: Path):
    """遍历 ToolMods 发布文件，排除任意层级下以 Source 开头的目录内容。"""
    if not toolmods_dir.exists():
        return
    for current_root, dirnames, filenames in os.walk(toolmods_dir, followlinks=True):
        current_path = Path(current_root)
        relative_dir = current_path.relative_to(toolmods_dir)
        dirnames[:] = [name for name in dirnames if not name.startswith("Source")]
        if any(part.startswith("Source") for part in relative_dir.parts):
            continue
        for filename in filenames:
            file_path = current_path / filename
            yield file_path, Path("toolmods") / file_path.relative_to(toolmods_dir)

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

def create_release_zip(app_name: str, version: str):
    """基于 dist 中的 exe 生成发布压缩包，并附带运行所需的外部资源。"""
    project_root = Path(__file__).resolve().parent
    dist_dir = project_root / "dist"
    exe_path = dist_dir / f"{app_name}.exe"
    zip_path = dist_dir / _release_zip_name(app_name, version)
    archive_root = Path(app_name)

    if not exe_path.exists():
        raise FileNotFoundError(f"未找到打包产物: {exe_path}")

    release_items = [(exe_path, Path(exe_path.name))]
    release_items.extend(_iter_toolmods_files(project_root / "toolmods") or [])
    release_items.extend(_iter_tools_files(project_root / "tools") or [])
    release_items.extend(_iter_data_files(project_root / "data") or [])

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
    if not HAS_PATHSPEC: return None
    
    gitignore_path = os.path.join(root_path, '.gitignore')
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            return pathspec.PathSpec.from_lines('gitwildmatch', f)
    return None

def filestree( start_path: str = '.', exclude_dirs: List[str] | None = None, max_depth: int = -1, use_gitignore: bool = True ) -> str:
    """
    生成目录树结构字符串（重构版：递归逻辑更清晰，支持 .gitignore）
    
    Args:
        start_path: 起始路径
        exclude_dirs: 要强制排除的目录名列表 (如 ['.git', '__pycache__'])
        max_depth: 最大深度，-1 表示无限
        use_gitignore: 是否读取 .gitignore 进行过滤
    """
    if exclude_dirs is None: exclude_dirs = []
    output_lines = []
    # 准备 gitignore spec
    spec = get_gitignore_spec(start_path) if use_gitignore else None
    # 获取根目录名
    root_name = os.path.basename(os.path.abspath(start_path))
    output_lines.append(f"·[{root_name}]")
    def _tree_body(current_path: str, prefix: str = "", depth: int = 0):
        if max_depth != -1 and depth >= max_depth: return
        # 获取当前目录下的所有项目
        try: entries = os.listdir(current_path)
        except PermissionError: return

        # 过滤和排序
        # 1. 基础过滤
        items = []
        for entry in entries:
            # 排除特定目录名
            if entry in exclude_dirs: continue
            full_path = os.path.join(current_path, entry)
            rel_path = os.path.relpath(full_path, start_path)
            # 2. .gitignore 过滤
            # 注意：pathspec 需要 unix 风格的路径分隔符
            if spec and spec.match_file(rel_path.replace(os.sep, '/')): continue
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
            if is_last: output_lines.append(f"{prefix}")
            if is_dir:
                # 递归下一级
                # 如果当前是最后一个，子级的前缀是空格；否则是竖线
                extension = "    " if is_last else "│   "
                _tree_body(full_path, prefix + extension, depth + 1)

    # 开始递归
    _tree_body(start_path)
    return "\n".join(output_lines)

if __name__ == "__main__":
    from backend._version import __version__
    # pack_zip = False
    pack_zip = True
    # 配置
    APP_MAIN = 'main.py'
    APP_NAME = 'RimModManager'
    APP_VERSION = __version__  # 在这里修改版本号
    APP_COMPANY = 'Inky Feather'
    ICON_PATH = 'icon.ico'
    SPLASH_PATH = 'splash.png'
    DEFAULT_UPX_DIR = r'D:\Environment\upx-5.0.0-win64'
    os.environ["SETUPTOOLS_USE_DISTUTILS"] = "local"
    
    # 0. 构建前端项目
    buildFrontend(start_path='frontend')
    
    # 1. 执行打包
    print(f'=== 开始打包 {APP_NAME} v{APP_VERSION} ===')
    packed = packApplication(
        main_file=APP_MAIN,
        icon_path=ICON_PATH,
        name=APP_NAME,
        splash_path=SPLASH_PATH,
        version=APP_VERSION,
        company=APP_COMPANY,
        upx_dir=DEFAULT_UPX_DIR,
    )
    
    if packed and pack_zip:
        print(f'=== 生成发布压缩包 {_release_zip_name(APP_NAME, APP_VERSION)} ===')
        create_release_zip(APP_NAME, APP_VERSION)
    
    # 2. 生成目录树
    print('\n=== 生成项目目录树 ===')
    target_dir = r'.'
    
    # 强制排除的系统/构建目录
    excludes = [
        '__pycache__', '.git', '.venv', '.idea', '.vscode', 
        'build', 'dist', 'node_modules', 
        'cache', 'temp', 'backups','Downloads','updates'
    ]
    
    tree_text = filestree(
        target_dir, 
        exclude_dirs=excludes, 
        use_gitignore=True, # 开启 gitignore 支持
        max_depth=5         # 限制深度，防止太长
    )
    
    output_file = 'files_tree.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(tree_text)
    
    print(f'目录树已保存至: {output_file}')
    # print(tree_text) # 可选：在控制台打印预览
