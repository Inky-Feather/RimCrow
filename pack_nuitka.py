import ast
import os
import re
import subprocess
import sys
from typing import Callable, Optional

def packApplication(main_file="main.py", icon_path="", name=""):
    """
    使用 Nuitka 打包应用程序
    
    Args:
        main_file (str): 主程序文件路径
        icon_path (str): 图标文件路径
        name (str): 程序名称
    """
    try:
        # 确保文件存在
        if not os.path.exists(main_file):
            raise FileNotFoundError(f"主程序文件 '{main_file}' 不存在")
        
        if not os.path.exists(icon_path):
            raise FileNotFoundError(f"图标文件 '{icon_path}' 不存在")
            
        # 构建 Nuitka 命令
        cmd = [
            "uv","run",     # 使用uv运行pyinstaller
            "nuitka",
            "--standalone", # 独立环境
            # "--onefile",    # 打包成单个文件
            "--mingw64",    # 强制 mingw64 编译
            # "--msvc=latest",  # 使用最新的 MSVC 编译
            "--plugin-enable=upx",  # 启用 upx 插件
            r'--upx-binary=D:\Environment\upx-5.0.0-win64',    # 指定 UPX 路径
            "--assume-yes-for-downloads",  # 自动同意下载
            "--windows-console-mode=force",  # 强制控制台模式
            # "--windows-console-mode=disable",  # 禁用控制台模式
            "--show-progress",  # 显示进度
            "--remove-output",  # 删除输出文件
            '--include-data-dir=frontend/dist=frontend/dist',  # 包含资源目录
            # "--nofollow-import-to=icecream",  # 不跟踪导入的模块
            "--include-package=pygments",       # 包含 pygments 模块
            "--include-package=send2trash",       # 包含 send2trash 模块
            f'--windows-icon-from-ico={icon_path}',  # 指定图标
            '--output-dir=dist',  # 指定输出目录
            f'--output-filename={name}',   # 指定名称
            f'--main={main_file}' # 主程序文件
        ]
        
        # F:/programe/Python/RimModManager/.venv/Scripts/python.exe -m nuitka --standalone --show-progress --remove-output --mingw64 --lto=no --assume-yes-for-downloads --jobs=16 --output-dir=F:/programe/Python/RimModManager/output --main=F:/programe/Python/RimModManager/main.py --plugin-enable=pywebview --include-data-dir=F:/programe/Python/RimModManager/frontend/dist=frontend/dist
        
        # 执行打包命令
        result = subprocess.run(cmd, shell=True, text=True, encoding='utf-8')
        
        if result.returncode == 0:
            print("打包成功！")
            print(f"输出目录: {os.path.abspath('dist')}")
        else:
            print("打包失败！")
            print("错误信息：")
            print(result.stderr)
            
    except Exception as e:
        print(f"打包过程中出错: {str(e)}")
        sys.exit(1)

