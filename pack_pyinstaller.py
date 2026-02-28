import os
import sys
import subprocess
import tempfile
from typing import List

# 尝试导入 pathspec 用于 gitignore 匹配
try:
    import pathspec
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False
    print("提示: 未安装 'pathspec' 库，.gitignore 过滤功能将不可用。")

def create_version_file(version="1.0.0.0", company_name="", file_description="", internal_name="", legal_copyright="", product_name=""):
    """
    生成 PyInstaller 所需的版本信息文件
    """
    # 将版本号字符串 "1.0.0" 转换为元组 (1, 0, 0, 0)
    try:
        v = version.split(".")
        while len(v) < 4:
            v.append("0")
        v_tuple = tuple(map(int, v[:4]))
    except:
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

def packApplication(main_file="main.py", icon_path="", name="", version="1.0.0", company=""):
    """
    使用 PyInstaller 打包应用程序
    Args:
        main_file (str): 主程序文件路径
        icon_path (str): 图标文件路径
        name (str): 程序名称
    """
    version_file_path = None
    try:
        if not os.path.exists(main_file):
            raise FileNotFoundError(f"主程序文件 '{main_file}' 不存在")
        
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

        # 2. 构建命令
        cmd = [
            "uv", "run", "pyinstaller", # 使用uv运行pyinstaller
            "-F",  # 打包成单个文件
            # "-D",  # 打包成目录
            "-w",  # 无控制台窗口
            "--noconfirm",  # 跳过确认提示
            "--contents-directory", "lib",
            "--add-data", "frontend/dist;frontend/dist", # 注意：Windows下通常用分号; Linux用冒号:
            "--collect-binaries", "steamworks",
            "--collect-data", "litellm",
            # 排除一些可能导致问题的模块
            "--exclude-module", "setuptools",  # 排除这个模块， 避免打包时出现问题
            "--exclude-module", "pkg_resources", # 通常这两个是一起出现的，建议一并排除
            
            "--clean",  # 清理旧构建文件
            "--upx-dir", r"D:\Environment\upx-5.0.0-win64",  # 指定 UPX 路径
            "-n", name,  # 指定名称
            main_file  # 主程序文件
        ]

        if icon_path and os.path.exists(icon_path):
            cmd.extend(["-i", icon_path])
        
        if version_file_path:
            cmd.extend(["--version-file", version_file_path])

        print(f"执行命令: {' '.join(cmd)}")
        
        # 3. 执行打包
        result = subprocess.run(cmd, text=True, encoding='utf-8') # 显式指定编码防止乱码
        
        if result.returncode == 0:
            print("\n" + "="*30)
            print("★ 打包成功！")
            print(f"★ 输出文件: dist/{name}.exe")
            print("="*30 + "\n")
        else:
            print("打包失败！")
            print("错误信息：")
            print(result.stderr)
    except Exception as e:
        print(f"打包过程中出错: {str(e)}")
    finally:
        # 清理临时版本文件
        if version_file_path and os.path.exists(version_file_path):
            try:
                os.remove(version_file_path)
            except:
                pass

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

def filestree(
    start_path: str = '.', 
    exclude_dirs: List[str] = [], 
    max_depth: int = -1,
    use_gitignore: bool = True
) -> str:
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
    
    output_lines = []
    
    # 准备 gitignore spec
    spec = get_gitignore_spec(start_path) if use_gitignore else None
    
    # 获取根目录名
    root_name = os.path.basename(os.path.abspath(start_path))
    output_lines.append(f"·[{root_name}]")

    def _tree_body(current_path: str, prefix: str = "", depth: int = 0):
        if max_depth != -1 and depth >= max_depth:
            return

        try:
            # 获取当前目录下的所有项目
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
            
            # 2. .gitignore 过滤
            # 注意：pathspec 需要 unix 风格的路径分隔符
            if spec and spec.match_file(rel_path.replace(os.sep, '/')):
                continue
                
            items.append(entry)

        # 3. 排序：文件夹在前，然后按字母顺序
        items.sort(key=lambda x: (
            not os.path.isdir(os.path.join(current_path, x)), 
            x.lower()
        ))

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
    # 配置
    APP_MAIN = 'main.py'
    APP_NAME = 'RimModManager'
    APP_VERSION = __version__  # 在这里修改版本号
    APP_COMPANY = 'Inky Feather'
    ICON_PATH = 'icon.ico'
    os.environ["SETUPTOOLS_USE_DISTUTILS"] = "local"
    # 1. 执行打包
    print(f'=== 开始打包 {APP_NAME} v{APP_VERSION} ===')
    packApplication(APP_MAIN, ICON_PATH, APP_NAME, version=APP_VERSION, company=APP_COMPANY)
    
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