# 目录树结构
def filestree(path='.', exclude:list[str]=[], ignore='', max_depth:int=None, filter_func:Optional[Callable[[str], bool]]=None, # type: ignore
              indent=2,branch_indent:int=None,sub_indent:int=None, # type: ignore
              branch_sign='·[',branch_sign_end=']',leaf_sign=' ',leaf_sign_end=''):
    
    if not path or not os.path.isdir(path): return '路径错误！' # 路径检查
    if not exclude: exclude = []    # 排除项默认空列表
    if not filter_func: filter_func = lambda x: True  # 过滤函数默认正确
    ignore_pattern = re.compile(ignore) if ignore else None # 正则表达式默认
    # 本质为先叠加后替换，先复制父级前缀，再将尾端分支符号替换为无分支的插入符号
    if indent==None: indent=2   # 通用缩进处理
    if indent!=None: branch_indent_=sub_indent_=indent
    if branch_indent!=None: branch_indent_=branch_indent    # 细节缩进优先级更高
    if sub_indent!=None: sub_indent_=sub_indent
    branch_sign = branch_sign or '' # 文件夹标记
    branch_sign_end = branch_sign_end or ''
    leaf_sign = leaf_sign or '' # 文件标记
    leaf_sign_end = leaf_sign_end or ''
    branch_mid = '├' + '─'*branch_indent_
    branch_end = '└' + '─'*branch_indent_
    sub_insert_mid = '│' + ' '*sub_indent_
    sub_insert_end = ' ' + ' '*sub_indent_
    treestr = [branch_sign + os.path.basename(path)+branch_sign_end]  # 结果列表
    # 读取目录内文件，输出按类型排序后的列表 [[地址，前缀符号，深度],……]
    def process_path(path, files, prefix='', depth=0):
        pathlist = []
        for item in files:
            # 过滤设置
            if item in exclude: continue # 排除项过滤
            if not filter_func(item): continue  # 函数过滤
            if ignore_pattern and ignore_pattern.match(item): continue   # 正则过滤
            item_path = os.path.join(path, item)    # 获取文件地址
            pathlist.append([item_path,prefix+branch_mid,depth])    # 添加到结果列表[地址，前缀符号，深度]
        # 按类型排序文件
        pathlist = sorted(pathlist, key=lambda x: (
            not os.path.isdir(x[0]),  # 文件夹在前（False < True）
            os.path.splitext(x[0])[1] if os.path.isfile(x[0]) else '',  # 按扩展名排序
            os.path.basename(x[0])  # 按文件名排序（如果扩展名相同）
        ))
        if pathlist: pathlist[-1][1] = prefix+branch_end   # 修改最后项的前缀
        
        return pathlist[::-1]   # 返回反序列表（pop()会逆序处理）
    
    # 添加结果到任务序列
    worklist = process_path(path,os.listdir(path))
    while worklist:
        item_path,prefix,depth = worklist.pop()
        name = os.path.basename(item_path)   # 输出行=前缀+文件名
        add = sub_insert_mid if prefix.endswith(branch_mid) else sub_insert_end    # 前缀处理，判断父级是否在中间分支
        if os.path.isdir(item_path):
            # treestr.append(prefix[:-len(branch_mid)]+sub_insert_mid) # 目录前空一行
            if max_depth and depth+1>=max_depth:continue    # 深度过滤
            worklist.extend(process_path(item_path,os.listdir(item_path),prefix[:-len(branch_mid)]+add,depth+1))
            line = prefix + branch_sign + name + branch_sign_end # 文件夹标记
        else:
            line = prefix + leaf_sign + name + leaf_sign_end    # 文件标记
        treestr.append(line)
        if add==sub_insert_end: treestr.append(prefix[:-len(branch_mid)]+sub_insert_end) # 分支结束后空一行
    
    return "\n".join(treestr)   # 合并结果行

def file_tree(
    path: str = '.',
    exclude: list[str] = [],
    ignore: str = '',
    max_depth: Optional[int] = None,
    filter_func: Optional[Callable[[str], bool]] = None,
    branch_sign: str = '·[',
    branch_sign_end: str = ']',
    leaf_sign: str = ' ',
    leaf_sign_end: str = '',
    indent: int = 2,
    branch_indent: Optional[int] = None,
    sub_indent: Optional[int] = None
) -> str:
    """
    生成指定路径的文件目录树字符串
    
    参数:
        path: 起始目录路径
        exclude: 要排除的文件名列表
        ignore: 用于匹配要忽略的文件名的正则表达式
        max_depth: 最大递归深度，None表示无限制
        filter_func: 用于过滤文件的函数，返回True保留
        branch_sign: 目录节点的前缀符号
        branch_sign_end: 目录节点的后缀符号
        leaf_sign: 文件节点的前缀符号
        leaf_sign_end: 文件节点的后缀符号
        indent: 通用缩进量
        branch_indent: 分支缩进量，优先级高于indent
        sub_indent: 子缩进量，优先级高于indent
    
    返回:
        格式化的目录树字符串，若路径无效则返回错误信息
    """
    # 路径有效性检查
    if not path or not os.path.isdir(path): return "错误：无效的目录路径"
    
    # 初始化参数默认值
    exclude = exclude or [] # 排除项默认空列表
    filter_func = filter_func or (lambda x: True)   # 默认过滤函数，保留所有文件
    ignore_pattern = re.compile(ignore) if ignore else None # 正则表达式匹配忽略项
    
    # 处理缩进参数，特定缩进优先于通用缩进
    branch_indent_val = branch_indent if branch_indent is not None else indent 
    sub_indent_val = sub_indent if sub_indent is not None else indent
    
    # 定义目录树的分支符号
    branch_mid = f"├{'─' * branch_indent_val}"    # 中间分支符号
    branch_end = f"└{'─' * branch_indent_val}"    # 末尾分支符号
    sub_insert_mid = f"│{' ' * sub_indent_val}"   # 中间分支的子缩进
    sub_insert_end = f" {' ' * sub_indent_val}"   # 末尾分支的子缩进
    
    # 初始化结果列表，添加根目录
    tree_lines = [f"{branch_sign}{os.path.basename(path)}{branch_sign_end}"]
    
    def process_directory(current_path: str, parent_prefix: str, current_depth: int) -> list:
        """处理目录并返回需要进一步处理的子项列表"""
        try:
            items = os.listdir(current_path)
        except PermissionError:
            return []  # 无权限访问的目录直接跳过
        
        # 过滤不符合条件的项
        filtered_items = []
        for item in items:
            # 应用各种过滤条件
            if item in exclude: continue
            if not filter_func(item): continue
            if ignore_pattern and ignore_pattern.match(item): continue
            # 构建完整路径和前缀
            item_path = os.path.join(current_path, item)
            filtered_items.append([item_path, parent_prefix + branch_mid, current_depth])
        
        # 排序：目录在前，文件在后；按名称和扩展名排序
        filtered_items.sort(key=lambda x: (
            not os.path.isdir(x[0]),  # 目录在前 (False < True)
            os.path.splitext(x[0])[1] if os.path.isfile(x[0]) else '',  # 按扩展名
            os.path.basename(x[0])  # 按文件名
        ))
        
        # 将最后一项的分支符号改为末尾样式
        if filtered_items:
            filtered_items[-1][1] = parent_prefix + branch_end
            
        # 反转列表，以便后续使用pop()从前面取元素
        return filtered_items[::-1]
    
    # 初始化工作列表，处理根目录
    work_list = process_directory(path, '', 0)
    
    # 递归处理所有目录和文件
    while work_list:
        item_path, prefix, depth = work_list.pop()
        item_name = os.path.basename(item_path)
        
        # 确定子项的前缀插入符号
        is_mid_branch = prefix.endswith(branch_mid)
        sub_prefix = sub_insert_mid if is_mid_branch else sub_insert_end
        
        # 处理目录项
        if os.path.isdir(item_path):
            # 检查是否超过最大深度
            if max_depth is not None and depth + 1 >= max_depth:
                continue
                
            # 添加子目录到工作列表
            new_parent_prefix = prefix[:-len(branch_mid)] + sub_prefix if is_mid_branch else \
                               prefix[:-len(branch_end)] + sub_prefix
            work_list.extend(process_directory(item_path, new_parent_prefix, depth + 1))
            
            # 添加目录行到结果
            tree_lines.append(f"{prefix}{branch_sign}{item_name}{branch_sign_end}")
        
        # 处理文件项
        else:
            tree_lines.append(f"{prefix}{leaf_sign}{item_name}{leaf_sign_end}")
        
        # 在末尾分支后添加空行分隔
        if not is_mid_branch:
            tree_lines.append(f"{prefix[:-len(branch_end)]}{sub_insert_end}")
    
    return "\n".join(tree_lines)


if __name__ == "__main__":
    # 执行打包
    main_file = 'main.py'
    icon_path = 'icon.ico'
    print('开始打包')
    packApplication(main_file, icon_path, 'RimModManager')
    print('生成目录结构')
    p = r'.'
    tree = filestree(p, exclude=['__pycache__','__init__.py','build','old','cache','node_modules','dist','data','backups','public','assets','temp','test','tools'],ignore=r'^\.')
    with open('files_tree.txt','w',encoding='utf-8') as n:
        n.write(tree)
    print('生成完毕')
    
    